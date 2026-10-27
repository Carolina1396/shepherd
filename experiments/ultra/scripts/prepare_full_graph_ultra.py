"""Prepare the agreed Drug-only pair split on the full native Gandalf graph."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import subprocess
import time

import numpy as np
from gandalf import CSRGraph
from full_graph_common import digest, evaluation_edge_mask, save, split_pairs

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/full-graph-ultra/run_001")
    parser.add_argument("--masking", choices=("all-direct", "treats-only", "treats-only-all-splits", "all-direct-no-visible-treats"), default="all-direct",
                        help="Masking rule; all-direct-no-visible-treats removes all hidden pair edges and only visible target treats")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"Refusing to overwrite {output}")
    started = time.perf_counter()
    graph = CSRGraph.load_mmap(ROOT / "output/gandalf/full-store", mmap_mode="r")
    drug = np.zeros(graph.num_nodes, dtype=bool)
    disease = drug.copy()
    for idx, props in graph.node_store.iter_properties():
        categories = props.get("categories", [])
        drug[idx] = "biolink:Drug" in categories
        disease[idx] = "biolink:Disease" in categories
    candidates = np.flatnonzero(drug)
    assert len(candidates) == 5326
    candidate_rows = [{"index": int(i), "id": graph.get_node_id(int(i)),
                       "name": graph.get_node_property(int(i), "name", "")} for i in candidates]
    predicates = [graph.id_to_predicate[i] for i in range(len(graph.predicate_to_idx))]
    target = predicates.index("biolink:treats")
    positions = np.flatnonzero(graph.fwd_predicates == target)
    heads = np.searchsorted(graph.fwd_offsets, positions, side="right") - 1
    tails = graph.fwd_targets[positions]
    eligible = drug[heads] & disease[tails]
    pairs = {(graph.get_node_id(int(h)), graph.get_node_id(int(t)))
             for h, t in zip(heads[eligible], tails[eligible])}
    inventory = ROOT / "output/treatment_pairs/pairs.csv"
    with inventory.open() as stream:
        reference = {(row["chemical_id"], row["disease_id"]) for row in csv.DictReader(stream)
                     if row["subject_is_drug"] == "1" and "biolink:treats" in json.loads(row["predicates"])}
    assert pairs == reference and len(pairs) == 18079
    labels = [{"drug": h, "disease": t, "drug_index": int(graph.get_node_idx(h)),
               "disease_index": int(graph.get_node_idx(t)), "split": split}
              for h, t, split in split_pairs(pairs)]
    counts = dict(Counter(row["split"] for row in labels))
    assert counts == {"visible": 14463, "validation": 1807, "test": 1809}
    hidden = {(row["drug_index"], row["disease_index"]) for row in labels if row["split"] != "visible"}
    visible = {(row["drug_index"], row["disease_index"]) for row in labels if row["split"] == "visible"}
    remove_visible_treats = args.masking in ("treats-only-all-splits", "all-direct-no-visible-treats")
    print(f"Verified {len(labels):,} target pairs; split {counts}", flush=True)

    n, p = graph.num_nodes, len(predicates)
    sources = np.repeat(np.arange(n, dtype=np.int64), np.diff(graph.fwd_offsets))
    encoded = (sources * p + graph.fwd_predicates) * n + graph.fwd_targets
    del sources
    unique = np.unique(encoded)
    del encoded
    assert len(unique) == 27927289
    heads, rels, tails = unique // (n * p), (unique // n) % p, unique % n
    raw_count = len(unique)
    del unique
    remove = evaluation_edge_mask(heads, rels, tails, hidden, visible, n, target, args.masking)
    removed_predicates = dict(Counter(predicates[int(r)] for r in rels[remove]))
    triples = np.column_stack([heads[~remove], rels[~remove], tails[~remove]])
    print(f"Masked {int(remove.sum()):,} direct connections; {len(triples):,} remain", flush=True)
    assert not evaluation_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2],
                                   hidden, visible, n, target, args.masking).any()
    actual = {(int(h), int(t)) for h, r, t in triples[triples[:, 1] == target]
              if drug[h] and disease[t]}
    expected = set() if remove_visible_treats else visible
    assert actual == expected
    degree = np.bincount(triples[triples[:, 1] == target, 0], minlength=n)[candidates]
    active = np.zeros(n, dtype=bool)
    active[triples[:, 0]] = True
    active[triples[:, 2]] = True
    visible_diseases = {row["disease"] for row in labels if row["split"] == "visible"}
    if remove_visible_treats:
        visible_diseases = set()
    for row in labels:
        row["disease_has_visible_treatment"] = row["disease"] in visible_diseases
        row["drug_isolated"] = not bool(active[row["drug_index"]])
        row["disease_isolated"] = not bool(active[row["disease_index"]])
    validation = [row for row in labels if row["split"] == "validation"]
    assert len({r["disease"] for r in validation}) == 986
    unsupported_validation = sum(not r["disease_has_visible_treatment"] for r in validation)
    assert unsupported_validation == (1807 if remove_visible_treats else 184)
    data = output / "data"
    data.mkdir(parents=True)
    np.save(data / "triples.npy", triples)
    np.save(data / "candidate_degree.npy", degree)
    save(data / "candidates.json", candidate_rows)
    save(data / "predicates.json", predicates)
    save(data / "labels.json", labels)
    checkpoint = ROOT / "vendor/ULTRA/ckpts/ultra_4g.pth"
    masking_description = {
        "all-direct": "all direct held-out pair connections removed in both directions; visible pairs unchanged",
        "treats-only": "only biolink:treats connections of held-out pairs removed in both directions; other direct predicates retained; visible pairs unchanged",
        "treats-only-all-splits": "only biolink:treats connections of visible, validation, and test target pairs removed in both directions; other direct predicates and treats outside the target pairs retained",
        "all-direct-no-visible-treats": "all direct validation/test pair connections and only biolink:treats connections of visible target pairs removed in both directions; visible non-treats connections and treats outside target pairs retained",
    }[args.masking]
    config = {"num_nodes": n, "num_relations": p, "target_predicate": "biolink:treats",
              "masking": args.masking,
              "candidate_category": "biolink:Drug", "disease_category": "biolink:Disease",
              "split_seed": 731, "pair_splits": counts, "training_epochs": 0,
              "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": digest(checkpoint),
              "ultra_commit": subprocess.check_output(["git", "-C", str(ROOT / "vendor/ULTRA"), "rev-parse", "HEAD"], text=True).strip(),
              "protocol": f"Global disjoint Drug-Disease treats pair split; full graph context with {masking_description}; fixed Drug-only candidates; filtered pessimistic head ranks"}
    save(output / "config.json", config)
    manifest = {"masking": args.masking,
                "nodes": n, "candidate_drugs": len(candidates), "diseases": len({r["disease"] for r in labels}),
                "stored_records": len(graph.fwd_targets), "original_unique_connections": raw_count,
                "model_connections_before_inverses": len(triples), "removed_connections": int(remove.sum()),
                "removed_connections_by_predicate": removed_predicates, "pair_splits": counts,
                "remaining_treats_connections": int(np.count_nonzero(triples[:, 1] == target)),
                "visible_target_treats_removed": remove_visible_treats,
                "isolated_nodes_after_mask": int((~active).sum()),
                "isolated_candidate_drugs": int((~active[candidates]).sum()),
                "validation_isolated_drug_pairs": sum(r["drug_isolated"] for r in validation),
                "validation_isolated_disease_pairs": sum(r["disease_isolated"] for r in validation),
                "validation_diseases": 986, "validation_pairs_without_visible_treatment_for_disease": unsupported_validation,
                "source_inventory_sha256": digest(inventory), "config_sha256": digest(output / "config.json"),
                "dataset_sha256": {f.name: digest(f) for f in sorted(data.iterdir())},
                "checks": ["source inventory equals full Gandalf target pairs", "exact disjoint global split",
                           "visible target treats removed" if remove_visible_treats else "visible targets retained", masking_description],
                "limitations": ["Graph assertions are not clinically adjudicated treatments",
                                "Indirect clues through equivalent or related entities may remain",
                                "Previously explored pairs may occur in this broader exploratory split"],
                "preparation_seconds": time.perf_counter() - started}
    if args.masking in ("treats-only", "treats-only-all-splits"):
        manifest["limitations"].append("Other direct held-out pair predicates, including treatment-related assertions, remain visible by design")
    if remove_visible_treats:
        manifest["limitations"].append("Treats edges outside the 18,079 target pairs remain; this is not global predicate removal")
    for name in ("prepare_full_graph_ultra.py", "full_graph_common.py"):
        shutil.copyfile(Path(__file__).parent / name, output / name)
    save(output / "preparation.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
