"""Count DrugCentral treats records and same-pair overlap with other predicates.

Uses analyze_graph's drug/disease categories. Both edge directions are matched
by the same drug and disease identifiers; no synonym or subclass expansion.
Source selection requires infores:drugcentral as primary_knowledge_source.
Reads only the existing graph. Run with the existing Gandalf Python environment.
"""

import argparse
import pickle
import sys

import numpy as np

from analyze_graph import DEFAULT_GRAPH, node_masks


def pair_codes(subjects, objects, drug, disease):
    """Return matching edge mask and direction-normalized drug/disease keys."""
    forward = drug[subjects] & disease[objects]
    reverse = disease[subjects] & drug[objects] & ~forward
    keep = forward | reverse
    drugs = np.where(forward[keep], subjects[keep], objects[keep]).astype(np.int64)
    diseases = np.where(forward[keep], objects[keep], subjects[keep]).astype(np.int64)
    return keep, drugs * len(drug) + diseases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=type(DEFAULT_GRAPH), default=DEFAULT_GRAPH)
    args = parser.parse_args()
    graph = args.graph.resolve()
    with (graph / 'metadata.pkl').open('rb') as stream:
        metadata = pickle.load(stream)
    with (graph / 'edge_property_pools.pkl').open('rb') as stream:
        sources = pickle.load(stream)['sources_pool']
    is_drugcentral = np.array([
        any(s.get('resource_id') == 'infores:drugcentral'
            and s.get('resource_role') == 'primary_knowledge_source' for s in group)
        for group in sources
    ], dtype=bool)
    print('Reading categories and scanning graph...', file=sys.stderr, flush=True)
    drug, disease = node_masks(graph, metadata['num_nodes'])
    arrays = {
        name: np.load(graph / f'{name}.npy', mmap_mode='r', allow_pickle=False)
        for name in ('fwd_offsets', 'fwd_targets', 'fwd_predicates', 'edge_sources_idx')
    }
    pair_chunks, predicate_chunks, source_chunks = [], [], []
    for start in range(0, len(arrays['fwd_targets']), 1_000_000):
        end = min(start + 1_000_000, len(arrays['fwd_targets']))
        subjects = np.searchsorted(arrays['fwd_offsets'], np.arange(start, end), side='right') - 1
        keep, pairs = pair_codes(subjects, arrays['fwd_targets'][start:end], drug, disease)
        pair_chunks.append(pairs)
        predicate_chunks.append(arrays['fwd_predicates'][start:end][keep])
        source_chunks.append(is_drugcentral[arrays['edge_sources_idx'][start:end][keep]])
    pairs = np.concatenate(pair_chunks)
    predicates = np.concatenate(predicate_chunks)
    dc = np.concatenate(source_chunks)
    treats = metadata['predicate_to_idx']['biolink:treats']
    training = dc & (predicates == treats)
    training_pairs = np.unique(pairs[training])
    matching = np.isin(pairs, training_pairs)
    other = matching & (predicates != treats)
    overlap_pairs = np.unique(pairs[other])
    denominator = len(training_pairs)
    print(f'Graph: {graph}')
    print('Source: infores:drugcentral, primary_knowledge_source')
    print('Predicate: exact biolink:treats; categories from analyze_graph.py')
    print('Overlap: same drug/disease IDs in either direction, across all sources.')
    print(f'DrugCentral treats edge records: {training.sum():,}')
    print(f'DrugCentral treats unique pairs: {denominator:,}')
    print(f'Pairs with any OTHER predicate: {len(overlap_pairs):,} / {denominator:,}')
    print(f'Pairs with no other predicate: {denominator - len(overlap_pairs):,}')
    print(f'Other-predicate edge records on these pairs: {other.sum():,}')
    other_treats = matching & (predicates == treats) & ~dc
    print(f'Pairs also having treats without DrugCentral primary provenance: {len(np.unique(pairs[other_treats])):,} ({other_treats.sum():,} records)')
    print('\nOther predicates (rows can overlap; percentages use DrugCentral treats unique pairs):')
    rows = []
    for predicate, idx in metadata['predicate_to_idx'].items():
        mask = other & (predicates == idx)
        if mask.any():
            rows.append((predicate, int(mask.sum()), len(np.unique(pairs[mask])),
                         len(np.unique(pairs[mask & ~dc]))))
    rows.sort(key=lambda row: (-row[2], row[0]))
    width = max([len('Predicate')] + [len(row[0]) for row in rows])
    print(f"{'Predicate':<{width}}  {'Records':>10}  {'Pairs':>10}  {'% pairs':>8}  {'Pairs non-DC':>12}")
    for predicate, records, count, non_dc in rows:
        print(f'{predicate:<{width}}  {records:>10,}  {count:>10,}  {100 * count / denominator:>7.2f}%  {non_dc:>12,}')
    print('Pairs non-DC: overlap pairs with at least one record lacking DrugCentral primary provenance.')


if __name__ == '__main__':
    main()
