"""Resume label-first comparison using the original DAKP extraction entry point."""
import argparse
import collections
import copy
import csv
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
PARSER = HERE.parent
OLD_CACHE = HERE.parents[1] / "03-dailymed-screening/labels"
sys.path.insert(0, str(PARSER / "upstream/src"))
NS = "{urn:hl7-org:v3}"
SAFETY = {"34066-1", "34070-3", "34071-1", "43685-7", "42232-9", "34084-4",
          "50570-1", "50569-3", "50568-5", "50567-7", "50566-9", "53414-9", "50565-1"}
VERSION = 1


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def normalize(text):
    text = re.sub(r"['’]s\b", "", text.lower())
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def cut_safety(root):
    """Remove only coded safety sections nested beneath an indication section."""
    cleaned = copy.deepcopy(root)
    removed = []

    def walk(parent, in_indication=False):
        for child in list(parent):
            inside = in_indication
            if child.tag == NS + "section":
                code = child.find(NS + "code")
                value = code.get("code", "") if code is not None else ""
                if inside and value in SAFETY:
                    title = child.find(NS + "title")
                    removed.append({"code": value, "title": "".join(title.itertext()) if title is not None else "",
                                    "text": " ".join("".join(child.itertext()).split())})
                    parent.remove(child)
                    continue
                inside = inside or value == "34067-9"
            walk(child, inside)
    walk(cleaned)
    return cleaned, removed


def extract_text(path, work):
    import polars as pl
    from dakp_pipeline.extract import spl_xml
    from dakp_pipeline.io.contracts import TaskContext
    from dakp_pipeline.paths import Workdir
    assert Path(spl_xml.__file__).resolve() == (PARSER / "upstream/src/dakp_pipeline/extract/spl_xml.py").resolve()
    ctx = TaskContext(workdir=work, fixture_root=path.parent, params={})
    Workdir(work).create()
    outputs = spl_xml.extract([ctx.fixture(path.name)], ctx)
    table = next(r.uri for r in outputs if r.uri.name == "spl_sections.parquet")
    return "\n".join(r["clean_text"] for r in pl.read_parquet(table).to_dicts() if r["loinc_code"] == "34067-9")


def cached_path(sid):
    for directory in [HERE / "labels", OLD_CACHE]:
        path = directory / f"{sid}.xml.gz"
        if path.exists():
            return path
    return None


