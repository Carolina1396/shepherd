"""Independently reconstruct the ablated graph from the original raw sources."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import random
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    args = parser.parse_args()
    base = args.dataset.resolve()
    read = lambda p: json.loads(p.read_text())
    manifest = read(base / 'preparation.json')
    cfg = read(base / 'config.json')
    assert manifest['complete'] and digest(base / 'config.json') == manifest['config_sha256']
    for name, expected in manifest['dataset_sha256'].items():
        assert digest(base / 'data' / name) == expected, name
    for name in ['nodes.json', 'candidates.json', 'predicates.json']:
        assert manifest['dataset_sha256'][name] == manifest['baseline_dataset_sha256'][name]
    sources = [Path(p) for p in manifest['source_files']]
    for path in sources:
        assert digest(path) == manifest['source_files'][str(path)]
    graph_path = next(p for p in sources if p.name == 'graph.txt.backup')
    node_path = next(p for p in sources if p.name == 'nodes.csv')
    with node_path.open() as stream:
        categories = {r['id']: r['label'] for r in csv.DictReader(stream)}
    nodes = read(base / 'data/nodes.json')
    indices = {r['id']: i for i, r in enumerate(nodes)}
    assert all(categories[r['id']] == r['category'] for r in nodes)
    predicates = read(base / 'data/predicates.json')
    relations = {p: i for i, p in enumerate(predicates)}
    labels = read(base / 'data/labels.json')
    candidates = read(base / 'data/candidates.json')
    assert {c['id'] for c in candidates} == {n['id'] for n in nodes if n['category'] == 'ChemicalSubstance'}
    assert all(indices[c['id']] == c['index'] for c in candidates)
    hidden = {frozenset((r['drug'], r['disease'])) for r in labels if r['split'] != 'visible'}
    pairs, connected, seen_relations = set(), set(), set()
    removed, kept_indications = Counter(), Counter()
    n, p = len(nodes), len(predicates)

    def expected_connections():
        with graph_path.open() as stream:
            for line in stream:
                h, rel, t = line.rstrip('\n').split('\t')
                connected.update((h, t))
                seen_relations.add(rel)
                hc, tc = categories[h], categories[t]
                if rel == 'indication' and hc == 'ChemicalSubstance' and tc == 'Disease':
                    pairs.add((h, t))
                if frozenset((h, t)) in hidden:
                    removed['heldout:' + rel] += 1
                    continue
                if rel != 'indication' and {hc, tc} == {'ChemicalSubstance', 'Disease'}:
                    removed['ablation:' + rel] += 1
                    continue
                if rel == 'indication':
                    kept_indications[hc + ' -> ' + tc] += 1
                yield (indices[h] * p + relations[rel]) * n + indices[t]

    expected = np.unique(np.fromiter(expected_connections(), dtype=np.int64))
    triples = np.load(base / 'data/triples.npy')
    actual = (triples[:, 0] * p + triples[:, 1]) * n + triples[:, 2]
    assert np.array_equal(expected, np.sort(actual)), 'Graph differs from independent raw-source reconstruction'
    assert connected == set(indices) and seen_relations == set(predicates)
    ordered = sorted(pairs)
    random.Random(731).shuffle(ordered)
    a, b = int(0.8 * len(ordered)), int(0.1 * len(ordered))
    expected_labels = {(h, t): 'visible' if i < a else 'validation' if i < a + b else 'test'
                       for i, (h, t) in enumerate(ordered)}
    assert len(labels) == len(expected_labels) == 3439
    assert {(r['drug'], r['disease']): r['split'] for r in labels} == expected_labels
    active = set(triples[:, 0]) | set(triples[:, 2])
    for row in labels:
        assert row['drug_index'] == indices[row['drug']] and row['disease_index'] == indices[row['disease']]
        assert row['drug_isolated'] == (row['drug_index'] not in active)
        assert row['disease_isolated'] == (row['disease_index'] not in active)
    assert kept_indications['ChemicalSubstance -> Disease'] == 2751
    assert sum(kept_indications.values()) == 2977
    assert removed['heldout:indication'] == 688
    assert {k.removeprefix('ablation:'): v for k, v in removed.items() if k.startswith('ablation:')} == manifest['additional_removed_by_predicate']
    assert len(triples) == manifest['remaining_connections'] == 9560423
    report = {'complete': True, 'raw_source_hashes_verified': True,
              'entire_graph_matches_independent_raw_reconstruction': True,
              'split_independently_reconstructed': True, 'unchanged_nodes_candidates_and_predicates': True,
              'heldout_pairs': len(hidden), 'removed_connections': dict(removed),
              'retained_indication_categories': dict(kept_indications), 'remaining_connections': len(triples),
              'isolated_candidates': sum(c['index'] not in active for c in candidates)}
    save(base / 'preparation_verification.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
