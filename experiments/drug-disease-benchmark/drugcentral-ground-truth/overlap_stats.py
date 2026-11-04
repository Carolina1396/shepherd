"""Reproduce DrugCentral treats overlap statistics from the Tier 0 edge extract.

Uses only the Python standard library. Counts unique normalized drug-condition
pairs, not edges; includes all DrugCentral treats statuses and phenotypes.
"""

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_EDGES = HERE.parent / "results/tier0-1.0.4/drug_disease_edges.tsv.gz"
REQUIRED = {"direction", "subject", "object", "predicate", "primary_knowledge_source"}


def read_edges(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns: {', '.join(sorted(missing))}")
        for row in reader:
            if row["direction"] == "drug->disease":
                pair = (row["subject"], row["object"])
            elif row["direction"] == "disease->drug":
                pair = (row["object"], row["subject"])
            else:
                raise ValueError(f"Line {reader.line_num}: invalid direction {row['direction']!r}")
            yield pair, row["predicate"].removeprefix("biolink:"), row["primary_knowledge_source"].removeprefix("infores:")


def analyze(path, eligible_pairs=None):
    drugcentral = {pair for pair, predicate, source in read_edges(path)
                   if predicate == "treats" and source == "drugcentral"}
    if eligible_pairs is not None:
        drugcentral.intersection_update(eligible_pairs)
    other_treats = set()
    non_treats = set()
    other_source = set()
    treats_sources = defaultdict(set)
    predicates = defaultdict(set)
    for pair, predicate, source in read_edges(path):
        if pair not in drugcentral:
            continue
        if source and source != "drugcentral":
            other_source.add(pair)
        if predicate == "treats" and source != "drugcentral":
            other_treats.add(pair)
            treats_sources[source or "unknown"].add(pair)
        elif predicate != "treats":
            non_treats.add(pair)
            predicates[predicate].add(pair)

    metrics = {
        "drugcentral_treats_pairs": len(drugcentral),
        "other_treats_pairs": len(other_treats),
        "non_treats_pairs": len(non_treats),
        "either_overlap_pairs": len(other_treats | non_treats),
        "both_overlap_pairs": len(other_treats & non_treats),
        "no_other_edge_pairs": len(drugcentral - (other_treats | non_treats)),
        "other_known_source_any_predicate_pairs": len(other_source),
    }
    def counts(groups):
        return {key: len(pairs) for key, pairs in
                sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))}
    return metrics, counts(treats_sources), counts(predicates)


def write_table(path, heading, counts, total, percent_heading="percent_of_drugcentral_treats"):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([heading, "unique_pairs", percent_heading])
        for name, count in counts.items():
            writer.writerow([name, count, f"{100 * count / total:.2f}" if total else ""])


