"""Resumable, read-only exact training-pair meta-path frequency study.

Run with the existing Gandalf virtual environment; see README.txt.
Pair checkpoints are atomic and bind to a frozen manifest. No services are used.
"""
import argparse
from collections import Counter, defaultdict
import csv
from functools import lru_cache
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import pickle
import random
import sys
import time

import lmdb
import msgpack
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'data_split'))
from analyze_graph import DRUG_CATEGORIES

GRAPH = ROOT / 'artifacts/gandalf_no_drug_disease'
LABELS = ROOT / 'data_split/train.csv'
LIMITS = {2: {'seconds': 30, 'edges': 20_000_000, 'walks': 1_000_000, 'signatures': 500_000},
          3: {'seconds': 5, 'edges': 5_000_000, 'walks': 100_000, 'signatures': 100_000}}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def log(*args):
    print(time.strftime('%H:%M:%S'), *args, flush=True)


class Bound(Exception):
    pass


class Graph:
    def __init__(self):
        self.meta = pickle.load((GRAPH / 'metadata.pkl').open('rb'))
        self.predicates = {int(v): k for k, v in self.meta['predicate_to_idx'].items()}
        for name in ('fwd_offsets', 'fwd_targets', 'fwd_predicates', 'rev_offsets',
                     'rev_sources', 'rev_to_fwd', 'edge_quals_idx'):
            setattr(self, name, np.load(GRAPH / (name + '.npy'), mmap_mode='r'))
        log('Loading qualifier dictionary')
        pools = pickle.load((GRAPH / 'edge_property_pools.pkl').open('rb'))
        raw = [tuple(sorted((q['qualifier_type_id'], q['qualifier_value']) for q in qs))
               for qs in pools['quals_pool']]
        del pools
        self.qualifiers = sorted(set(raw))
        qmap = {q: i for i, q in enumerate(self.qualifiers)}
        self.qual_map = np.array([qmap[q] for q in raw], dtype=np.int32)
        del raw, qmap
        self.env = lmdb.open(str(GRAPH / 'node_store.lmdb'), readonly=True,
                             lock=False, max_dbs=3, readahead=False)
        self.ids = self.env.open_db(b'id_to_idx')
        self.names = self.env.open_db(b'idx_to_id')
        self.props = self.env.open_db(b'properties')
        self.tx = self.env.begin()
        log('Indexing complete stored category sets')
        self.node_class = np.empty(self.meta['num_nodes'], dtype=np.int32)
        cmap = {}
        for key, val in self.tx.cursor(self.props):
            c = msgpack.unpackb(val, raw=False).get('categories', [])
            c = tuple(sorted([c] if isinstance(c, str) else c))
            if c not in cmap:
                cmap[c] = len(cmap)
            self.node_class[int.from_bytes(key, 'big')] = cmap[c]
        self.classes = list(cmap)
        self.chemical = {i for i, c in enumerate(self.classes) if DRUG_CATEGORIES.intersection(c)}
        log('Loaded graph', len(self.node_class), 'nodes;', len(self.classes), 'category sets')

    def idx(self, curie):
        v = self.tx.get(curie.encode(), db=self.ids)
        return int.from_bytes(v, 'big') if v is not None else None

    @lru_cache(maxsize=100_000)
    def node(self, i):
        key = int(i).to_bytes(4, 'big')
        p = msgpack.unpackb(self.tx.get(key, db=self.props), raw=False)
        return {'id': self.tx.get(key, db=self.names).decode(), 'name': p.get('name'),
                'categories': list(self.classes[int(self.node_class[i])])}

    def arrays(self, i):
        lo, hi = map(int, self.fwd_offsets[i:i+2])
        rl, rh = map(int, self.rev_offsets[i:i+2])
        return ((self.fwd_targets[lo:hi], np.arange(lo, hi), 1),
                (self.rev_sources[rl:rh], self.rev_to_fwd[rl:rh], -1))

    def edge(self, e, direction):
        return direction, int(self.fwd_predicates[e]), int(self.qual_map[self.edge_quals_idx[e]])

    @lru_cache(maxsize=64)
    def adjacency(self, i):
        out = defaultdict(set)
        for ns, es, direction in self.arrays(i):
            for n, e in zip(ns, es):
                if int(n) != i:
                    out[int(n)].add(self.edge(e, direction))
        return dict(out)

    def degree(self, i):
        if i is None:
            return 0
        return int(self.fwd_offsets[i+1] - self.fwd_offsets[i]
                   + self.rev_offsets[i+1] - self.rev_offsets[i])

    def volume(self, nodes):
        ns = np.fromiter(nodes, dtype=np.int64)
        return int(np.sum(self.fwd_offsets[ns+1] - self.fwd_offsets[ns])
                   + np.sum(self.rev_offsets[ns+1] - self.rev_offsets[ns]))

    def dictionaries(self):
        return {'categories': self.classes, 'predicates': self.predicates,
                'qualifiers': self.qualifiers, 'chemical_classes': sorted(self.chemical)}


