"""Preserve split assignments, excluding pairs isolated by the planned graph filter.

Run with ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python.
This simulates removing all drug/chemical--disease/phenotype edges in either
direction. It writes label CSVs only, never modifies the graph, and does not
guarantee a connecting path between retained endpoints. Output must be new.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import lmdb
import numpy as np

from analyze_graph import DEFAULT_GRAPH, DRUG_CATEGORIES, DISEASE_CATEGORIES, node_masks
from generate_split import FIELDS


def remaining_degrees(offsets, targets, drug, disease):
    degrees = np.zeros(len(drug), dtype=np.int64)
    removed = 0
    for start in range(0, len(targets), 1_000_000):
        end = min(start + 1_000_000, len(targets))
        subjects = np.searchsorted(offsets, np.arange(start, end), side='right') - 1
        objects = targets[start:end]
        drop = ((drug[subjects] & disease[objects])
                | (disease[subjects] & drug[objects]))
        removed += int(drop.sum())
        degrees += np.bincount(subjects[~drop], minlength=len(drug))
        degrees += np.bincount(objects[~drop], minlength=len(drug))
    return degrees, removed


def partition_rows(rows, degrees_by_id):
    kept, excluded = [], []
    for row in rows:
        # Missing IDs are input errors, not silently excluded labels.
        isolated = [col for col in ('drug_id', 'disease_id')
                    if degrees_by_id[row[col]] == 0]
        if isolated:
            excluded.append(dict(row, reason='isolated_' + '_and_'.join(isolated)))
        else:
            kept.append(row)
    return kept, excluded


def write_csv(path, fields, rows):
    with path.open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, default=DEFAULT_GRAPH)
    parser.add_argument('--splits', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parent / 'nonisolated')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output directory already exists; choose a new --out directory')
    splits, hashes, seen = {}, {}, set()
    for name in ('train', 'val', 'test'):
        path = args.splits / f'{name}.csv'
        with path.open(newline='', encoding='utf-8') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != list(FIELDS):
                raise ValueError(f'Unexpected columns in {path}')
            rows = list(reader)
        for row in rows:
            pair = row['drug_id'], row['disease_id']
            if not all(pair) or pair in seen:
                raise ValueError(f'Missing or duplicate pair in source splits: {pair}')
            seen.add(pair)
        splits[name] = rows
        hashes[name] = sha256(path)
    graph = args.graph.resolve()
    offsets = np.load(graph / 'fwd_offsets.npy', mmap_mode='r', allow_pickle=False)
    targets = np.load(graph / 'fwd_targets.npy', mmap_mode='r', allow_pickle=False)
    print('Computing degrees after the planned edge removal (read-only)...', flush=True)
    drug, disease = node_masks(graph, len(offsets) - 1)
    degrees, removed = remaining_degrees(offsets, targets, drug, disease)
    ids = {curie for pair in seen for curie in pair}
    degrees_by_id = {}
    with lmdb.open(str(graph / 'node_store.lmdb'), readonly=True,
                   lock=False, max_dbs=3, readahead=False) as env:
        db = env.open_db(b'id_to_idx', create=False)
        with env.begin(db=db) as txn:
            for curie in sorted(ids):
                value = txn.get(curie.encode())
                if value is None:
                    raise ValueError(f'Split node missing from graph: {curie}')
                degrees_by_id[curie] = int(degrees[int.from_bytes(value, 'big')])
    retained, excluded, counts = {}, [], {}
    for name, rows in splits.items():
        kept, dropped = partition_rows(rows, degrees_by_id)
        retained[name] = kept
        excluded.extend(dict(row, split=name) for row in dropped)
        counts[name] = {'original': len(rows), 'retained': len(kept), 'excluded': len(dropped)}
    args.out.mkdir(parents=True, exist_ok=False)
    for name, rows in retained.items():
        write_csv(args.out / f'{name}.csv', FIELDS, rows)
        print(f'{name}: {len(rows):,} retained; {counts[name]["excluded"]:,} excluded')
    write_csv(args.out / 'excluded_pairs.csv', ('split', *FIELDS, 'reason'), excluded)
    report = {
        'graph': str(graph),
        'source_splits': str(args.splits.resolve()),
        'source_csv_sha256': hashes,
        'rule': 'Remove all drug/chemical--disease/phenotype edges in either direction, all predicates and sources; retain pairs only if both endpoint degrees remain positive.',
        'drug_categories': sorted(DRUG_CATEGORIES),
        'disease_categories': sorted(DISEASE_CATEGORIES),
        'original_nodes': len(drug),
        'original_edges': len(targets),
        'edges_to_remove': removed,
        'edges_to_retain': len(targets) - removed,
        'isolated_nodes_after_filtering': int((degrees == 0).sum()),
        'splits': counts,
        'retained_pairs': sum(len(rows) for rows in retained.values()),
        'excluded_pairs': len(excluded),
        'assignments_preserved': True,
        'graph_modified': False,
        'limitation': 'Positive endpoint degrees do not guarantee a connecting path.',
        'output_csv_sha256': {path.name: sha256(path) for path in sorted(args.out.glob('*.csv'))},
    }
    marker = graph / 'local-build-complete.json'
    if marker.exists():
        report['source_graph_build'] = json.loads(marker.read_text())
    with (args.out / 'filtering_report.json').open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(f'Saved {report["retained_pairs"]:,} retained pairs in {args.out}')


if __name__ == '__main__':
    main()
