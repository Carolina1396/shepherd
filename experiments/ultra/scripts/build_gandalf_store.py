"""Prepare, build, and verify Gandalf stores using the existing Gandalf environment.

Run stages in order: prepare, sample, verify-sample, full, verify-full.
Gandalf itself is not modified. All generated files stay under this experiment.
"""

import argparse
from collections import Counter
import hashlib
import json
import logging
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "tier0-20260621"
OUT = ROOT / "output" / "gandalf"
RAW = DATA / "raw"
SAMPLE = OUT / "sample-input"


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def prepare():
    import orjson

    inventory = json.loads((ROOT / "output/overview/archive_inventory.json").read_text())
    RAW.mkdir(parents=True, exist_ok=True)
    expected = {m["name"]: m["bytes"] for m in inventory["members"]
                if m["name"] in {"nodes.jsonl", "edges.jsonl"}}
    if not all((RAW / n).exists() and (RAW / n).stat().st_size == size
               for n, size in expected.items()):
        archive = DATA / "translator_kg.tar.zst"
        with archive.open("rb") as stream:
            assert hashlib.file_digest(stream, "sha256").hexdigest() == inventory["archive_sha256"]
        process = subprocess.Popen(["zstd", "-dc", str(archive)], stdout=subprocess.PIPE)
        try:
            with tarfile.open(fileobj=process.stdout, mode="r|") as tar:
                for member in tar:
                    if member.name in expected and member.isfile():
                        target = RAW / member.name
                        temporary = target.with_suffix(".partial")
                        with tar.extractfile(member) as source, temporary.open("wb") as dest:
                            shutil.copyfileobj(source, dest, 4 * 1024 * 1024)
                        assert temporary.stat().st_size == expected[member.name]
                        temporary.replace(target)
                        print(f"Extracted {target.name}", flush=True)
            # Drain trailing archive padding before checking zstd's exit status.
            while process.stdout.read(4 * 1024 * 1024):
                pass
            assert process.wait() == 0
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()

    SAMPLE.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    selected = Counter()
    endpoints = set()
    levels = Counter()
    with (RAW / "edges.jsonl").open("rb") as source, (SAMPLE / "edges.jsonl").open("wb") as dest:
        for number, line in enumerate(source, 1):
            edge = orjson.loads(line)
            predicate = edge["predicate"]
            counts[predicate] += 1
            levels[edge.get("knowledge_level")] += 1
            if selected[predicate] < 100:
                dest.write(line)
                selected[predicate] += 1
                endpoints.update((edge["subject"], edge["object"]))
            if number % 5_000_000 == 0:
                print(f"Scanned {number:,} edges", flush=True)
    node_count = 0
    found = set()
    with (RAW / "nodes.jsonl").open("rb") as source, (SAMPLE / "nodes.jsonl").open("wb") as dest:
        for line in source:
            node_count += 1
            node = orjson.loads(line)
            if node["id"] in endpoints:
                dest.write(line)
                found.add(node["id"])
    assert found == endpoints, "Sample has endpoints missing from nodes.jsonl"
    write_json(OUT / "preparation.json", {
        "release": "2026_06_21", "archive_sha256": inventory["archive_sha256"],
        "sample_method": "First 100 edges per exact predicate in archive order; setup check, not an evaluation dataset",
        "raw_nodes": node_count, "raw_edges": sum(counts.values()),
        "predicate_counts": dict(counts), "knowledge_level_counts": dict(levels),
        "sample_nodes": len(endpoints), "sample_edges": sum(selected.values()),
        "sample_predicate_counts": dict(selected),
    })


def build(which):
    from gandalf import build_graph_from_jsonl
    from gandalf.normalize import _get_bmt
    import gandalf

    source = SAMPLE if which == "sample" else RAW
    destination = OUT / f"{which}-store"
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite existing store: {destination}")
    # Fail visibly if the pinned schema cannot load instead of silently using
    # the normalizer's offline fallback qualifier list for a permanent build.
    _get_bmt()
    started = time.perf_counter()
    graph = build_graph_from_jsonl(str(source / "edges.jsonl"), str(source / "nodes.jsonl"))
    built = time.perf_counter()
    graph.save_mmap(destination)
    repo = Path(gandalf.__file__).resolve().parents[1]
    write_json(OUT / f"{which}-build.json", {
        "gandalf_path": str(repo),
        "gandalf_commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "build_seconds": built - started, "save_seconds": time.perf_counter() - built,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "nodes": graph.num_nodes, "edges": len(graph.fwd_targets),
        "store_bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file()),
    })


