"""Isolated, qualifier-exact AMIE experiment. See README.txt for the protocol."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import signal
import sqlite3
import subprocess
import sys
import time

import lmdb
import msgpack
import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'data_split'))
from analyze_graph import DRUG_CATEGORIES, DISEASE_CATEGORIES

COMMIT = 'add2b6a7e36a68fc85c9d004a089b264e138ff62'
JAR_SHA = 'bfdb11577fc5404f29eb30b3e16b1002f3b8e38fb53717eccc790a22f63763ca'
TARGET = 'benchmark:treats'


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def read(path):
    return json.loads(Path(path).read_text())


def canonical_quals(quals):
    # Preserve every qualifier field, canonicalize order and repeated entries.
    return tuple(sorted({json.dumps(q, sort_keys=True, separators=(',', ':')) for q in quals}))


def relation_key(predicate, quals):
    return json.dumps([predicate, canonical_quals(quals)], separators=(',', ':'))


def load_splits(folder):
    splits, seen, hashes = {}, set(), {}
    for name in ('train', 'val', 'test'):
        path = folder / f'{name}.csv'
        with path.open(newline='') as f:
            rows = list(csv.DictReader(f))
        pairs = [(r['drug_id'], r['disease_id']) for r in rows]
        for pair in pairs:
            if not all(pair) or pair in seen:
                raise ValueError(f'Missing or overlapping split pair: {pair}')
            seen.add(pair)
        splits[name] = pairs
        hashes[name] = digest(path)
    return splits, hashes


class Graph:
    def __init__(self, root):
        self.root = Path(root)
        with (self.root / 'metadata.pkl').open('rb') as f:
            self.meta = pickle.load(f)
        with (self.root / 'edge_property_pools.pkl').open('rb') as f:
            self.pools = pickle.load(f)
        for n in ('fwd_offsets', 'fwd_targets', 'fwd_predicates', 'edge_quals_idx',
                  'rev_offsets', 'rev_sources', 'rev_predicates', 'rev_to_fwd'):
            setattr(self, n, np.load(self.root / (n + '.npy'), mmap_mode='r'))
        self.pred = {v: k for k, v in self.meta['predicate_to_idx'].items()}
        self.env = lmdb.open(str(self.root / 'node_store.lmdb'), readonly=True,
                             lock=False, max_dbs=3, readahead=False)
        self.ids = self.env.open_db(b'id_to_idx', create=False)
        self.names = self.env.open_db(b'idx_to_id', create=False)
        self.props = self.env.open_db(b'properties', create=False)
        self.tx = self.env.begin()
        self.drugs = np.zeros(self.meta['num_nodes'], dtype=bool)
        self.diseases = np.zeros_like(self.drugs)
        for key, value in self.tx.cursor(self.props):
            cats = msgpack.unpackb(value, raw=False).get('categories', [])
            if isinstance(cats, str):
                cats = [cats]
            idx = int.from_bytes(key, 'big')
            self.drugs[idx] = bool(DRUG_CATEGORIES.intersection(cats))
            self.diseases[idx] = bool(DISEASE_CATEGORIES.intersection(cats))

    def idx(self, curie):
        value = self.tx.get(curie.encode(), db=self.ids)
        return None if value is None else int.from_bytes(value, 'big')

    def curie(self, idx):
        return self.tx.get(int(idx).to_bytes(4, 'big'), db=self.names).decode()

    def close(self):
        self.tx.abort()
        self.env.close()


def export(graph_path, splits_path, out):
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest = {'state': 'exporting', 'graph': str(graph_path.resolve()),
                'splits': str(splits_path.resolve()), 'code_sha256': digest(__file__),
                'semantics': 'exact predicate + complete qualifier set; no hierarchy expansion'}
    save(out / 'manifest.json', manifest)
    g = None
    db = None
    try:
        splits, hashes = load_splits(splits_path)
        g = Graph(graph_path)
        for name, pairs in splits.items():
            for drug, disease in pairs:
                d, t = g.idx(drug), g.idx(disease)
                if d is None or t is None or not g.drugs[d] or not g.diseases[t]:
                    raise ValueError(f'Invalid {name} endpoints: {(drug, disease)}')
        manifest.update(split_sha256=hashes, split_counts={k: len(v) for k, v in splits.items()})
        # Hash all graph files used by this experiment (streaming; no graph writes).
        manifest['graph_sha256'] = {str(p.relative_to(graph_path)): digest(p)
                                   for p in sorted(graph_path.rglob('*'))
                                   if p.is_file() and (p.suffix in ('.npy', '.pkl')
                                                      or p.name in ('filtering_report.json', 'data.mdb'))}
        db = sqlite3.connect(out / 'export.sqlite')
        db.execute('PRAGMA journal_mode=OFF')
        db.execute('PRAGMA synchronous=OFF')
        db.execute('PRAGMA cache_size=-65536')
        db.execute('CREATE TABLE triples(s INTEGER, r INTEGER, o INTEGER, PRIMARY KEY(s,r,o)) WITHOUT ROWID')
        qpool = g.pools['quals_pool']
        keys, relations, combo_ids = {}, {}, {}
        edge_count = len(g.fwd_targets)
        for lo in range(0, edge_count, 100_000):
            hi = min(lo + 100_000, edge_count)
            subjects = np.searchsorted(g.fwd_offsets, np.arange(lo, hi), side='right') - 1
            objects = g.fwd_targets[lo:hi]
            if np.any((g.drugs[subjects] & g.diseases[objects]) |
                      (g.diseases[subjects] & g.drugs[objects])):
                raise ValueError('Filtered graph still contains a chemical–disease edge')
            combos = g.fwd_predicates[lo:hi].astype(np.int64) * len(qpool) + g.edge_quals_idx[lo:hi]
            for combo in np.unique(combos):
                combo = int(combo)
                if combo in combo_ids:
                    continue
                pid, qid = divmod(combo, len(qpool))
                key = relation_key(g.pred[pid], qpool[qid])
                if key not in keys:
                    rid = len(keys)
                    keys[key] = rid
                    relations[f'r{rid}'] = {'predicate': g.pred[pid],
                                           'qualifiers': [json.loads(q) for q in canonical_quals(qpool[qid])]}
                combo_ids[combo] = keys[key]
            db.executemany('INSERT OR IGNORE INTO triples VALUES(?,?,?)',
                           ((int(s), combo_ids[int(c)], int(o)) for s, c, o in zip(subjects, combos, objects)))
            db.commit()
            if lo % 1_000_000 == 0:
                print(f'Exported {hi:,}/{edge_count:,} source records', flush=True)
        save(out / 'relations.json', relations)
        with (out / 'nodes.tsv').open('w') as f:
            for idx in range(g.meta['num_nodes']):
                f.write(f'n{idx}\t{g.curie(idx)}\n')
        with (out / 'evidence.tsv').open('w') as f:
            for s, r, o in db.execute('SELECT s,r,o FROM triples ORDER BY s,r,o'):
                f.write(f'n{s}\tr{r}\tn{o}\n')
        with (out / 'train.tsv').open('w') as f:
            for drug, disease in sorted(splits['train']):
                f.write(f'n{g.idx(drug)}\t{TARGET}\tn{g.idx(disease)}\n')
        manifest.update(state='complete', source_edges=edge_count,
                        evidence_triples=db.execute('SELECT COUNT(*) FROM triples').fetchone()[0],
                        relations=len(relations), seconds=time.monotonic() - started)
        manifest['export_sha256'] = {n: digest(out / n) for n in
                                      ('evidence.tsv', 'train.tsv', 'relations.json', 'nodes.tsv')}
        save(out / 'manifest.json', manifest)
    except BaseException as exc:
        manifest.update(state='failed', error=repr(exc), seconds=time.monotonic() - started)
        save(out / 'manifest.json', manifest)
        raise
    finally:
        if db is not None:
            db.close()
        if g is not None:
            g.close()


def path_rule(text):
    """Return canonical chemical->disease path steps, independent of variable spelling."""
    sides = text.split('=>')
    if len(sides) != 2:
        return None
    body, head = sides[0].split(), sides[1].split()
    if len(head) != 3 or head[1] != TARGET or head[0] == head[2] or len(body) not in (6, 9):
        return None
    atoms = [tuple(body[i:i+3]) for i in range(0, len(body), 3)]
    adj = defaultdict(list)
    for s, r, o in atoms:
        if r == TARGET or s == o or not s.startswith('?') or not o.startswith('?'):
            return None
        adj[s].append((o, r, 'out'))
        adj[o].append((s, r, 'in'))
    if len(adj) != len(atoms) + 1 or len(adj[head[0]]) != 1 or len(adj[head[2]]) != 1:
        return None
    if any(len(es) != (1 if v in (head[0], head[2]) else 2) for v, es in adj.items()):
        return None
    steps, seen, current = [], {head[0]}, head[0]
    while current != head[2]:
        choices = [x for x in adj[current] if x[0] not in seen]
        if len(choices) != 1:
            return None
        current, relation, direction = choices[0]
        seen.add(current)
        steps.append({'relation': relation, 'direction': direction})
    return steps if len(steps) == len(atoms) else None


def parse_rules(log, body_length, relations):
    header, rules, counts = None, {}, Counter()
    for line in Path(log).read_text(errors='replace').splitlines():
        if line.startswith('Rule\t'):
            header = line.strip().split('\t')
            continue
        if '=>' not in line:
            continue
        counts['raw_rule_lines'] += 1
        fields = line.strip().split('\t')
        if header is None or len(fields) != len(header):
            counts['malformed'] += 1
            continue
        row = dict(zip(header, fields))
        steps = path_rule(row['Rule'])
        if steps is None or len(steps) != body_length:
            counts['not_requested_path'] += 1
            continue
        if any(s['relation'] not in relations for s in steps):
            raise ValueError('AMIE emitted an unknown evidence relation')
        try:
            support = float(row['Positive Examples'])
            confidence = float(row['Std Confidence'])
            pca = float(row['PCA Confidence'])
            if not all(math.isfinite(v) for v in (support, confidence, pca)):
                raise ValueError('Non-finite metric')
        except (KeyError, ValueError):
            counts['invalid_metrics'] += 1
            continue
        if support < 10 or confidence < 0.001:
            counts['below_threshold'] += 1
            continue
        key = json.dumps(steps, sort_keys=True)
        readable = []
        for i, step in enumerate(steps):
            rel = relations[step['relation']]
            readable.append(dict(step, **rel, from_variable=f'x{i}', to_variable=f'x{i+1}'))
        rule = {'id': hashlib.sha256(key.encode()).hexdigest()[:16], 'body_length': body_length,
                'steps': steps, 'readable_steps': readable, 'amie_rule': row['Rule'],
                'support': support, 'standard_confidence': confidence, 'pca_confidence': pca,
                'treatment_evidence': any('treat' in x['predicate'] for x in readable)}
        if key in rules:
            counts['duplicates'] += 1
        if key not in rules or (confidence, support) > (rules[key]['standard_confidence'], rules[key]['support']):
            rules[key] = rule
    result = sorted(rules.values(), key=lambda r: (-r['standard_confidence'], -r['support'],
                                                  json.dumps(r['steps'], sort_keys=True)))
    counts['retained_paths'] = len(result)
    return result, dict(counts)


def bounded_process(command, stdout, stderr, seconds):
    start = time.monotonic()
    with open(stdout, 'w') as out, open(stderr, 'w') as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err, start_new_session=True)
        state = 'complete'
        try:
            code = proc.wait(timeout=seconds)
            if code != 0:
                state = 'failed'
        except subprocess.TimeoutExpired:
            state = 'timeout'
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                code = proc.wait()
        except BaseException:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            raise
    return {'state': state, 'exit_code': code, 'seconds': time.monotonic() - start}


def mining_command(jar, exported, length, heap):
    return ['java', f'-Xmx{heap}m', '-XX:ActiveProcessorCount=2', '-jar', str(jar),
            '-htr', TARGET, '-bexr', TARGET, '-maxad', str(length + 1),
            '-mins', '10', '-minis', '10', '-minc', '0.001', '-minpca', '0',
            '-pm', 'support', '-nc', '2', str(exported / 'evidence.tsv'), str(exported / 'train.tsv')]


def mine(exported, out, jar):
    out.mkdir(parents=True, exist_ok=False)
    (out / 'workflow.snapshot.py').write_bytes(Path(__file__).read_bytes())
    manifest = read(exported / 'manifest.json')
    if manifest['state'] != 'complete':
        raise ValueError('Export is incomplete')
    for name, expected in manifest['export_sha256'].items():
        if digest(exported / name) != expected:
            raise ValueError(f'Export hash mismatch: {name}')
    if digest(jar) != JAR_SHA:
        raise ValueError('AMIE executable checksum mismatch')
    help_result = subprocess.run(['java', '-jar', str(jar), '-h'], capture_output=True, text=True)
    help_text = help_result.stdout + help_result.stderr
    (out / 'amie-help.txt').write_text(help_text)
    required = ('-htr', '-bexr', '-maxad', '-mins', '-minis', '-minc', '-minpca', '-pm', '-nc')
    if not all(flag in help_text for flag in required):
        raise ValueError('Pinned AMIE does not advertise required flags')
    java = subprocess.run(['java', '-version'], capture_output=True, text=True)
    memory = psutil.virtual_memory()
    heap = min(16 * 1024, memory.total // (2 * 1024**2))
    status = {'state': 'preflight', 'amie_commit': COMMIT, 'jar_sha256': JAR_SHA,
              'binary_note': 'Bundled executable at pinned commit; not claimed to match current source build.',
              'java_version': java.stderr + java.stdout, 'heap_mib': heap,
              'available_bytes': memory.available, 'export': str(exported.resolve()),
              'export_manifest_sha256': digest(exported / 'manifest.json'), 'code_sha256': digest(__file__)}
    if memory.available < heap * 1024**2 + 1024**3:
        status.update(state='blocked_memory', reason='Require planned heap plus 1 GiB native/process headroom')
        save(out / 'manifest.json', status)
        print(json.dumps(status, indent=2), flush=True)
        return
    relations = read(exported / 'relations.json')
    status['runs'] = {}
    save(out / 'manifest.json', status)
    for length in (2, 3):
        run = out / f'body-{length}'
        run.mkdir()
        memory = psutil.virtual_memory()
        if memory.available < heap * 1024**2 + 1024**3:
            result = {'state': 'blocked_memory', 'available_bytes': memory.available}
            save(run / 'manifest.json', result)
            status['runs'][str(length)] = result
            continue
        command = mining_command(jar.resolve(), exported.resolve(), length, heap)
        save(run / 'manifest.json', {'state': 'running', 'command': command})
        print(f'Starting {length}-edge mining, limit 3600 seconds', flush=True)
        result = bounded_process(command, run / 'stdout.txt', run / 'stderr.txt', 3600)
        rules, counts = parse_rules(run / 'stdout.txt', length, relations)
        save(run / 'rules.json', rules)
        result.update(command=command, counts=counts, complete=result['state'] == 'complete')
        result['rules_sha256'] = digest(run / 'rules.json')
        save(run / 'manifest.json', result)
        status['runs'][str(length)] = result
        save(out / 'manifest.json', status)
    status['state'] = 'complete' if all(r['state'] == 'complete' for r in status['runs'].values()) else 'partial'
    save(out / 'manifest.json', status)


class QueryLimit(Exception):
    pass


def enumerate_path(rule, disease, neighbors, is_drug, seconds=10, max_edges=2_000_000,
                   max_candidates=100_000, deadline=None):
    """neighbors(node, step, tick) must charge examined records BEFORE traversal."""
    start = time.monotonic()
    end = min(start + seconds, deadline if deadline is not None else float('inf'))
    candidates, witnesses, work = set(), {}, 0

    def tick(count=0):
        nonlocal work
        if time.monotonic() >= end:
            raise QueryLimit('time_limit')
        if work + count > max_edges:
            raise QueryLimit('edge_limit')
        work += count

    def visit(node, depth, path):
        tick()
        if depth < 0:
            if is_drug(node):
                if node not in candidates and len(candidates) >= max_candidates:
                    raise QueryLimit('candidate_limit')
                candidates.add(node)
                if len(witnesses) < 5:
                    witnesses.setdefault(node, list(reversed(path)))
            return
        step = rule['steps'][depth]
        for target in neighbors(node, step, tick):
            if target not in path:
                visit(target, depth - 1, path + [target])
    state = 'complete'
    try:
        visit(disease, len(rule['steps']) - 1, [disease])
    except QueryLimit as exc:
        state = str(exc)
    return {'state': state, 'candidates': sorted(candidates), 'witnesses': witnesses,
            'edges_examined': work, 'seconds': time.monotonic() - start}


def validate(exported, mined, out, graph_override=None, splits_override=None):
    start = time.monotonic()
    deadline = start + 3600
    out.mkdir(parents=True, exist_ok=False)
    (out / 'workflow.snapshot.py').write_bytes(Path(__file__).read_bytes())
    em = read(exported / 'manifest.json')
    mm = read(mined / 'manifest.json')
    if mm.get('export_manifest_sha256') != digest(exported / 'manifest.json'):
        raise ValueError('Mining/export mismatch')
    if mm['state'] == 'blocked_memory':
        save(out / 'report.json', {'state': 'blocked', 'reason': 'Mining blocked by memory preflight'})
        return
    graph_path = Path(graph_override) if graph_override else Path(em['graph'])
    for name, expected in em['graph_sha256'].items():
        if digest(graph_path / name) != expected:
            raise ValueError(f'Graph changed: {name}')
    splits_path = Path(splits_override) if splits_override else Path(em['splits'])
    vp = splits_path / 'val.csv'
    if digest(vp) != em['split_sha256']['val']:
        raise ValueError('Validation split changed')
    with vp.open(newline='') as f:
        labels = list(csv.DictReader(f))
    truths = defaultdict(set)
    for row in labels:
        truths[row['disease_id']].add(row['drug_id'])
    relations = read(exported / 'relations.json')
    if digest(exported / 'relations.json') != em['export_sha256']['relations.json']:
        raise ValueError('Relation mapping changed')
    rules = []
    for length in (2, 3):
        path = mined / f'body-{length}' / 'rules.json'
        if path.exists():
            run_manifest = read(path.parent / 'manifest.json')
            if digest(path) != run_manifest['rules_sha256']:
                raise ValueError('Mined rules changed after mining')
            rules.extend(read(path)[:100])
    save(out / 'selected_rules.json', rules)
    g = Graph(graph_path)
    # Map all pool entries to canonical qualifier sets once, then integer membership checks.
    qkeys = [canonical_quals(q) for q in g.pools['quals_pool']]
    qids = defaultdict(set)
    for idx, key in enumerate(qkeys):
        qids[key].add(idx)
    compiled = {}
    for rule in rules:
        for step in rule['steps']:
            rid = step['relation']
            rel = relations[rid]
            compiled[rid] = (g.meta['predicate_to_idx'][rel['predicate']], qids[canonical_quals(rel['qualifiers'])])

    def neighbors(node, step, tick):
        # Traverse backward from disease: an out-directed forward step needs incoming edges.
        incoming = step['direction'] == 'out'
        offsets = g.rev_offsets if incoming else g.fwd_offsets
        targets = g.rev_sources if incoming else g.fwd_targets
        predicates = g.rev_predicates if incoming else g.fwd_predicates
        pid, qualifiers = compiled[step['relation']]
        lo, hi = map(int, offsets[node:node+2])
        seen = set()
        for pos in range(lo, hi):
            tick(1)
            if predicates[pos] != pid:
                continue
            fwd = int(g.rev_to_fwd[pos]) if incoming else pos
            if int(g.edge_quals_idx[fwd]) not in qualifiers:
                continue
            target = int(targets[pos])
            if target not in seen:
                seen.add(target)
                yield target

    unions = {str(n): defaultdict(set) for n in (2, 3)}
    per_rule, states, complete_queries = {}, Counter(), 0
    total_queries = len(rules) * len(truths)
    try:
        with (out / 'queries.jsonl').open('w') as stream:
            for rule in rules:
                recovered, candidate_total, done = 0, 0, 0
                for disease, true_drugs in sorted(truths.items()):
                    if time.monotonic() >= deadline:
                        break
                    idx = g.idx(disease)
                    result = enumerate_path(rule, idx, neighbors, lambda n: g.drugs[n], deadline=deadline)
                    candidates = {g.curie(n) for n in result.pop('candidates')}
                    result['witnesses'] = {g.curie(n): [g.curie(x) for x in path]
                                           for n, path in result['witnesses'].items()}
                    result.update(rule=rule['id'], disease=disease, candidate_count=len(candidates),
                                  recovered=sorted(candidates & true_drugs))
                    # Candidates retained for reproducibility; no held-out labels enter enumeration.
                    result['candidates'] = sorted(candidates)
                    stream.write(json.dumps(result) + '\n')
                    stream.flush()
                    unions[str(rule['body_length'])][disease].update(candidates)
                    recovered += len(candidates & true_drugs)
                    candidate_total += len(candidates)
                    done += 1
                    states[result['state']] += 1
                    complete_queries += result['state'] == 'complete'
                per_rule[rule['id']] = {'recovered_pairs': recovered, 'candidate_total': candidate_total,
                                        'queries_executed': done, 'recovery_lower_bound': recovered / len(labels)}
                if time.monotonic() >= deadline:
                    break
    finally:
        g.close()
    unions['combined'] = {d: unions['2'][d] | unions['3'][d] for d in truths}
    summaries = {}
    for name, by_disease in unions.items():
        counts = [len(by_disease.get(d, set())) for d in truths]
        summaries[name] = {
            'recovered_pairs': sum(len(by_disease.get(d, set()) & true) for d, true in truths.items()),
            'pair_recovery': sum(len(by_disease.get(d, set()) & true) for d, true in truths.items()) / len(labels),
            'disease_average_recovery': sum(len(by_disease.get(d, set()) & true) / len(true)
                                            for d, true in truths.items()) / len(truths),
            'candidate_mean': float(np.mean(counts)), 'candidate_median': float(np.median(counts)),
            'candidate_max': max(counts, default=0)}
    report = {'state': 'complete' if complete_queries == total_queries and mm['state'] == 'complete' else 'partial',
              'mining_state': mm['state'], 'validation_pairs': len(labels), 'validation_diseases': len(truths),
              'selected_rules': len(rules), 'expected_queries': total_queries,
              'query_states': dict(states), 'unstarted_queries': total_queries - sum(states.values()),
              'seconds': time.monotonic() - start, 'unions': summaries, 'per_rule': per_rule,
              'test_evaluated': False, 'code_sha256': digest(__file__),
              'mining_manifest_sha256': digest(mined / 'manifest.json'),
              'graph': str(graph_path.resolve()), 'splits': str(splits_path.resolve()),
              'interpretation': 'Incomplete query recovery is a lower bound; mining may be partial. No precision estimate.'}
    save(out / 'report.json', report)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    e = sub.add_parser('export')
    e.add_argument('--graph', type=Path, default=ROOT / 'artifacts/gandalf_no_drug_disease')
    e.add_argument('--splits', type=Path, default=ROOT / 'data_split/nonisolated')
    e.add_argument('--out', type=Path, required=True)
    m = sub.add_parser('mine')
    m.add_argument('--export', type=Path, required=True)
    m.add_argument('--jar', type=Path, default=HERE / 'vendor/amie.jar')
    m.add_argument('--out', type=Path, required=True)
    v = sub.add_parser('validate')
    v.add_argument('--export', type=Path, required=True)
    v.add_argument('--mined', type=Path, required=True)
    v.add_argument('--out', type=Path, required=True)
    v.add_argument('--graph', type=Path, help='Relocated graph; original content hashes still required')
    v.add_argument('--splits', type=Path, help='Relocated splits; original validation hash still required')
    args = ap.parse_args()
    os.nice(10)
    if args.command == 'export':
        export(args.graph, args.splits, args.out)
    elif args.command == 'mine':
        mine(args.export, args.out, args.jar)
    else:
        validate(args.export, args.mined, args.out, args.graph, args.splits)


if __name__ == '__main__':
    main()
