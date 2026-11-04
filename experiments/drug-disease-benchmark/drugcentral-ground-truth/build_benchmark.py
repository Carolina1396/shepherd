"""Build and audit an 80/10/10 DrugCentral approved-indication benchmark.

All original direct chemical-condition edges are removed. Only canonical
DrugCentral approved training treats edges are added back. Other edges and all
nodes are preserved byte-for-byte. Uses only the Python standard library.
"""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import time


CHEMICAL = "biolink:ChemicalEntity"
CONDITION = "biolink:DiseaseOrPhenotypicFeature"
TREATS = "biolink:treats"
SOURCE = "infores:drugcentral"
APPROVED = "approved_for_condition"
SUBJECT = re.compile(rb'"subject"\s*:\s*"([^"\\]*)"')
OBJECT = re.compile(rb'"object"\s*:\s*"([^"\\]*)"')


def endpoints(line):
    subject, obj = SUBJECT.search(line), OBJECT.search(line)
    if subject and obj:
        return subject[1].decode(), obj[1].decode()
    edge = json.loads(line)
    return edge["subject"], edge["object"]


def normalized_pair(subject, obj, drugs, conditions):
    if subject in drugs and obj in conditions:
        return subject, obj
    if obj in drugs and subject in conditions:
        return obj, subject
    return None


def primary_source(edge):
    return next((s.get("resource_id") for s in edge.get("sources") or []
                 if s.get("resource_role") == "primary_knowledge_source"),
                edge.get("primary_knowledge_source"))


def split_pairs(pairs, seed):
    # Hash ranking is stable across input order and Python versions.
    pairs = set(pairs)
    ordered = sorted(pairs, key=lambda p: (hashlib.sha256(
        json.dumps([seed, *p], ensure_ascii=True).encode()).digest(), p))
    heldout_size = len(ordered) // 10
    train_size = len(ordered) - 2 * heldout_size
    result = {"train": set(ordered[:train_size]),
              "validation": set(ordered[train_size:train_size + heldout_size]),
              "test": set(ordered[train_size + heldout_size:])}
    if (result["train"] & result["test"] or result["train"] & result["validation"]
            or result["test"] & result["validation"]):
        raise ValueError("Overlapping split assignments")
    if set.union(*result.values()) != set(pairs):
        raise ValueError("Split does not cover the positive set")
    return result


def canonical_edge(pair):
    drug, condition = pair
    identifier = hashlib.sha256(json.dumps(list(pair)).encode()).hexdigest()
    return {"id": "drugcentral-benchmark:" + identifier,
            "subject": drug, "predicate": TREATS, "object": condition,
            "clinical_approval_status": APPROVED,
            "sources": [{"resource_id": SOURCE, "resource_role": "primary_knowledge_source"}]}


def audit_graph(path, splits, drugs, conditions):
    """Independently reread the saved graph, checking ALL predicates and directions."""
    heldout = splits["validation"] | splits["test"]
    heldout_unordered = {frozenset(p) for p in heldout}
    seen = set()
    relevant_nodes = {node for part in splits.values() for pair in part for node in pair}
    connected = set()
    edge_count = 0
    digest = hashlib.sha256()
    last_update = time.monotonic()
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            edge_count += 1
            subject, obj = endpoints(line)
            if frozenset((subject, obj)) in heldout_unordered:
                raise ValueError(f"Held-out pair leaked into saved training graph: {subject}, {obj}")
            if subject in relevant_nodes:
                connected.add(subject)
            if obj in relevant_nodes:
                connected.add(obj)
            pair = normalized_pair(subject, obj, drugs, conditions)
            if pair is not None:
                edge = json.loads(line)
                if (pair not in splits["train"] or pair in seen
                        or edge != canonical_edge(pair)):
                    raise ValueError(f"Unexpected or duplicate direct drug-condition edge: {pair}")
                seen.add(pair)
            if time.monotonic() - last_update > 30:
                print(f"Audit: {edge_count:,} saved edges checked", flush=True)
                last_update = time.monotonic()
    if seen != splits["train"]:
        raise ValueError("Saved training graph is missing training pairs")
    return {"passed": True, "edges_checked": edge_count,
            "direct_drug_condition_edges": len(seen),
            "validation_pairs_in_training_graph": 0, "test_pairs_in_training_graph": 0,
            "train_validation_pair_overlap": 0, "train_test_pair_overlap": 0,
            "validation_test_pair_overlap": 0, "edges_sha256": digest.hexdigest(),
            "heldout_pairs_with_isolated_endpoint": {
                name: sum(any(node not in connected for node in p) for p in splits[name])
                for name in ("validation", "test")}}


