"""Audit the full Gandalf graph and explicit treatment pairs without changing it."""

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import random
import time

import numpy as np
from gandalf import CSRGraph

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = {"biolink:Drug", "biolink:SmallMolecule", "biolink:ChemicalEntity"}


def main():
    started = time.perf_counter()
    output = ROOT / "output/full-graph-ultra-inspection"
    if output.exists():
        raise FileExistsError(output)
    graph = CSRGraph.load_mmap(ROOT / "output/gandalf/full-store", mmap_mode="r")
    chemical = np.zeros(graph.num_nodes, dtype=bool)
    drug = chemical.copy()
    disease = chemical.copy()
    for idx, props in graph.node_store.iter_properties():
        categories = set(props.get("categories", []))
        chemical[idx] = bool(categories & CATEGORIES)
        drug[idx] = "biolink:Drug" in categories
        disease[idx] = "biolink:Disease" in categories
    print("Counted connected node categories", flush=True)
    positions = np.flatnonzero(graph.fwd_predicates == graph.predicate_to_idx["biolink:treats"])
    heads = np.searchsorted(graph.fwd_offsets, positions, side="right") - 1
    tails = graph.fwd_targets[positions]
    eligible = chemical[heads] & disease[tails]
    encoded = heads.astype(np.int64) * graph.num_nodes + tails
    broad_pairs = set(map(int, np.unique(encoded[eligible])))
    drug_pairs = set(map(int, np.unique(encoded[eligible & drug[heads]])))

    inventory = ROOT / "output/treatment_pairs/pairs.csv"
    reference = set()
    overlap_predicates = Counter()
    with inventory.open() as stream:
        for row in csv.DictReader(stream):
            predicates = json.loads(row["predicates"])
            if "biolink:treats" not in predicates:
                continue
            h = graph.get_node_idx(row["chemical_id"])
            t = graph.get_node_idx(row["disease_id"])
            assert h is not None and t is not None
            reference.add(h * graph.num_nodes + t)
            overlap_predicates.update(p for p in predicates if p != "biolink:treats")
    assert broad_pairs == reference

    populations = {}
    per_disease = []
    for name, pairs in (("chemical_or_drug", broad_pairs), ("drug_only", drug_pairs)):
        degrees = Counter(p % graph.num_nodes for p in pairs)
        # Preview exact global 80/10/10 allocation; these are not finalized labels.
        ordered = sorted((graph.get_node_id(p // graph.num_nodes),
                          graph.get_node_id(p % graph.num_nodes)) for p in pairs)
        random.Random(731).shuffle(ordered)
        n_visible, n_validation = int(0.8 * len(ordered)), int(0.1 * len(ordered))
        visible_diseases = {t for _, t in ordered[:n_visible]}
        valid = ordered[n_visible:n_visible + n_validation]
        test = ordered[n_visible + n_validation:]
        populations[name] = {
            "pairs": len(pairs), "distinct_treatment_subjects": len({p // graph.num_nodes for p in pairs}),
            "diseases": len(degrees), "diseases_with_one_pair": sum(n == 1 for n in degrees.values()),
            "diseases_with_two_pairs": sum(n == 2 for n in degrees.values()),
            "largest_disease_pair_count": max(degrees.values()),
            "global_split_preview_seed": 731,
            "global_split_preview_counts": {"visible": n_visible, "validation": n_validation,
                                             "test": len(test)},
            "validation_diseases": len({t for _, t in valid}),
            "test_diseases": len({t for _, t in test}),
            "validation_pairs_without_visible_treatment_for_disease": sum(t not in visible_diseases for _, t in valid),
            "test_pairs_without_visible_treatment_for_disease": sum(t not in visible_diseases for _, t in test),
        }
        for idx, count in sorted(degrees.items()):
            per_disease.append({"population": name, "disease": graph.get_node_id(idx),
                                "name": graph.get_node_property(idx, "name", ""), "treatment_pairs": count})
    print("Verified all eligible treats pairs against the independent source inventory", flush=True)
    # Count unique triples to distinguish evidence records from model connections.
    sources = np.repeat(np.arange(graph.num_nodes, dtype=np.int64), np.diff(graph.fwd_offsets))
    keys = (sources * len(graph.predicate_to_idx) + graph.fwd_predicates) * graph.num_nodes + graph.fwd_targets
    unique_connections = len(np.unique(keys))
    with inventory.open("rb") as stream:
        source_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {
        "connected_nodes": graph.num_nodes, "stored_edge_records": len(graph.fwd_targets),
        "unique_directed_triples_before_masking": unique_connections,
        "predicates": len(graph.predicate_to_idx),
        "connected_candidate_chemicals_or_drugs": int(chemical.sum()),
        "connected_candidate_drugs": int(drug.sum()), "connected_disease_nodes": int(disease.sum()),
        "treats_records_all_endpoint_types": len(positions),
        "eligible_treats_records": int(eligible.sum()),
        "eligible_treats_pairs_match_source_inventory": True,
        "populations": populations,
        "eligible_treats_pairs_with_other_treatment_predicates": dict(overlap_predicates),
        "source_inventory_sha256": source_hash,
        "split_status": "Global allocation preview only; no evaluation dataset or scores created",
        "elapsed_seconds": time.perf_counter() - started,
    }
    output.mkdir()
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    with (output / "per_disease.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(per_disease[0]))
        writer.writeheader()
        writer.writerows(per_disease)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
