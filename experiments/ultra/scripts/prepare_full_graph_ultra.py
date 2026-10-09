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
from full_graph_common import digest, hidden_pair_mask, save, split_pairs

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/full-graph-ultra/run_001")
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
    remove = hidden_pair_mask(heads, tails, hidden, n)
    removed_predicates = dict(Counter(predicates[int(r)] for r in rels[remove]))
    triples = np.column_stack([heads[~remove], rels[~remove], tails[~remove]])
    print(f"Masked {int(remove.sum()):,} direct connections; {len(triples):,} remain", flush=True)
    assert not hidden_pair_mask(triples[:, 0], triples[:, 2], hidden, n).any()
    actual = {(int(h), int(t)) for h, r, t in triples[triples[:, 1] == target]
              if drug[h] and disease[t]}
    expected = {(row["drug_index"], row["disease_index"]) for row in labels if row["split"] == "visible"}
    assert actual == expected
    degree = np.bincount(triples[triples[:, 1] == target, 0], minlength=n)[candidates]
    active = np.zeros(n, dtype=bool)
    active[triples[:, 0]] = True
    active[triples[:, 2]] = True
    visible_diseases = {row["disease"] for row in labels if row["split"] == "visible"}
    for row in labels:
        row["disease_has_visible_treatment"] = row["disease"] in visible_diseases
        row["drug_isolated"] = not bool(active[row["drug_index"]])
        row["disease_isolated"] = not bool(active[row["disease_index"]])
    validation = [row for row in labels if row["split"] == "validation"]
    assert len({r["disease"] for r in validation}) == 986
    assert sum(not r["disease_has_visible_treatment"] for r in validation) == 184
    data = output / "data"
    data.mkdir(parents=True)
    np.save(data / "triples.npy", triples)
    np.save(data / "candidate_degree.npy", degree)
    save(data / "candidates.json", candidate_rows)
    save(data / "predicates.json", predicates)
    save(data / "labels.json", labels)
    checkpoint = ROOT / "vendor/ULTRA/ckpts/ultra_4g.pth"
    config = {"num_nodes": n, "num_relations": p, "target_predicate": "biolink:treats",
              "candidate_category": "biolink:Drug", "disease_category": "biolink:Disease",
              "split_seed": 731, "pair_splits": counts, "training_epochs": 0,
              "checkpoint": str(checkpoint.relative_to(ROOT)), "checkpoint_sha256": digest(checkpoint),
              "ultra_commit": subprocess.check_output(["git", "-C", str(ROOT / "vendor/ULTRA"), "rev-parse", "HEAD"], text=True).strip(),
              "protocol": "Global disjoint Drug-Disease treats pair split; full graph context with all direct held-out pair connections removed in both directions; fixed Drug-only candidates; filtered pessimistic head ranks"}
    save(output / "config.json", config)
    manifest = {"nodes": n, "candidate_drugs": len(candidates), "diseases": len({r["disease"] for r in labels}),
                "stored_records": len(graph.fwd_targets), "original_unique_connections": raw_count,
                "model_connections_before_inverses": len(triples), "removed_connections": int(remove.sum()),
                "removed_connections_by_predicate": removed_predicates, "pair_splits": counts,
                "isolated_nodes_after_mask": int((~active).sum()),
                "isolated_candidate_drugs": int((~active[candidates]).sum()),
                "validation_isolated_drug_pairs": sum(r["drug_isolated"] for r in validation),
                "validation_isolated_disease_pairs": sum(r["disease_isolated"] for r in validation),
                "validation_diseases": 986, "validation_pairs_without_visible_treatment_for_disease": 184,
                "source_inventory_sha256": digest(inventory), "config_sha256": digest(output / "config.json"),
                "dataset_sha256": {f.name: digest(f) for f in sorted(data.iterdir())},
                "checks": ["source inventory equals full Gandalf target pairs", "exact disjoint global split",
                           "visible targets retained", "all direct held-out pair predicates and directions absent"],
                "limitations": ["Graph assertions are not clinically adjudicated treatments",
                                "Indirect clues through equivalent or related entities may remain",
                                "Previously explored pairs may occur in this broader exploratory split"],
                "preparation_seconds": time.perf_counter() - started}
    for name in ("prepare_full_graph_ultra.py", "full_graph_common.py"):
        shutil.copyfile(Path(__file__).parent / name, output / name)
    save(output / "preparation.json", manifest)
    print(json.dumps(manifest, indent=2), flush=True)


if __name__ == "__main__":
    main()
