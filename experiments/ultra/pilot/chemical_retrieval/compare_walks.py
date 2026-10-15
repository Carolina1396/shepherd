"""Compare native Gandalf walks with frozen ARAGORN treats-only retrieval."""
import argparse
from collections import defaultdict
import csv
import importlib.util
import json
from pathlib import Path
import random
import resource
import shutil
import subprocess
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('chemical_walk_comparison', HERE / 'run.py')
comparison = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = comparison
spec.loader.exec_module(comparison)
ROOT = comparison.ROOT
from compare_walk_lengths import sample
from generate_queries import GraphSampler
from metrics import measure

read, save, digest = comparison.read, comparison.save, comparison.digest
SPLITS = ('validation', 'test')


def check_edges(edges, graph, hidden, treats, cap):
    assert len(edges) <= cap
    for h, p, t in edges:
        assert graph._find_edge_index(h, t, p) is not None, 'Retrieved edge absent from masked graph'
        assert not (p == treats and ((h, t) in hidden or (t, h) in hidden)), 'Held-out treats leaked'


def graph_metric(edges, anchor, candidates, answers):
    metrics = measure(edges, anchor, candidates, answers, set())
    # Walks supply graph context, not bindings to an answer variable.
    return {key: value for key, value in metrics.items() if key not in (
        'answers_bound', 'bound_answer_coverage', 'bound_answer_indices')}


