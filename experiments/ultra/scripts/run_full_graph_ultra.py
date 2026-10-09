"""Resumable held-out pretrained ULTRA scoring on the full masked graph."""
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
import torch
from torch_geometric.data import Data
from full_graph_common import digest, filtered_rank, save, summarize

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/ULTRA"
sys.path.insert(0, str(UPSTREAM))
from ultra import tasks, util
from ultra.models import Ultra


def collect_results(prepared, output, labels, candidates, degree, split="validation"):
    positions = {row["index"]: i for i, row in enumerate(candidates)}
    known = defaultdict(set)
    by_disease = defaultdict(list)
    for row in labels:
        known[row["disease_index"]].add(positions[row["drug_index"]])
        if row["split"] == split:
            by_disease[row["disease_index"]].append(row)
    answers, timings = [], []
    for idx, rows in sorted(by_disease.items()):
        path = output / "scores" / f"{idx}.npz"
        if not path.exists():
            continue
        with np.load(path, allow_pickle=False) as data:
            scores = data["scores"]
            assert scores.shape == (len(candidates),) and np.isfinite(scores).all()
            assert int(data["disease_index"]) == idx
            timings.append(float(data["seconds"]))
            for row in rows:
                target = positions[row["drug_index"]]
                answers.append({**row, "ultra_rank": filtered_rank(scores, target, known[idx]),
                                "baseline_rank": filtered_rank(degree, target, known[idx])})
    with (output / "answer_ranks.csv").open("w", newline="") as stream:
        if answers:
            writer = csv.DictWriter(stream, fieldnames=list(answers[0]))
            writer.writeheader()
            writer.writerows(answers)
    progress = {"split": split, "scored_diseases": len(timings),
                f"total_{split}_diseases": len(by_disease), "evaluated_pairs": len(answers),
                f"total_{split}_pairs": sum(map(len, by_disease.values())),
                "complete": len(timings) == len(by_disease),
                "inference_seconds_completed": sum(timings)}
    save(output / "progress.json", progress)
    if progress["complete"]:
        report = {**progress, "ultra": summarize(answers, "ultra_rank"),
                  "degree_baseline": summarize(answers, "baseline_rank"),
                  "candidates_per_disease": len(candidates), "training_epochs": 0,
                  "test_metrics_computed": split == "test", "coverage": 1.0,
                  "filter": "All known explicit Drug-Disease treats pairs across all splits; rank filtering only",
                  "ties": "pessimistic", "preparation_sha256": digest(prepared / "preparation.json"),
                  "config_sha256": digest(prepared / "config.json"),
                  "answer_ranks_sha256": digest(output / "answer_ranks.csv"),
                  "score_files_sha256": {p.name: digest(p) for p in sorted((output / "scores").glob("*.npz"))},
                  "subgroups": {}}
        for supported in (True, False):
            group = [r for r in answers if r["disease_has_visible_treatment"] == supported]
            report["subgroups"]["disease_with_visible_treatment" if supported else "disease_without_visible_treatment"] = {
                "ultra": summarize(group, "ultra_rank"), "degree_baseline": summarize(group, "baseline_rank")}
        reuse_path = output / "reused_validation_scores.json"
        if reuse_path.exists():
            reused = json.loads(reuse_path.read_text())
            report["reused_validation_query_scores"] = len(reused["files"])
            report["new_query_scores"] = len(timings) - len(reused["files"])
            report["new_inference_seconds"] = sum(timings) - reused["original_inference_seconds"]
            report["reuse_manifest_sha256"] = digest(reuse_path)
        save(output / "metrics.json", report)
        print(json.dumps({k: v for k, v in report.items() if k != "score_files_sha256"}, indent=2), flush=True)
    return progress


