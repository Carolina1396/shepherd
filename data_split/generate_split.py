"""Generate 80/10/10 train/val/test CSVs of DrugCentral treats pairs.

Run using the existing environment (no installation needed):
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python data_split/generate_split.py

Only exact biolink:treats edges with infores:drugcentral as a primary source
are labels. Drug/disease categories come from analyze_graph.py. Both stored
directions are normalized to drug,disease; pairs are deduplicated before
splitting. This is a random PAIR split: drugs and diseases can appear in more
than one partition. It does not enforce training coverage of every entity.

The input graph is read-only and must be trusted (its metadata uses pickle).
Creating label files does NOT remove any edges or prevent graph leakage.
"""

import argparse
import csv
from pathlib import Path
import pickle
import random
import sys

import lmdb
import msgpack
import numpy as np

from analyze_graph import DEFAULT_GRAPH, DRUG_CATEGORIES, DISEASE_CATEGORIES


FIELDS = ('drug_id', 'drug_name', 'disease_id', 'disease_name')


def extract_pairs(graph):
    """Return distinct ID/name rows and the number of eligible edge records."""
    with (graph / 'metadata.pkl').open('rb') as stream:
        metadata = pickle.load(stream)
    with (graph / 'edge_property_pools.pkl').open('rb') as stream:
        pools = pickle.load(stream)
    primary_dc = np.array([
        any(source.get('resource_id') == 'infores:drugcentral'
            and source.get('resource_role') == 'primary_knowledge_source'
            for source in group)
        for group in pools['sources_pool']
    ], dtype=bool)
    del pools
    offsets, targets, predicates, sources = (
        np.load(graph / f'{name}.npy', mmap_mode='r', allow_pickle=False)
        for name in ('fwd_offsets', 'fwd_targets', 'fwd_predicates', 'edge_sources_idx')
    )
    treats = metadata['predicate_to_idx']['biolink:treats']
    positions = []
    for start in range(0, len(targets), 1_000_000):
        end = min(start + 1_000_000, len(targets))
        mask = (predicates[start:end] == treats) & primary_dc[sources[start:end]]
        positions.extend((np.flatnonzero(mask) + start).tolist())
    subjects = np.searchsorted(offsets, positions, side='right') - 1
    objects = targets[positions]
    nodes = {}
    with lmdb.open(str(graph / 'node_store.lmdb'), readonly=True,
                   lock=False, max_dbs=3, readahead=False) as env:
        ids_db = env.open_db(b'idx_to_id', create=False)
        props_db = env.open_db(b'properties', create=False)
        with env.begin() as txn:
            for idx in sorted(set(subjects.tolist()) | set(objects.tolist())):
                key = int(idx).to_bytes(4, 'big')
                curie = txn.get(key, db=ids_db)
                value = txn.get(key, db=props_db)
                if curie is None or value is None:
                    raise ValueError(f'Missing node data for index {idx}')
                props = msgpack.unpackb(value, raw=False)
                categories = props.get('categories', [])
                if isinstance(categories, str):
                    categories = [categories]
                nodes[idx] = (curie.decode(), props.get('name') or '', set(categories))
    rows = {}
    records = 0
    for subject, obj in zip(subjects, objects):
        left, right = nodes[int(subject)], nodes[int(obj)]
        if left[2] & DRUG_CATEGORIES and right[2] & DISEASE_CATEGORIES:
            drug, disease = left, right
        elif right[2] & DRUG_CATEGORIES and left[2] & DISEASE_CATEGORIES:
            drug, disease = right, left
        else:
            continue
        records += 1
        rows[drug[0], disease[0]] = (drug[0], drug[1], disease[0], disease[1])
    return sorted(rows.values()), records


def split_pairs(rows, seed=42):
    """Shuffle canonical ID order, then reserve rounded 10% val and test sets."""
    rows = sorted(rows, key=lambda row: (row[0], row[2]))
    keys = {(row[0], row[2]) for row in rows}
    if len(keys) != len(rows):
        raise ValueError('Pairs must be deduplicated before splitting')
    holdout = (len(rows) + 5) // 10  # nearest integer, with halves rounded up
    if holdout == 0 or len(rows) - 2 * holdout <= 0:
        raise ValueError('Too few pairs for three nonempty partitions')
    random.Random(seed).shuffle(rows)
    train_end = len(rows) - 2 * holdout
    return {
        'train': sorted(rows[:train_end]),
        'val': sorted(rows[train_end:train_end + holdout]),
        'test': sorted(rows[train_end + holdout:]),
    }


def write_splits(splits, out):
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in splits.items():
        with (out / f'{name}.csv').open('x', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, default=DEFAULT_GRAPH)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    existing = [args.out / f'{name}.csv' for name in ('train', 'val', 'test')
                if (args.out / f'{name}.csv').exists()]
    if existing:
        parser.error('Output files already exist; use a fresh --out directory: '
                     + ', '.join(map(str, existing)))
    print('Reading DrugCentral treats labels from the existing graph...',
          file=sys.stderr, flush=True)
    rows, records = extract_pairs(args.graph.resolve())
    splits = split_pairs(rows, args.seed)
    pair_sets = [{(row[0], row[2]) for row in part} for part in splits.values()]
    assert sum(map(len, pair_sets)) == len(set.union(*pair_sets)) == len(rows)
    write_splits(splits, args.out)
    print(f'Graph: {args.graph.resolve()}')
    print(f'Seed: {args.seed}; split: 80/10/10; records: {records:,}; unique pairs: {len(rows):,}')
    train_drugs = {row[0] for row in splits['train']}
    train_diseases = {row[2] for row in splits['train']}
    for name, part in splits.items():
        print(f'{name}: {len(part):,} pairs -> {args.out / (name + ".csv")}')
        if name != 'train':
            unseen_drugs = {row[0] for row in part} - train_drugs
            unseen_diseases = {row[2] for row in part} - train_diseases
            print(f'  Entities absent from training LABELS: {len(unseen_drugs)} drugs, '
                  f'{len(unseen_diseases)} diseases (not necessarily absent from the graph)')
    print('Verified: no duplicate pairs, no pair overlap, all extracted pairs included.')
    print('The graph is unchanged; these files contain positive labels only.')


if __name__ == '__main__':
    main()
