"""Count raw edge knowledge levels globally and by primary source/predicate.

No edge filtering or model evaluation. Memory use is limited to aggregate counts.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

from inspect_treatment_pairs import records

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output" / "resources" / "knowledge_levels.json"


def knowledge_level(edge):
    if "knowledge_level" not in edge:
        return "[missing field]"
    value = edge["knowledge_level"]
    if value is None:
        return "[null]"
    if isinstance(value, str):
        return value if value.strip() else "[empty string]"
    return "[non-string] " + json.dumps(value, sort_keys=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "download.json").read_text())
    entry = next(f for f in manifest["files"] if f["path"].endswith(".tar.zst"))
    archive = ROOT / entry["path"]
    if archive.stat().st_size != entry["bytes"]:
        raise ValueError("Archive size differs from download manifest")
    identity = {
        "archive_sha256_from_manifest": entry["sha256"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reader_sha256": hashlib.sha256(Path(__file__).with_name("inspect_treatment_pairs.py").read_bytes()).hexdigest(),
    }
    if not args.refresh and OUTPUT.exists():
        if json.loads(OUTPUT.read_text()).get("identity") == identity:
            print(f"Using cached knowledge-level counts: {OUTPUT}", flush=True)
            return
    started = time.monotonic()
    levels = Counter()
    by_source = Counter()
    by_predicate = Counter()
    by_group = Counter()
    count = missing_sources = multiple_sources = 0
    print("Scanning raw edges for knowledge levels...", flush=True)
    with records(archive, "edges.jsonl") as handle:
        for line in handle:
            if not line.strip():
                continue
            edge = json.loads(line)
            level = knowledge_level(edge)
            predicate = edge["predicate"]
            sources = {s["resource_id"] for s in edge.get("sources", [])
                       if s.get("resource_role") == "primary_knowledge_source" and s.get("resource_id")}
            if not sources:
                missing_sources += 1
                sources = {"[missing primary source]"}
            elif len(sources) > 1:
                multiple_sources += 1
            levels[level] += 1
            by_predicate[predicate, level] += 1
            for source in sources:
                by_source[source, level] += 1
                by_group[source, predicate, level] += 1
            count += 1
            if count % 2_000_000 == 0:
                print(f"Scanned {count:,} edges", flush=True)
    metadata_entry = next(f for f in manifest["files"] if f["path"].endswith("graph-metadata.json"))
    metadata = json.loads((ROOT / metadata_entry["path"]).read_text())["schema"]["edges_summary"]
    observed_sources = Counter()
    for (source, level), n in by_source.items():
        observed_sources[source] += n
    observed_groups = Counter()
    for (source, predicate, level), n in by_group.items():
        observed_groups[source, predicate] += n
    expected_groups = {(s, p): n for s, predicates in metadata["predicates_by_knowledge_source"].items()
                       for p, n in predicates.items()}
    checks = {
        "edge_total_matches_metadata": count == metadata["total_count"],
        "source_totals_match_metadata": dict(observed_sources) == metadata["primary_knowledge_sources"],
        "source_predicate_totals_match_metadata": dict(observed_groups) == expected_groups,
    }
    result = {
        "identity": identity, "release": manifest["release"], "edges_scanned": count,
        "edges_without_primary_source": missing_sources,
        "edges_with_multiple_primary_sources": multiple_sources,
        "checks": checks, "levels": dict(levels.most_common()),
        "by_source": [{"source": s, "knowledge_level": level, "edges": n}
                      for (s, level), n in sorted(by_source.items())],
        "by_predicate": [{"predicate": p, "knowledge_level": level, "edges": n}
                         for (p, level), n in sorted(by_predicate.items())],
        "by_source_predicate": [{"source": s, "predicate": p, "knowledge_level": level, "edges": n}
                                for (s, p, level), n in sorted(by_group.items())],
        "elapsed_seconds": round(time.monotonic() - started, 1),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.part")
    temporary.write_text(json.dumps(result, indent=2) + "\n")
    temporary.replace(OUTPUT)
    print(f"Complete: {count:,} edges. Knowledge levels: {dict(levels)}", flush=True)
    print(f"Metadata checks: {checks}", flush=True)


if __name__ == "__main__":
    main()
