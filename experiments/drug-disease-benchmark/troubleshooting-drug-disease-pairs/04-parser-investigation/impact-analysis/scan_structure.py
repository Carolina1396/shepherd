"""Scan cited SPL XML for nested warning sections; no DAKP or name matching."""
import argparse
import collections
import concurrent.futures
import csv
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import threading
import time
import xml.etree.ElementTree as ET

from analyze import HERE, NS, SAFETY, cached_path, fetch, save

WARNINGS = {"34066-1", "34071-1", "43685-7"}


def inspect_xml(raw):
    root = ET.fromstring(raw)
    hits = []
    indication_count = 0

    def walk(element, indication_path=None, path=()):
        nonlocal indication_count
        if element.tag == NS + "section":
            code = element.find(NS + "code")
            value = code.get("code", "") if code is not None else ""
            title_node = element.find(NS + "title")
            title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
            path = path + (title or value or "untitled section",)
            # Preserve the exact coded indication definition used in the bug investigation.
            if value == "34067-9":
                indication_count += 1
                indication_path = " / ".join(path)
            elif indication_path is not None:
                warning_code = value in WARNINGS
                warning_heading = bool(re.search(r"\bwarnings?\b", title, re.I))
                if warning_code or warning_heading or value in SAFETY:
                    hits.append({"code": value, "title": title, "path": " / ".join(path),
                                 "indication_path": indication_path,
                                 "warning_code": warning_code, "warning_heading": warning_heading})
        for child in element:
            if child.tag not in {NS + "text", NS + "title"}:
                walk(child, indication_path, path)
    walk(root)
    return root, indication_count, hits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Retrieve every missing cited label")
    args = parser.parse_args()
    pairs = json.loads((HERE / "pairs.json").read_text())
    ids = sorted({sid for row in pairs for sid in row["set_ids"]})
    results = {}; lock = threading.Lock(); next_request = [0.0]
    stop = threading.Event()
    def request_stop(signum, frame):
        stop.set()
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)

    def gate():
        if stop.is_set():
            raise InterruptedError("Scan paused")
        with lock:
            delay = max(0, next_request[0] - time.monotonic())
            next_request[0] = max(time.monotonic(), next_request[0]) + 0.25
        if stop.wait(delay):
            raise InterruptedError("Scan paused")

    def scan(sid):
        record = {"set_id": sid}
        try:
            if stop.is_set():
                raise InterruptedError("Scan paused")
            path = cached_path(sid)
            if path is None:
                if not args.download:
                    return {**record, "status": "not_downloaded"}
                for attempt in range(3):
                    try:
                        path = fetch(sid, request_gate=gate)
                        break
                    except InterruptedError:
                        raise
                    except Exception:
                        if attempt == 2: raise
                        if stop.wait(2 ** attempt):
                            raise InterruptedError("Scan paused")
            raw = gzip.decompress(path.read_bytes())
            root, count, hits = inspect_xml(raw)
            assert root.find(NS + "setId").get("root").lower() == sid
            title = root.find(NS + "title")
            return {**record, "status": "ok", "sha256": hashlib.sha256(raw).hexdigest(),
                    "title": " ".join("".join(title.itertext()).split()) if title is not None else "",
                    "indication_sections": count, "nested_sections": hits,
                    "nested_coded_warning": any(h["warning_code"] for h in hits),
                    "nested_warning_by_code_or_heading": any(h["warning_code"] or h["warning_heading"] for h in hits),
                    "nested_safety": bool(hits)}
        except InterruptedError:
            return {**record, "status": "interrupted"}
        except Exception as exc:
            return {**record, "status": "error", "error": f"{type(exc).__name__}: {exc}"}

    def checkpoint(state):
        ok = [r for r in results.values() if r["status"] == "ok"]
        statuses = collections.Counter(r["status"] for r in results.values())
        summary = {"state": state, "pid": os.getpid(), "target_labels": len(ids),
            "inspected_labels": len(ok), "failed_labels": statuses["error"],
            "not_downloaded": statuses["not_downloaded"], "not_yet_attempted": len(ids)-len(results),
            "labels_with_coded_indications": sum(r["indication_sections"] > 0 for r in ok),
            "labels_with_nested_coded_warnings": sum(r["nested_coded_warning"] for r in ok),
            "labels_with_nested_warnings_by_code_or_heading": sum(r["nested_warning_by_code_or_heading"] for r in ok),
            "labels_with_nested_safety": sum(r["nested_safety"] for r in ok),
            "updated_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        save(HERE / "structure-summary.json", summary)
        save(HERE / "structure-matches.json", [r for r in ok if r["nested_safety"]])
        save(HERE / "structure-failures.json", [r for r in results.values() if r["status"] == "error"])
        print(json.dumps(summary), flush=True)

    # Report cached coverage before spending time on missing documents.
    cached = [sid for sid in ids if cached_path(sid) is not None]
    missing = sorted(set(ids) - set(cached))
    checkpoint("running")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for group in [cached, missing]:
            if stop.is_set(): break
            futures = {pool.submit(scan, sid): sid for sid in group}
            for future in concurrent.futures.as_completed(futures):
                row = future.result()
                if row["status"] != "interrupted":
                    results[row["set_id"]] = row
                if stop.is_set():
                    for pending in futures:
                        pending.cancel()
                    break
                if len(results) % 500 == 0:
                    checkpoint("running")
            checkpoint("running")
    save(HERE / "structure-inventory.json", [results[sid] for sid in sorted(results)])
    checkpoint("paused" if stop.is_set() else "finished")


if __name__ == "__main__":
    main()
