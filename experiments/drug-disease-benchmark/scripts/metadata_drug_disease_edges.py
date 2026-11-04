"""Summarize drug <-> disease edges from a Tier 0 release's graph-metadata.json.

Uses only the published schema counts (no edges.jsonl scan). A schema row counts
as drug-side if any of its categories is chemical, and disease-side if any is a
disease or phenotype category.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

CHEMICAL = {
    "biolink:ChemicalEntity", "biolink:SmallMolecule", "biolink:Drug",
    "biolink:MolecularMixture", "biolink:ChemicalMixture", "biolink:ComplexMolecularMixture",
}
DISEASE = {"biolink:Disease", "biolink:PhenotypicFeature", "biolink:DiseaseOrPhenotypicFeature"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    graph = json.loads(args.metadata.read_text())
    counts = Counter()
    sources = defaultdict(Counter)
    for row in graph["schema"]["edges"]:
        subj, obj = set(row["subject_category"]), set(row["object_category"])
        if subj & CHEMICAL and obj & DISEASE:
            direction = "drug->disease"
        elif subj & DISEASE and obj & CHEMICAL:
            direction = "disease->drug"
        else:
            continue
        key = (direction, row["predicate"])
        counts[key] += row["count"]
        sources[key].update(row.get("primary_knowledge_sources") or {})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["direction", "predicate", "edges", "primary_knowledge_sources"])
        for (direction, predicate), n in counts.most_common():
            top = "; ".join(f"{s.removeprefix('infores:')}={c}" for s, c in sources[(direction, predicate)].most_common())
            writer.writerow([direction, predicate, n, top])
    print(f"{sum(counts.values())} drug-disease edges in {len(counts)} direction/predicate groups -> {args.out}")


if __name__ == "__main__":
    main()
