"""Reproducible, conservative section-location screen of shared approved pairs.

This locates condition names in selected labels; it does not validate clinical
indications. No match is not evidence of absent indication.
"""
import argparse
import collections
import concurrent.futures
import csv
import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

import requests

HERE = Path(__file__).resolve().parent
NS = {"s": "urn:hl7-org:v3"}
INDICATION_CODES = {"34067-9"}
SAFETY_CODES = {"34066-1", "34070-3", "34071-1", "43685-7", "42232-9",
                "50570-1", "50569-3", "50568-5", "50567-7", "50566-9",
                "53414-9", "50565-1"}


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def normalized(value):
    value = re.sub(r"\b([A-Za-z]+)['’]s\b", r"\1", value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())


def content(element):
    return " ".join(" ".join(element.itertext()).split()) if element is not None else ""


def extract(raw):
    sources = {"infores:drugcentral": {}, "infores:multiomics-drugapprovals": {}}
    with (raw / "edges.jsonl").open() as handle:
        for line in handle:
            if '"predicate":"biolink:treats"' not in line or "approved_for_condition" not in line:
                continue
            edge = json.loads(line)
            if edge.get("clinical_approval_status") != "approved_for_condition":
                continue
            source = next((s["resource_id"] for s in edge["sources"]
                           if s.get("resource_role") == "primary_knowledge_source"), None)
            if source in sources:
                sources[source][(edge["subject"], edge["object"])] = edge
    shared = sources["infores:drugcentral"].keys() & sources["infores:multiomics-drugapprovals"].keys()
    ids = {node for pair in shared for node in pair}
    nodes = {}
    with (raw / "nodes.jsonl").open() as handle:
        for line in handle:
            node = json.loads(line)
            if node["id"] in ids:
                nodes[node["id"]] = node
    rows = [{"subject": s, "object": o, "drug_name": nodes[s].get("name"),
             "condition_name": nodes[o].get("name"),
             "drugcentral_edge": sources["infores:drugcentral"][(s, o)],
             "multiomics_edge": sources["infores:multiomics-drugapprovals"][(s, o)]}
            for s, o in sorted(shared)]
    dump(HERE / "pairs.json", rows)
    dump(HERE / "nodes.json", nodes)
    print(f"Extracted {len(rows)} shared pairs", flush=True)


def cited_labels(pair):
    return {x.split(":")[-1] for x in pair["multiomics_edge"].get("publications", [])
            if x.startswith("dailymed:") and re.fullmatch(r"[0-9a-fA-F-]{36}", x.split(":")[-1])}


def select_labels(rows, coverage=1):
    by_label = collections.defaultdict(set)
    for i, row in enumerate(rows):
        for label in cited_labels(row):
            by_label[label].add(i)
    needed = {i: min(coverage, len(cited_labels(row))) for i, row in enumerate(rows)}
    selected = []
    # Deterministic set-cover heuristic, covering pairs rather than sampling drugs.
    while any(needed.values()):
        pending = {i for i, n in needed.items() if n}
        best = max(sorted(by_label), key=lambda k: len(by_label[k] & pending))
        covered = by_label.pop(best) & pending
        if not covered:
            break
        selected.append(best)
        for i in covered:
            needed[i] -= 1
    dump(HERE / "selected-labels.json", selected)
    print(f"Selected {len(selected)} labels for coverage target {coverage}", flush=True)