def build(raw, out, seed):
    # Refuse overwrite: a failed/incomplete build remains inspectable.
    out.mkdir(parents=True, exist_ok=False)
    graph = out / "graph"
    graph.mkdir()
    labels = out / "labels"
    labels.mkdir()
    drugs, conditions = set(), set()
    nodes_hash = hashlib.sha256()
    nodes_count = 0
    print("Copying nodes and loading chemical/condition categories...", flush=True)
    with (raw / "nodes.jsonl").open("rb") as source, (graph / "nodes.jsonl").open("wb") as target:
        for line in source:
            nodes_hash.update(line)
            target.write(line)
            nodes_count += 1
            if b"biolink:ChemicalEntity" not in line and b"biolink:DiseaseOrPhenotypicFeature" not in line:
                continue
            node = json.loads(line)
            categories = node.get("category") or []
            if CHEMICAL in categories:
                drugs.add(node["id"])
            if CONDITION in categories:
                conditions.add(node["id"])
    print("Removing original drug-condition edges and collecting approved positives...", flush=True)
    positives = {}
    raw_edges_hash = hashlib.sha256()
    input_count = removed_count = 0
    last_update = time.monotonic()
    with (raw / "edges.jsonl").open("rb") as source, (graph / "edges.jsonl").open("wb") as target:
        for line in source:
            raw_edges_hash.update(line)
            input_count += 1
            subject, obj = endpoints(line)
            pair = normalized_pair(subject, obj, drugs, conditions)
            if pair is None:
                target.write(line)
            else:
                removed_count += 1
                if b"drugcentral" in line and b"approved_for_condition" in line:
                    edge = json.loads(line)
                    if (edge.get("predicate") == TREATS and primary_source(edge) == SOURCE
                            and edge.get("clinical_approval_status") == APPROVED):
                        positives.setdefault(pair, []).append(edge)
            if time.monotonic() - last_update > 30:
                print(f"Build: {input_count:,} input edges; {removed_count:,} removed", flush=True)
                last_update = time.monotonic()
        if not positives:
            raise ValueError("No approved DrugCentral positives found")
        splits = split_pairs(positives, seed)
        for pair in sorted(splits["train"]):
            target.write((json.dumps(canonical_edge(pair), sort_keys=True) + "\n").encode())
    print("Split sizes:", {name: len(pairs) for name, pairs in splits.items()}, flush=True)
    label_hashes = {}
    for name, pairs in splits.items():
        path = labels / f"{name}.csv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["drug_id", "condition_id"])
            writer.writerows(sorted(pairs))
        label_hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    with (labels / "positive_evidence.jsonl").open("w") as handle:
        for pair in sorted(positives):
            handle.write(json.dumps({"drug_id": pair[0], "condition_id": pair[1],
                                     "source_edges": positives[pair]}, sort_keys=True) + "\n")
    print("Independently auditing the saved training graph...", flush=True)
    audit = audit_graph(graph / "edges.jsonl", splits, drugs, conditions)
    expected_edges = input_count - removed_count + len(splits["train"])
    if audit["edges_checked"] != expected_edges:
        raise ValueError("Output edge count does not reconcile")
    manifest = {
        "seed": seed, "split_method": "SHA-256 ranking of JSON [seed, drug_id, condition_id]",
        "split_proportions": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "rounding": "floor 10% each for validation/test; remainder to train",
        "raw_directory": str(raw.resolve()),
        "input_sha256": {"nodes.jsonl": nodes_hash.hexdigest(), "edges.jsonl": raw_edges_hash.hexdigest()},
        "output_sha256": {"graph/nodes.jsonl": nodes_hash.hexdigest(),
                          "graph/edges.jsonl": audit["edges_sha256"],
                          **{f"labels/{k}": v for k, v in label_hashes.items()}},
        "nodes": nodes_count, "input_edges": input_count,
        "removed_direct_drug_condition_edges": removed_count,
        "output_edges": expected_edges, "approved_pairs": len(positives),
        "split_pairs": {name: len(pairs) for name, pairs in splits.items()},
        "policy": "Remove all direct ChemicalEntity-DiseaseOrPhenotypicFeature edges in both directions; add one approved DrugCentral treats edge per training pair",
        "scope": "Existing normalized Tier 0 IDs; source-asserted approval; no independent clinical adjudication or additional alias/hierarchy expansion",
        "evaluation": "Use graph/ for every system; labels/ contains evaluation answers and must not be ingested into the training graph",
        "leakage_audit": audit,
    }
    # Manifest is written only after the independent saved-graph audit passes.
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="Pinned Tier 0 directory with nodes.jsonl and edges.jsonl")
    parser.add_argument("--out", type=Path, required=True, help="New output directory; must not exist")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    build(args.raw, args.out, args.seed)


if __name__ == "__main__":
    main()
