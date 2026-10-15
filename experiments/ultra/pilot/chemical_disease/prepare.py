"""Prepare full Tier 0 chemical/drug-to-Disease treats labels for Experiment 10."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import sys
import time
import numpy as np
from gandalf import CSRGraph

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, hidden_pair_mask, save, split_pairs

CHEMICAL = {'biolink:Drug', 'biolink:SmallMolecule', 'biolink:ChemicalEntity'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.scope = 'chemical-disease'
    args.candidates = 'chemical'
    out = args.output.resolve()
    if out.exists(): parser.error('Refusing to overwrite existing output')
    started = time.perf_counter()
    graph = CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
    n = graph.num_nodes
    predicates = [graph.id_to_predicate[i] for i in range(len(graph.predicate_to_idx))]
    p = len(predicates); target = predicates.index('biolink:treats')
    chemical = np.zeros(n, dtype=bool); protein = chemical.copy(); disease = chemical.copy()
    for i, props in graph.node_store.iter_properties():
        cats = set(props.get('categories', []))
        chemical[i] = bool(cats & CHEMICAL)
        protein[i] = 'biolink:Protein' in cats
        disease[i] = 'biolink:Disease' in cats
    pos = np.flatnonzero(graph.fwd_predicates == target)
    heads = np.searchsorted(graph.fwd_offsets, pos, side='right') - 1
    tails = graph.fwd_targets[pos]
    keys = np.unique(heads.astype(np.int64) * n + tails)
    all_count = len(keys)
    keys = keys[chemical[keys // n] & disease[keys % n]]
    subject_indices = np.unique(keys // n)
    candidate_indices = np.flatnonzero(chemical)
    assert np.isin(subject_indices, candidate_indices).all(), 'Candidate pool excludes target subjects'
    pairs = {(graph.get_node_id(int(k // n)), graph.get_node_id(int(k % n))) for k in keys}
    inventory = ROOT / 'output/treatment_pairs/pairs.csv'
    with inventory.open() as stream:
        reference = {(row['chemical_id'], row['disease_id']) for row in csv.DictReader(stream)
                     if 'biolink:treats' in json.loads(row['predicates'])}
    assert pairs == reference and len(pairs) == 22918
    assert len(candidate_indices) == 1117832
    assert not any((t,h) in pairs for h,t in pairs), 'Reverse target pairs need grouped splitting'
    labels = [{'drug': h, 'disease': t, 'drug_index': int(graph.get_node_idx(h)),
               'disease_index': int(graph.get_node_idx(t)), 'split': s} for h,t,s in split_pairs(pairs)]
    counts = dict(Counter(r['split'] for r in labels))
    assert counts == {'visible': 18334, 'validation': 2291, 'test': 2293}
    hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
    print(f'{len(labels):,} target pairs; split {counts}; {len(candidate_indices):,} candidates', flush=True)
    candidates = [{'index': int(i), 'id': graph.get_node_id(int(i))} for i in candidate_indices]
    sources = np.repeat(np.arange(n, dtype=np.int64), np.diff(graph.fwd_offsets))
    encoded = (sources * p + graph.fwd_predicates) * n + graph.fwd_targets
    del sources
    unique = np.unique(encoded); del encoded
    raw_unique = len(unique)
    h, r, t = unique // (n*p), (unique // n) % p, unique % n
    del unique
    remove = hidden_pair_mask(h, t, hidden, n)
    removed = dict(Counter(predicates[int(v)] for v in r[remove]))
    triples = np.column_stack((h[~remove], r[~remove], t[~remove]))
    assert not hidden_pair_mask(triples[:,0], triples[:,2], hidden, n).any()
    actual = {(int(h), int(t)) for h,r,t in triples[triples[:,1] == target]}
    expected = {(row['drug_index'], row['disease_index']) for row in labels if row['split'] == 'visible'}
    assert expected <= actual
    eligible_actual = {(h,t) for h,t in actual if chemical[h] and disease[t]}
    assert eligible_actual == expected
    active = np.zeros(n, dtype=bool); active[triples[:,0]] = True; active[triples[:,2]] = True
    visible_targets = {row['disease'] for row in labels if row['split'] == 'visible'}
    for row in labels:
        row.update(disease_has_visible_treatment=row['disease'] in visible_targets,
                   drug_isolated=not bool(active[row['drug_index']]), disease_isolated=not bool(active[row['disease_index']]))
    data = out / 'data'; data.mkdir(parents=True)
    np.save(data / 'triples.npy', triples)
    save(data / 'labels.json', labels); save(data / 'candidates.json', candidates); save(data / 'predicates.json', predicates)
    original = json.loads((ROOT / 'output/full-graph-ultra/run_001/config.json').read_text())
    assert digest(ROOT / original['checkpoint']) == original['checkpoint_sha256']
    cfg = {k: original[k] for k in ['checkpoint','checkpoint_sha256','ultra_commit']}
    cfg.update(experiment=10, num_nodes=n, num_relations=p, target_predicate='biolink:treats',
               target_scope=args.scope, candidate_scope=args.candidates, split_seed=731, pair_splits=counts, training_epochs=0,
               ranking='Predict chemical/drug subject given Disease object; fixed chemical/drug candidates; all-known filtering; pessimistic ties',
               mask='All direct held-out pair connections, all predicates, both directions, before inverse/relation graph construction',
               legacy_field_names='drug means subject with Drug, ChemicalEntity or SmallMolecule category; disease requires Disease category')
    save(out / 'config.json', cfg)
    report = {'complete': True, 'nodes': n, 'treats_records_all_types': len(pos), 'all_unique_treats_pairs': all_count,
              'eligible_treats_records': int(np.sum(chemical[heads] & disease[tails])), 'selected_pairs': len(labels), 'pair_splits': counts, 'candidates': len(candidates),
              'distinct_treatment_subjects': len(subject_indices), 'distinct_target_objects': len({r['disease'] for r in labels}),
              'candidate_scope': args.candidates, 'target_scope': args.scope,
              'chemical_candidates': int(chemical.sum()), 'protein_candidates': int(protein.sum()),
              'queries_by_split': {s: len({r['disease'] for r in labels if r['split'] == s}) for s in counts},
              'target_category_pair_counts': dict(Counter('Disease' if disease[r['disease_index']] else 'Other' for r in labels)),
              'original_unique_connections': raw_unique, 'removed_connections': int(remove.sum()),
              'removed_by_predicate': removed, 'remaining_connections': len(triples), 'edges_with_inverses': 2*len(triples),
              'isolated_candidates': int((~active[candidate_indices]).sum()),
              'all_heldout_direct_connections_absent': True, 'all_visible_targets_retained': True,
              'source_inventory_sha256': digest(inventory),
              'source_code_sha256': {path.name: digest(path) for path in [Path(__file__), ROOT / 'scripts/full_graph_common.py']},
              'config_sha256': digest(out / 'config.json'),
              'dataset_sha256': {f.name: digest(f) for f in sorted(data.iterdir())},
              'preparation_seconds': time.perf_counter() - started}
    for path in [Path(__file__), ROOT / 'scripts/full_graph_common.py']:
        shutil.copyfile(path, out / path.name)
    save(out / 'preparation.json', report)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__': main()
