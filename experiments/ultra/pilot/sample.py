"""Sample walks from a fixed disease cohort using Gandalf's GraphSampler."""

import argparse
from collections import Counter
import csv
import hashlib
from itertools import combinations
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GANDALF = ROOT / "vendor/gandalf"
CHEMICAL_CATEGORIES = {"biolink:Drug", "biolink:SmallMolecule", "biolink:ChemicalEntity"}


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="New output directory name")
    parser.add_argument("--attempts-per-disease", type=positive, default=1000)
    parser.add_argument("--length", type=positive, default=3)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--graph", type=Path, default=ROOT / "output/gandalf/full-store")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.run_id):
        parser.error("run-id must contain only letters, digits, underscores or hyphens")
    output = HERE / "results" / args.run_id
    if output.exists():
        parser.error(f"Refusing to overwrite {output}; choose a new run-id")
    if not args.graph.is_dir():
        parser.error(f"Graph store not found: {args.graph}")
    cohort_path = HERE / "cohort.json"
    cohort = json.loads(cohort_path.read_text())
    diseases = sorted(cohort["diseases"], key=lambda row: row["id"])
    if len(diseases) != 20 or len({row["id"] for row in diseases}) != 20:
        parser.error("cohort.json must contain the 20 distinct disease IDs")

    # Import the original implementation. No subclass, copy, or overridden method.
    sys.path.insert(0, str(GANDALF))
    sys.path.insert(0, str(GANDALF / "scripts/benchmarks"))
    from gandalf import CSRGraph
    from generate_queries import GraphSampler

    commit = subprocess.check_output(
        ["git", "-C", str(GANDALF), "rev-parse", "HEAD"], text=True).strip()
    subprocess.run(["git", "-C", str(GANDALF), "diff", "--quiet", "HEAD", "--",
                    "gandalf", "scripts/benchmarks/generate_queries.py"], check=True)
    started = time.perf_counter()
    graph = CSRGraph.load_mmap(args.graph.resolve(), mmap_mode="r")
    anchors = {}
    for disease in diseases:
        anchor = graph.get_node_idx(disease["id"])
        if anchor is None:
            parser.error(f"Disease missing from graph: {disease['id']}")
        if "biolink:Disease" not in graph.get_node_property(anchor, "categories", []):
            parser.error(f"Node lacks Disease category: {disease['id']}")
        anchors[disease["id"]] = int(anchor)
    sampler = GraphSampler(graph, random.Random(args.seed))
    setup_seconds = time.perf_counter() - started
    print(f"Loaded Gandalf graph and verified {len(diseases)} disease anchors", flush=True)

    output.mkdir(parents=True)
    walks_dir = output / "walks"
    walks_dir.mkdir()
    shutil.copyfile(cohort_path, output / "cohort.json")
    shutil.copyfile(Path(__file__), output / "sample.py")
    per_disease = []
    node_sets, connection_sets = {}, {}
    predicate_counts = Counter()
    sampling_started = time.perf_counter()
    for number, disease in enumerate(diseases, 1):
        disease_id = disease["id"]
        anchor = anchors[disease_id]
        filename = f"{number:02d}.jsonl"
        completed = 0
        nodes_seen, connections = set(), set()
        predicates = Counter()
        with (walks_dir / filename).open("x") as stream:
            for attempt in range(args.attempts_per_disease):
                walked = sampler.walk(anchor, args.length)
                nodes, edges = walked if walked is not None else (None, None)
                stream.write(json.dumps({"disease": disease_id, "attempt": attempt,
                                         "anchor": anchor, "nodes": nodes, "edges": edges}) + "\n")
                if walked is not None:
                    completed += 1
                    nodes_seen.update(nodes)
                    for source, predicate, target in edges:
                        connections.add((nodes[source], predicate, nodes[target]))
                        predicates[graph.id_to_predicate[predicate]] += 1
        node_sets[disease_id] = nodes_seen
        connection_sets[disease_id] = connections
        predicate_counts.update(predicates)
        per_disease.append({
            "disease": disease_id, "name": disease["name"], "anchor": anchor,
            "walks_file": f"walks/{filename}", "attempts": args.attempts_per_disease,
            "completed_walks": completed, "failed_walks": args.attempts_per_disease - completed,
            "success_fraction": completed / args.attempts_per_disease,
            "distinct_nodes_in_completed_walks": len(nodes_seen),
            "distinct_nodes_reached": len(nodes_seen - {anchor}),
            "distinct_directed_connections": len(connections),
            "predicate_occurrences": dict(sorted(predicates.items())),
        })
        print(f"{disease_id}: {completed}/{args.attempts_per_disease} completed; {len(nodes_seen):,} distinct nodes", flush=True)
    sampling_seconds = time.perf_counter() - sampling_started

    # Coverage analysis only; these sets never influence Gandalf's sampling.
    all_nodes = set().union(*node_sets.values())
    lookup_ids = sorted(all_nodes | set(anchors.values()))
    properties = graph.get_all_node_properties_batch(lookup_ids)
    curies = graph.get_node_ids_batch(lookup_ids)
    drug_nodes = {node for node in all_nodes if "biolink:Drug" in properties[node]["categories"]}
    chemical_nodes = {node for node in all_nodes if CHEMICAL_CATEGORIES.intersection(properties[node]["categories"])}
    reached = {d: nodes - {anchors[d]} for d, nodes in node_sets.items()}
    drugs_by_disease = {d: nodes & drug_nodes for d, nodes in reached.items()}
    for row in per_disease:
        disease_id = row["disease"]
        row["distinct_drugs_reached"] = len(drugs_by_disease[disease_id])
        row["distinct_chemicals_or_drugs_reached"] = len(reached[disease_id] & chemical_nodes)
    overlaps = []
    for a, b in combinations(sorted(reached), 2):
        union_nodes = reached[a] | reached[b]
        shared_nodes = reached[a] & reached[b]
        union_drugs = drugs_by_disease[a] | drugs_by_disease[b]
        shared_drugs = drugs_by_disease[a] & drugs_by_disease[b]
        overlaps.append({"disease_a": a, "disease_b": b,
                         "shared_reached_nodes": len(shared_nodes),
                         "node_jaccard": len(shared_nodes) / len(union_nodes) if union_nodes else None,
                         "shared_drugs": len(shared_drugs),
                         "drug_jaccard": len(shared_drugs) / len(union_drugs) if union_drugs else None})
    write_csv(output / "overlap.csv", overlaps)
    write_csv(output / "per_disease.csv", [
        {key: value for key, value in row.items() if key != "predicate_occurrences"} for row in per_disease])
    save(output / "nodes.json", [
        {"gandalf_id": node, "id": curies[node], "name": properties[node].get("name"),
         "categories": properties[node]["categories"]} for node in lookup_ids])
    save(output / "predicates.json", {
        str(index): predicate for predicate, index in
        sorted(graph.predicate_to_idx.items(), key=lambda item: item[1])})
    completed = sum(row["completed_walks"] for row in per_disease)
    attempted = args.attempts_per_disease * len(diseases)
    summary = {
        "run_id": args.run_id, "graph": str(args.graph.resolve()),
        "gandalf_commit": commit, "gandalf_implementation_unmodified": True,
        "sampler": "scripts/benchmarks/generate_queries.py:GraphSampler.walk",
        "sampler_sha256": digest(GANDALF / "scripts/benchmarks/generate_queries.py"),
        "graph_metadata_sha256": digest(args.graph / "metadata.pkl"),
        "python": sys.version, "seed": args.seed,
        "rng_order": "One random.Random(seed); disease IDs sorted; all attempts for each disease in order; anchor() is never called",
        "walk_length": args.length, "attempts_per_disease": args.attempts_per_disease,
        "diseases": len(diseases), "attempted_walks": attempted, "completed_walks": completed,
        "failed_walks": attempted - completed, "success_fraction": completed / attempted,
        "distinct_nodes_in_completed_walks": len(all_nodes),
        "distinct_drugs": len(drug_nodes), "distinct_chemicals_or_drugs": len(chemical_nodes),
        "distinct_directed_connections": len(set().union(*connection_sets.values())),
        "edge_occurrences_in_completed_walks": completed * args.length,
        "predicate_occurrences": dict(sorted(predicate_counts.items())),
        "graph_nodes": graph.num_nodes, "graph_edge_records": len(graph.fwd_targets),
        "load_and_setup_seconds": setup_seconds, "sampling_and_walk_export_seconds": sampling_seconds,
        "total_seconds": time.perf_counter() - started,
        "per_disease": per_disease,
        "output_sha256": {str(path.relative_to(output)): digest(path)
                          for path in sorted(output.rglob("*")) if path.is_file()},
    }
    save(output / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in (
        "attempted_walks", "completed_walks", "failed_walks", "distinct_nodes_in_completed_walks",
        "distinct_drugs", "distinct_chemicals_or_drugs", "distinct_directed_connections")}, indent=2), flush=True)
    print(f"Saved {output}", flush=True)


if __name__ == "__main__":
    main()
