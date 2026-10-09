"""Create a masked ULTRA dataset from the fixed union of native Gandalf walks."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import re
import shutil

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TARGET = "biolink:treats"
CATEGORIES = {"biolink:Drug", "biolink:SmallMolecule", "biolink:ChemicalEntity"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def split_pairs(pairs, visible_fraction, seed):
    """Round visible counts per disease; split the remainder, odd pair to test."""
    if not 0 < visible_fraction < 1:
        raise ValueError("visible_fraction must lie strictly between 0 and 1")
    if len(pairs) != len(set(pairs)):
        raise ValueError("Treatment pairs must be unique")
    grouped = defaultdict(list)
    for chemical, disease in pairs:
        grouped[disease].append(chemical)
    rng = random.Random(seed)
    labels = []
    for disease in sorted(grouped):
        chemicals = sorted(grouped[disease])
        rng.shuffle(chemicals)
        visible = max(1, int(len(chemicals) * visible_fraction + 0.5))
        validation = (len(chemicals) - visible) // 2
        for i, chemical in enumerate(chemicals):
            split = "visible" if i < visible else "validation" if i < visible + validation else "test"
            labels.append({"chemical": chemical, "disease": disease, "split": split})
    return sorted(labels, key=lambda r: (r["disease"], r["chemical"]))


def mask_hidden_pairs(triples, hidden_pairs):
    """Remove every predicate in both directions for each held-out pair."""
    hidden = {tuple(sorted(pair)) for pair in hidden_pairs}
    return np.array([tuple(sorted((int(h), int(t)))) not in hidden for h, _, t in triples], dtype=bool)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", default="disease_001")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--visible-fraction", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=731)
    args = parser.parse_args()
    for value in (args.source_run, args.run_id):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
            parser.error("Run IDs must contain only letters, digits, underscores or hyphens")
    if not 0 < args.visible_fraction < 1:
        parser.error("visible-fraction must lie strictly between 0 and 1")
    source = HERE / "results" / args.source_run
    destination = source / args.run_id
    if destination.exists():
        parser.error(f"Refusing to overwrite {destination}")
    sampling = json.loads((source / "summary.json").read_text())
    for name, expected in sampling["output_sha256"].items():
        assert digest(source / name) == expected, name
    recovery = json.loads((source / "recovery/summary.json").read_text())
    assert recovery["source_run_summary_sha256"] == digest(source / "summary.json")
    for name, expected in recovery["output_sha256"].items():
        assert digest(source / "recovery" / name) == expected, name

    nodes = json.loads((source / "nodes.json").read_text())
    local = {node["gandalf_id"]: i for i, node in enumerate(nodes)}
    curies = {node["id"]: i for i, node in enumerate(nodes)}
    predicates_by_id = {int(k): v for k, v in json.loads((source / "predicates.json").read_text()).items()}
    connections = set()
    for disease in sampling["per_disease"]:
        with (source / disease["walks_file"]).open() as stream:
            for line in stream:
                walk = json.loads(line)
                if walk["nodes"] is not None:
                    connections.update((local[walk["nodes"][h]], predicates_by_id[p], local[walk["nodes"][t]])
                                       for h, p, t in walk["edges"])
    assert len(connections) == sampling["distinct_directed_connections"]
    candidates = [i for i, node in enumerate(nodes) if CATEGORIES.intersection(node["categories"])]
    assert len(candidates) == sampling["distinct_chemicals_or_drugs"]
    with (source / "recovery/pairs.csv").open() as stream:
        known = {(row["chemical"], row["disease"]) for row in csv.DictReader(stream)
                 if row["known_explicit_treats"] == "True"}
    targets = {(nodes[h]["id"], nodes[t]["id"]) for h, p, t in connections
               if p == TARGET and (nodes[h]["id"], nodes[t]["id"]) in known}
    labels = split_pairs(targets, args.visible_fraction, args.seed)
    candidate_set = set(candidates)
    assert all(curies[row["chemical"]] in candidate_set for row in labels)
    predicates = sorted({p for _, p, _ in connections})
    relation = {p: i for i, p in enumerate(predicates)}
    raw = np.array(sorted((h, relation[p], t) for h, p, t in connections), dtype=np.int64)
    hidden = {(curies[row["chemical"]], curies[row["disease"]]) for row in labels if row["split"] != "visible"}
    keep = mask_hidden_pairs(raw, hidden)
    triples = raw[keep]
    visible = {(curies[row["chemical"]], curies[row["disease"]]) for row in labels if row["split"] == "visible"}
    cohort_ids = {curies[d["disease"]] for d in sampling["per_disease"]}
    actual = {(int(h), int(t)) for h, p, t in triples if p == relation[TARGET] and t in cohort_ids and h in candidate_set}
    assert actual == visible
    assert mask_hidden_pairs(triples, hidden).all()
    assert len(triples) == len(np.unique(triples, axis=0))
    counts = dict(Counter(row["split"] for row in labels))
    if not counts.get("validation") or not counts.get("test"):
        parser.error("This split leaves no validation or test pairs; choose another visible fraction")
    dataset = destination / "data"
    dataset.mkdir(parents=True)
    shutil.copyfile(source / "nodes.json", dataset / "nodes.json")
    save(dataset / "predicates.json", predicates)
    save(dataset / "candidates.json", candidates)
    save(dataset / "labels.json", labels)
    save(dataset / "known_pairs.json", [{"chemical": h, "disease": t} for h, t in sorted(known)])
    np.save(dataset / "triples.npy", triples)
    config = {
        "source_run": args.source_run, "run_id": args.run_id,
        "target_predicate": TARGET, "visible_fraction_requested": args.visible_fraction,
        "split_seed": args.seed, "default_evaluation_split": "validation",
        "training_epochs": 0, "checkpoint": "ultra_4g.pth",
        "checkpoint_sha256": digest(ROOT / "vendor/ULTRA/ckpts/ultra_4g.pth"),
        "candidate_categories": sorted(CATEGORIES),
        "evaluation_scope": "Exploratory link ranking within a fixed graph sampled before label masking; not an end-to-end held-out benchmark",
    }
    save(destination / "config.json", config)
    per_disease = []
    for disease in sampling["per_disease"]:
        split_counts = Counter(row["split"] for row in labels if row["disease"] == disease["disease"])
        per_disease.append({"disease": disease["disease"], "name": disease["name"],
                            "sampled_treatment_pairs": sum(split_counts.values()),
                            **{split: split_counts[split] for split in ("visible", "validation", "test")}})
    active_nodes = set(map(int, triples[:, 0])) | set(map(int, triples[:, 2]))
    manifest = {
        "source_summary_sha256": digest(source / "summary.json"),
        "reference_pairs": len(known),
        "reference_pairs_with_endpoints_in_union": sum(h in curies and t in curies for h, t in known),
        "split_population": "Explicit treats connections in the sampled union for the selected diseases and eligible chemicals",
        "split_pairs": len(labels), "pair_splits": counts,
        "split_rounding": "Per disease: round visible fraction to nearest integer (half up), minimum one visible; halve remainder, odd pair to test",
        "nodes": len(nodes), "candidates": len(candidates), "predicates": len(predicates),
        "original_connections": len(raw), "model_connections": len(triples),
        "connections_removed": int((~keep).sum()),
        "removed_connections_by_predicate": dict(Counter(predicates[int(p)] for p in raw[~keep, 1])),
        "remaining_treats_connections": int(np.count_nonzero(triples[:, 1] == relation[TARGET])),
        "isolated_nodes_after_mask": len(nodes) - len(active_nodes),
        "isolated_candidates_after_mask": len(candidate_set - active_nodes),
        "per_disease": per_disease,
        "checks": ["source file hashes", "unique pair splits", "fixed sampled nodes and candidates",
                   "every visible target edge retained", "all direct hidden-pair edges removed in both directions",
                   "unique triples", "all validation/test candidates present"],
        "limitations": ["Sampling saw treatment edges before splitting", "The same cohort was explored in earlier experiments",
                        "Pair masking does not remove indirect clues through related or equivalent entities"],
        "dataset_sha256": {path.name: digest(path) for path in sorted(dataset.iterdir())},
    }
    save(destination / "preparation.json", manifest)
    shutil.copyfile(Path(__file__), destination / "prepare_ultra.py")
    print(json.dumps({k: manifest[k] for k in ("split_pairs", "pair_splits", "nodes", "candidates",
                                              "original_connections", "model_connections", "connections_removed")}, indent=2))
    print(destination)


if __name__ == "__main__":
    main()
