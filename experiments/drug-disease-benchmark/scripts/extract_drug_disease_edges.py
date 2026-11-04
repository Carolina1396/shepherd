"""Extract every drug <-> disease edge from a Tier 0 KGX release and summarize it.

Drug side: nodes whose category list includes biolink:ChemicalEntity.
Disease side: nodes whose category list includes biolink:DiseaseOrPhenotypicFeature.
Node categories in Tier 0 carry the full Biolink ancestry, so these two checks
cover SmallMolecule, Drug, mixtures, Disease and PhenotypicFeature.

Outputs (in --out):
  drug_disease_edges.tsv.gz  one row per edge: direction, subject, predicate, object,
                             primary_knowledge_source, knowledge_level, agent_type
  predicate_summary.csv      edges and unique drug-disease pairs per direction/predicate,
                             with primary knowledge sources
  node_categories.csv        drug-side and disease-side node counts by first listed category
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
SUBJECT = re.compile(r'"subject"\s*:\s*"([^"\\]*)"')
OBJECT = re.compile(r'"object"\s*:\s*"([^"\\]*)"')


def primary_source(edge):
    """Primary knowledge source from the TRAPI-style `sources` list (or the flat KGX field)."""
    for source in edge.get("sources") or []:
        if source.get("resource_role") == "primary_knowledge_source":
            return source.get("resource_id") or ""
    return edge.get("primary_knowledge_source") or ""


def load_nodes(path):
    drugs, diseases = {}, {}
    with path.open() as handle:
        for line in handle:
            if CHEMICAL not in line and DISEASE not in line:
                continue
            node = json.loads(line)
            categories = node.get("category") or []
            if CHEMICAL in categories:
                drugs[node["id"]] = categories[0]
            if DISEASE in categories:
                diseases[node["id"]] = categories[0]
    return drugs, diseases


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path, help="directory with nodes.jsonl and edges.jsonl")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    drugs, diseases = load_nodes(args.raw / "nodes.jsonl")
    print(f"nodes: {len(drugs):,} drug-side, {len(diseases):,} disease-side", flush=True)

    edges = Counter()
    pairs = defaultdict(set)
    sources = defaultdict(Counter)
    scanned = 0
    with (args.raw / "edges.jsonl").open() as handle, gzip.open(
        args.out / "drug_disease_edges.tsv.gz", "wt", newline=""
    ) as out:
        writer = csv.writer(out, delimiter="\t")
        writer.writerow(["direction", "subject", "predicate", "object",
                         "primary_knowledge_source", "knowledge_level", "agent_type"])
        for line in handle:
            scanned += 1
            if scanned % 20_000_000 == 0:
                print(f"  scanned {scanned:,} edges", flush=True)
            subject, obj = SUBJECT.search(line), OBJECT.search(line)
            if subject and obj:
                subject, obj = subject.group(1), obj.group(1)
                edge = None
            else:
                # Escaped identifier strings require JSON decoding. Keep the
                # fast prefilter for ordinary CURIEs in the full graph.
                edge = json.loads(line)
                subject, obj = edge.get("subject"), edge.get("object")
            if subject in drugs and obj in diseases:
                direction, pair = "drug->disease", (subject, obj)
            elif subject in diseases and obj in drugs:
                direction, pair = "disease->drug", (obj, subject)
            else:
                continue
            edge = edge if edge is not None else json.loads(line)
            predicate = edge["predicate"]
            source = primary_source(edge)
            key = (direction, predicate)
            edges[key] += 1
            pairs[key].add(pair)
            sources[key][source.removeprefix("infores:")] += 1
            writer.writerow([direction, subject, predicate, obj, source,
                             edge.get("knowledge_level") or "", edge.get("agent_type") or ""])

    with (args.out / "predicate_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["direction", "predicate", "edges", "unique_pairs", "primary_knowledge_sources"])
        for (direction, predicate), n in edges.most_common():
            top = "; ".join(f"{s}={c}" for s, c in sources[(direction, predicate)].most_common())
            writer.writerow([direction, predicate, n, len(pairs[(direction, predicate)]), top])

    with (args.out / "node_categories.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        # Retain the historical column name for existing consumers. This is
        # categories[0]; node_types.csv supplies the separately derived leaf type.
        writer.writerow(["side", "most_specific_category", "nodes"])
        for side, nodes in (("drug", drugs), ("disease", diseases)):
            for category, n in Counter(nodes.values()).most_common():
                writer.writerow([side, category, n])

    all_pairs = set().union(*pairs.values()) if pairs else set()
    print(f"scanned {scanned:,} edges; {sum(edges.values()):,} drug-disease edges, "
          f"{len(all_pairs):,} unique drug-disease pairs", flush=True)


if __name__ == "__main__":
    main()