def inverse(edges):
    return {(-direction, pred, qual) for direction, pred, qual in edges}


def walks(g, d, z, hops, budget, limit):
    start = budget['start']
    def check():
        if time.monotonic() - start > limit['seconds']:
            raise Bound('time_limit')
        if budget['edges'] > limit['edges']:
            raise Bound('edge_limit')
    budget['edges'] = g.degree(d) + g.degree(z)
    check()
    a, b = g.adjacency(d), g.adjacency(z)
    assert z not in a, 'Direct benchmark edge unexpectedly present'
    check()
    if hops == 2:
        for mid in sorted(a.keys() & b.keys()):
            check()
            yield (d, mid, z), (a[mid], inverse(b[mid]))
        return
    reverse = g.volume(b) < g.volume(a)
    left, right = (b, a) if reverse else (a, b)
    right_nodes = np.fromiter(right, dtype=np.int64)
    # Dense membership avoids rebuilding np.isin's lookup for every adjacency.
    mask = np.zeros(len(g.node_class), dtype=bool)
    mask[right_nodes] = True
    for u in sorted(left):
        check()
        links = defaultdict(set)
        for ns, es, direction in g.arrays(u):
            budget['edges'] += len(ns)
            check()
            for j in np.flatnonzero(mask[ns] & (ns != u)):
                links[int(ns[j])].add(g.edge(int(es[j]), direction))
        for v, middle in links.items():
            check()
            if reverse:
                yield (d, v, u, z), (a[v], inverse(middle), inverse(b[u]))
            else:
                yield (d, u, v, z), (a[u], middle, inverse(b[v]))


def sigs(g, ns, edges, qualified):
    cats = tuple(int(g.node_class[n]) for n in ns)
    choices = edges if qualified else [{(d, p, -1) for d, p, q in ee} for ee in edges]
    for es in itertools.product(*choices):
        yield cats, es


def pair_file(run, hops, i):
    return run / f'{hops}hop/pairs/{i:05d}.msgpack.gz'


def read_pair(path):
    with gzip.open(path, 'rb') as f:
        return msgpack.unpackb(f.read(), raw=False)


