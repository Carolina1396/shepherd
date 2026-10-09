"""Compare reached chemicals/drugs with explicit treats pairs in the full graph."""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TREATS = "biolink:treats"
TREATMENT_FAMILY = {
    TREATS, "biolink:treats_or_applied_or_studied_to_treat", "biolink:applied_to_treat",
    "biolink:studied_to_treat", "biolink:in_clinical_trials_for",
    "biolink:in_preclinical_trials_for", "biolink:ameliorates_condition",
    "biolink:contraindicated_in",
}
CHEMICAL_CATEGORIES = {"biolink:Drug", "biolink:SmallMolecule", "biolink:ChemicalEntity"}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.run_id):
        parser.error("Invalid run ID")
    run = HERE / "results" / args.run_id
    out = run / "recovery"
    if out.exists():
        parser.error(f"Refusing to overwrite {out}")
    summary = json.loads((run / "summary.json").read_text())
    for name, expected in summary["output_sha256"].items():
        assert digest(run / name) == expected, name
    graph_path = Path(summary["graph"])
    assert digest(graph_path / "metadata.pkl") == summary["graph_metadata_sha256"]
    sys.path.insert(0, str(ROOT / "vendor/gandalf"))
    from gandalf import CSRGraph

    commit = subprocess.check_output(
        ["git", "-C", str(ROOT / "vendor/gandalf"), "rev-parse", "HEAD"], text=True).strip()
    assert commit == summary["gandalf_commit"]
    graph = CSRGraph.load_mmap(graph_path, mmap_mode="r")
    relationships, reached, traversed_treats, occurrences = {}, {}, {}, {}
    all_reference_nodes = set()
    for disease in summary["per_disease"]:
        d = disease["disease"]
        anchor = graph.get_node_idx(d)
        assert anchor == disease["anchor"]
        relations = defaultdict(set)
        for chemical, predicate in graph.get_incoming_edges(anchor):
            if predicate in TREATMENT_FAMILY:
                relations[chemical].add(predicate)
        relationships[d] = relations
        nodes, treats_edges, counts = set(), set(), Counter()
        with (run / disease["walks_file"]).open() as stream:
            for line in stream:
                walk = json.loads(line)
                assert walk["disease"] == d and walk["anchor"] == anchor
                if walk["nodes"] is None:
                    continue
                visited = set(walk["nodes"]) - {anchor}
                nodes.update(visited)
                counts.update(visited)
                for h, p, t in walk["edges"]:
                    if graph.id_to_predicate[p] == TREATS and walk["nodes"][t] == anchor:
                        treats_edges.add(walk["nodes"][h])
        reached[d], traversed_treats[d], occurrences[d] = nodes, treats_edges, counts
        all_reference_nodes.update(nodes)
        all_reference_nodes.update(relations)
    ids = sorted(all_reference_nodes)
    props = graph.get_all_node_properties_batch(ids)
    curies = graph.get_node_ids_batch(ids)
    scopes = {
        "drug": {n for n in ids if "biolink:Drug" in props[n]["categories"]},
        "chemical_or_drug": {n for n in ids if CHEMICAL_CATEGORIES.intersection(props[n]["categories"])},
    }
    per_disease, totals, pair_rows = [], {}, []
    for scope, eligible in scopes.items():
        known_union, recovered_union, additional_union, reached_union = set(), set(), set(), set()
        scoped_rows = []
        for disease in summary["per_disease"]:
            d = disease["disease"]
            known = {n for n, predicates in relationships[d].items() if TREATS in predicates} & eligible
            found = reached[d] & eligible
            recovered, additional = known & found, found - known
            other = {n for n in additional if relationships[d].get(n)}
            contraindicated = {n for n in additional
                              if "biolink:contraindicated_in" in relationships[d].get(n, set())}
            direct = traversed_treats[d] & eligible
            assert direct <= recovered
            expected_reached = disease["distinct_drugs_reached" if scope == "drug" else "distinct_chemicals_or_drugs_reached"]
            assert len(found) == expected_reached
            row = {
                "scope": scope, "disease": d, "name": disease["name"],
                "known_pairs": len(known), "known_recovered": len(recovered),
                "known_missed": len(known - found),
                "recovery_fraction": len(recovered) / len(known) if known else None,
                "reached_pairs": len(found), "additional_pairs_no_explicit_treats": len(additional),
                "additional_with_other_treatment_family_links": len(other),
                "additional_without_treatment_family_links": len(additional - other),
                "additional_contraindicated_pairs": len(contraindicated),
                "recovered_known_treats_edges_traversed": len(direct),
            }
            assert row["known_recovered"] + row["additional_pairs_no_explicit_treats"] == row["reached_pairs"]
            assert row["additional_with_other_treatment_family_links"] + row["additional_without_treatment_family_links"] == len(additional)
            scoped_rows.append(row)
            known_union.update(known)
            recovered_union.update(recovered)
            additional_union.update(additional)
            reached_union.update(found)
            if scope == "chemical_or_drug":
                for node in sorted(known | found, key=lambda n: curies[n]):
                    predicates = relationships[d].get(node, set())
                    if node in known:
                        status = "known_recovered" if node in found else "known_not_recovered"
                    else:
                        status = "additional_with_other_treatment_family_link" if predicates else "additional_without_treatment_family_link"
                    pair_rows.append({
                        "disease": d, "disease_name": disease["name"], "chemical": curies[node],
                        "chemical_name": props[node].get("name"), "is_drug": node in scopes["drug"],
                        "categories": json.dumps(props[node]["categories"]), "status": status,
                        "known_explicit_treats": node in known, "reached": node in found,
                        "completed_walks_containing_node": occurrences[d][node],
                        "explicit_treats_edge_traversed": node in direct,
                        "treatment_family_predicates": json.dumps(sorted(predicates)),
                        "contraindicated_in_graph": "biolink:contraindicated_in" in predicates,
                    })
        per_disease.extend(scoped_rows)
        count_fields = [key for key in scoped_rows[0] if key not in {"scope", "disease", "name", "recovery_fraction"}]
        total = {key: sum(row[key] for row in scoped_rows) for key in count_fields}
        total.update(
            recovery_fraction=total["known_recovered"] / total["known_pairs"] if total["known_pairs"] else None,
            distinct_known_nodes=len(known_union), distinct_recovered_known_nodes=len(recovered_union),
            distinct_additional_nodes=len(additional_union), distinct_reached_nodes=len(reached_union),
            distinct_nodes_in_both_recovered_and_additional_roles=len(recovered_union & additional_union))
        totals[scope] = total
    # Independent reference: the original cohort had 777 eligible explicit treats pairs.
    cohort = json.loads((run / "cohort.json").read_text())
    old_manifest = ROOT / cohort["source"]
    assert digest(old_manifest) == cohort["source_sha256"]
    old_counts = {r["id"]: r["pairs"] for r in json.loads(old_manifest.read_text())["diseases"]}
    for row in per_disease:
        if row["scope"] == "chemical_or_drug":
            assert row["known_pairs"] == old_counts[row["disease"]]
    out.mkdir()
    write_csv(out / "per_disease.csv", per_disease)
    write_csv(out / "pairs.csv", pair_rows)
    report = {
        "run_id": args.run_id, "source_run_summary_sha256": digest(run / "summary.json"),
        "gandalf_commit": commit, "graph": str(graph_path),
        "known_definition": "Unique chemical/drug -> explicit biolink:treats -> disease pairs in the full graph, all sources; no clinical adjudication",
        "recovery_definition": "Known treatment node occurs anywhere in a completed walk from its disease; exact CURIE match",
        "additional_definition": "Reached eligible node without explicit treats for that disease; graph candidates, not validated treatments",
        "treatment_family": sorted(TREATMENT_FAMILY),
        "counting_unit": "Unique disease-node pair unless field name starts with distinct; a node can be known for one disease and additional for another",
        "known_links_visible_during_sampling": True,
        "checks": ["sampling output hashes", "same graph metadata and Gandalf commit", "coverage matches sampling summary",
                   "reached pairs partition into known recovered and additional", "known counts match archived cohort for every disease"],
        "totals": totals,
        "output_sha256": {name: digest(out / name) for name in ("per_disease.csv", "pairs.csv")},
    }
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(totals, indent=2), flush=True)
    print(f"Saved {out}", flush=True)


if __name__ == "__main__":
    main()
