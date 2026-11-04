"""Detail tables for Tier 0 drug <-> disease edges.

Reads the output of extract_drug_disease_edges.py plus the raw release, and writes:
  top_predicates.csv    predicates (both directions combined): edges, share, unique pairs,
                        drugs, diseases, top sources
  node_types.csv        drug-side and disease-side nodes by leaf Biolink category: nodes in
                        the graph, in any drug-disease edge, and in a treats edge
  treats_approval.csv   treats edges and unique pairs by primary source and approval status
                        (clinical_approval_status, else max_research_phase)
  approved_overlap.csv  overlap of approved treats pairs between sources
"""
import argparse
import csv
import gzip
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

CHEMICAL = "biolink:ChemicalEntity"
DISEASE = "biolink:DiseaseOrPhenotypicFeature"
TREATS = "biolink:treats"
TREATS_FIELD = re.compile(r'"predicate"\s*:\s*"biolink:treats"')
# Categories reported as node types, with the Biolink ancestors to drop when a more
# specific one is present (node category lists in Tier 0 carry the full ancestry).
ANCESTORS = {
    "biolink:Drug": {"biolink:MolecularMixture", "biolink:ChemicalMixture", CHEMICAL},
    "biolink:SmallMolecule": {"biolink:MolecularEntity", CHEMICAL},
    "biolink:NucleicAcidEntity": {"biolink:MolecularEntity", CHEMICAL},
    "biolink:MolecularMixture": {"biolink:ChemicalMixture", CHEMICAL},
    "biolink:ComplexMolecularMixture": {"biolink:ChemicalMixture", CHEMICAL},
    "biolink:ChemicalMixture": {CHEMICAL},
    "biolink:MolecularEntity": {CHEMICAL},
    CHEMICAL: set(),
    "biolink:Protein": {"biolink:Polypeptide"},
    "biolink:Polypeptide": set(),
    "biolink:OrganismTaxon": set(),
    "biolink:AnatomicalEntity": set(),
    "biolink:CellularComponent": {"biolink:AnatomicalEntity"},
    "biolink:Disease": {DISEASE},
    "biolink:PhenotypicFeature": {DISEASE},
    DISEASE: set(),
}


def leaf_type(categories):
    present = [c for c in ANCESTORS if c in categories]
    dropped = set().union(*(ANCESTORS[c] for c in present)) if present else set()
    leaves = sorted(c.removeprefix("biolink:") for c in present if c not in dropped)
    return "+".join(leaves) or "other"


def primary_source(edge):
    for source in edge.get("sources") or []:
        if source.get("resource_role") == "primary_knowledge_source":
            return source.get("resource_id") or ""
    return edge.get("primary_knowledge_source") or ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path, help="directory with nodes.jsonl and edges.jsonl")
    parser.add_argument("--results", type=Path, required=True, help="extract_drug_disease_edges.py output")
    args = parser.parse_args()
    out = args.results

    # Edge-level tables from the extracted drug-disease edges
    edges, pairs, drugs, diseases = Counter(), defaultdict(set), defaultdict(set), defaultdict(set)
    sources = defaultdict(Counter)
    in_edge, in_treats = set(), set()
    with gzip.open(out / "drug_disease_edges.tsv.gz", "rt") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            drug, disease = ((row["subject"], row["object"]) if row["direction"] == "drug->disease"
                             else (row["object"], row["subject"]))
            predicate = row["predicate"]
            edges[predicate] += 1
            pairs[predicate].add((drug, disease))
            drugs[predicate].add(drug)
            diseases[predicate].add(disease)
            sources[predicate][row["primary_knowledge_source"].removeprefix("infores:")] += 1
            in_edge.update((drug, disease))
            if predicate == TREATS:
                in_treats.update((drug, disease))

    total = sum(edges.values())
    with (out / "top_predicates.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["rank", "predicate", "edges", "share_of_edges", "unique_pairs", "drugs",
                         "diseases", "primary_knowledge_sources"])
        for rank, (predicate, n) in enumerate(edges.most_common(), 1):
            top = "; ".join(f"{s}={c}" for s, c in sources[predicate].most_common(4))
            writer.writerow([rank, predicate, n, f"{n / total:.3f}", len(pairs[predicate]),
                             len(drugs[predicate]), len(diseases[predicate]), top])

    # Node types
    node_rows = Counter()
    with (args.raw / "nodes.jsonl").open() as handle:
        for line in handle:
            if CHEMICAL not in line and DISEASE not in line:
                continue
            node = json.loads(line)
            categories = node.get("category") or []
            for side, marker in (("drug", CHEMICAL), ("disease", DISEASE)):
                if marker in categories:
                    key = (side, leaf_type(categories))
                    node_rows[key + ("graph",)] += 1
                    if node["id"] in in_edge:
                        node_rows[key + ("drug_disease_edge",)] += 1
                    if node["id"] in in_treats:
                        node_rows[key + ("treats_edge",)] += 1
    with (out / "node_types.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["side", "node_type", "nodes_in_graph", "in_drug_disease_edge", "in_treats_edge"])
        types = sorted({k[:2] for k in node_rows}, key=lambda k: (k[0] != "drug", -node_rows[k + ("graph",)]))
        for side, node_type in types:
            writer.writerow([side, node_type, node_rows[(side, node_type, "graph")],
                             node_rows[(side, node_type, "drug_disease_edge")],
                             node_rows[(side, node_type, "treats_edge")]])

    # Approval status on treats edges (needs the raw edge attributes)
    treats_pairs = pairs[TREATS]
    status_edges, status_pairs = Counter(), defaultdict(set)
    approved = defaultdict(set)
    fda_numbers = set()
    with (args.raw / "edges.jsonl").open() as handle:
        for line in handle:
            if not TREATS_FIELD.search(line):
                continue
            edge = json.loads(line)
            pair = (edge["subject"], edge["object"])
            if pair not in treats_pairs:
                continue
            source = primary_source(edge).removeprefix("infores:")
            status = (edge.get("clinical_approval_status") or edge.get("max_research_phase")
                      or "not_provided")
            status_edges[(source, status)] += 1
            status_pairs[(source, status)].add(pair)
            if status == "approved_for_condition":
                approved[source].add(pair)
            fda_numbers.update(edge.get("FDA_regulatory_approvals") or [])
    with (out / "treats_approval.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["primary_knowledge_source", "status", "edges", "unique_pairs"])
        for (source, status), n in status_edges.most_common():
            writer.writerow([source, status, n, len(status_pairs[(source, status)])])

    union = set().union(*approved.values()) if approved else set()
    with (out / "approved_overlap.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        names = sorted(approved)
        writer.writerow(["source"] + names + ["only_this_source"])
        for a in names:
            others = set().union(*(approved[b] for b in names if b != a))
            writer.writerow([a] + [len(approved[a] & approved[b]) for b in names]
                            + [len(approved[a] - others)])
        writer.writerow(["union", len(union)] + [""] * len(names))
    print(f"approved_for_condition treats pairs: union {len(union):,} "
          f"({', '.join(f'{s} {len(p):,}' for s, p in sorted(approved.items()))}); "
          f"{len(fda_numbers):,} distinct FDA application numbers")


if __name__ == "__main__":
    main()
