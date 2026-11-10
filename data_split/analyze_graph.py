"""Print drug–disease edge frequencies from an existing Gandalf graph.

Run with the already-installed Gandalf Python environment, for example:
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python data_split/analyze_graph.py

Reads the node store and forward adjacency arrays only; never changes the graph.
Counts stored edges (including separate source records), not unique node pairs.
All predicates are included, not just treatment relationships. Categories are
matched against any node label, using the explicit sets below (no inference).
Only open trusted graph directories: Gandalf's metadata uses Python pickle.
"""

import argparse
from pathlib import Path
import pickle
import sys

import lmdb
import msgpack
import numpy as np


DEFAULT_GRAPH = (
    Path(__file__).resolve().parents[2]
    / "shepherd-new-pathfinder/.local/data/gandalf_1.0.4"
)
DRUG_CATEGORIES = {
    "biolink:Drug", "biolink:ChemicalEntity", "biolink:SmallMolecule",
    "biolink:MolecularMixture", "biolink:ChemicalMixture",
    "biolink:ComplexMolecularMixture",
}
DISEASE_CATEGORIES = {
    "biolink:Disease", "biolink:PhenotypicFeature",
    "biolink:DiseaseOrPhenotypicFeature",
}


def node_masks(graph, node_count):
    drug = np.zeros(node_count, dtype=bool)
    disease = np.zeros(node_count, dtype=bool)
    # lock=False also avoids modifying the LMDB lock file. The built graph
    # must remain immutable during analysis, as in the existing serving setup.
    with lmdb.open(str(graph / "node_store.lmdb"), readonly=True,
                   lock=False, max_dbs=3, readahead=False) as env:
        db = env.open_db(b"properties", create=False)
        with env.begin(db=db) as txn:
            for key, value in txn.cursor():
                idx = int.from_bytes(key, "big")
                categories = msgpack.unpackb(value, raw=False).get("categories", [])
                if isinstance(categories, str):
                    categories = [categories]
                drug[idx] = bool(DRUG_CATEGORIES.intersection(categories))
                disease[idx] = bool(DISEASE_CATEGORIES.intersection(categories))
    return drug, disease


def count_edges(offsets, targets, predicates, drug, disease, predicate_count):
    """Count each forward-array record once, retaining its original direction."""
    forward = np.zeros(predicate_count, dtype=np.int64)
    reverse = np.zeros(predicate_count, dtype=np.int64)
    for start in range(0, len(targets), 1_000_000):
        end = min(start + 1_000_000, len(targets))
        subjects = np.searchsorted(offsets, np.arange(start, end), side="right") - 1
        objects = targets[start:end]
        drug_to_disease = drug[subjects] & disease[objects]
        # If both endpoints belong to both groups, count once in the first column.
        disease_to_drug = disease[subjects] & drug[objects] & ~drug_to_disease
        edge_predicates = predicates[start:end]
        forward += np.bincount(edge_predicates[drug_to_disease], minlength=predicate_count)
        reverse += np.bincount(edge_predicates[disease_to_drug], minlength=predicate_count)
    return forward, reverse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH,
                        help="Existing, trusted Gandalf graph directory")
    args = parser.parse_args()
    graph = args.graph.resolve()
    with (graph / "metadata.pkl").open("rb") as stream:
        metadata = pickle.load(stream)
    print("Reading node categories...", file=sys.stderr, flush=True)
    drug, disease = node_masks(graph, metadata["num_nodes"])
    offsets, targets, predicates = (
        np.load(graph / f"fwd_{name}.npy", mmap_mode="r", allow_pickle=False)
        for name in ("offsets", "targets", "predicates")
    )
    predicate_ids = metadata["predicate_to_idx"]
    print(f"Scanning {len(targets):,} stored edges...", file=sys.stderr, flush=True)
    forward, reverse = count_edges(
        offsets, targets, predicates, drug, disease,
        max(predicate_ids.values(), default=-1) + 1,
    )
    total = int(forward.sum() + reverse.sum())
    print(f"Graph: {graph}")
    print("Drug categories: " + ", ".join(sorted(DRUG_CATEGORIES)))
    print("Disease categories: " + ", ".join(sorted(DISEASE_CATEGORIES)))
    print(f"Matching nodes: {drug.sum():,} drug/chemical; {disease.sum():,} disease/phenotype")
    print("Stored edges, all predicates; separate source records are not deduplicated.")
    print("Nodes matching both groups: " + str(int((drug & disease).sum())))
    rows = []
    for predicate, idx in predicate_ids.items():
        count = int(forward[idx] + reverse[idx])
        if count:
            rows.append((predicate, int(forward[idx]), int(reverse[idx]), count))
    rows.sort(key=lambda row: (-row[3], row[0]))
    width = max([len("Predicate")] + [len(row[0]) for row in rows])
    print(f"\n{'Predicate':<{width}}  {'Drug -> Disease':>15}  {'Disease -> Drug':>15}  {'Total':>12}  {'Percent':>8}")
    print("-" * (width + 60))
    for predicate, fwd, rev, count in rows:
        print(f"{predicate:<{width}}  {fwd:>15,}  {rev:>15,}  {count:>12,}  {100 * count / total:>7.2f}%")
    print(f"{'TOTAL':<{width}}  {int(forward.sum()):>15,}  {int(reverse.sum()):>15,}  {total:>12,}")


if __name__ == "__main__":
    main()
