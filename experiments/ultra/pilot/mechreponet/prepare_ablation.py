"""Remove non-indication chemical–disease context from a frozen MechRepoNet run."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, hidden_pair_mask, save


def removal_mask(triples, categories, indication):
    chemical = np.asarray(categories) == 'ChemicalSubstance'
    disease = np.asarray(categories) == 'Disease'
    h, p, t = triples.T
    direct = (chemical[h] & disease[t]) | (disease[h] & chemical[t])
    return direct & (p != indication)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base, out = args.baseline.resolve(), args.output.resolve()
    if out.exists():
        parser.error('Refusing to overwrite an existing preparation')
    start = time.perf_counter()
    read = lambda path: json.loads(path.read_text())
    original = read(base / 'preparation.json')
    cfg = read(base / 'config.json')
    reference = read(ROOT / 'pilot/studies/mechreponet_ultra4g_masked.json')
    assert original['complete'] and cfg['training_epochs'] == 0
    assert digest(base / 'config.json') == original['config_sha256']
    assert original['dataset_sha256'] == reference['comparison']['preparation']['dataset_sha256']
    assert cfg['checkpoint_sha256'] == reference['settings']['checkpoint_sha256']
    for name, expected in original['dataset_sha256'].items():
        assert digest(base / 'data' / name) == expected, name
    nodes = read(base / 'data/nodes.json')
    labels = read(base / 'data/labels.json')
    candidates = read(base / 'data/candidates.json')
    predicates = read(base / 'data/predicates.json')
    indication = predicates.index('indication')
    triples = np.load(base / 'data/triples.npy')
    remove = removal_mask(triples, [n['category'] for n in nodes], indication)
    removed = dict(Counter(predicates[int(p)] for p in triples[remove, 1]))
    expected = {'treats_CtD': 65009, 'marker_or_mechanism_CmD': 20924,
                'palliates_CplD': 2087, 'prevents_CpvD': 1280}
    assert removed == expected, removed
    masked = triples[~remove]
    assert np.array_equal(triples[triples[:, 1] == indication], masked[masked[:, 1] == indication])
    hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
    assert not hidden_pair_mask(masked[:, 0], masked[:, 2], hidden, len(nodes)).any()
    active = np.zeros(len(nodes), dtype=bool)
    active[masked[:, 0]] = True
    active[masked[:, 2]] = True
    for row in labels:
        row.update(drug_isolated=not bool(active[row['drug_index']]),
                   disease_isolated=not bool(active[row['disease_index']]))
    baseline_results = {}
    baseline_hashes = {}
    for split in ['validation', 'test']:
        path = base / 'evaluation' / split / 'metrics.json'
        metrics = read(path)
        assert metrics['complete']
        assert metrics['ultra'] == reference['comparison']['results'][split]['ultra']
        baseline_results[split] = metrics['ultra']
        baseline_hashes[split] = digest(path)
    data = out / 'data'
    data.mkdir(parents=True)
    for name in ['nodes.json', 'candidates.json', 'predicates.json']:
        shutil.copyfile(base / 'data' / name, data / name)
    save(data / 'labels.json', labels)
    np.save(data / 'triples.npy', masked)
    cfg.update(experiment='8_non_indication_ablation',
               context_ablation='Remove all non-indication ChemicalSubstance–Disease edges in both directions; retain visible indications',
               baseline_results=baseline_results, baseline_metrics_sha256=baseline_hashes,
               baseline_preparation_sha256=digest(base / 'preparation.json'))
    save(out / 'config.json', cfg)
    sources = [Path(__file__), ROOT / 'scripts/full_graph_common.py']
    for path in sources:
        shutil.copyfile(path, out / path.name)
    total_removed = Counter(original['removed_by_predicate']) + Counter(removed)
    report = {**original, 'baseline_path': str(base),
              'baseline_preparation_sha256': digest(base / 'preparation.json'),
              'baseline_dataset_sha256': original['dataset_sha256'],
              'baseline_remaining_connections': len(triples),
              'additional_removed_connections': int(remove.sum()),
              'additional_removed_by_predicate': removed,
              'removed_connections': original['removed_connections'] + int(remove.sum()),
              'removed_by_predicate': dict(total_removed),
              'remaining_connections': len(masked), 'edges_with_inverses': 2 * len(masked),
              'remaining_indication_connections': int(np.count_nonzero(masked[:, 1] == indication)),
              'isolated_candidate_compounds': sum(not bool(active[c['index']]) for c in candidates),
              'all_non_indication_chemical_disease_connections_absent': True,
              'all_baseline_indication_connections_retained': True,
              'source_code_sha256': {p.name: digest(p) for p in sources},
              'config_sha256': digest(out / 'config.json'),
              'dataset_sha256': {p.name: digest(p) for p in sorted(data.iterdir())},
              'preparation_seconds': time.perf_counter() - start}
    save(out / 'preparation.json', report)
    print(json.dumps({k: report[k] for k in ['additional_removed_by_predicate', 'remaining_connections',
          'remaining_indication_connections', 'isolated_candidate_compounds', 'preparation_seconds']}, indent=2))


if __name__ == '__main__':
    main()