def collect(out, baseline, cfg, candidates, answers, indices, graph, hidden):
    rows, paired = [], {split: {'both': [], 'walk_only': [], 'aragorn_only': [], 'neither': []} for split in SPLITS}
    completed, walk_seconds, completed_walks = 0, 0.0, 0
    target = graph.predicate_to_idx['biolink:treats']
    for number, disease in enumerate(cfg['cohort']):
        directory = out / 'diseases' / f'{number:04d}'
        if not (directory / 'report.json').exists():
            continue
        report = read(directory / 'report.json')
        assert report['disease'] == disease and report['anchor'] == indices[disease]
        assert digest(directory / 'graph.json') == report['graph_sha256']
        artifact = read(directory / 'graph.json')
        assert artifact['anchor'] == indices[disease] and artifact['disease'] == disease
        walk_edges = {tuple(edge) for edge in artifact['edges']}
        assert len(walk_edges) == len(artifact['edges'])
        check_edges(walk_edges, graph, hidden, target, cfg['edge_cap'])
        old_dir = baseline / 'treats_only/diseases' / f'{number:04d}'
        old = read(old_dir / 'report.json')
        assert old['disease'] == disease and old['policy'] == 'treats_only'
        assert digest(old_dir / 'graph.json') == old['artifact_sha256']['graph.json']
        assert digest(old_dir / 'report.json') == report['aragorn_report_sha256']
        old_graph = read(old_dir / 'graph.json')
        rule_edges = {tuple(edge) for edge in old_graph['edges']}
        assert old_graph['anchor'] == indices[disease]
        check_edges(rule_edges, graph, hidden, target, cfg['edge_cap'])
        for split in SPLITS:
            truth = answers[split][disease]
            if not truth:
                continue
            a = graph_metric(walk_edges, indices[disease], candidates, truth)
            b = graph_metric(rule_edges, indices[disease], candidates, truth)
            assert a == report['splits'][split]
            for key, value in b.items():
                assert value == old['splits'][split][key]
            for strategy, value, seconds in (
                    ('gandalf_walks', a, report['sampling_seconds']), ('aragorn_rules', b, old['retrieval_seconds'])):
                rows.append({'disease': disease, 'split': split, 'strategy': strategy,
                             **{key: val for key, val in value.items() if not key.endswith('_indices')},
                             'retrieval_seconds': seconds})
            wa, ra = set(a['recovered_answer_indices']), set(b['recovered_answer_indices'])
            groups = {'both': wa & ra, 'walk_only': wa - ra, 'aragorn_only': ra - wa, 'neither': truth - (wa | ra)}
            assert sum(map(len, groups.values())) == len(truth)
            for key, members in groups.items():
                paired[split][key].extend({'disease': disease, 'chemical': graph.get_node_id(i), 'chemical_index': i}
                                          for i in sorted(members))
        completed += 1
        walk_seconds += report['sampling_seconds']
        completed_walks += report['completed_walks']
    result = {'complete': completed == len(cfg['cohort']), 'completed_diseases': completed,
              'total_diseases': len(cfg['cohort']), 'settings_sha256': digest(out / 'settings.json'),
              'policy': 'treats_only', 'source_graph': read(out / 'source_graph.json'),
              'attempted_walks': completed * cfg['attempts'], 'completed_walks': completed_walks,
              'walk_sampling_seconds': walk_seconds, 'results': {}, 'paired_recovery': {},
              'verification': {'saved_graph_hashes_checked': True, 'coverage_recomputed': True,
                               'both_methods_checked_against_masked_graph': True, 'heldout_treats_absent': True},
              'scope': 'Graph-present retrieval coverage; fixed three-hop, 1000-attempt, 3000-connection budget. '
                       'Test is exploratory. No ULTRA ranking or model selection. One random seed.'}
    for strategy in ('gandalf_walks', 'aragorn_rules'):
        result['results'][strategy] = {}
        for split in SPLITS:
            subset = [row for row in rows if row['strategy'] == strategy and row['split'] == split]
            pairs = sum(row['answer_pairs'] for row in subset)
            reached = sum(row['answers_reached'] for row in subset)
            result['results'][strategy][split] = {
                'diseases': len(subset), 'answer_pairs': pairs,
                'expected_answer_pairs': sum(len(answers[split][d]) for d in cfg['cohort']),
                'answers_reached': reached, 'answer_coverage': reached / pairs if pairs else None,
                'mean_disease_answer_coverage': float(np.mean([r['answer_coverage'] for r in subset])) if subset else None,
                'empty_graphs': sum(r['edges'] == 0 for r in subset),
                'graphs_at_cap': sum(r['edges'] == cfg['edge_cap'] for r in subset),
                'graph_sizes': {key: {'mean': float(np.mean([r[key] for r in subset])),
                                      'median': float(np.median([r[key] for r in subset])),
                                      'min': min(r[key] for r in subset), 'max': max(r[key] for r in subset)}
                                for key in ('nodes', 'edges', 'candidate_nodes')} if subset else {}}
    for split, groups in paired.items():
        save(out / f'{split}_paired_answers.json', groups)
        counts = {key: len(value) for key, value in groups.items()}
        pairs = sum(counts.values())
        either = counts['both'] + counts['walk_only'] + counts['aragorn_only']
        result['paired_recovery'][split] = {**counts, 'either_method': either,
            'either_method_coverage': either / pairs if pairs else None,
            'note': 'Set union of answers from two separate graphs; not a merged graph subject to one 3000-edge cap.'}
    if result['complete']:
        reference = read(baseline / 'summary.json')['results']['treats_only']
        for split in SPLITS:
            assert result['results']['aragorn_rules'][split]['answers_reached'] == reference[split]['answers_reached']
            assert result['results']['gandalf_walks'][split]['answer_pairs'] == reference[split]['answer_pairs_expected']
    with (out / 'per_disease.csv').open('w', newline='') as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    save(out / ('summary.json' if result['complete'] else 'partial.json'), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT / 'pilot/results/chemical_retrieval_001')
    parser.add_argument('--output', type=Path, default=ROOT / 'pilot/results/chemical_walks_treats_only_001')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    baseline, out = args.baseline.resolve(), args.output.resolve()
    if out.exists() and not (args.resume or args.verify_only):
        parser.error('Output exists; choose a new directory or use --resume')
    if (args.resume or args.verify_only) and not (out / 'settings.json').exists():
        parser.error('No saved settings to resume or verify')
    old = read(baseline / 'settings.json')
    old_summary = read(baseline / 'summary.json')
    assert old_summary['complete'] and digest(baseline / 'settings.json') == old_summary['settings_sha256']
    for source, expected in old['source_sha256'].items():
        assert digest(ROOT / source) == expected, f'Baseline code changed: {source}'
    prepared = Path(old['dataset'])
    for name, expected in old['dataset_sha256'].items():
        assert digest(prepared / 'data' / name) == expected
    store = ROOT / 'output/gandalf/full-store'
    assert digest(store / 'metadata.pkl') == old['source_graph_metadata_sha256']
    gandalf = ROOT / 'vendor/gandalf'
    assert subprocess.check_output(['git', '-C', str(gandalf), 'rev-parse', 'HEAD'], text=True).strip() == old['gandalf_commit']
    subprocess.run(['git', '-C', str(gandalf), 'diff', '--quiet', 'HEAD', '--', 'gandalf',
                    'scripts/benchmarks/generate_queries.py'], check=True)
    sources = [Path(__file__), HERE / 'test_walk_comparison.py', HERE / 'run.py', HERE / 'masking.py', HERE / 'metrics.py',
               ROOT / 'pilot/retrieval/compare_walk_lengths.py', ROOT / 'pilot/retrieval/run.py',
               ROOT / 'pilot/retrieval/masked_graph.py', ROOT / 'scripts/full_graph_common.py',
               gandalf / 'scripts/benchmarks/generate_queries.py']
    cfg = {'experiment': 'Gandalf versus ARAGORN on chemical/drug treats-only graph',
           'baseline': str(baseline), 'baseline_settings_sha256': digest(baseline / 'settings.json'),
           'baseline_summary_sha256': digest(baseline / 'summary.json'),
           'policy': 'treats_only', 'cohort': old['cohort'], 'candidate_count': old['candidate_count'],
           'dataset_sha256': old['dataset_sha256'], 'source_graph_metadata_sha256': old['source_graph_metadata_sha256'],
           'seed': old['seed'], 'seed_per_disease': 'seed + position in frozen cohort',
           'attempts': 1000, 'walk_length': 3, 'edge_cap': old['edge_cap'],
           'gandalf_commit': old['gandalf_commit'], 'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in sources},
           'mask': 'Exact treats on all validation and test pairs, both directions, before sampling; training edges retained',
           'sampling': 'Unchanged native self-avoiding walk; either direction; excludes subclass_of; whole-walk union cap; no answer-guided sampling',
           'model_evaluation': False}
    assert cfg['edge_cap'] == 3000
    if out.exists():
        assert read(out / 'settings.json') == cfg, 'Configuration or source changed; use a fresh output'
    else:
        out.mkdir(parents=True)
        save(out / 'settings.json', cfg)
        for source in sources:
            destination = out / 'source' / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    status = {'phase': 'preparation', 'complete': False, 'started_unix': time.time()}
    save(out / 'status.json', status)
    tick = time.perf_counter()
    try:
        labels = read(prepared / 'data/labels.json')
        candidate_rows = read(prepared / 'data/candidates.json')
        candidates = {row['index'] for row in candidate_rows}
        assert len(candidates) == cfg['candidate_count']
        answers = {split: defaultdict(set) for split in SPLITS}
        indices = {}
        for row in labels:
            indices[row['disease']] = row['disease_index']
            if row['split'] in SPLITS:
                answers[row['split']][row['disease']].add(row['drug_index'])
        assert cfg['cohort'] == sorted(set(answers['validation']) | set(answers['test']))
        print('Loading original graph and verifying the exact ARAGORN treats-only mask...', flush=True)
        source = comparison.CSRGraph.load_mmap(store, mmap_mode='r')
        assert [source.id_to_predicate[i] for i in range(len(source.predicate_to_idx))] == read(prepared / 'data/predicates.json')
        for row in candidate_rows:
            assert source.get_node_id(row['index']) == row['id']
        for disease, index in indices.items():
            assert source.get_node_id(index) == disease
        del candidate_rows
        hidden = {(row['drug_index'], row['disease_index']) for row in labels if row['split'] in SPLITS}
        graph = comparison.mask_graph(source, hidden, 'treats_only')
        verified = comparison.verify_mask(source, graph, hidden, 'treats_only', prepared, candidates, labels)
        assert verified == read(baseline / 'source_graphs.json')['treats_only']
        save(out / 'source_graph.json', verified)
        print(json.dumps({'mask_verified': True, 'unique_directed_connections': verified['unique_directed_connections'],
                          'removed_connections': verified['removed_unique_connections']}), flush=True)
        status.update(phase='verification' if args.verify_only else 'sampling', completed_diseases=0)
        save(out / 'status.json', status)
        if not args.verify_only:
            sampler = GraphSampler(graph, random.Random(cfg['seed']))
            for number, disease in enumerate(cfg['cohort']):
                directory = out / 'diseases' / f'{number:04d}'
                directory.mkdir(parents=True, exist_ok=True)
                if not (directory / 'report.json').exists():
                    # No labels are passed to the native sampler or budget selection.
                    edges, completed, seconds = sample(sampler, indices[disease], cfg['walk_length'],
                                                       cfg['attempts'], cfg['edge_cap'], cfg['seed'] + number)
                    save(directory / 'graph.json', {'disease': disease, 'anchor': indices[disease], 'edges': sorted(edges)})
                    report = {'disease': disease, 'anchor': indices[disease], 'attempted_walks': cfg['attempts'],
                              'completed_walks': completed, 'sampling_seconds': seconds,
                              'splits': {split: graph_metric(edges, indices[disease], candidates, answers[split][disease])
                                         for split in SPLITS if answers[split][disease]},
                              'graph_sha256': digest(directory / 'graph.json'),
                              'aragorn_report_sha256': digest(baseline / 'treats_only/diseases' / f'{number:04d}' / 'report.json')}
                    save(directory / 'report.json', report)
                if (number + 1) % 100 == 0 or number + 1 == len(cfg['cohort']):
                    status.update(completed_diseases=number + 1, updated_unix=time.time())
                    save(out / 'status.json', status)
                    print(f"Sampled {number + 1}/{len(cfg['cohort'])} diseases", flush=True)
        status['phase'] = 'verifying_saved_graphs'
        save(out / 'status.json', status)
        print('Verifying saved graphs, recovery, and paired differences for both methods...', flush=True)
        result = collect(out, baseline, cfg, candidates, answers, indices, graph, hidden)
        result['elapsed_seconds_this_invocation'] = time.perf_counter() - tick
        result['peak_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        save(out / ('summary.json' if result['complete'] else 'partial.json'), result)
        if result['complete']:
            save(ROOT / 'pilot/studies' / f'{out.name}_results.json', result)
        status.update(complete=result['complete'], phase='complete' if result['complete'] else 'partial', finished_unix=time.time())
        save(out / 'status.json', status)
        print(json.dumps(result, indent=2), flush=True)
    except BaseException as error:
        status.update(phase='failed', error=repr(error), finished_unix=time.time())
        save(out / 'status.json', status)
        raise


if __name__ == '__main__':
    main()