def fetch_labels():
    selected = json.loads((HERE / "selected-labels.json").read_text())
    cache = HERE / "labels"
    cache.mkdir(exist_ok=True)
    lock = threading.Lock()
    next_request = [0.0]

    def fetch(setid):
        path = cache / f"{setid}.xml.gz"
        meta_path = cache / f"{setid}.json"
        if path.exists() and meta_path.exists():
            return "cached"
        url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/{setid}.xml"
        meta = {"set_id": setid, "url": url}
        for attempt in range(3):
            with lock:
                delay = max(0, next_request[0] - time.monotonic())
                next_request[0] = max(next_request[0], time.monotonic()) + 0.25
            time.sleep(delay)
            try:
                response = requests.get(url, timeout=(10, 40), headers={"User-Agent": "DrugDiseaseBenchmarkAudit/1.0"})
                meta.update({"http_status": response.status_code, "retrieved_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()})
                if response.status_code == 404:
                    # The XML API can omit archived labels still available as ZIPs.
                    fallback = f"https://dailymed.nlm.nih.gov/dailymed/downloadzipfile.cfm?setId={setid}"
                    time.sleep(0.5)
                    response = requests.get(fallback, timeout=(10, 40))
                    meta.update({"fallback_url": fallback, "http_status": response.status_code})
                    response.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                        xml_members = [name for name in archive.namelist() if name.lower().endswith('.xml')]
                        if len(xml_members) != 1:
                            raise ValueError("Expected exactly one SPL XML in fallback ZIP")
                        xml_bytes = archive.read(xml_members[0])
                else:
                    xml_bytes = response.content
                response.raise_for_status()
                root = ET.fromstring(xml_bytes)
                actual = root.find("s:setId", NS)
                if actual is None or actual.get("root", "").lower() != setid.lower():
                    raise ValueError("Response is not the requested SPL document")
                with gzip.open(path, "wb") as out:
                    out.write(xml_bytes)
                meta.update({"sha256": hashlib.sha256(xml_bytes).hexdigest(),
                             "bytes": len(xml_bytes), "title": content(root.find("s:title", NS)),
                             "version": root.find("s:versionNumber", NS).get("value"),
                             "effective_time": root.find("s:effectiveTime", NS).get("value"),
                             "status": "ok"})
                meta.pop("error", None)
                dump(meta_path, meta)
                return "ok"
            except Exception as exc:
                meta["error"] = str(exc)
                if meta.get("http_status") == 404:
                    break
                time.sleep(1 + attempt * 2)
        meta["status"] = "error"
        dump(meta_path, meta)
        return "error"

    counts = collections.Counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for i, result in enumerate(pool.map(fetch, selected), 1):
            counts[result] += 1
            if i % 50 == 0 or i == len(selected):
                print(f"Labels {i}/{len(selected)}: {dict(counts)}", flush=True)


def expand_labels(rows):
    """Retain initial labels; add up to three cited labels for unresolved pairs."""
    with (HERE / "pair-screen.csv").open() as handle:
        screened = list(csv.DictReader(handle))
    targets = {int(r["pair_index"]) for r in screened
               if not r["screening_category"].startswith("indication_")}
    selected = set(json.loads((HERE / "selected-labels.json").read_text()))
    by_label = collections.defaultdict(set)
    needed = {}
    for i in targets:
        labels = cited_labels(rows[i])
        needed[i] = max(0, min(3, len(labels)) - len(labels & selected))
        for label in labels - selected:
            by_label[label].add(i)
    additions = []
    while any(needed.values()) and by_label:
        pending = {i for i, n in needed.items() if n}
        best = max(sorted(by_label), key=lambda k: len(by_label[k] & pending))
        covered = by_label.pop(best) & pending
        if not covered:
            break
        additions.append(best)
        for i in covered:
            needed[i] -= 1
    selected.update(additions)
    dump(HERE / "selected-labels.json", sorted(selected))
    dump(HERE / "expansion.json", {"target_pair_indices": sorted(targets), "added_labels": additions,
                                  "rule": "Up to three cited labels for pairs without indication-name matches after first pass"})
    print(f"Expanded {len(targets)} unresolved pairs with {len(additions)} additional labels", flush=True)


def parse_sections(path):
    with gzip.open(path, "rb") as handle:
        root = ET.parse(handle).getroot()
    sections = []

    def walk(element, inherited="other", ancestors=()):
        group = inherited
        titles = ancestors
        if element.tag == "{urn:hl7-org:v3}section":
            code = element.find("s:code", NS)
            code_value = code.get("code", "") if code is not None else ""
            display = code.get("displayName", "") if code is not None else ""
            title = content(element.find("s:title", NS))
            key = normalized(title + " " + display)
            if code_value in INDICATION_CODES or "indications and usage" in key or "indications usage" in key:
                group = "indication"
            elif code_value in SAFETY_CODES or any(w in key for w in ("warning", "contraindication", "precaution", "adverse reaction")):
                group = "safety"
            titles = ancestors + (title or display,)
            body = content(element.find("s:text", NS))
            if body or title:
                sections.append({"group": group, "code": code_value, "title": " / ".join(titles), "text": body})
        for child in element:
            if child.tag not in {"{urn:hl7-org:v3}text", "{urn:hl7-org:v3}title"}:
                walk(child, group, titles)

    walk(root)
    return sections


def screen():
    rows = json.loads((HERE / "pairs.json").read_text())
    nodes = json.loads((HERE / "nodes.json").read_text())
    alias_file = HERE / "condition-aliases.json"
    alias_data = json.loads(alias_file.read_text()) if alias_file.exists() else {}
    review_file = HERE / "manual-review.json"
    reviews = {r["pair_index"]: r for r in json.loads(review_file.read_text())} if review_file.exists() else {}
    selected = set(json.loads((HERE / "selected-labels.json").read_text()))
    parsed = {}
    for setid in sorted(selected):
        path = HERE / "labels" / f"{setid}.xml.gz"
        if path.exists():
            parsed[setid] = parse_sections(path)
    output = []
    evidence = []
    for i, pair in enumerate(rows):
        names = [pair["condition_name"]] + nodes[pair["object"]].get("synonym", []) + alias_data.get(pair["object"], [])
        terms = sorted({normalized(n) for n in names if isinstance(n, str) and len(normalized(n)) >= 4}, key=lambda t: (-len(t), t))
        # Whole phrases; no fuzzy matching, stemming or invented parent concepts.
        patterns = [(t, re.compile(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])")) for t in terms]
        labels = cited_labels(pair)
        successes = labels & parsed.keys()
        groups = collections.defaultdict(set)
        for setid in sorted(successes):
            for sec in parsed[setid]:
                body = normalized(sec["title"] + " " + sec["text"])
                matches = [(t, pattern.search(body)) for t, pattern in patterns]
                matches = [(t, match) for t, match in matches if match]
                if not matches:
                    continue
                groups[sec["group"]].add(setid)
                term, match = matches[0]
                # Normalized text is intentionally used so offsets are reproducible.
                snippet = body[max(0, match.start() - 200):min(len(body), match.end() + 350)]
                evidence.append({"pair_index": i, "drug": pair["drug_name"], "condition": pair["condition_name"],
                                 "set_id": setid, "section_group": sec["group"], "section_code": sec["code"],
                                 "section_title": sec["title"], "matched_term": term, "excerpt_normalized": snippet,
                                 "label_url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}"})
        if not successes:
            category = "no_label_retrieved"
        elif groups["indication"] and groups["safety"]:
            category = "indication_and_safety_mentions"
        elif groups["indication"]:
            category = "indication_mentions_without_safety_match"
        elif groups["safety"]:
            category = "safety_mentions_without_indication_match"
        elif groups["other"]:
            category = "other_sections_only"
        else:
            category = "no_condition_name_match"
        output.append({"pair_index": i, "drug_id": pair["subject"], "drug_name": pair["drug_name"],
                       "condition_id": pair["object"], "condition_name": pair["condition_name"],
                       "screening_category": category, "cited_labels": len(labels),
                       "selected_labels": len(labels & selected), "retrieved_labels": len(successes),
                       "all_cited_labels_inspected": len(successes) == len(labels),
                       "inspected_set_ids": " | ".join(sorted(successes)),
                       "FDA_application_numbers": " | ".join(pair["multiomics_edge"].get("FDA_regulatory_approvals", [])),
                       "indication_labels": len(groups["indication"]), "safety_labels": len(groups["safety"]),
                       "other_labels": len(groups["other"]), "condition_terms": " | ".join(terms),
                       "multiomics_edge_id": pair["multiomics_edge"]["id"],
                       "drugcentral_edge_id": pair["drugcentral_edge"]["id"],
                       "manual_review": reviews.get(i, {}).get("disposition", "not_reviewed"),
                       "manual_review_notes": reviews.get(i, {}).get("notes", ""),
                       "reviewed_set_ids": " | ".join(reviews.get(i, {}).get("set_ids", []))})
    for name, records in [("pair-screen.csv", output), ("mention-evidence.csv", evidence)]:
        with (HERE / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(records[0]) if records else [])
            writer.writeheader()
            writer.writerows(records)
    summary = {"pairs": len(rows), "unique_cited_labels": len(set().union(*(cited_labels(p) for p in rows))),
               "selected_labels": len(selected), "retrieved_labels": len(parsed),
               "categories": dict(collections.Counter(r["screening_category"] for r in output)),
               "pairs_with_any_retrieved_label": sum(r["retrieved_labels"] > 0 for r in output),
               "pairs_all_cited_labels_inspected": sum(r["all_cited_labels_inspected"] for r in output),
               "pairs_with_warning_section_mentions": len({r["pair_index"] for r in evidence
                                                           if r["section_group"] == "safety" and "warn" in r["section_title"].lower()}),
               "manually_reviewed_pairs": len(reviews),
               "scope": "Automated name-location screening on selected current cited labels; not clinical validation"}
    dump(HERE / "summary.json", summary)
    print(json.dumps(summary, indent=2), flush=True)


def export_evidence():
    """Export a download manifest, focused review queue, and reviewed case inputs."""
    rows = list(csv.DictReader((HERE / "pair-screen.csv").open()))
    pairs = json.loads((HERE / "pairs.json").read_text())
    reviews = json.loads((HERE / "manual-review.json").read_text())
    selected = json.loads((HERE / "selected-labels.json").read_text())
    queue = [r for r in rows if not r["screening_category"].startswith("indication_")
             or r["manual_review"] == "matched_passage_is_adverse_effect_not_indication"]
    with (HERE / "review-queue.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(queue)
    keys = ["set_id", "status", "url", "fallback_url", "retrieved_utc", "version", "effective_time", "title", "sha256", "bytes"]
    with (HERE / "label-manifest.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys, extrasaction="ignore")
        writer.writeheader()
        for sid in selected:
            writer.writerow(json.loads((HERE / "labels" / f"{sid}.json").read_text()))
    cases = []
    for review in reviews:
        labels = []
        for sid in review["set_ids"]:
            labels.append({"set_id": sid,
                           "metadata": json.loads((HERE / "labels" / f"{sid}.json").read_text()),
                           "indication_sections": [s for s in parse_sections(HERE / "labels" / f"{sid}.xml.gz")
                                                   if s["group"] == "indication"]})
        cases.append({"review": review, "graph_pair": pairs[review["pair_index"]], "label_evidence": labels})
    dump(HERE / "reviewed-case-evidence.json", cases)
    print(f"Exported {len(queue)} review-queue rows and {len(cases)} manually reviewed cases")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["extract", "select", "fetch", "screen", "expand", "export"])
    parser.add_argument("--raw", type=Path, default=Path("/home/agonzalez/shepherd/experiments/ultra/data/tier0-1.0.4/raw"))
    parser.add_argument("--coverage", type=int, default=1)
    args = parser.parse_args()
    if args.stage == "extract": extract(args.raw)
    elif args.stage == "select": select_labels(json.loads((HERE / "pairs.json").read_text()), args.coverage)
    elif args.stage == "fetch": fetch_labels()
    elif args.stage == "screen": screen()
    elif args.stage == "expand": expand_labels(json.loads((HERE / "pairs.json").read_text()))
    elif args.stage == "export": export_evidence()
