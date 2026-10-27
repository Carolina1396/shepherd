"""Experiment 6: score unchanged test pairs without any direct Drug-Disease edges."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import torch
from torch_geometric.data import Data

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "pilot"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "vendor/ULTRA"))
from full_graph_common import digest, save
from finetune.run import evaluate
from ultra import tasks
from ultra.models import Ultra


def direct_drug_disease_mask(triples, drug, disease):
    """Match either direction and every predicate, including multi-category nodes."""
    h, t = triples[:, 0], triples[:, 2]
    return (drug[h] & disease[t]) | (disease[h] & drug[t])


def prepare(source, output, categories, num_nodes, predicates):
    drug = np.zeros(num_nodes, dtype=bool)
    disease = np.zeros(num_nodes, dtype=bool)
    drug[[r["index"] for r in categories["disease_to_drug"]]] = True
    disease[[r["index"] for r in categories["drug_to_disease"]]] = True
    data = output / "data"
    data.mkdir(exist_ok=True)
    manifest_path = output / "preparation.json"
    triples = np.load(source / "data/triples.npy", mmap_mode="r")
    if manifest_path.exists():
        info = json.loads(manifest_path.read_text())
        assert info["source_triples_sha256"] == digest(source / "data/triples.npy")
        assert info["categories_sha256"] == digest(output / "categories.json")
        assert info["triples_sha256"] == digest(data / "triples.npy")
        masked = np.load(data / "triples.npy", mmap_mode="r")
        assert len(masked) == info["remaining_connections"]
        for start in range(0, len(masked), 1_000_000):
            assert not direct_drug_disease_mask(masked[start:start+1_000_000], drug, disease).any()
        return info
    tick = time.perf_counter()
    keep = np.ones(len(triples), dtype=bool)
    removed = Counter()
    for start in range(0, len(triples), 1_000_000):
        chunk = triples[start:start+1_000_000]
        mask = direct_drug_disease_mask(chunk, drug, disease)
        keep[start:start+len(chunk)] = ~mask
        counts = np.bincount(chunk[mask, 1], minlength=len(predicates))
        removed.update({predicates[i]: int(n) for i, n in enumerate(counts) if n})
    masked = triples[keep]
    assert not direct_drug_disease_mask(masked, drug, disease).any()
    path = data / "triples.npy"
    with path.with_suffix(".tmp").open("wb") as stream:
        np.save(stream, masked)
    path.with_suffix(".tmp").replace(path)
    active = np.zeros(num_nodes, dtype=bool)
    active[masked[:, 0]] = True
    active[masked[:, 2]] = True
    source_active = np.zeros(num_nodes, dtype=bool)
    source_active[triples[:, 0]] = True
    source_active[triples[:, 2]] = True
    for name in ["labels.json", "candidates.json", "predicates.json"]:
        shutil.copyfile(source / "data" / name, data / name)
    info = {"num_nodes": num_nodes, "source_connections": len(triples),
            "removed_connections": int((~keep).sum()), "remaining_connections": len(masked),
            "edges_with_inverses": 2*len(masked), "removed_by_predicate": dict(sorted(removed.items())),
            "drug_nodes": int(drug.sum()), "disease_nodes": int(disease.sum()),
            "isolated_nodes_after": int((~active).sum()), "newly_isolated_nodes": int((source_active & ~active).sum()),
            "isolated_drugs_after": int((drug & ~active).sum()), "isolated_diseases_after": int((disease & ~active).sum()),
            "source_triples_sha256": digest(source / "data/triples.npy"),
            "categories_sha256": digest(output / "categories.json"), "triples_sha256": digest(path),
            "preparation_seconds": time.perf_counter()-tick,
            "verification": "Zero direct Drug-Disease connections remain in either direction under any predicate. All nodes and candidates retained."}
    save(manifest_path, info)
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-queries", type=int, help="Partial smoke run per checkpoint; resume without this limit for full results")
    args = parser.parse_args()
    if args.max_queries is not None and args.max_queries < 1:
        parser.error("max-queries must be positive")
    out = args.output.resolve()
    if out.exists() and not args.resume:
        parser.error("Refusing to overwrite; use --resume or a new directory")
    if args.resume and not (out / "settings.json").exists():
        parser.error("Resume requires an existing settings.json")
    assert torch.cuda.is_available(), "Use scripts/gpu_python.sh"
    torch.set_num_threads(8)
    torch.manual_seed(1024)
    source = ROOT / "output/full-graph-ultra/run_001"
    trained = ROOT / "pilot/results/finetune_4g_001"
    config = json.loads((source / "config.json").read_text())
    original = json.loads((source / "preparation.json").read_text())
    study = json.loads((ROOT / "pilot/studies/full_graph_ultra3g_bidirectional.json").read_text())
    assert digest(source / "config.json") == original["config_sha256"] == study["graph"]["prepared_config_sha256"]
    for name, expected in study["graph"]["input_file_sha256"].items():
        assert expected == original["dataset_sha256"][name] == digest(source / "data" / name), name
    completion = json.loads((trained / "completed.json").read_text())
    training_settings = json.loads((trained / "settings.json").read_text())
    assert training_settings["dataset_sha256"] == original["dataset_sha256"]
    assert completion["best_step"] == 1000
    checkpoints = {"pretrained_4g": ROOT / config["checkpoint"], "finetuned_4g": trained / "best.pt"}
    hashes = {name: digest(path) for name, path in checkpoints.items()}
    assert hashes["pretrained_4g"] == config["checkpoint_sha256"]
    assert hashes["finetuned_4g"] == completion["checkpoint_sha256"]
    upstream = ROOT / "vendor/ULTRA"
    assert subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() == config["ultra_commit"]
    subprocess.run(["git", "-C", str(upstream), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    sources = [Path(__file__), ROOT / "pilot/finetune/run.py", ROOT / "pilot/reference_candidates.py", ROOT / "scripts/full_graph_common.py"]
    settings = {"experiment": 6, "split": "test", "test_pairs": 1809, "test_diseases": 977,
                "drug_candidates": 5326, "training_updates": 0, "batch_size": 1, "seed": 1024,
                "checkpoint_sha256": hashes, "finetuned_step": 1000,
                "source_dataset_sha256": original["dataset_sha256"], "ultra_commit": config["ultra_commit"],
                "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
                "torch": torch.__version__, "cuda": torch.version.cuda, "gpu": torch.cuda.get_device_name(0),
                "mask": "All explicit biolink:Drug--biolink:Disease connections globally, both directions, every predicate",
                "ranking": "Same 5326 Drug nodes; all-known filtered pessimistic head ranks; isolated candidates retained",
                "relation_graph": "Rebuilt exclusively from the modified graph; original cache never reused",
                "interpretation": "Inference-context ablation; fine-tuned checkpoint retains learning from training labels. Previously inspected test split is exploratory."}
    if args.resume:
        if json.loads((out / "settings.json").read_text()) != settings:
            raise ValueError("Inputs, checkpoint, code, or environment changed")
    else:
        out.mkdir(parents=True)
        save(out / "settings.json", settings)
        for path in sources:
            target = out / "source" / path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    if not (out / "categories.json").exists():
        subprocess.run([str(ROOT / ".venv/bin/python"), "-B", str(ROOT / "pilot/reference_candidates.py"),
                        "--output", str(out / "categories.json")], check=True)
    categories = json.loads((out / "categories.json").read_text())
    predicates = json.loads((source / "data/predicates.json").read_text())
    info = prepare(source, out, categories, config["num_nodes"], predicates)
    print(json.dumps(info), flush=True)
    triples = np.load(out / "data/triples.npy")
    edges = torch.from_numpy(triples[:, [0, 2]].T.copy())
    types = torch.from_numpy(triples[:, 1].copy())
    p = len(predicates)
    graph = Data(edge_index=torch.cat([edges, edges.flip(0)], 1), edge_type=torch.cat([types, types+p]),
                 num_nodes=config["num_nodes"], num_relations=2*p)
    del triples, edges, types
    cache = out / "relation_graph.pt"
    meta = out / "relation_graph.json"
    if meta.exists():
        details = json.loads(meta.read_text())
        assert details["triples_sha256"] == info["triples_sha256"] and details["sha256"] == digest(cache)
        graph.relation_graph = torch.load(cache, map_location="cpu")
    else:
        print("Building a fresh relation graph from the ablated context...", flush=True)
        tick = time.perf_counter()
        graph = tasks.build_relation_graph(graph)
        torch.save(graph.relation_graph, cache.with_suffix(".tmp"))
        cache.with_suffix(".tmp").replace(cache)
        details = {"sha256": digest(cache), "triples_sha256": info["triples_sha256"],
                   "seconds": time.perf_counter()-tick, "num_nodes": graph.relation_graph.num_nodes,
                   "edges": graph.relation_graph.num_edges}
        save(meta, details)
    graph = graph.to("cuda")
    labels = json.loads((source / "data/labels.json").read_text())
    candidates = json.loads((source / "data/candidates.json").read_text())
    assert len(candidates) == 5326 and sum(r["split"] == "test" for r in labels) == 1809
    common = {"input_dim": 64, "hidden_dims": [64]*6, "message_func": "distmult", "aggregate_func": "sum", "short_cut": True, "layer_norm": True}
    model = Ultra(rel_model_cfg={"class": "RelNBFNet", **common}, entity_model_cfg={"class": "EntityNBFNet", **common}).cuda()
    reports = {}
    for name, checkpoint in checkpoints.items():
        model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
        model.eval()
        torch.cuda.reset_peak_memory_stats()
        print(f"Scoring {name}: same 1809 test pairs, 5326 Drug candidates", flush=True)
        report = evaluate(model, graph, labels, candidates, predicates.index("biolink:treats"), out / name, "test", limit=args.max_queries)
        save(out / name / "provenance.json", {"checkpoint_sha256": hashes[name], "settings_sha256": digest(out / "settings.json"),
             "triples_sha256": info["triples_sha256"], "relation_graph_sha256": details["sha256"],
             "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(), "complete": report["complete"]})
        reports[name] = {k:v for k,v in report.items() if k != "score_files_sha256"}
    complete = all(r["complete"] for r in reports.values())
    save(out / "progress.json", {"complete": complete, "checkpoints": {k:r["scored_queries"] for k,r in reports.items()}})
    if complete:
        assert all(r["evaluated_pairs"] == 1809 for r in reports.values())
        baselines = {"pretrained_4g": json.loads((source / "test/metrics.json").read_text())["ultra"],
                     "finetuned_4g": json.loads((trained / "test/metrics.json").read_text())["ultra"]}
        save(out / "comparison.json", {"complete": True, "experiment": 6, "split": "test", "pairs": 1809,
             "preparation": info, "original_context_test": baselines, "no_direct_drug_disease_edges": reports,
             "checkpoint_sha256": hashes, "settings_sha256": digest(out / "settings.json")})
        print(json.dumps({k:r["ultra"] for k,r in reports.items()}, indent=2), flush=True)
    print("Complete" if complete else "Partial run; no final comparison. Resume without --max-queries to finish.", flush=True)


if __name__ == "__main__":
    main()
