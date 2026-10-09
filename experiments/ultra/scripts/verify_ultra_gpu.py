"""Verify CUDA kernel gradients and pretrained ULTRA inference against CPU."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import torch
from torch_geometric.data import Data

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor/ULTRA"
sys.path.insert(0, str(UPSTREAM))
from ultra import tasks, util
from ultra.models import Ultra


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "output/gpu-verification")
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"Refusing to overwrite {args.output}")
    assert torch.cuda.is_available(), "CUDA is unavailable"
    assert torch.version.cuda == "11.8"
    torch.set_num_threads(1)
    torch.manual_seed(1024)
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    print(f"Using {torch.cuda.get_device_name(0)} with PyTorch {torch.__version__}", flush=True)
    started = time.perf_counter()
    from ultra.rspmm.rspmm import generalized_rspmm, rspmm
    edges = torch.tensor([[0, 0, 1, 2], [1, 2, 2, 0]])
    types = torch.tensor([0, 1, 0, 1])
    base = [torch.rand(4), torch.randn(2, 8), torch.randn(3, 8)]
    kernel_results = []
    for device in ("cpu", "cuda:0"):
        weight, relation, inputs = [x.to(device).detach().requires_grad_() for x in base]
        result = generalized_rspmm(edges.to(device), types.to(device), weight, relation, inputs)
        result.square().sum().backward()
        kernel_results.append([x.detach().cpu() for x in (result, weight.grad, relation.grad, inputs.grad)])
    for cpu, gpu in zip(*kernel_results):
        torch.testing.assert_close(gpu, cpu, rtol=1e-4, atol=1e-5)
    print("CPU/CUDA kernel outputs and all input gradients match", flush=True)

    prepared = ROOT / "pilot/results/disease_001/ultra_001"
    manifest = json.loads((prepared / "preparation.json").read_text())
    dataset = prepared / "data"
    for name, expected in manifest["dataset_sha256"].items():
        assert digest(dataset / name) == expected
    config = json.loads((prepared / "config.json").read_text())
    nodes = json.loads((dataset / "nodes.json").read_text())
    predicates = json.loads((dataset / "predicates.json").read_text())
    candidates = json.loads((dataset / "candidates.json").read_text())
    labels = json.loads((dataset / "labels.json").read_text())
    curies = {row["id"]: i for i, row in enumerate(nodes)}
    disease = sorted({row["disease"] for row in labels if row["split"] == "validation"})[0]
    triples = torch.from_numpy(np.load(dataset / "triples.npy"))
    edges = triples[:, [0, 2]].T.contiguous()
    relations = len(predicates)
    graph = tasks.build_relation_graph(Data(
        edge_index=torch.cat([edges, edges.flip(0)], dim=1),
        edge_type=torch.cat([triples[:, 1], triples[:, 1] + relations]),
        num_nodes=len(nodes), num_relations=2 * relations))
    checkpoint = UPSTREAM / "ckpts/ultra_4g.pth"
    assert digest(checkpoint) == config["checkpoint_sha256"]
    cfg = util.load_config(str(UPSTREAM / "config/transductive/inference.yaml"), context={
        "dataset": "gpu-verification", "gpus": "[0]", "epochs": 0,
        "bpe": "null", "ckpt": str(checkpoint)})
    model = Ultra(rel_model_cfg=cfg.model.relation_model, entity_model_cfg=cfg.model.entity_model)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
    model.eval()
    batch = torch.tensor([[c, curies[disease], predicates.index("biolink:treats")]
                          for c in candidates]).unsqueeze(0)
    with torch.no_grad():
        cpu_scores = model(graph, batch).cpu()
        model = model.cuda()
        graph = graph.to("cuda:0")
        torch.cuda.reset_peak_memory_stats()
        inference_start = time.perf_counter()
        gpu_scores = model(graph, batch.cuda())
        torch.cuda.synchronize()
        gpu_seconds = time.perf_counter() - inference_start
        gpu_scores = gpu_scores.cpu()
    assert torch.isfinite(gpu_scores).all()
    torch.testing.assert_close(gpu_scores, cpu_scores, rtol=1e-3, atol=1e-4)
    report = {
        "passed": True, "torch": torch.__version__, "cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0), "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "cuda_home": os.environ.get("CUDA_HOME"), "cxx": os.environ.get("CXX"),
        "extension_path": rspmm.__file__, "kernel_forward_and_backward_match_cpu": True,
        "checkpoint_sha256": digest(checkpoint),
        "ultra_commit": subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip(),
        "dataset": str(prepared.relative_to(ROOT)), "disease": disease,
        "nodes": len(nodes), "original_edges": len(triples), "candidate_scores": len(candidates),
        "gpu_scores_match_cpu": True,
        "max_absolute_score_difference": float((gpu_scores - cpu_scores).abs().max()),
        "gpu_inference_seconds": gpu_seconds,
        "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
        "elapsed_seconds_including_extension_build": time.perf_counter() - started,
        "scope": "Kernel verification and one sampled-graph validation disease; no full-graph or test evaluation",
    }
    args.output.mkdir(parents=True)
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    frozen = subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True)
    (args.output / "requirements-freeze.txt").write_text(frozen)
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
