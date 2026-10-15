"""Complete visible-pair retrieval coverage under the frozen treats-only protocol."""
import argparse
from collections import defaultdict, Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import importlib.util
import json
import multiprocessing as mp
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('chemical_comparison', HERE / 'run.py')
comparison = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = comparison
spec.loader.exec_module(comparison)
comparison.SPLITS = ('visible',)
ROOT = comparison.ROOT
read, save, digest = comparison.read, comparison.save, comparison.digest


def summarize(out, original, cohort, training, original_positions):
    counts = Counter()
    records = []
    statuses = Counter()
    for number, disease in enumerate(cohort):
        if not training[disease]:
            continue
        base = original if disease in original_positions else out
        directory = base / 'treats_only/diseases' / f'{number:04d}'
        if not (directory / 'report.json').exists():
            continue
        report = read(directory / 'report.json')
        assert report['disease'] == disease
        for name, expected in report['artifact_sha256'].items():
            assert digest(directory / name) == expected
        g = read(directory / 'graph.json')
        edges = {tuple(e) for e in g['edges']}
        nodes = {g['anchor']} | {x for h, p, t in edges for x in (h, t)}
        bound = set(g['rule_answer_nodes'])
        assert edges == {tuple(e) for units in g['retained_matches_by_rule'].values()
                         for unit in units for e in unit['edges']}
        assert bound == {a for units in g['retained_matches_by_rule'].values() for unit in units for a in unit['answers']}
        truth = training[disease]
        reached, returned = truth & nodes, truth & bound
        records.append({'disease': disease, 'answers': len(truth), 'reached': len(reached),
                        'bound': len(returned), 'nodes': len(nodes), 'edges': len(edges),
                        'recovered_indices': sorted(reached), 'bound_indices': sorted(returned),
                        'missing_indices': sorted(truth-nodes), 'graph_path': str(directory / 'graph.json')})
        counts.update(diseases=1, pairs=len(truth), reached=len(reached), bound=len(returned))
        statuses.update(report['rule_status_counts'])
    expected = sum(len(a) for a in training.values())
    result = {'policy': 'treats_only', 'complete': counts['pairs'] == expected,
              'training_pairs_expected': expected, 'training_diseases_expected': sum(bool(a) for a in training.values()),
              **dict(counts), 'recovery': counts['reached']/counts['pairs'] if counts['pairs'] else None,
              'bound_recovery': counts['bound']/counts['pairs'] if counts['pairs'] else None,
              'rule_status_counts': dict(statuses), 'verified_from_saved_graphs': True,
              'source_comparison': str(original), 'settings_sha256': digest(out / 'settings.json'),
              'interpretation': 'Visible training treats edges remain in the graph; this is retrieval coverage of known evidence, not held-out prediction.'}
    save(out / 'per_disease.json', records)
    save(out / ('summary.json' if result['complete'] else 'partial.json'), result)
    if result['complete']:
        save(ROOT / 'pilot/studies/chemical_retrieval_001_train_recovery.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'pilot/results/chemical_retrieval_001_train')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    original = ROOT / 'pilot/results/chemical_retrieval_001'
    out = args.output.resolve()
    cfg = read(original / 'settings.json')
    for source, expected in cfg['source_sha256'].items():
        assert digest(ROOT / source) == expected
    prepared = Path(cfg['dataset'])
    for name in ('labels.json', 'candidates.json', 'triples.npy'):
        assert digest(prepared / 'data' / name) == cfg['dataset_sha256'][name]
    labels = read(prepared / 'data/labels.json')
    candidate_rows = read(prepared / 'data/candidates.json')
    candidates = {r['index'] for r in candidate_rows}
    training = defaultdict(set)
    indices = {}
    for row in labels:
        indices[row['disease']] = row['disease_index']
        if row['split'] == 'visible':
            training[row['disease']].add(row['drug_index'])
    existing = {d: n for n, d in enumerate(cfg['cohort'])}
    cohort = cfg['cohort'] + sorted(set(training)-set(existing))
    settings = {'source_comparison_settings_sha256': digest(original / 'settings.json'),
                'policy': 'treats_only', 'cohort': cohort, 'training_pairs': sum(map(len, training.values())),
                'workers': cfg['workers'], 'seed': cfg['seed'], 'edge_cap': cfg['edge_cap'],
                'rule_timeout': cfg['rule_timeout_seconds'], 'source_sha256': digest(Path(__file__)),
                'reuse': 'Original disease indices and seeds preserved; training-only diseases appended in sorted order'}
    if out.exists():
        if not (args.resume or args.verify_only):
            parser.error('Output exists; use --resume')
        assert read(out / 'settings.json') == settings
    else:
        out.mkdir()
        save(out / 'settings.json', settings)
    initial = summarize(out, original, cohort, training, existing)
    if args.verify_only or initial['complete']:
        print(json.dumps(initial), flush=True)
        return
    status = {'phase': 'preparation', 'complete': False, 'started_unix': time.time(),
              'reused_training_diseases': initial['diseases'], 'reused_training_pairs': initial['pairs']}
    save(out / 'status.json', status)
    try:
        source = comparison.CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
        assert digest(ROOT / 'output/gandalf/full-store/metadata.pkl') == cfg['source_graph_metadata_sha256']
        for row in candidate_rows:
            assert source.get_node_id(row['index']) == row['id']
        hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
        graph = comparison.mask_graph(source, hidden, 'treats_only')
        verified = comparison.verify_mask(source, graph, hidden, 'treats_only', prepared, candidates, labels)
        assert verified == read(original / 'source_graphs.json')['treats_only']
        save(out / 'source_graph.json', verified)
        bmt = comparison.make_toolkit()
        assert str(bmt.get_model_version()) == read(original / 'biolink.json')['version']
        rules_path = original / 'aragorn_rules.json'
        assert digest(rules_path) == cfg['rules_sha256']
        rules = read(rules_path)['{"predicate": "biolink:treats"}']
        runtime = argparse.Namespace(seed=cfg['seed'], edge_cap=cfg['edge_cap'], rule_timeout=cfg['rule_timeout_seconds'])
        comparison.CONTEXT.update(args=runtime, out=out, graphs={'treats_only': graph}, candidates=candidates,
                                  answers={'visible': training}, hidden=hidden,
                                  target=source.predicate_to_idx['biolink:treats'], indices=indices, rules=rules, bmt=bmt)
        tasks = [('treats_only', n, d) for n, d in enumerate(cohort) if d not in existing and
                 not (out / 'treats_only/diseases' / f'{n:04d}' / 'report.json').exists()]
        status.update(phase='retrieval', completed_new_queries=0, pending_new_queries=len(tasks))
        save(out / 'status.json', status)
        with ProcessPoolExecutor(max_workers=cfg['workers'], mp_context=mp.get_context('fork')) as executor:
            for future in as_completed([executor.submit(comparison.retrieve, task) for task in tasks]):
                policy, number, disease = future.result()
                status['completed_new_queries'] += 1
                status['updated_unix'] = time.time()
                save(out / 'status.json', status)
                print(f"{status['completed_new_queries']}/{len(tasks)} {disease}", flush=True)
        result = summarize(out, original, cohort, training, existing)
        assert result['complete']
        status.update(phase='complete', complete=True, finished_unix=time.time())
        save(out / 'status.json', status)
        print(json.dumps(result), flush=True)
    except BaseException as error:
        status.update(phase='failed', error=repr(error), finished_unix=time.time())
        save(out / 'status.json', status)
        raise


if __name__ == '__main__':
    main()