def reuse_validation_scores(prepared, output, diseases, settings):
    """Reuse identical disease queries only after checking data/model provenance."""
    manifest = output / "reused_validation_scores.json"
    if manifest.exists():
        saved = json.loads(manifest.read_text())
        for filename, expected in saved["files"].items():
            assert digest(output / "scores" / filename) == expected
        return
    source = prepared / "validation"
    previous = json.loads((source / "settings.json").read_text())
    metrics = json.loads((source / "metrics.json").read_text())
    assert previous["split"] == "validation" and metrics["complete"]
    for name in ("config_sha256", "preparation_sha256", "common_sha256", "checkpoint_sha256",
                 "ultra_commit", "torch", "cuda", "gpu", "batch_size", "training_epochs"):
        assert previous[name] == settings[name], f"Cannot reuse scores: {name} differs"
    reused, seconds = {}, 0.0
    for _, idx in diseases:
        filename = f"{idx}.npz"
        if filename not in metrics["score_files_sha256"]:
            continue
        expected = metrics["score_files_sha256"][filename]
        assert digest(source / "scores" / filename) == expected
        destination = output / "scores" / filename
        if destination.exists():
            assert digest(destination) == expected
        else:
            shutil.copyfile(source / "scores" / filename, destination)
        reused[filename] = expected
        with np.load(destination, allow_pickle=False) as data:
            assert int(data["disease_index"]) == idx
            seconds += float(data["seconds"])
    save(manifest, {"files": reused, "original_inference_seconds": seconds,
                   "validation_metrics_sha256": digest(source / "metrics.json"),
                   "validation_settings_sha256": digest(source / "settings.json"),
                   "reason": "Identical disease query, candidates, masked graph, checkpoint and inference settings; only evaluated answer pairs change"})
    print(f"Reused {len(reused)} identical validation disease queries", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "output/full-graph-ultra/run_001")
    parser.add_argument("--max-new-diseases", type=int, help="Limit new queries for a benchmark; not a final metric")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--summarize-only", action="store_true")
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--reuse-validation-scores", action="store_true")
    args = parser.parse_args()
    if args.max_new_diseases is not None and args.max_new_diseases < 1:
        parser.error("max-new-diseases must be positive")
    prepared = args.dataset.resolve()
    if args.reuse_validation_scores and args.split != "test":
        parser.error("Validation score reuse applies only to test evaluation")
    output = prepared / args.split
    if output.exists() and not args.resume:
        parser.error(f"{args.split} output exists; use --resume")
    config = json.loads((prepared / "config.json").read_text())
    manifest = json.loads((prepared / "preparation.json").read_text())
    assert digest(prepared / "config.json") == manifest["config_sha256"]
    for name, expected in manifest["dataset_sha256"].items():
        assert digest(prepared / "data" / name) == expected, name
    labels = json.loads((prepared / "data/labels.json").read_text())
    candidates = json.loads((prepared / "data/candidates.json").read_text())
    degree = np.load(prepared / "data/candidate_degree.npy")
    if args.summarize_only:
        assert output.is_dir()
        collect_results(prepared, output, labels, candidates, degree, args.split)
        return
    assert torch.cuda.is_available()
    assert config["training_epochs"] == 0
    checkpoint = ROOT / config["checkpoint"]
    assert digest(checkpoint) == config["checkpoint_sha256"]
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    assert subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip() == config["ultra_commit"]
    settings = {"config_sha256": digest(prepared / "config.json"),
                "preparation_sha256": digest(prepared / "preparation.json"),
                "runner_sha256": digest(Path(__file__)),
                "common_sha256": digest(Path(__file__).with_name("full_graph_common.py")),
                "checkpoint_sha256": digest(checkpoint), "ultra_commit": config["ultra_commit"],
                "torch": torch.__version__, "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(0), "batch_size": 1,
                "training_epochs": 0, "split": args.split,
                "reuse_validation_scores": args.reuse_validation_scores}
    if output.exists():
        assert json.loads((output / "settings.json").read_text()) == settings, "Resume settings changed"
        if (output / "metrics.json").exists():
            print(f"{args.split} already complete", flush=True)
            return
    else:
        (output / "scores").mkdir(parents=True)
        save(output / "settings.json", settings)
        for name in ("run_full_graph_ultra.py", "full_graph_common.py"):
            shutil.copyfile(Path(__file__).parent / name, output / name)
    diseases = sorted({(r["disease"], r["disease_index"]) for r in labels if r["split"] == args.split})
    if args.reuse_validation_scores:
        reuse_validation_scores(prepared, output, diseases, settings)
    torch.set_num_threads(8)
    torch.manual_seed(1024)
    setup_started = time.perf_counter()
    triples = torch.from_numpy(np.load(prepared / "data/triples.npy"))
    predicates = json.loads((prepared / "data/predicates.json").read_text())
    p = len(predicates)
    edges = triples[:, [0, 2]].T.contiguous()
    graph = Data(edge_index=torch.cat([edges, edges.flip(0)], dim=1),
                 edge_type=torch.cat([triples[:, 1], triples[:, 1] + p]),
                 num_nodes=config["num_nodes"], num_relations=2 * p)
    del edges, triples
    relation_cache = prepared / "relation_graph.pt"
    if relation_cache.exists():
        cache_info = json.loads((prepared / "relation_graph.json").read_text())
        assert cache_info["sha256"] == digest(relation_cache)
        assert cache_info["triples_sha256"] == manifest["dataset_sha256"]["triples.npy"]
        graph.relation_graph = torch.load(relation_cache, map_location="cpu")
    else:
        print(f"Building upstream relation graph from {graph.num_edges:,} directed/inverse edges", flush=True)
        graph = tasks.build_relation_graph(graph)
        torch.save(graph.relation_graph, relation_cache)
        save(prepared / "relation_graph.json", {"sha256": digest(relation_cache),
             "triples_sha256": manifest["dataset_sha256"]["triples.npy"], "ultra_commit": config["ultra_commit"]})
    graph = graph.to("cuda:0")
    cfg = util.load_config(str(UPSTREAM / "config/transductive/inference.yaml"), context={
        "dataset": "full-graph", "gpus": "[0]", "epochs": 0, "bpe": "null", "ckpt": str(checkpoint)})
    model = Ultra(rel_model_cfg=cfg.model.relation_model, entity_model_cfg=cfg.model.entity_model)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
    model = model.cuda().eval()
    from ultra.rspmm.rspmm import generalized_rspmm  # Finish any kernel load before timing.
    torch.cuda.synchronize()
    print(f"Graph ready on {torch.cuda.get_device_name(0)} in {time.perf_counter() - setup_started:.1f}s", flush=True)
    candidate_indices = torch.tensor([r["index"] for r in candidates], device="cuda:0")
    batch = torch.empty((1, len(candidates), 3), dtype=torch.long, device="cuda:0")
    batch[0, :, 0] = candidate_indices
    batch[0, :, 2] = predicates.index("biolink:treats")
    new = 0
    for number, (disease, idx) in enumerate(diseases, 1):
        destination = output / "scores" / f"{idx}.npz"
        if destination.exists():
            continue
        batch[0, :, 1] = idx
        torch.cuda.reset_peak_memory_stats()
        tick = time.perf_counter()
        with torch.no_grad():
            scores = model(graph, batch).squeeze(0)
        torch.cuda.synchronize()
        seconds = time.perf_counter() - tick
        scores = scores.cpu().numpy()
        assert scores.shape == (len(candidates),) and np.isfinite(scores).all()
        temporary = destination.with_suffix(".tmp")
        with temporary.open("wb") as stream:
            np.savez(stream, scores=scores, disease_index=idx, seconds=seconds)
        temporary.replace(destination)
        new += 1
        if not (output / "benchmark.json").exists():
            benchmark = {"disease": disease, "seconds": seconds, "nodes": graph.num_nodes,
                         "edges_with_inverses": graph.num_edges, "candidate_drugs": len(candidates),
                         "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
                         "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(),
                         "rough_total_inference_hours_at_first_query_rate": seconds * len(diseases) / 3600,
                         "includes_first_query_warmup": True}
            save(output / "benchmark.json", benchmark)
            print(json.dumps(benchmark, indent=2), flush=True)
        print(f"{number}/{len(diseases)} {disease}: {seconds:.2f}s", flush=True)
        if new % 10 == 0:
            save(output / "progress.json", {"split": args.split, "complete": False,
                 "scored_diseases": len(list((output / "scores").glob("*.npz"))),
                 f"total_{args.split}_diseases": len(diseases), "last_disease": disease})
        if args.max_new_diseases is not None and new >= args.max_new_diseases:
            break
    collect_results(prepared, output, labels, candidates, degree, args.split)


if __name__ == "__main__":
    main()
