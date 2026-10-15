"""Compare ARAGORN retrieval under two masks on Experiment 11's frozen split."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import json
import logging
import multiprocessing as mp
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'pilot/retrieval'))
from full_graph_common import digest, hidden_pair_mask, save
from run import bounded_rule, queries_for_disease
from gandalf import CSRGraph
from gandalf.biolink import make_toolkit
from masking import mask_graph
from metrics import measure, select_matches

POLICIES = ('all_direct', 'treats_only')
SPLITS = ('validation', 'test')
CONTEXT = {}


def read(path):
    return json.loads(path.read_text())


def unique_connections(graph):
    n, p = graph.num_nodes, len(graph.predicate_to_idx)
    heads = np.repeat(np.arange(n, dtype=np.int64), np.diff(graph.fwd_offsets))
    return np.unique((heads*p + graph.fwd_predicates)*n + graph.fwd_targets)


def verify_mask(source, masked, hidden, policy, prepared, candidates, labels):
    n, p = source.num_nodes, len(source.predicate_to_idx)
    target = source.predicate_to_idx['biolink:treats']
    raw = unique_connections(source)
    h, r, t = raw//(n*p), (raw//n) % p, raw % n
    remove = hidden_pair_mask(h, t, hidden, n)
    if policy == 'treats_only':
        remove &= r == target
    actual = unique_connections(masked)
    assert np.array_equal(actual, raw[~remove]), 'CSR mask differs from independent triple mask'
    if policy == 'all_direct':
        frozen = np.load(prepared / 'data/triples.npy', mmap_mode='r')
        expected = (frozen[:, 0]*p + frozen[:, 1])*n + frozen[:, 2]
        assert np.array_equal(actual, expected), 'Strict graph differs from Experiment 11'
    for row in labels:
        if row['split'] == 'visible':
            assert masked._find_edge_index(row['drug_index'], row['disease_index'], target) is not None
    ah, at = actual//(n*p), actual % n
    active = np.zeros(n, dtype=bool)
    active[ah] = True
    active[at] = True
    active_candidates = int(active[list(candidates)].sum())
    report = {'policy': policy, 'nodes': n, 'active_nodes': int(active.sum()),
              'isolated_nodes': int((~active).sum()), 'unique_directed_connections': len(actual),
              'source_unique_directed_connections': len(raw), 'removed_unique_connections': int(remove.sum()),
              'removed_by_predicate': dict(Counter(source.id_to_predicate[int(x)] for x in r[remove])),
              'evidence_records': len(masked.fwd_targets),
              'removed_evidence_records': len(source.fwd_targets)-len(masked.fwd_targets),
              'candidate_nodes': len(candidates), 'active_candidates': active_candidates,
              'isolated_candidates': len(candidates)-active_candidates,
              'heldout_pairs': len(hidden), 'all_visible_treats_retained': True,
              'exact_mask_verified': True, 'reverse_index_verified': True,
              'matches_experiment11_triples': policy == 'all_direct'}
    return report


def retrieve(task):
    policy, number, disease = task
    ctx = CONTEXT
    graph = ctx['graphs'][policy]
    anchor = ctx['indices'][disease]
    seed = ctx['args'].seed + number
    queries = queries_for_disease(disease, ctx['rules'])
    # Only the direct lookup was Drug-only in Experiment 7; broaden it to the
    # exact subject-category union. Keep all 18 ARAGORN templates unchanged.
    queries[0]['query']['query_graph']['nodes']['drug']['categories'] = [
        'biolink:Drug', 'biolink:ChemicalEntity', 'biolink:SmallMolecule']
    start = time.perf_counter()
    groups, diagnostics = [], []
    for rule_number, item in enumerate(queries):
        result = bounded_rule(graph, item['query'], ctx['bmt'], ctx['args'].rule_timeout,
                              ctx['args'].edge_cap, seed*100+rule_number)
        units = result.pop('units')
        groups.append(units)
        diagnostics.append({'rule_id': item['rule_id'], 'requires_direct_pair': item['requires_direct_pair'],
                            'bounded_matches_before_union': len(units), **result})
    edges, bound, retained = select_matches(groups, ctx['args'].edge_cap, seed)
    for h, p, t in edges:
        assert graph._find_edge_index(h, t, p) is not None
        if (h, t) in ctx['hidden'] or (t, h) in ctx['hidden']:
            assert policy == 'treats_only' and p != ctx['target']
    directory = ctx['out'] / policy / 'diseases' / f'{number:04d}'
    directory.mkdir(parents=True, exist_ok=True)
    artifact = {'disease': disease, 'anchor': anchor, 'edges': sorted(edges),
                'rule_answer_nodes': sorted(bound),
                'retained_matches_by_rule': {q['rule_id']: units for q, units in zip(queries, retained)}}
    save(directory / 'graph.json', artifact)
    splits = {split: measure(edges, anchor, ctx['candidates'], ctx['answers'][split][disease], bound)
              for split in SPLITS if ctx['answers'][split][disease]}
    for detail, before, after in zip(diagnostics, groups, retained):
        detail['retained_matches'] = len(after)
        detail['coverage'] = {}
        for stage, units in [('before_union_cap', before), ('retained', after)]:
            es = {tuple(e) for unit in units for e in unit['edges']}
            bs = {a for unit in units for a in unit['answers']}
            detail['coverage'][stage] = {
                split: measure(es, anchor, ctx['candidates'], ctx['answers'][split][disease], bs)
                for split in splits}
    save(directory / 'rules.json', diagnostics)
    report = {'policy': policy, 'disease': disease, 'anchor': anchor, 'splits': splits,
              'retrieval_seconds': time.perf_counter()-start,
              'rule_status_counts': dict(Counter(d['status'] for d in diagnostics)),
              'bounded_rule_queries': sum(bool(d.get('bounded_results')) for d in diagnostics),
              'artifact_sha256': {name: digest(directory / name) for name in ('graph.json', 'rules.json')}}
    save(directory / 'report.json', report)
    return policy, number, disease


def summarize(out, selected, candidates, answers, settings):
    reports = {}
    rows, rule_rows = [], []
    for policy in POLICIES:
        for number, disease in enumerate(selected):
            directory = out / policy / 'diseases' / f'{number:04d}'
            if not (directory / 'report.json').exists():
                continue
            report = read(directory / 'report.json')
            assert report['disease'] == disease and report['policy'] == policy
            for name, expected in report['artifact_sha256'].items():
                assert digest(directory / name) == expected
            graph = read(directory / 'graph.json')
            edges = {tuple(e) for e in graph['edges']}
            assert len(edges) <= settings['edge_cap']
            retained = list(graph['retained_matches_by_rule'].values())
            assert edges == {tuple(e) for units in retained for unit in units for e in unit['edges']}
            bound = set(graph['rule_answer_nodes'])
            assert bound == {a for units in retained for unit in units for a in unit['answers']}
            assert bound <= {x for h, p, t in edges for x in (h, t)}
            for split, measured in report['splits'].items():
                assert measured == measure(edges, graph['anchor'], candidates, answers[split][disease], bound)
                rows.append({'policy': policy, 'split': split, 'disease': disease,
                             **{k: v for k, v in measured.items() if not k.endswith('_indices')},
                             'retrieval_seconds': report['retrieval_seconds']})
            rules = read(directory / 'rules.json')
            for rule in rules:
                units = graph['retained_matches_by_rule'][rule['rule_id']]
                es = {tuple(e) for unit in units for e in unit['edges']}
                bs = {a for unit in units for a in unit['answers']}
                for split, measured in rule['coverage']['retained'].items():
                    assert measured == measure(es, graph['anchor'], candidates, answers[split][disease], bs)
                    rule_rows.append({'policy': policy, 'split': split, 'disease': disease,
                                      'rule_id': rule['rule_id'], 'status': rule['status'],
                                      'retained_matches': len(units), 'answers_reached': measured['answers_reached'],
                                      'answers_bound': measured['answers_bound']})
            reports[policy, disease] = report
    summary = {'complete': len(reports) == len(selected)*2, 'diseases': len(selected),
               'completed_policy_queries': len(reports), 'settings_sha256': digest(out / 'settings.json'),
               'source_graphs': read(out / 'source_graphs.json'), 'results': {}, 'paired_changes': {},
               'coverage_recomputed_from_saved_graphs': True,
               'scope': 'Bounded retrieval coverage; no ULTRA scores or model selection. Test is exploratory.'}
    for policy in POLICIES:
        summary['results'][policy] = {}
        for split in SPLITS:
            subset = [r for r in rows if r['policy'] == policy and r['split'] == split]
            total = sum(r['answer_pairs'] for r in subset)
            expected = sum(len(answers[split][d]) for d in selected)
            summary['results'][policy][split] = {
                'diseases_evaluated': len(subset), 'answer_pairs_evaluated': total, 'answer_pairs_expected': expected,
                **{k: sum(r[k] for r in subset) for k in ('answers_reached', 'answers_bound')},
                'answer_coverage': sum(r['answers_reached'] for r in subset)/total if total else None,
                'bound_answer_coverage': sum(r['answers_bound'] for r in subset)/total if total else None,
                'empty_graphs': sum(r['edges'] == 0 for r in subset),
                'graphs_at_edge_cap': sum(r['edges'] == settings['edge_cap'] for r in subset),
                'graph_sizes': {k: {'mean': float(np.mean([r[k] for r in subset])),
                                     'median': float(np.median([r[k] for r in subset])),
                                     'min': min(r[k] for r in subset), 'max': max(r[k] for r in subset)}
                               for k in ('nodes', 'edges', 'candidate_nodes')} if subset else {},
                'rules': {rule_id: {k: sum(r[k] for r in rule_rows if r['policy'] == policy and
                                                   r['split'] == split and r['rule_id'] == rule_id)
                                   for k in ('retained_matches', 'answers_reached', 'answers_bound')}
                          for rule_id in ['direct'] + [str(i) for i in range(18)]}}
    for split in SPLITS:
        changes = {}
        for field in ('recovered_answer_indices', 'bound_answer_indices'):
            gained, lost, both = [], [], []
            for d in selected:
                if (POLICIES[0], d) not in reports or (POLICIES[1], d) not in reports:
                    continue
                a = set(reports[POLICIES[0], d]['splits'].get(split, {}).get(field, []))
                b = set(reports[POLICIES[1], d]['splits'].get(split, {}).get(field, []))
                gained.extend([[x, d] for x in sorted(b-a)])
                lost.extend([[x, d] for x in sorted(a-b)])
                both.extend([[x, d] for x in sorted(a & b)])
            changes[field] = {'gained': len(gained), 'lost': len(lost), 'both': len(both),
                              'net_gain': len(gained)-len(lost)}
            save(out / f'{split}_{field}_changes.json', {'gained': gained, 'lost': lost, 'both': both})
        summary['paired_changes'][split] = changes
    summary['rule_status_counts'] = {policy: dict(sum((Counter(r['rule_status_counts'])
        for (p, d), r in reports.items() if p == policy), Counter())) for policy in POLICIES}
    summary['bounded_rule_queries'] = {policy: sum(r['bounded_rule_queries'] for (p, d), r in reports.items()
                                                  if p == policy) for policy in POLICIES}
    summary['retrieval_seconds'] = {policy: sum(r['retrieval_seconds'] for (p, d), r in reports.items()
                                               if p == policy) for policy in POLICIES}
    for name, values in [('per_disease.csv', rows), ('per_rule.csv', rule_rows)]:
        if values:
            with (out / name).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(values[0]))
                writer.writeheader()
                writer.writerows(values)
    save(out / ('summary.json' if summary['complete'] else 'partial.json'), summary)
    if summary['complete']:
        save(ROOT / 'pilot/studies' / f'{out.name}_results.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--seed', type=int, default=7317)
    parser.add_argument('--edge-cap', type=int, default=3000)
    parser.add_argument('--rule-timeout', type=float, default=5)
    parser.add_argument('--max-new-diseases', type=int, help='Run both policies for this many pending diseases, then pause')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if min(args.workers, args.edge_cap, args.rule_timeout) <= 0 or (
            args.max_new_diseases is not None and args.max_new_diseases < 1):
        parser.error('Budgets must be positive')
    out = args.output.resolve()
    if out.exists() and not (args.resume or args.verify_only):
        parser.error('Output exists; use --resume')
    if (args.resume or args.verify_only) and not (out / 'settings.json').exists():
        parser.error('Missing settings')
    prepared = ROOT / 'pilot/results/chemical_disease_4g_001'
    prep = read(prepared / 'preparation.json')
    for name, expected in prep['dataset_sha256'].items():
        assert digest(prepared / 'data' / name) == expected
    labels = read(prepared / 'data/labels.json')
    candidate_rows = read(prepared / 'data/candidates.json')
    candidates = {r['index'] for r in candidate_rows}
    answers = {s: defaultdict(set) for s in SPLITS}
    indices = {}
    for row in labels:
        indices[row['disease']] = row['disease_index']
        if row['split'] in SPLITS:
            answers[row['split']][row['disease']].add(row['drug_index'])
    selected = sorted(set(answers['validation']) | set(answers['test']))
    rule_file = ROOT / 'pilot/results/retrieval_validation_001/aragorn_rules.json'
    rules = read(rule_file)['{"predicate": "biolink:treats"}']
    assert len(rules) == 18 and len(candidates) == 1117832
    gandalf = ROOT / 'vendor/gandalf'
    commit = subprocess.check_output(['git', '-C', str(gandalf), 'rev-parse', 'HEAD'], text=True).strip()
    assert commit == '3fbaded1c922de3d61ff2af17694264d13b221f5'
    subprocess.run(['git', '-C', str(gandalf), 'diff', '--quiet', 'HEAD', '--', 'gandalf'], check=True)
    sources = [Path(__file__), HERE / 'masking.py', HERE / 'metrics.py', ROOT / 'pilot/retrieval/run.py',
               ROOT / 'pilot/retrieval/masked_graph.py', ROOT / 'scripts/full_graph_common.py']
    settings = {'experiment': 'ARAGORN chemical/drug masking comparison', 'dataset': str(prepared),
                'policies': list(POLICIES), 'splits': list(SPLITS), 'seed': args.seed,
                'edge_cap': args.edge_cap, 'rule_timeout_seconds': args.rule_timeout,
                'workers': args.workers, 'rule_hard_timeout_grace_seconds': 2,
                'rule_extra_virtual_memory_gb': 4, 'rules_count': 18, 'includes_direct_lookup': True,
                'direct_lookup_categories': ['biolink:Drug', 'biolink:ChemicalEntity', 'biolink:SmallMolecule'],
                'subclass_expansion': False, 'dataset_sha256': prep['dataset_sha256'],
                'rules_sha256': digest(rule_file), 'gandalf_commit': commit,
                'source_graph_metadata_sha256': digest(ROOT / 'output/gandalf/full-store/metadata.pkl'),
                'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
                'cohort': selected, 'candidate_count': len(candidates),
                'pair_splits': dict(Counter(r['split'] for r in labels)),
                'mask_scope': 'Both validation and test pairs masked globally; treats_only removes exact biolink:treats in both directions',
                'rule_templates': 'All 18 original templates unchanged, including categories, directions, and qualifiers',
                'budget_selection': 'No answer labels provided to lookup or match selection',
                'coverage': 'Answer-pair recall in final graph and explicitly bound answers; no model scoring'}
    if args.resume or args.verify_only:
        assert read(out / 'settings.json') == settings, 'Settings changed'
    else:
        out.mkdir(parents=True)
        save(out / 'settings.json', settings)
        shutil.copyfile(rule_file, out / 'aragorn_rules.json')
        for source in sources:
            dest = out / 'source' / source.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
    if args.verify_only:
        summary = summarize(out, selected, candidates, answers, settings)
        print(json.dumps({'complete': summary['complete'], 'verified_queries': summary['completed_policy_queries']}), flush=True)
        return
    status = {'phase': 'preparation', 'complete': False, 'started_unix': time.time()}
    save(out / 'status.json', status)
    try:
        graph = CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
        assert graph.num_nodes == prep['nodes']
        assert [graph.id_to_predicate[i] for i in range(len(graph.predicate_to_idx))] == read(prepared / 'data/predicates.json')
        for row in candidate_rows:
            assert graph.get_node_id(row['index']) == row['id']
        for row in labels:
            assert graph.get_node_id(row['disease_index']) == row['disease']
        del candidate_rows
        hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
        graphs, graph_stats = {}, {}
        for policy in POLICIES:
            graphs[policy] = mask_graph(graph, hidden, policy)
            graph_stats[policy] = verify_mask(graph, graphs[policy], hidden, policy, prepared, candidates, labels)
            print(json.dumps(graph_stats[policy]), flush=True)
        save(out / 'source_graphs.json', graph_stats)
        bmt = make_toolkit()
        save(out / 'biolink.json', {'version': str(bmt.get_model_version())})
        CONTEXT.update(args=args, out=out, graphs=graphs, candidates=candidates, answers=answers,
                       hidden=hidden, target=graph.predicate_to_idx['biolink:treats'],
                       indices=indices, rules=rules, bmt=bmt)
        # Verify completed artifacts before allowing a resume to skip them.
        before = summarize(out, selected, candidates, answers, settings)
        tasks, pending_diseases = [], 0
        for number, disease in enumerate(selected):
            pending = [(p, number, disease) for p in POLICIES
                       if not (out / p / 'diseases' / f'{number:04d}' / 'report.json').exists()]
            if pending:
                if args.max_new_diseases is not None and pending_diseases >= args.max_new_diseases:
                    break
                tasks.extend(pending)
                pending_diseases += 1
        status.update(phase='retrieval', completed_policy_queries=before['completed_policy_queries'],
                      total_policy_queries=len(selected)*2)
        save(out / 'status.json', status)
        with ProcessPoolExecutor(max_workers=args.workers, mp_context=mp.get_context('fork')) as executor:
            futures = [executor.submit(retrieve, task) for task in tasks]
            for future in as_completed(futures):
                policy, number, disease = future.result()
                status['completed_policy_queries'] += 1
                status['updated_unix'] = time.time()
                save(out / 'status.json', status)
                print(f"{status['completed_policy_queries']}/{len(selected)*2} {policy} {disease}", flush=True)
        status['phase'] = 'verification'
        save(out / 'status.json', status)
        summary = summarize(out, selected, candidates, answers, settings)
        status.update(complete=summary['complete'], phase='complete' if summary['complete'] else 'paused',
                      finished_unix=time.time())
        save(out / 'status.json', status)
        print(json.dumps({'complete': summary['complete'], 'completed_policy_queries': summary['completed_policy_queries']}), flush=True)
    except BaseException as error:
        status.update(phase='failed', error=repr(error), finished_unix=time.time())
        save(out / 'status.json', status)
        raise


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    main()