def read_approval_counts(path):
    """Read source-asserted status counts produced by describe_drug_disease_edges.py."""
    counts = {}
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"primary_knowledge_source", "status", "unique_pairs"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing approval-summary columns: {', '.join(sorted(missing))}")
        for row in reader:
            if row["primary_knowledge_source"].removeprefix("infores:") != "drugcentral":
                continue
            status = row["status"]
            count = int(row["unique_pairs"])
            if count < 0 or status in counts:
                raise ValueError(f"Invalid or duplicate DrugCentral status count: {status}")
            counts[status] = count
    if not counts:
        raise ValueError(f"No DrugCentral status counts in {path}")
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def read_status_pairs(path):
    """Recover pair-level status, absent from the compact TSV and status counts."""
    pairs = defaultdict(set)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as handle:
        for line in handle:
            if "drugcentral" not in line:
                continue
            edge = json.loads(line)
            if edge.get("predicate") != "biolink:treats":
                continue
            source = next((s.get("resource_id") for s in edge.get("sources") or []
                           if s.get("resource_role") == "primary_knowledge_source"),
                          edge.get("primary_knowledge_source"))
            if source != "infores:drugcentral":
                continue
            # The compact extract supplies drug/condition direction on intersection.
            pair = (edge["subject"], edge["object"])
            status = edge.get("clinical_approval_status") or edge.get("max_research_phase") or "not_provided"
            pairs[status].add(pair)
            pairs[status].add(pair[::-1])
    return pairs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edges", type=Path, default=DEFAULT_EDGES,
                        help="Extracted drug_disease_edges.tsv[.gz]; defaults to Tier 0 1.0.4")
    parser.add_argument("--out", type=Path, default=HERE / "tables",
                        help="Output directory (default: tables/ beside this script)")
    parser.add_argument("--approval-summary", type=Path,
                        help="Matching treats_approval.csv (default: beside --edges)")
    parser.add_argument("--raw-edges", type=Path,
                        help="Matching raw edges.jsonl[.gz]; enables approved and off-label overlap statistics")
    args = parser.parse_args()
    approval_path = args.approval_summary or args.edges.parent / "treats_approval.csv"
    approval_counts = read_approval_counts(approval_path)
    metrics, sources, predicates = analyze(args.edges)
    with args.edges.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    with approval_path.open("rb") as handle:
        approval_checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    summary = {
        "input_file": args.edges.name,
        "input_sha256": checksum,
        "approval_input_file": approval_path.name,
        "approval_input_sha256": approval_checksum,
        "scope": "All DrugCentral treats statuses; includes phenotype conditions; exact normalized pairs in either direction",
        "notes": [
            "Overlap means another predicate or a non-DrugCentral treats record for the same pair.",
            "Duplicate records do not increase pair counts. Breakdown rows are not mutually exclusive.",
            "Unknown-source treats records count as additional treats evidence and appear as unknown.",
            "The extract has no approval-status column; these are not approved-only statistics.",
            "Approval counts come from the matching treats_approval.csv and reflect source assertions, not independent validation.",
            "Status counts may overlap if a pair has multiple statuses; their sum alone does not prove a partition.",
        ],
        "counts": metrics,
        "drugcentral_approval_status_pairs": approval_counts,
        "approval_status_count_sum": sum(approval_counts.values()),
        "approval_status_count_sum_matches_total": sum(approval_counts.values()) == metrics["drugcentral_treats_pairs"],
        "other_treats_sources": sources,
        "non_treats_predicates": predicates,
    }
    subsets = [("approved", "approved_only", "approved_for_condition"),
               ("off_label", "off_label_only", "off_label_use")]
    if args.raw_edges:
        print("Reading DrugCentral status-specific pairs from raw edges...", flush=True)
        status_pairs = read_status_pairs(args.raw_edges)
        for prefix, key, status in subsets:
            subset_metrics, subset_sources, subset_predicates = analyze(
                args.edges, status_pairs.get(status, set()))
            if subset_metrics["drugcentral_treats_pairs"] != approval_counts.get(status, 0):
                raise ValueError(f"{status} pair count differs from treats_approval.csv; check input snapshots")
            summary[key] = {
                "raw_edges_file": str(args.raw_edges.resolve()),
                "counts": subset_metrics,
                "other_treats_sources": subset_sources,
                "non_treats_predicates": subset_predicates,
            }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    total = metrics["drugcentral_treats_pairs"]
    write_table(args.out / "overlap_summary.csv", "metric", metrics, total)
    write_table(args.out / "treats_source_overlap.csv", "primary_knowledge_source", sources, total)
    write_table(args.out / "predicate_overlap.csv", "predicate", predicates, total)
    write_table(args.out / "approval_status.csv", "status", approval_counts, total)
    if args.raw_edges:
        for prefix, key, status in subsets:
            subset = summary[key]
            subset_total = subset["counts"]["drugcentral_treats_pairs"]
            for filename, heading, counts in [
                (f"{prefix}_overlap_summary.csv", "metric", subset["counts"]),
                (f"{prefix}_treats_source_overlap.csv", "primary_knowledge_source", subset["other_treats_sources"]),
                (f"{prefix}_predicate_overlap.csv", "predicate", subset["non_treats_predicates"]),
            ]:
                write_table(args.out / filename, heading, counts, subset_total,
                            f"percent_of_drugcentral_{prefix}_treats")
            print(f"{status} overlap:", json.dumps(subset, indent=2))
    for name, count in metrics.items():
        percent = f" ({100 * count / total:.1f}%)" if total else ""
        print(f"{name}: {count:,}{percent}")
    for status, count in approval_counts.items():
        percent = f" ({100 * count / total:.2f}%)" if total else ""
        print(f"DrugCentral {status}: {count:,}{percent}")
    print(f"Saved tables to {args.out.resolve()}")


if __name__ == "__main__":
    main()