def verify(which):
    import numpy as np
    from gandalf import CSRGraph
    from gandalf.search.edge_constraints import EdgeConstraints

    started = time.perf_counter()
    graph = CSRGraph.load_mmap(OUT / f"{which}-store", mmap_mode="r")
    load_seconds = time.perf_counter() - started
    preparation = json.loads((OUT / "preparation.json").read_text())
    expected = preparation["sample_predicate_counts" if which == "sample" else "predicate_counts"]
    counts = np.bincount(graph.fwd_predicates, minlength=len(graph.predicate_to_idx))
    assert {p: int(counts[i]) for p, i in graph.predicate_to_idx.items()} == expected
    assert int(graph.fwd_offsets[-1]) == len(graph.fwd_targets) == int(graph.rev_offsets[-1])
    assert len(graph.rev_sources) == len(graph.fwd_targets)
    if which == "full":
        levels = Counter()
        pool_counts = np.bincount(graph.edge_properties._kl_at_idx)
        for i, count in enumerate(pool_counts):
            levels[graph.edge_properties._kl_at_pool[i][0]] += int(count)
        assert dict(levels) == preparation["knowledge_level_counts"]
    checked = 0
    # Locate each sampled physical edge by ID, preserving parallel reports.
    for line in (SAMPLE / "edges.jsonl").open():
        raw = json.loads(line)
        src, dst = graph.get_node_idx(raw["subject"]), graph.get_node_idx(raw["object"])
        assert dst in graph.neighbors(src, raw["predicate"])
        assert src in graph.incoming_neighbors(dst, raw["predicate"])
        lo, hi = int(graph.fwd_offsets[src]), int(graph.fwd_offsets[src + 1])
        positions = np.flatnonzero((graph.fwd_targets[lo:hi] == dst) &
                                  (graph.fwd_predicates[lo:hi] == graph.predicate_to_idx[raw["predicate"]])) + lo
        matches = [int(i) for i in positions if graph.get_edge_id(int(i)) == raw["id"]]
        assert len(matches) == 1, raw["id"]
        i = matches[0]
        props = graph.get_edge_properties_by_index(i)
        assert props["knowledge_level"] == raw.get("knowledge_level", "not_provided")
        assert props["agent_type"] == raw.get("agent_type", "not_provided")
        sources = {s["resource_id"] for s in props["sources"] if s["resource_role"] == "primary_knowledge_source"}
        if raw.get("sources"):
            original = {s["resource_id"] for s in raw["sources"]
                        if s["resource_role"] == "primary_knowledge_source"}
        else:
            value = raw["primary_knowledge_source"]
            original = set(value if isinstance(value, list) else [value])
        assert sources == original
        if "publications" in raw:
            attributes = {a["attribute_type_id"]: a["value"] for a in props["attributes"]}
            assert attributes["biolink:publications"] == raw["publications"]
        for field, values in [("sources", sorted(sources)), ("knowledge_level", [props["knowledge_level"]])]:
            for behavior in ("ALLOW", "DENY"):
                constraint = {"behavior": behavior, "values": values}
                if field == "sources":
                    constraint["primary_only"] = True
                rule = EdgeConstraints.parse({"constraints": {field: constraint}})
                assert rule.permits(graph, props, i) == (behavior == "ALLOW")
        checked += 1
    for line in (SAMPLE / "nodes.jsonl").open():
        raw = json.loads(line)
        props = graph.get_all_node_properties(graph.get_node_idx(raw["id"]))
        categories = raw.get("category", raw.get("categories", []))
        assert set(props["categories"]) == set(categories if isinstance(categories, list) else [categories])
    if which == "sample":
        assert graph.num_nodes == preparation["sample_nodes"]
    # Gandalf indexes edge endpoints, so raw isolated nodes may be absent.
    write_json(OUT / f"{which}-verification.json", {
        "passed": True, "load_seconds": load_seconds, "nodes": graph.num_nodes,
        "edges": len(graph.fwd_targets), "predicates": len(expected),
        "sampled_edges_checked": checked,
        "checks": (["all knowledge-level counts"] if which == "full" else []) +
                  ["all predicate counts", "CSR edge counts", "sample edge IDs and endpoints",
                   "incoming/outgoing neighbors", "primary sources", "knowledge levels", "agent types",
                   "source and knowledge-level allow/deny", "publications", "sample node categories"],
        "raw_nodes_not_indexed": preparation["raw_nodes"] - graph.num_nodes if which == "full" else None,
    })
    print(f"Verified {which}: {graph.num_nodes:,} nodes, {len(graph.fwd_targets):,} edges", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "sample", "verify-sample", "full", "verify-full"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("gandalf.loader").setLevel(logging.DEBUG)
    if args.stage == "prepare":
        prepare()
    elif args.stage.startswith("verify-"):
        verify(args.stage.removeprefix("verify-"))
    else:
        # Upstream creates temporary LMDB stores; keep and clean only our own
        # build scratch files after the saved store has been written.
        with tempfile.TemporaryDirectory(prefix="build-scratch-", dir=OUT) as scratch:
            previous_tempdir = tempfile.tempdir
            try:
                tempfile.tempdir = scratch
                build(args.stage)
            finally:
                tempfile.tempdir = previous_tempdir