def fetch(sid, request_gate=None):
    url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{sid}.xml"
    def request(address):
        if request_gate is None:
            time.sleep(0.25)
        else:
            request_gate()
        with urllib.request.urlopen(urllib.request.Request(address, headers={"User-Agent": "DrugDiseaseBenchmarkAudit/1.0"}), timeout=45) as response:
            return response.read()
    import urllib.error
    try:
        raw = request(url)
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            raise
        url = f"https://dailymed.nlm.nih.gov/dailymed/downloadzipfile.cfm?setId={sid}"
        with zipfile.ZipFile(io.BytesIO(request(url))) as archive:
            members = [m for m in archive.namelist() if m.lower().endswith(".xml")]
            if len(members) != 1:
                raise ValueError("Expected one XML document")
            raw = archive.read(members[0])
    root = ET.fromstring(raw)
    assert root.find(NS + "setId").get("root").lower() == sid
    path = HERE / "labels" / f"{sid}.xml.gz"
    path.parent.mkdir(exist_ok=True)
    with gzip.open(path.with_suffix(".tmp"), "wb") as stream:
        stream.write(raw)
    path.with_suffix(".tmp").replace(path)
    save(path.with_suffix("").with_suffix(".json"), {"url": url, "set_id": sid,
         "sha256": hashlib.sha256(raw).hexdigest(), "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    return path


def parse_label(sid, path):
    raw = gzip.decompress(path.read_bytes())
    digest = hashlib.sha256(raw).hexdigest()
    output = HERE / "parsed" / f"{sid}.json"
    if output.exists():
        previous = json.loads(output.read_text())
        if previous.get("version") == VERSION and previous["sha256"] == digest:
            return
    root = ET.fromstring(raw)
    assert root.find(NS + "setId").get("root").lower() == sid
    cleaned, removed = cut_safety(root)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        original = d / "original.xml"
        original.write_bytes(raw)
        before = extract_text(original, d / "before")
        if removed:
            altered = d / "comparison.xml"
            ET.ElementTree(cleaned).write(altered, encoding="utf-8", xml_declaration=True)
            after = extract_text(altered, d / "after")
        else:
            after = before
    save(output, {"version": VERSION, "set_id": sid, "sha256": digest,
                  "original_indication": before, "comparison_indication": after, "removed_sections": removed})


def summarize(rows):
    alias_path = HERE.parents[1] / "03-dailymed-screening/condition-aliases.json"
    aliases = json.loads(alias_path.read_text())
    nodes = json.loads((HERE / "nodes.json").read_text())
    parsed = {p.stem: json.loads(p.read_text()) for p in (HERE / "parsed").glob("*.json")}
    normalized = {sid: (normalize(r["original_indication"]), normalize(r["comparison_indication"]),
                       normalize(" ".join(s["text"] for s in r["removed_sections"]))) for sid, r in parsed.items()}
    results = []; evidence = []; terms_by_condition = {}
    for row in rows:
        terms = sorted({normalize(t) for t in [row["condition_name"]] + aliases.get(row["object"], [])
                        + nodes[row["object"]].get("synonym", []) if t and len(normalize(t)) >= 4})
        terms_by_condition[row["object"]] = terms
        pattern = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)) + r")(?!\w)") if terms else None
        inspected = set(row["set_ids"]) & parsed.keys()
        leaked = []; lost = []; retained = []; before_labels = []
        for sid in sorted(inspected):
            before, after, removed = normalized[sid]
            b = pattern.search(before) if pattern else None
            a = pattern.search(after) if pattern else None
            w = pattern.search(removed) if pattern else None
            if b: before_labels.append(sid)
            if a: retained.append(sid)
            if b and w:
                leaked.append(sid)
                if not a: lost.append(sid)
                evidence.append({"drug_id": row["subject"], "condition_id": row["object"],
                    "drug_name": row["drug_name"], "condition_name": row["condition_name"],
                    "set_id": sid, "matched_removed_term": w.group(), "match_retained": bool(a),
                    "removed_codes": " | ".join(s["code"] for s in parsed[sid]["removed_sections"]),
                    "removed_excerpt": removed[max(0,w.start()-120):w.end()+200],
                    "label_url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={sid}"})
        full = bool(row["set_ids"]) and len(inspected) == len(row["set_ids"])
        results.append({"drug_id": row["subject"], "condition_id": row["object"], "drug_name": row["drug_name"],
            "condition_name": row["condition_name"], "cited_labels": len(row["set_ids"]), "inspected_labels": len(inspected),
            "complete_coverage": full, "original_match_labels": len(before_labels), "retained_match_labels": len(retained),
            "nested_safety_match_labels": len(leaked), "lost_match_labels": len(lost),
            "suspected_support_loss": bool(lost) and not retained, "lost_set_ids": " | ".join(lost)})
    for name, data in [("pair-impact.csv", results), ("label-evidence.csv", evidence)]:
        if data:
            temp = HERE / (name + ".tmp")
            with temp.open("w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
            temp.replace(HERE / name)
    counts = {"pairs": len(rows), "cited_labels": len({s for r in rows for s in r['set_ids']}),
        "parsed_labels": len(parsed), "labels_with_nested_safety": sum(bool(r['removed_sections']) for r in parsed.values()),
        "pairs_with_any_label_inspected": sum(r['inspected_labels'] > 0 for r in results),
        "pairs_with_complete_coverage": sum(r['complete_coverage'] for r in results),
        "pairs_with_nested_safety_matches": sum(r['nested_safety_match_labels'] > 0 for r in results),
        "pairs_losing_match_in_at_least_one_label": sum(r['lost_match_labels'] > 0 for r in results),
        "pairs_with_observed_support_loss": sum(r['suspected_support_loss'] for r in results),
        "complete_pairs_with_observed_support_loss": sum(r['suspected_support_loss'] and r['complete_coverage'] for r in results),
        "scope": "Lexical matches, not clinical adjudication; safety includes warnings, contraindications and precautions",
        "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    save(HERE / "condition-terms.json", terms_by_condition)
    save(HERE / "summary.json", counts)
    print(json.dumps(counts), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Fetch missing cited labels (network; potentially hours)")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--max-labels", type=int, help="Stop after this many successfully parsed labels, including cached results")
    args = parser.parse_args()
    if args.max_labels is not None and args.max_labels < 1:
        parser.error("--max-labels must be positive")
    from loguru import logger
    logger.disable("dakp_pipeline")
    snapshot = json.loads((PARSER / "upstream-snapshot.json").read_text())
    for entry in snapshot["files"]:
        assert hashlib.sha256((PARSER / "upstream" / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    rows = json.loads((HERE / "pairs.json").read_text())
    (HERE / "parsed").mkdir(exist_ok=True)
    if args.summarize_only:
        summarize(rows); return
    save(HERE / "run-status.json", {"pid": os.getpid(), "state": "running", "download": args.download,
         "max_labels": args.max_labels,
         "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    labels = {sid for r in rows for sid in r["set_ids"]}
    # Include the original case-study fixtures as cached inputs, preserving bytes.
    manifest = json.loads((PARSER / "manifest.json").read_text())
    for entry in manifest["files"]:
        if not entry["path"].startswith("fixtures/"):
            continue
        sid = entry["set_id"]
        raw = (PARSER / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        if sid in labels and cached_path(sid) is None:
            path = HERE / "labels" / f"{sid}.xml.gz"
            path.parent.mkdir(exist_ok=True)
            with gzip.open(path, "wb") as stream:
                stream.write(raw)
            save(path.with_suffix("").with_suffix(".json"), entry)
    failures = {}
    # Reuse available labels first; the subsequent download pass resumes cached work.
    ordered = sorted(labels, key=lambda sid: (cached_path(sid) is None, sid))
    processed = 0
    for i, sid in enumerate(ordered, 1):
        if args.max_labels is not None and processed >= args.max_labels:
            break
        path = cached_path(sid)
        if path is None and not args.download: continue
        try:
            if path is None:
                path = fetch(sid)
            parse_label(sid, path)
            processed += 1
        except Exception as exc:
            failures[sid] = f"{type(exc).__name__}: {exc}"
        if processed % 100 == 0 or i == len(ordered):
            save(HERE / "failures.json", failures)
            save(HERE / "run-status.json", {"pid": os.getpid(), "state": "running", "download": args.download,
                 "max_labels": args.max_labels,
                 "processed_labels": processed, "attempted_position": i, "total_labels": len(ordered),
                 "failures": len(failures), "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
            print(f"Processed {processed}; attempted position {i}/{len(ordered)}; failures {len(failures)}", flush=True)
        if processed and processed % 1000 == 0:
            summarize(rows)
    save(HERE / "failures.json", failures)
    summarize(rows)
    save(HERE / "run-status.json", {"pid": os.getpid(), "state": "finished", "download": args.download,
         "max_labels": args.max_labels,
         "stop_reason": "label_limit_reached" if args.max_labels is not None and processed >= args.max_labels else "pass_finished",
         "processed_labels": processed, "failures": len(failures), "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})


if __name__ == "__main__":
    main()
