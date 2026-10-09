"""Rerun the frozen full-graph ULTRA 3g study, retaining both directions' outputs."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
PREPARED = ROOT / "output/full-graph-ultra/run_001"
UPSTREAM = ROOT / "vendor/ULTRA"
sys.path.insert(0, str(ROOT / "scripts"))
from full_graph_common import digest, filtered_rank, hidden_pair_mask, save, split_pairs

DIRECTIONS = {"disease_to_drug": ("disease", "drug"),
              "drug_to_disease": ("drug", "disease")}


def query_groups(labels, direction):
    query, _ = DIRECTIONS[direction]
    grouped = defaultdict(list)
    for row in labels:
        if row["split"] == "test":
            grouped[row[f"{query}_index"]].append(row)
    return dict(sorted(grouped.items(), key=lambda item: item[1][0][query]))


def known_answers(labels, candidates, direction):
    query, answer = DIRECTIONS[direction]
    positions = {r["index"]: i for i, r in enumerate(candidates)}
    known = defaultdict(set)
    for row in labels:
        known[row[f"{query}_index"]].add(positions[row[f"{answer}_index"]])
    return positions, known


def summarize(rows):
    ranks = np.array([row["rank"] for row in rows], dtype=float)
    return {"answers": len(rows), "mrr": float(np.mean(1 / ranks)),
            **{f"hits_at_{k}": float(np.mean(ranks <= k)) for k in (1, 3, 10)},
            "top_10_answers": int(np.sum(ranks <= 10))}


def read_score(path, idx, size):
    metadata = json.loads(path.with_suffix(".json").read_text())
    if metadata["query_index"] != idx or metadata["sha256"] != digest(path):
        raise ValueError(f"Score integrity check failed: {path}")
    with np.load(path, allow_pickle=False) as data:
        scores = data["scores"]
        if int(data["query_index"]) != idx or scores.shape != (size,) or not np.isfinite(scores).all():
            raise ValueError(f"Invalid scores: {path}")
    return scores


def collect_results(output, labels, candidates):
    """Verify saved scores; publish final metrics only when both directions finish."""
    progress, metrics = {}, {}
    for direction in DIRECTIONS:
        directory = output / direction
        directory.mkdir(exist_ok=True)
        groups = query_groups(labels, direction)
        positions, known = known_answers(labels, candidates[direction], direction)
        answer = DIRECTIONS[direction][1]
        rows, hashes = [], {}
        for idx, targets in groups.items():
            path = directory / "scores" / f"{idx}.npz"
            if not path.exists():
                continue
            scores = read_score(path, idx, len(positions))
            hashes[path.name] = digest(path)
            keep = np.ones(len(scores), dtype=bool)
            keep[list(known[idx])] = False
            competitors = np.sort(scores[keep])
            for target in targets:
                position = positions[target[f"{answer}_index"]]
                rank = filtered_rank(scores, position, known[idx])
                assert rank == 1 + len(competitors) - np.searchsorted(competitors, scores[position], side="left")
                rows.append({"drug": target["drug"], "disease": target["disease"], "rank": rank})
        with (directory / "answer_ranks.csv").open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["drug", "disease", "rank"])
            writer.writeheader()
            writer.writerows(rows)
        progress[direction] = {"scored_queries": len(hashes), "total_queries": len(groups),
                               "evaluated_pairs": len(rows), "complete": len(hashes) == len(groups)}
        if progress[direction]["complete"]:
            assert len(rows) == sum(map(len, groups.values()))
            metrics[direction] = {**summarize(rows), "candidates_per_query": len(positions),
                                  "score_files_sha256": hashes,
                                  "answer_ranks_sha256": digest(directory / "answer_ranks.csv")}
    complete = all(p["complete"] for p in progress.values())
    if not complete and (output / "metrics.json").exists():
        raise ValueError("A completed run is missing score files; restore them or use a new directory")
    save(output / "progress.json", {"complete": complete, "directions": progress})
    if complete:
        left, right = (metrics[d] for d in DIRECTIONS)
        assert left["answers"] == right["answers"]
        combined = {"unique_pairs": left["answers"],
                    "directional_answers": left["answers"] + right["answers"],
                    **{k: (left[k] + right[k]) / 2 for k in ("mrr", "hits_at_1", "hits_at_3", "hits_at_10")},
                    "top_10_directional_answers": left["top_10_answers"] + right["top_10_answers"]}
        save(output / "metrics.json", {"complete": True, "split": "test", "training_epochs": 0,
                                       "units": "fractions", "directions": metrics, "combined": combined,
                                       "settings_sha256": digest(output / "settings.json")})
    return complete


def validate_resume(path, expected):
    if json.loads(path.read_text()) != expected:
        raise ValueError("Resume settings changed; use a new output directory")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New run directory; original study inputs are read-only")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-new-queries-per-direction", type=int, help="Smoke-test limit; incomplete runs never publish final metrics")
    args = parser.parse_args()
    if args.batch_size < 1 or (args.max_new_queries_per_direction is not None and args.max_new_queries_per_direction < 1):
        parser.error("Batch size and query limit must be positive")
    output = args.output.resolve()
    if output.exists() and not args.resume:
        parser.error(f"Refusing to overwrite {output}; use --resume or a new directory")
    if args.resume and not (output / "settings.json").is_file():
        parser.error("Resume requires an existing run with settings.json")

    import torch
    from torch_geometric.data import Data
    sys.path.insert(0, str(UPSTREAM))
    from ultra.models import Ultra

    assert torch.cuda.is_available(), "Use scripts/gpu_python.sh with the GPU environment"
    torch.set_num_threads(8)
    torch.manual_seed(1024)
    study = json.loads((HERE / "studies/full_graph_ultra3g_bidirectional.json").read_text())
    preparation = json.loads((PREPARED / "preparation.json").read_text())
    assert digest(PREPARED / "config.json") == study["graph"]["prepared_config_sha256"] == preparation["config_sha256"]
    for name, expected in study["graph"]["input_file_sha256"].items():
        assert expected == preparation["dataset_sha256"][name] == digest(PREPARED / "data" / name), name
    relation = json.loads((PREPARED / "relation_graph.json").read_text())
    assert relation["triples_sha256"] == preparation["dataset_sha256"]["triples.npy"]
    assert relation["sha256"] == study["graph"]["relation_graph_sha256"] == digest(PREPARED / "relation_graph.pt")
    checkpoint = ROOT / study["model"]["checkpoint"]
    assert digest(checkpoint) == study["model"]["checkpoint_sha256"]
    assert subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip() == study["model"]["ultra_commit"]
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    labels = json.loads((PREPARED / "data/labels.json").read_text())
    assert [(r["drug"], r["disease"], r["split"]) for r in labels] == split_pairs({(r["drug"], r["disease"]) for r in labels}, 731)
    sources = [Path(__file__), HERE / "reference_candidates.py", ROOT / "scripts/full_graph_common.py"]
    settings = {"checkpoint_sha256": digest(checkpoint), "ultra_commit": study["model"]["ultra_commit"],
                "prepared_dataset_sha256": preparation["dataset_sha256"], "relation_graph_sha256": relation["sha256"],
                "source_sha256": {p.name: digest(p) for p in sources}, "split": "test", "training_epochs": 0,
                "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                "batch_size": args.batch_size, "seed": 1024, "ties": "pessimistic"}
    if not args.resume:
        output.mkdir(parents=True)
        subprocess.run([str(ROOT / ".venv/bin/python"), "-B", str(HERE / "reference_candidates.py"),
                        "--output", str(output / "candidates.json")], check=True)
    candidates = json.loads((output / "candidates.json").read_text())
    settings["candidates_sha256"] = digest(output / "candidates.json")
    if args.resume:
        validate_resume(output / "settings.json", settings)
    else:
        save(output / "settings.json", settings)
        for path in sources:
            shutil.copyfile(path, output / path.name)
        shutil.copyfile(HERE / "studies/full_graph_ultra3g_bidirectional.json", output / "original_study.json")
    # Also verify existing score checksums before spending GPU time on a resume.
    if collect_results(output, labels, candidates):
        print("Both directions already complete; saved ranks and metrics verified", flush=True)
        return

    triples = np.load(PREPARED / "data/triples.npy")
    n, p = study["graph"]["nodes"], study["graph"]["original_relations"]
    hidden = {(r["drug_index"], r["disease_index"]) for r in labels if r["split"] != "visible"}
    assert not hidden_pair_mask(triples[:, 0], triples[:, 2], hidden, n).any()
    ei = torch.from_numpy(triples[:, [0, 2]].T.copy())
    et = torch.from_numpy(triples[:, 1].copy())
    graph = Data(edge_index=torch.cat([ei, ei.flip(0)], 1), edge_type=torch.cat([et, et + p]), num_nodes=n, num_relations=2*p)
    graph.relation_graph = torch.load(PREPARED / "relation_graph.pt", map_location="cpu")
    del triples, ei, et
    graph = graph.to("cuda:0")
    common = {"input_dim": 64, "hidden_dims": [64]*6, "message_func": "distmult", "aggregate_func": "sum", "short_cut": True, "layer_norm": True}
    model = Ultra(rel_model_cfg={"class": "RelNBFNet", **common}, entity_model_cfg={"class": "EntityNBFNet", **common})
    model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
    model = model.cuda().eval()
    target_relation = json.loads((PREPARED / "data/predicates.json").read_text()).index("biolink:treats")
    for direction in DIRECTIONS:
        groups = query_groups(labels, direction)
        directory = output / direction / "scores"
        directory.mkdir(exist_ok=True)
        missing = [idx for idx in groups if not (directory / f"{idx}.npz").exists()]
        if args.max_new_queries_per_direction is not None:
            missing = missing[:args.max_new_queries_per_direction]
        indices = torch.tensor([r["index"] for r in candidates[direction]], device="cuda:0")
        for offset in range(0, len(missing), args.batch_size):
            queries = missing[offset:offset + args.batch_size]
            batch = torch.empty((len(queries), len(indices), 3), dtype=torch.long, device="cuda:0")
            anchors = torch.tensor(queries, device="cuda:0")[:, None]
            if direction == "disease_to_drug":
                batch[:, :, 0], batch[:, :, 1] = indices, anchors
            else:
                batch[:, :, 0], batch[:, :, 1] = anchors, indices
            batch[:, :, 2] = target_relation
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.inference_mode():
                scores = model(graph, batch)
            torch.cuda.synchronize()
            seconds = time.perf_counter() - started
            peak = torch.cuda.max_memory_allocated()
            scores = scores.cpu().numpy()
            assert scores.shape == (len(queries), len(indices)) and np.isfinite(scores).all()
            for idx, values in zip(queries, scores):
                path = directory / f"{idx}.npz"
                temporary = path.with_suffix(".tmp")
                with temporary.open("wb") as stream:
                    np.savez(stream, scores=values, query_index=idx)
                save(path.with_suffix(".json"), {"query_index": idx, "sha256": digest(temporary),
                     "batch_query_indices": queries, "batch_seconds": seconds, "amortized_query_seconds": seconds / len(queries),
                     "batch_peak_allocated_bytes": peak})
                temporary.replace(path)
            if offset == 0 or (offset + len(queries)) % 40 == 0 or offset + len(queries) == len(missing):
                print(f"{direction}: {offset + len(queries)}/{len(missing)} new queries", flush=True)
        collect_results(output, labels, candidates)
    complete = collect_results(output, labels, candidates)
    print(f"{'Complete' if complete else 'Incomplete; resume to finish'}: {output}", flush=True)
    if complete:
        report = json.loads((output / "metrics.json").read_text())
        print(json.dumps(report["combined"], indent=2), flush=True)


if __name__ == "__main__":
    main()
