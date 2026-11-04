"""Inventory all Multiomics approved treatment pairs and their cited SPL labels."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", type=Path, help="Tier 0 directory containing nodes.jsonl and edges.jsonl")
    args = parser.parse_args()
    grouped = defaultdict(list)
    with (args.raw / "edges.jsonl").open() as stream:
        for line in stream:
            if "multiomics-drugapprovals" not in line or "approved_for_condition" not in line:
                continue
            edge = json.loads(line)
            if edge.get("predicate") != "biolink:treats" or edge.get("clinical_approval_status") != "approved_for_condition":
                continue
            if not any(s.get("resource_id") == "infores:multiomics-drugapprovals"
                       and s.get("resource_role") == "primary_knowledge_source" for s in edge.get("sources", [])):
                continue
            grouped[(edge["subject"], edge["object"])].append(edge)
    ids = {node for pair in grouped for node in pair}
    nodes = {}
    with (args.raw / "nodes.jsonl").open() as stream:
        for line in stream:
            node = json.loads(line)
            if node["id"] in ids:
                nodes[node["id"]] = node
    rows = []
    for (subject, obj), edges in sorted(grouped.items()):
        labels = sorted({p.split(":")[-1].lower() for e in edges for p in e.get("publications", [])
                         if p.startswith("dailymed:") and re.fullmatch(r"[0-9a-fA-F-]{36}", p.split(":")[-1])})
        rows.append({"subject": subject, "object": obj, "drug_name": nodes[subject].get("name"),
                     "condition_name": nodes[obj].get("name"), "set_ids": labels, "edges": edges})
    cache = HERE.parents[1] / "03-dailymed-screening/labels"
    labels = {sid for row in rows for sid in row["set_ids"]}
    cached = {sid for sid in labels if (cache / f"{sid}.xml.gz").exists()}
    summary = {"pairs": len(rows), "source_edges": sum(map(len, grouped.values())),
               "drugs": len({r["subject"] for r in rows}), "conditions": len({r["object"] for r in rows}),
               "distinct_cited_labels": len(labels), "cached_labels": len(cached),
               "pairs_without_label_citations": sum(not r["set_ids"] for r in rows),
               "pairs_with_cached_label": sum(bool(set(r["set_ids"]) & cached) for r in rows),
               "pairs_with_all_labels_cached": sum(bool(r["set_ids"]) and set(r["set_ids"]) <= cached for r in rows),
               "status": "Inventory only; parser impact has not been measured"}
    for name, data in [("pairs.json", rows), ("nodes.json", nodes), ("inventory.json", summary)]:
        (HERE / name).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
