"""Recover every chemical-to-Disease treats pair after globally masking that scope."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import multiprocessing as mp
from pathlib import Path
import random
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'pilot/retrieval'))
from run import bounded_rule, queries_for_disease, GraphSampler, CSRGraph, make_toolkit
from compare_walk_lengths import sample
sys.path.insert(0, str(ROOT / 'pilot/chemical_retrieval'))
from masking import mask_graph
from metrics import measure, select_matches
from full_graph_common import digest, save

CHEMICAL = {'biolink:Drug', 'biolink:ChemicalEntity', 'biolink:SmallMolecule'}
METHODS = ('gandalf_walks', 'aragorn_rules')
CONTEXT = {}


def read(path):
    return json.loads(path.read_text())


def categories(graph):
    chemical = np.zeros(graph.num_nodes, dtype=bool)
    disease = chemical.copy()
    rows = (graph.node_store.iter_properties() if graph.node_store is not None else
            ((i, {'categories': graph.get_node_property(i, 'categories', [])}) for i in range(graph.num_nodes)))
    for i, props in rows:
        cats = set(props.get('categories', []))
        chemical[i] = bool(cats & CHEMICAL)
        disease[i] = 'biolink:Disease' in cats
    return chemical, disease


def target_inventory(graph, chemical, disease):
    """Labels are directed chemical -> Disease; mask also covers reverse-only records."""
    target = graph.predicate_to_idx['biolink:treats']
    positions = np.flatnonzero(graph.fwd_predicates == target)
    h = np.searchsorted(graph.fwd_offsets, positions, side='right') - 1
    t = graph.fwd_targets[positions]
    forward = chemical[h] & disease[t]
    reverse = disease[h] & chemical[t]
    pairs = {(int(a), int(b)) for a, b in zip(h[forward], t[forward])}
    mask_pairs = {(int(a), int(b)) for a, b in zip(h[forward | reverse], t[forward | reverse])}
    return pairs, mask_pairs, int(np.sum(forward | reverse))


def verify_mask(source, masked, chemical, disease, removed_records):
    """Independently check every retained evidence position, including its properties."""
    target = source.predicate_to_idx['biolink:treats']
    cursor = 0
    for start in range(0, len(source.fwd_targets), 1_000_000):
        end = min(start + 1_000_000, len(source.fwd_targets))
        pos = np.arange(start, end)
        h = np.searchsorted(source.fwd_offsets, pos, side='right') - 1
        t = source.fwd_targets[start:end]
        remove = (source.fwd_predicates[start:end] == target) & (
            (chemical[h] & disease[t]) | (disease[h] & chemical[t]))
        expected = pos[~remove]
        actual = masked.original_indices[cursor:cursor + len(expected)]
        assert np.array_equal(actual, expected), 'Mask differs from category/predicate definition'
        assert np.array_equal(masked.fwd_targets[cursor:cursor + len(expected)], source.fwd_targets[expected])
        assert np.array_equal(masked.fwd_predicates[cursor:cursor + len(expected)], source.fwd_predicates[expected])
        for name in ('_sources_idx', '_quals_idx', '_kl_at_idx'):
            assert np.array_equal(getattr(masked.edge_properties, name)[cursor:cursor + len(expected)],
                                  getattr(source.edge_properties, name)[expected])
        cursor += len(expected)
    assert cursor == len(masked.fwd_targets) == len(source.fwd_targets) - removed_records
    remaining, reverse, count = target_inventory(masked, chemical, disease)
    assert not remaining and not reverse and count == 0
    return {'source_evidence_records': len(source.fwd_targets),
            'removed_evidence_records': removed_records, 'remaining_evidence_records': cursor,
            'remaining_scoped_treats_records': 0,
            'remaining_treats_records_other_categories': int(np.sum(masked.fwd_predicates == target)),
            'exact_category_mask_verified': True, 'evidence_properties_preserved': True,
            'forward_reverse_indices_verified': True}


def check_edges(edges, graph, chemical, disease, cap):
    assert len(edges) <= cap
    target = graph.predicate_to_idx['biolink:treats']
    for h, p, t in edges:
        assert graph._find_edge_index(h, t, p) is not None
        assert not (p == target and ((chemical[h] and disease[t]) or (disease[h] and chemical[t])))


def retrieve(task):
    number, disease_id, anchor = task
    c = CONTEXT
    args, graph = c['args'], c['graph']
    seed = args.seed + number
    sampler = c['sampler']
    walk_edges, completed, walk_seconds = sample(sampler, anchor, 3, 1000, args.edge_cap, seed)
    queries = queries_for_disease(disease_id, c['rules'])
    queries[0]['query']['query_graph']['nodes']['drug']['categories'] = sorted(CHEMICAL)
    groups, diagnostics = [], []
    tick = time.perf_counter()
    for i, item in enumerate(queries):
        result = bounded_rule(graph, item['query'], c['bmt'], args.rule_timeout, args.edge_cap, seed*100+i)
        groups.append(result.pop('units'))
        diagnostics.append({'rule_id': item['rule_id'], **result})
    rule_edges, bound, retained = select_matches(groups, args.edge_cap, seed)
    rule_seconds = time.perf_counter() - tick
    directory = c['out'] / 'diseases' / f'{number:05d}'
    directory.mkdir(parents=True, exist_ok=True)
    for detail, units in zip(diagnostics, retained):
        detail['retained_matches'] = len(units)
    artifact = {'disease': disease_id, 'anchor': anchor,
                'gandalf_walks': {'edges': sorted(walk_edges)},
                'aragorn_rules': {'edges': sorted(rule_edges), 'bound': sorted(bound),
                                 'retained_matches_by_rule': {q['rule_id']: u for q, u in zip(queries, retained)}}}
    results = {}
    # Labels are consulted only after both retrieval strategies and cap selection finish.
    for method, edges, bindings, seconds in [('gandalf_walks', walk_edges, set(), walk_seconds),
                                            ('aragorn_rules', rule_edges, bound, rule_seconds)]:
        check_edges(edges, graph, c['chemical'], c['disease'], args.edge_cap)
        results[method] = dict(measure(edges, anchor, c['candidates'], c['answers'][anchor], bindings),
                               seconds=seconds)
    save(directory / 'graph.json', artifact)
    save(directory / 'rules.json', diagnostics)
    save(directory / 'report.json', {'disease': disease_id, 'anchor': anchor, 'results': results,
         'completed_walks': completed,
         'artifact_sha256': {name: digest(directory / name) for name in ('graph.json', 'rules.json')}})
    return number


def summarize(out, cohort, answers, candidates, settings, graph, chemical, disease):
    rows, pairs, rule_rows = [], [], []
    statuses, bounded = Counter(), 0
    completed_walks = completed = 0
    for number, disease_id, anchor in cohort:
        directory = out / 'diseases' / f'{number:05d}'
        if not (directory / 'report.json').exists():
            continue
        report = read(directory / 'report.json')
        assert (report['disease'], report['anchor']) == (disease_id, anchor)
        for name, expected in report['artifact_sha256'].items():
            assert digest(directory / name) == expected
        artifact = read(directory / 'graph.json')
        assert (artifact['disease'], artifact['anchor']) == (disease_id, anchor)
        reached = {}
        for method in METHODS:
            data = artifact[method]
            edges = {tuple(e) for e in data['edges']}
            assert len(edges) == len(data['edges'])
            check_edges(edges, graph, chemical, disease, settings['edge_cap'])
            bound = set(data.get('bound', []))
            if method == 'aragorn_rules':
                units = [u for group in data['retained_matches_by_rule'].values() for u in group]
                assert edges == {tuple(e) for u in units for e in u['edges']}
                assert bound == {a for u in units for a in u['answers']}
            value = measure(edges, anchor, candidates, answers[anchor], bound)
            assert value == {k: v for k, v in report['results'][method].items() if k != 'seconds'}
            reached[method] = set(value['recovered_answer_indices'])
            rows.append({'disease': disease_id, 'method': method,
                         **{k: v for k, v in value.items() if not k.endswith('_indices')},
                         'seconds': report['results'][method]['seconds']})
        for answer in sorted(answers[anchor]):
            w, r = answer in reached[METHODS[0]], answer in reached[METHODS[1]]
            pairs.append({'disease': disease_id, 'chemical': graph.get_node_id(answer),
                          'gandalf_recovered': w, 'aragorn_recovered': r,
                          'group': 'both' if w and r else 'gandalf_only' if w else 'aragorn_only' if r else 'neither'})
        for detail in read(directory / 'rules.json'):
            statuses[detail['status']] += 1
            bounded += bool(detail.get('bounded_results'))
            units = artifact['aragorn_rules']['retained_matches_by_rule'][detail['rule_id']]
            recovered = answers[anchor] & {a for u in units for a in u['answers']}
            rule_rows.append({'disease': disease_id, 'rule_id': detail['rule_id'],
                              'status': detail['status'], 'retained_matches': len(units),
                              'expected_pairs_bound': len(recovered)})
        completed_walks += report['completed_walks']
        completed += 1
    total = sum(map(len, answers.values()))
    summary = {'complete': completed == len(cohort), 'completed_diseases': completed,
               'total_diseases': len(cohort), 'expected_pairs': total,
               'evaluated_pairs': len(pairs), 'completed_walks': completed_walks,
               'attempted_walks': completed*1000, 'results': {},
               'paired_recovery': dict(Counter(p['group'] for p in pairs)),
               'rule_status_counts': dict(statuses), 'bounded_rule_queries': bounded,
               'settings_sha256': digest(out / 'settings.json'),
               'mask': read(out / 'mask_verification.json'),
               'saved_graphs_and_recovery_verified': True}
    for method in METHODS:
        rs = [r for r in rows if r['method'] == method]
        denominator = sum(r['answer_pairs'] for r in rs)
        count = sum(r['answers_reached'] for r in rs)
        summary['results'][method] = {'answer_pairs': denominator, 'answers_reached': count,
            'answer_coverage': count / denominator if denominator else None,
            'answers_bound': sum(r['answers_bound'] for r in rs) if method == 'aragorn_rules' else None,
            'mean_edges': float(np.mean([r['edges'] for r in rs])) if rs else None,
            'empty_graphs': sum(r['edges'] == 0 for r in rs),
            'retrieval_seconds': sum(r['seconds'] for r in rs)}
    for name, values in [('per_disease.csv', rows), ('pair_recovery.csv', pairs), ('per_rule.csv', rule_rows)]:
        if values:
            with (out / name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0]))
                writer.writeheader()
                writer.writerows(values)
    summary['outputs_sha256'] = {name: digest(out / name) for name in
                                ('per_disease.csv', 'pair_recovery.csv', 'per_rule.csv') if (out / name).exists()}
    if summary['complete']:
        assert len(pairs) == total
    save(out / ('summary.json' if summary['complete'] else 'partial.json'), summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'pilot/results/global_treats_recovery_001')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--seed', type=int, default=7317)
    parser.add_argument('--edge-cap', type=int, default=3000)
    parser.add_argument('--rule-timeout', type=float, default=5)
    args = parser.parse_args()
    if min(args.workers, args.edge_cap, args.rule_timeout) <= 0:
        parser.error('Budgets must be positive')
    out = args.output.resolve()
    if out.exists() and not (args.resume or args.verify_only):
        parser.error('Output exists; use --resume or a new output directory')
    if (args.resume or args.verify_only) and not (out / 'settings.json').exists():
        parser.error('Missing settings')
    store = ROOT / 'output/gandalf/full-store'
    rule_file = ROOT / 'pilot/results/retrieval_validation_001/aragorn_rules.json'
    rules = read(rule_file)['{"predicate": "biolink:treats"}']
    assert len(rules) == 18
    print('Loading source graph and discovering all eligible treats pairs...', flush=True)
    source = CSRGraph.load_mmap(store, mmap_mode='r')
    chemical, disease = categories(source)
    targets, hidden, removed = target_inventory(source, chemical, disease)
    assert targets, 'No eligible source treatment pairs'
    candidates = set(map(int, np.flatnonzero(chemical)))
    answers = defaultdict(set)
    for h, t in targets:
        answers[t].add(h)
    ids = sorted((source.get_node_id(t), t) for t in answers)
    cohort = [(i, name, t) for i, (name, t) in enumerate(ids)]
    sources = [Path(__file__), ROOT / 'pilot/chemical_retrieval/masking.py',
               ROOT / 'pilot/chemical_retrieval/metrics.py', ROOT / 'pilot/retrieval/run.py',
               ROOT / 'pilot/retrieval/masked_graph.py', ROOT / 'pilot/retrieval/compare_walk_lengths.py',
               ROOT / 'scripts/full_graph_common.py']
    sources += sorted((ROOT / 'vendor/gandalf/gandalf').rglob('*.py'))
    sources += [ROOT / 'vendor/gandalf/scripts/benchmarks/generate_queries.py']
    # Hash the actual CSR/evidence/category files, not only graph metadata.
    graph_files = sorted(p for p in store.rglob('*') if p.is_file() and p.name != 'lock.mdb')
    settings = {'experiment': 'All chemical-to-Disease treats pairs; global scoped treats mask',
                'mask': 'Exact biolink:treats between Disease and Drug/ChemicalEntity/SmallMolecule in either direction',
                'labels': 'Every unique directed chemical -> treats -> Disease source pair; no split',
                'other_predicates_retained': True, 'chemical_categories': sorted(CHEMICAL),
                'disease_category': 'biolink:Disease', 'category_matching': 'Explicit stored category membership',
                'seed': args.seed, 'seed_per_disease': 'seed + position in sorted disease IDs',
                'attempts': 1000, 'walk_length': 3, 'edge_cap': args.edge_cap,
                'rule_timeout_seconds': args.rule_timeout, 'rules_count': 18, 'includes_direct_lookup': True,
                'subclass_expansion': False, 'candidate_count': len(candidates),
                'expected_pairs': len(targets), 'diseases': len(cohort),
                'rules_sha256': digest(rule_file),
                'graph_sha256': {str(p.relative_to(store)): digest(p) for p in graph_files},
                'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
                'scope': 'Graph-present pair recovery, one seed; no ranking or model training'}
    if out.exists():
        assert read(out / 'settings.json') == settings, 'Inputs or settings changed; use a fresh output'
    else:
        out.mkdir(parents=True)
        save(out / 'settings.json', settings)
        save(out / 'targets.json', [{'chemical': source.get_node_id(h), 'chemical_index': h,
             'disease': source.get_node_id(t), 'disease_index': t} for h, t in sorted(targets)])
        save(out / 'cohort.json', [{'number': i, 'disease': d, 'anchor': t} for i, d, t in cohort])
        shutil.copyfile(rule_file, out / 'aragorn_rules.json')
        for p in sources:
            dest = out / 'source' / p.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
    print(f'{len(targets):,} target pairs across {len(cohort):,} diseases; masking all scoped treats records...', flush=True)
    graph = mask_graph(source, hidden, 'treats_only')
    mask = verify_mask(source, graph, chemical, disease, removed)
    save(out / 'mask_verification.json', mask)
    print(json.dumps(mask), flush=True)
    summary = summarize(out, cohort, answers, candidates, settings, graph, chemical, disease)
    if args.verify_only or summary['complete']:
        print(json.dumps(summary), flush=True)
        return
    bmt = make_toolkit()
    save(out / 'biolink.json', {'version': str(bmt.get_model_version())})
    CONTEXT.update(args=args, out=out, graph=graph, chemical=chemical, disease=disease,
                   sampler=GraphSampler(graph, random.Random(args.seed)),
                   candidates=candidates, answers=answers, rules=rules, bmt=bmt)
    pending = [task for task in cohort if not (out / 'diseases' / f'{task[0]:05d}' / 'report.json').exists()]
    status = {'phase': 'retrieval', 'complete': False, 'completed_diseases': summary['completed_diseases'],
              'total_diseases': len(cohort), 'started_unix': time.time()}
    save(out / 'status.json', status)
    try:
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context('fork')) as pool:
            futures = [pool.submit(retrieve, task) for task in pending]
            for future in as_completed(futures):
                future.result()
                status['completed_diseases'] += 1
                if status['completed_diseases'] % 100 == 0 or status['completed_diseases'] == len(cohort):
                    save(out / 'status.json', status)
                    print(f"Completed {status['completed_diseases']}/{len(cohort)} diseases", flush=True)
        status['phase'] = 'verification'
        save(out / 'status.json', status)
        summary = summarize(out, cohort, answers, candidates, settings, graph, chemical, disease)
        assert summary['complete']
        save(ROOT / 'pilot/studies' / f'{out.name}_results.json', summary)
        status.update(phase='complete', complete=True, finished_unix=time.time())
        save(out / 'status.json', status)
        print(json.dumps(summary, indent=2), flush=True)
    except BaseException as error:
        status.update(phase='failed', error=repr(error))
        save(out / 'status.json', status)
        raise


if __name__ == '__main__':
    main()
