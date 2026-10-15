"""Experiment 11: fine-tune ULTRA 4g on the corrected chemical-to-Disease split."""
import argparse
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
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "vendor/ULTRA"))
from full_graph_common import digest, hidden_pair_mask, save
from ultra.models import Ultra


sys.path.insert(0, str(ROOT / "pilot"))
from finetune.run import (training_batch, training_loss, improved, atomic_checkpoint,
                          cpu_weights, evaluate as evaluate_scores)
from chemical_finetune.sampling import NegativeSampler


def evaluate(model, graph, labels, candidates, relation, output, split, limit=None):
    torch.cuda.reset_peak_memory_stats()
    report = evaluate_scores(model, graph, labels, candidates, relation, output, split, limit)
    save(output / "resources.json", {"peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
         "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved()})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=HERE / "config.json")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--max-new-steps", type=int, help="Pause after this many new optimizer steps; resume with unchanged settings")
    parser.add_argument("--smoke-test", action="store_true", help="Two optimizer steps and two validation queries; no model selection")
    parser.add_argument("--test-only", action="store_true", help="Evaluate the selected checkpoint only after training completes")
    args = parser.parse_args()
    if args.max_new_steps is not None and (args.max_new_steps < 1 or args.test_only):
        parser.error("max-new-steps must be positive and applies to training only")
    if args.smoke_test and args.test_only:
        parser.error("Smoke and test modes are separate")
    output = args.output.resolve()
    if args.test_only:
        if not (output / "completed.json").exists():
            parser.error("Test requires a completed training run")
    elif args.resume:
        if not (output / "last.pt").exists():
            parser.error("Resume requires last.pt")
    elif output.exists():
        parser.error("Refusing to overwrite existing output; use --resume")
    cfg = json.loads(args.config.read_text())
    for k in ("steps", "validate_every", "patience", "num_negative"):
        if not isinstance(cfg[k], int) or cfg[k] < 1:
            parser.error(f"{k} must be a positive integer")
    if cfg["learning_rate"] <= 0 or cfg["adversarial_temperature"] <= 0 or cfg["weight_decay"] < 0:
        parser.error("Invalid optimizer/loss settings")
    torch.set_num_threads(8)
    torch.manual_seed(cfg["seed"])
    assert torch.cuda.is_available(), "Use scripts/gpu_python.sh"
    prepared = ROOT / "pilot/results/chemical_disease_4g_001"
    preparation = json.loads((prepared / "preparation.json").read_text())
    original = json.loads((prepared / "config.json").read_text())
    assert original["experiment"] == 10 and original["target_scope"] == "chemical-disease"
    assert original["candidate_scope"] == "chemical"
    assert digest(prepared / "config.json") == preparation["config_sha256"]
    for name, expected in preparation["dataset_sha256"].items():
        assert expected == digest(prepared / "data" / name), name
    cache = json.loads((prepared / "relation_graph.json").read_text())
    assert cache["sha256"] == digest(prepared / "relation_graph.pt")
    assert cache["triples_sha256"] == preparation["dataset_sha256"]["triples.npy"]
    upstream = ROOT / "vendor/ULTRA"
    assert subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() == original["ultra_commit"]
    subprocess.run(["git", "-C", str(upstream), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    checkpoint = ROOT / original["checkpoint"]
    assert digest(checkpoint) == original["checkpoint_sha256"]
    labels = json.loads((prepared / "data/labels.json").read_text())
    candidates = json.loads((prepared / "data/candidates.json").read_text())
    sampler = NegativeSampler(labels, candidates)
    train = sampler.train
    assert len(train) == 18334 and len(candidates) == 1117832
    baseline = json.loads((prepared / "evaluation/validation/metrics.json").read_text())
    baseline_settings = json.loads((prepared / "evaluation/settings.json").read_text())
    assert baseline["complete"] and baseline["evaluated_pairs"] == 2291
    assert baseline_settings["checkpoint_sha256"] == digest(checkpoint)
    assert baseline_settings["preparation_sha256"] == digest(prepared / "preparation.json")
    settings = {"experiment": 11, "prepared_dataset": str(prepared), "config": cfg, "smoke_test": args.smoke_test, "batch_size": 1,
                "initial_checkpoint_sha256": digest(checkpoint), "prepared_config_sha256": digest(prepared / "config.json"),
                "dataset_sha256": preparation["dataset_sha256"], "relation_graph_sha256": cache["sha256"],
                "baseline_validation_sha256": digest(prepared / "evaluation/validation/metrics.json"),
                "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), HERE / "sampling.py", ROOT / "pilot/finetune/run.py", ROOT / "scripts/full_graph_common.py"]},
                "ultra_commit": original["ultra_commit"], "torch": torch.__version__, "cuda": torch.version.cuda,
                "gpu": torch.cuda.get_device_name(0), "ranking": "Chemical/drug heads; all-known filtered; pessimistic ties",
                "negative_filter": "Visible training positives only; uniform rejection sampling with replacement over all chemical/drug candidates; held-out labels used for evaluation filtering only",
                "training_mask": "Native remove_one_hop=True: all direct predicates and directions for positives and sampled negatives",
                "relation_graph": "Frozen aggregate relation graph from the held-out-masked context, as in upstream training"}
    if args.resume or args.test_only:
        if json.loads((output / "settings.json").read_text()) != settings:
            raise ValueError("Settings or inputs changed; use a new output directory")
    else:
        output.mkdir(parents=True)
        save(output / "settings.json", settings)
        shutil.copyfile(args.config, output / "config.json")
        shutil.copyfile(Path(__file__), output / "run.py")
        for source in [HERE / "sampling.py", ROOT / "pilot/finetune/run.py"]:
            destination = output / "source" / source.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        shutil.copyfile(ROOT / "scripts/full_graph_common.py", output / "full_graph_common.py")
        shutil.copyfile(prepared / "evaluation/validation/metrics.json", output / "pretrained_validation.json")
    triples = np.load(prepared / "data/triples.npy")
    hidden = {(r["drug_index"], r["disease_index"]) for r in labels if r["split"] != "visible"}
    assert not hidden_pair_mask(triples[:, 0], triples[:, 2], hidden, original["num_nodes"]).any()
    edges = torch.from_numpy(triples[:, [0, 2]].T.copy())
    types = torch.from_numpy(triples[:, 1].copy())
    p = original["num_relations"]
    graph = Data(edge_index=torch.cat([edges, edges.flip(0)], 1), edge_type=torch.cat([types, types + p]),
                 num_nodes=original["num_nodes"], num_relations=2*p)
    graph.relation_graph = torch.load(prepared / "relation_graph.pt", map_location="cpu")
    del triples, edges, types
    graph = graph.to("cuda")
    common = {"input_dim": 64, "hidden_dims": [64]*6, "message_func": "distmult", "aggregate_func": "sum", "short_cut": True, "layer_norm": True}
    model = Ultra(rel_model_cfg={"class": "RelNBFNet", **common},
                  entity_model_cfg={"class": "EntityNBFNet", **common, "remove_one_hop": True}).cuda()
    model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    relation = json.loads((prepared / "data/predicates.json").read_text()).index("biolink:treats")
    rng = np.random.default_rng(cfg["seed"])
    state = {"step": 0, "validated_step": 0, "best_step": 0, "best_mrr": baseline["ultra"]["mrr"],
             "bad_checks": 0, "best_model": cpu_weights(model), "training_seconds": 0.0,
             "settings_sha256": digest(output / "settings.json")}
    if args.resume or args.test_only:
        state = torch.load(output / "last.pt", map_location="cpu")
        assert state["settings_sha256"] == digest(output / "settings.json")
        model.load_state_dict(state.pop("model"))
        optimizer.load_state_dict(state.pop("optimizer"))
        rng.bit_generator.state = state.pop("rng")
        torch.set_rng_state(state.pop("torch_rng"))
        torch.cuda.set_rng_state(state.pop("cuda_rng"))
    def persist():
        atomic_checkpoint(output / "last.pt", {**state, "model": cpu_weights(model), "optimizer": optimizer.state_dict(),
                          "rng": rng.bit_generator.state, "torch_rng": torch.get_rng_state(),
                          "cuda_rng": torch.cuda.get_rng_state()})
    if args.test_only:
        done = json.loads((output / "completed.json").read_text())
        assert done["best_step"] == state["best_step"] and done["checkpoint_sha256"] == digest(output / "best.pt")
        model.load_state_dict(torch.load(output / "best.pt", map_location="cpu")["model"])
        report = evaluate(model, graph, labels, candidates, relation, output / "test", "test")
        save(output / "test/result.json", {"checkpoint_sha256": digest(output / "best.pt"), "best_step": state["best_step"],
             "mrr": report["ultra"]["mrr"], "exploratory_previously_inspected_test": True})
        return
    if (output / ("smoke.json" if args.smoke_test else "completed.json")).exists():
        print("Run already complete", flush=True)
        return
    if args.smoke_test and state["step"] == 0:
        # Verify inference parity with Experiment 10 before any optimizer update.
        evaluate(model, graph, labels, candidates, relation, output / "pretrained_parity", "validation", limit=2)
        differences = []
        for path in sorted((output / "pretrained_parity/scores").glob("*.npz")):
            reference = prepared / "evaluation/validation/scores" / path.name
            assert digest(reference) == baseline["score_files_sha256"][path.name]
            with np.load(path, allow_pickle=False) as a, np.load(reference, allow_pickle=False) as b:
                assert np.allclose(a["scores"], b["scores"], atol=1e-5, rtol=1e-5)
                differences.append(float(np.max(np.abs(a["scores"] - b["scores"]))))
        save(output / "parity.json", {"queries": len(differences), "max_absolute_score_difference": max(differences)})
    max_steps = 2 if args.smoke_test else cfg["steps"]
    new_steps = 0
    print(f"Ready: {len(train)} training pairs; {graph.num_edges} context edges; {max_steps} optimizer steps", flush=True)
    while True:
        step = state["step"]
        due = step > 0 and (step % cfg["validate_every"] == 0 or step == max_steps)
        if due and state["validated_step"] != step:
            optimizer.zero_grad(set_to_none=True)
            report = evaluate(model, graph, labels, candidates, relation, output / f"validation_step_{step:06d}",
                              "validation", limit=2 if args.smoke_test else None)
            if not args.smoke_test:
                assert report["complete"] and report["evaluated_pairs"] == 2291
                if improved(report, state["best_mrr"]):
                    state.update(best_step=step, best_mrr=report["ultra"]["mrr"], best_model=cpu_weights(model), bad_checks=0)
                else:
                    state["bad_checks"] += 1
            state["validated_step"] = step
            persist()
        if step >= max_steps or state["bad_checks"] >= cfg["patience"]:
            break
        if args.max_new_steps is not None and new_steps >= args.max_new_steps:
            save(output / "progress.json", {"complete": False, "optimizer_steps": step,
                 "validated_step": state["validated_step"], "reason": "max-new-steps reached; resume to continue"})
            print("Step limit reached; checkpoint saved for resume", flush=True)
            return
        # Seeded permutations cover all training pairs before repeating, independent of resume.
        cycle, offset = divmod(step, len(train))
        order = np.random.default_rng(cfg["seed"] + cycle).permutation(len(train))
        row = train[int(order[offset])]
        negatives = sampler.sample(row["disease_index"], cfg["num_negative"], rng)
        batch = torch.from_numpy(training_batch(row, negatives, relation)).to("cuda")
        model.train()
        optimizer.zero_grad(set_to_none=True)
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        tick = time.perf_counter()
        logits = model(graph, batch)
        loss = training_loss(logits, cfg["adversarial_temperature"])
        if not torch.isfinite(loss):
            raise ValueError("Non-finite training loss")
        loss.backward()
        grads = [p.grad for p in model.parameters() if p.grad is not None]
        if not grads or not all(torch.isfinite(g).all() for g in grads):
            raise ValueError("Missing or non-finite gradients")
        grad_norm = sum(float(g.detach().square().sum()) for g in grads) ** 0.5
        if grad_norm == 0:
            raise ValueError("Zero gradients")
        optimizer.step()
        torch.cuda.synchronize()
        seconds = time.perf_counter() - tick
        state["step"] += 1
        new_steps += 1
        state["training_seconds"] += seconds
        record = {"step": state["step"], "loss": float(loss.detach()), "gradient_norm": grad_norm,
                  "seconds": seconds, "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
                  "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(),
                  "drug": row["drug"], "disease": row["disease"]}
        # One atomic record per committed step; resumed interrupted steps replace their own record.
        (output / "steps").mkdir(exist_ok=True)
        save(output / "steps" / f"{state['step']:06d}.json", record)
        persist()
        print(json.dumps(record), flush=True)
        del loss, logits, batch, grads
    if args.smoke_test:
        changed = any(not torch.equal(v.cpu(), state["best_model"][k]) for k, v in model.state_dict().items())
        assert changed
        save(output / "smoke.json", {"optimizer_steps": state["step"], "weights_changed": changed,
             "validation_queries": 2, "validation_complete": False, "model_selection_performed": False,
             "test_evaluated": False, "training_seconds": state["training_seconds"]})
    else:
        atomic_checkpoint(output / "best.pt", {"model": state["best_model"], "step": state["best_step"],
                          "validation_mrr": state["best_mrr"], "settings_sha256": state["settings_sha256"]})
        save(output / "completed.json", {"optimizer_steps": state["step"], "training_pairs_available": len(train),
             "full_passes_completed": state["step"] // len(train), "best_step": state["best_step"],
             "best_validation_mrr": state["best_mrr"], "pretrained_validation_mrr": baseline["ultra"]["mrr"],
             "checkpoint_sha256": digest(output / "best.pt"), "training_seconds": state["training_seconds"],
             "test_evaluated": False, "stopped_early": state["bad_checks"] >= cfg["patience"]})
    save(output / "progress.json", {"complete": True, "smoke_test": args.smoke_test, "optimizer_steps": state["step"]})
    print("Complete. Test evaluation is a separate command.", flush=True)


if __name__ == "__main__":
    main()