def write_pair(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with gzip.open(tmp, 'wb', compresslevel=3) as f:
        f.write(msgpack.packb(value, use_bin_type=True))
    tmp.replace(path)


def enumerate_pair(g, row, hops):
    start = time.monotonic()
    limit = LIMITS[hops]
    budget = {'start': start, 'edges': 0}
    result = {'state': 'complete', 'tables': [[], []], 'node_sequences': 0,
              'no_chemical_node_sequences': 0}
    d, z = g.idx(row['drug_id']), g.idx(row['disease_id'])
    tables = [{}, {}]
    if d is None or z is None:
        result['state'] = 'missing_endpoint'
    else:
        try:
            for ns, edges in walks(g, d, z, hops, budget, limit):
                if result['node_sequences'] >= limit['walks']:
                    raise Bound('walk_limit')
                # Commit whole node sequences, so qualified projection and bare counts agree.
                pending = []
                for q in (False, True):
                    keys = []
                    for k in sigs(g, ns, edges, q):
                        keys.append(k)
                        if len(keys) > limit['signatures']:
                            raise Bound('signature_limit')
                    if len(tables[q]) + sum(k not in tables[q] for k in keys) > limit['signatures']:
                        raise Bound('signature_limit')
                    pending.append(keys)
                if time.monotonic() - start > limit['seconds']:
                    raise Bound('time_limit')
                for q, keys in enumerate(pending):
                    for k in keys:
                        if k not in tables[q]:
                            tables[q][k] = [0, ns]
                        tables[q][k][0] += 1
                result['node_sequences'] += 1
                result['no_chemical_node_sequences'] += int(not any(
                    int(g.node_class[n]) in g.chemical for n in ns[1:-1]))
            projected = {(c, tuple((d, p, -1) for d, p, q in es)) for c, es in tables[1]}
            assert projected == set(tables[0])
        except Bound as exc:
            result['state'] = str(exc)
        for q in (False, True):
            result['tables'][q] = [[c, es, count, ns] for (c, es), (count, ns) in tables[q].items()]
    result.update(seconds=round(time.monotonic()-start, 6), scanned_edges=budget['edges'])
    return result


def freeze(run, g):
    manifest = run / 'manifest.json'
    fingerprints = {'labels_sha256': sha(LABELS), 'graph_report_sha256': sha(GRAPH / 'filtering_report.json'),
                    'script_sha256': sha(Path(__file__)), 'limits': {str(k): v for k, v in LIMITS.items()}}
    if manifest.exists():
        old = json.loads(manifest.read_text())
        assert old['fingerprints'] == fingerprints, 'Run inputs/code/limits changed; use a new run'
        return old
    rows = list(csv.DictReader(LABELS.open()))
    assert len({(r['drug_id'], r['disease_id']) for r in rows}) == len(rows)
    endpoints = [(g.idx(r['drug_id']), g.idx(r['disease_id'])) for r in rows]
    present = [i for i, (d, z) in enumerate(endpoints) if d is not None and z is not None]
    degree_order = sorted(present, key=lambda i: (g.degree(endpoints[i][0]) * g.degree(endpoints[i][1]), i))
    rng = random.Random(42)
    strata = [list(map(int, s)) for s in np.array_split(degree_order, 4)]
    pilot = [i for s in strata for i in sorted(rng.sample(s, min(8, len(s))))]
    data = {'fingerprints': fingerprints, 'graph': str(GRAPH), 'training_csv': str(LABELS),
            'training_pairs': len(rows), 'present_pairs': len(present), 'missing_pairs': len(rows)-len(present),
            'pairs': rows, 'present_indices': present, 'pilot_indices': pilot,
            'pilot_strata': [{'stratum': j, 'indices': [i for i in pilot if i in set(s)],
                              'population': len(s)} for j, s in enumerate(strata)],
            'pilot_method': 'Seed 42; eight pairs from each quartile of endpoint degree product. Pilot is a cost probe, not an unbiased performance estimate.',
            'semantics': 'Exact predicates and full category sets; both directions; no self-loops; repeated nodes otherwise allowed; source records collapsed; full qualifiers or qualifiers omitted.',
            'partial_policy': 'Incomplete pairs are retained as lower bounds and never interpreted as absent paths. Reports separate complete-pair support from observed support.',
            'chemical_categories': sorted(DRUG_CATEGORIES)}
    save(run / 'dictionaries.json', g.dictionaries())
    save(manifest, data)
    return data


def enumerate_run(run, hops, selection):
    g = Graph()
    manifest = freeze(run, g)
    indices = manifest['pilot_indices'] if selection == 'pilot' else list(range(manifest['training_pairs']))
    states = Counter()
    start = time.monotonic()
    for n, i in enumerate(indices, 1):
        path = pair_file(run, hops, i)
        if path.exists():
            r = read_pair(path)
        else:
            r = enumerate_pair(g, manifest['pairs'][i], hops)
            r['pair_index'] = i
            write_pair(path, r)
        states[r['state']] += 1
        save(run / f'{hops}hop/progress.json', {'selection': selection, 'processed': n,
             'scheduled': len(indices), 'states': states, 'elapsed_seconds': round(time.monotonic()-start, 3),
             'last_pair_index': i})
        if n % 50 == 0 or selection == 'pilot' or n == len(indices):
            log(hops, 'hop', n, '/', len(indices), dict(states), 'elapsed', round(time.monotonic()-start, 1))
    if selection == 'pilot':
        save(run / '3hop/pilot.json', {'indices': indices, 'records': [
            {k: v for k, v in read_pair(pair_file(run, hops, i)).items() if k != 'tables'} for i in indices]})


def decode(k, dictionaries):
    cats, edges = k
    return {'categories': [dictionaries['categories'][c] for c in cats],
            'edges': [{'direction': '>' if d == 1 else '<', 'predicate': dictionaries['predicates'][str(p)],
                       **({'qualifiers': dict(dictionaries['qualifiers'][q])} if q >= 0 else {})}
                      for d, p, q in edges]}


def bits(mask):
    while mask:
        bit = mask & -mask
        yield bit.bit_length() - 1
        mask ^= bit


def summarize(run, hops):
    manifest = json.loads((run / 'manifest.json').read_text())
    dictionaries = json.loads((run / 'dictionaries.json').read_text())
    rows = manifest['pairs']
    chemical = set(dictionaries['chemical_classes'])
    tables = [{}, {}]
    states = Counter()
    pair_states = []
    complete_mask = 0
    for i in range(len(rows)):
        path = pair_file(run, hops, i)
        if not path.exists():
            states['not_processed'] += 1
            pair_states.append({'pair_index': i, 'state': 'not_processed'})
            continue
        rec = read_pair(path)
        states[rec['state']] += 1
        pair_states.append({k: v for k, v in rec.items() if k != 'tables'})
        if rec['state'] == 'complete':
            complete_mask |= 1 << i
        for q in (False, True):
            for c, es, count, ns in rec['tables'][q]:
                k = tuple(c), tuple(tuple(e) for e in es)
                if k not in tables[q]:
                    tables[q][k] = [0, 0, ns, i]
                tables[q][k][0] |= 1 << i
                tables[q][k][1] += count
        if i % 500 == 0:
            log('Aggregate', hops, i, 'signatures', len(tables[0]), len(tables[1]))
    output = run / f'{hops}hop'
    save(output / 'pair_status.json', pair_states)
    view_summary = []
    for q in (False, True):
        for view in ('chemical_allowed', 'chemical_excluded'):
            ordered = sorted((k for k in tables[q] if view == 'chemical_allowed' or
                              not chemical.intersection(k[0][1:-1])),
                             key=lambda k: (-tables[q][k][0].bit_count(), -tables[q][k][1], k))
            stem = f'{"qualified" if q else "unqualified"}-{view}'
            top = []
            covered = 0
            with gzip.open(output / (stem + '.tsv.gz'), 'wt') as stream:
                writer = csv.writer(stream, delimiter='\t')
                writer.writerow(['rank', 'pair_support_observed', 'pair_support_complete_pairs',
                                 'coverage_all_training_lower_bound', 'coverage_present_lower_bound',
                                 'distinct_drugs', 'distinct_diseases', 'node_sequences_observed',
                                 'signature_id', 'unqualified_parent_id', 'signature_json'])
                for rank, k in enumerate(ordered, 1):
                    mask, count, witness, witness_pair = tables[q][k]
                    covered |= mask
                    ps = list(bits(mask))
                    drugs = len({rows[i]['drug_id'] for i in ps})
                    diseases = len({rows[i]['disease_id'] for i in ps})
                    sid = hashlib.sha256(msgpack.packb(k)).hexdigest()[:24]
                    parent = (k[0], tuple((d, p, -1) for d, p, qual in k[1]))
                    pid = hashlib.sha256(msgpack.packb(parent)).hexdigest()[:24]
                    decoded = decode(k, dictionaries)
                    vals = [rank, len(ps), (mask & complete_mask).bit_count(), len(ps)/len(rows),
                            len(ps)/manifest['present_pairs'], drugs, diseases, count, sid, pid]
                    writer.writerow(vals + [json.dumps(decoded, separators=(',', ':'))])
                    if rank <= 20:
                        top.append(dict(zip(['rank', 'pair_support_observed', 'pair_support_complete_pairs',
                                    'coverage_all_training_lower_bound', 'coverage_present_lower_bound',
                                    'distinct_drugs', 'distinct_diseases', 'node_sequences_observed',
                                    'signature_id', 'unqualified_parent_id'], vals), **decoded,
                                    encoded_signature=k, supporting_pair_indices=ps,
                                    witness_indices=witness, witness_pair_index=witness_pair))
            save(output / (stem + '-top20.json'), top)
            view_summary.append({'qualified': q, 'view': view, 'signatures_observed': len(ordered),
                                 'pairs_connected_observed': covered.bit_count(),
                                 'pairs_connected_complete': (covered & complete_mask).bit_count(),
                                 'coverage_all_training_lower_bound': covered.bit_count()/len(rows),
                                 'coverage_present_lower_bound': covered.bit_count()/manifest['present_pairs']})
    save(output / 'summary.json', {'hops': hops, 'states': states, 'training_pairs': len(rows),
         'present_pairs': manifest['present_pairs'], 'views': view_summary,
         'ranking': 'Observed distinct pair support descending, then observed node sequences, then exact signature. Rankings can change when partial pairs are completed.',
         'all_present_pairs_complete': states['complete'] == manifest['present_pairs']})
    log('SUMMARY', hops, dict(states), view_summary)


def audit(run, hops):
    """Re-enumerate only pairs supporting selected patterns, without Cartesian expansion.

    For each signature and position, collect each pair's distinct matching nodes.
    A hub is indispensable at that position only when it is the sole matching node.
    """
    g = Graph()
    manifest = freeze(run, g)
    files = sorted((run / f'{hops}hop').glob('*-top20.json'))
    selected = {}
    for path in files:
        for r in json.loads(path.read_text()):
            c, es = r['encoded_signature']
            k = tuple(c), tuple(tuple(e) for e in es)
            selected[k] = r
    needed = defaultdict(list)
    for k, r in selected.items():
        for i in r['supporting_pair_indices']:
            needed[i].append(k)
    hubs = {k: [defaultdict(set) for _ in range(hops-1)] for k in selected}
    indispensable = {k: [Counter() for _ in range(hops-1)] for k in selected}
    audited = {k: set() for k in selected}
    audit_states = Counter()
    # Audit time includes only traversal/matching; no full signature products.
    limit = {'seconds': 20, 'edges': 20_000_000, 'walks': 1_000_000, 'signatures': 500_000}
    for n, (i, ks) in enumerate(sorted(needed.items()), 1):
        row = manifest['pairs'][i]
        grouped = defaultdict(list)
        for k in ks:
            grouped[k[0]].append(k)
        seen = {k: [set() for _ in range(hops-1)] for k in ks}
        budget = {'start': time.monotonic(), 'edges': 0}
        state = 'complete'
        try:
            for ns, edges in walks(g, g.idx(row['drug_id']), g.idx(row['disease_id']), hops, budget, limit):
                c = tuple(int(g.node_class[v]) for v in ns)
                if c not in grouped:
                    continue
                bare = [{(d, p, -1) for d, p, q in ee} for ee in edges]
                for k in grouped[c]:
                    choices = bare if k[1][0][2] == -1 else edges
                    if all(e in available for e, available in zip(k[1], choices)):
                        for pos, v in enumerate(ns[1:-1]):
                            seen[k][pos].add(v)
        except Bound as exc:
            state = str(exc)
        audit_states[state] += 1
        if state == 'complete':
            for k in ks:
                assert all(seen[k]), 'Stored support could not be reproduced'
                audited[k].add(i)
                for pos, nodes in enumerate(seen[k]):
                    for v in nodes:
                        hubs[k][pos][v].add(i)
                    if len(nodes) == 1:
                        indispensable[k][pos][next(iter(nodes))] += 1
        if n % 100 == 0 or n == len(needed):
            log('Hub audit', hops, n, '/', len(needed), dict(audit_states))
    for path in files:
        rows = json.loads(path.read_text())
        for r in rows:
            c, es = r['encoded_signature']
            k = tuple(c), tuple(tuple(e) for e in es)
            r['example_path'] = [g.node(v) for v in r['witness_indices']]
            r['hub_audit_complete_pairs'] = len(audited[k])
            r['hub_audit_total_observed_support'] = r['pair_support_observed']
            r['hubs_by_position'] = []
            for pos, nodes in enumerate(hubs[k], 1):
                if not nodes:
                    continue
                v = min(nodes, key=lambda v: (-len(nodes[v]), g.node(v)['id']))
                r['hubs_by_position'].append({'position': pos, 'node': g.node(v),
                    'pairs_using_hub': len(nodes[v]),
                    'fraction_of_audited_support': len(nodes[v])/len(audited[k]),
                    'pairs_lost_if_hub_excluded_at_position': indispensable[k][pos-1][v],
                    'pairs_remaining_if_hub_excluded_at_position': len(audited[k])-indispensable[k][pos-1][v],
                    'distinct_nodes_at_position': len(nodes)})
        save(path, rows)
    save(run / f'{hops}hop/hub_audit.json', {'pair_states': audit_states,
         'selected_signatures': len(selected), 'scope': 'Complete audit pairs only. Exclusion is at the indicated position, not globally at all positions.'})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('task', choices=['enumerate', 'summarize', 'audit'])
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--hops', type=int, choices=[2, 3], required=True)
    ap.add_argument('--selection', choices=['all', 'pilot'], default='all')
    args = ap.parse_args()
    try:
        os.nice(10)
    except OSError:
        pass
    if args.task == 'enumerate':
        enumerate_run(args.run, args.hops, args.selection)
    elif args.task == 'summarize':
        summarize(args.run, args.hops)
    else:
        audit(args.run, args.hops)


if __name__ == '__main__':
    main()
