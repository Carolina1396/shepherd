"""Score one held-out split using the pretrained ULTRA checkpoint on CPU."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UPSTREAM = ROOT / "vendor/ULTRA"
os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
os.environ["TORCH_EXTENSIONS_DIR"] = str(ROOT / ".cache/torch_extensions")
os.environ.setdefault("MAX_JOBS", "2")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
sys.path.insert(0, str(UPSTREAM))

import numpy as np
import torch
from torch_geometric.data import Data
from ultra import tasks, util
from ultra.models import Ultra


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def filtered_rank(scores, target, known):
    competing = np.ones(len(scores), dtype=bool)
    competing[list(known)] = False
    competing[target] = False
    return 1 + int(np.count_nonzero((scores >= scores[target]) & competing))


def summarize(rows, field):
    ranks = [row[field] for row in rows]
    return {"answers": len(ranks), "mrr": sum(1 / rank for rank in ranks) / len(ranks),
            "hits_at_1": sum(rank == 1 for rank in ranks) / len(ranks),
            "hits_at_10": sum(rank <= 10 for rank in ranks) / len(ranks),
            "top_10_answers": sum(rank <= 10 for rank in ranks)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True, help="Folder containing config.json and data/")
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    args = parser.parse_args()
    prepared = args.dataset.resolve()
    output = prepared / args.split
    if output.exists():
        parser.error(f"Refusing to overwrite {output}")
    config = json.loads((prepared / "config.json").read_text())
    preparation = json.loads((prepared / "preparation.json").read_text())
    dataset = prepared / "data"
    for name, expected in preparation["dataset_sha256"].items():
        assert digest(dataset / name) == expected, name
    checkpoint = UPSTREAM / "ckpts" / config["checkpoint"]
    assert digest(checkpoint) == config["checkpoint_sha256"]
    assert config["training_epochs"] == 0
    subprocess.run(["git", "-C", str(UPSTREAM), "diff", "--quiet", "HEAD", "--", "ultra"], check=True)
    nodes = json.loads((dataset / "nodes.json").read_text())
    predicates = json.loads((dataset / "predicates.json").read_text())
    candidates = json.loads((dataset / "candidates.json").read_text())
    labels = json.loads((dataset / "labels.json").read_text())
    reference = json.loads((dataset / "known_pairs.json").read_text())
    curies = {row["id"]: i for i, row in enumerate(nodes)}
    positions = {nodes[node]["id"]: i for i, node in enumerate(candidates)}
    evaluation = [row for row in labels if row["split"] == args.split]
    if not evaluation:
        parser.error(f"No {args.split} labels")
    assert all(row["chemical"] in positions for row in evaluation)
    triples = np.load(dataset / "triples.npy")
    # Verify the model graph excludes both validation and test pairs, all predicates/directions.
    hidden = {tuple(sorted((curies[row["chemical"]], curies[row["disease"]])))
              for row in labels if row["split"] != "visible"}
    assert not any(tuple(sorted((int(h), int(t)))) in hidden for h, _, t in triples)
    assert filtered_rank(np.array([0.9, 0.8, 0.8, 0.1]), 1, {0, 1}) == 2
    assert filtered_rank(np.array([0.9, 0.8, 0.8, 0.1]), 1, {0, 1, 2}) == 1

    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.manual_seed(1024)
    tensor = torch.from_numpy(triples)
    relations = len(predicates)
    target = predicates.index(config["target_predicate"])
    edges = tensor[:, [0, 2]].T.contiguous()
    graph = Data(edge_index=torch.cat([edges, edges.flip(0)], dim=1),
                 edge_type=torch.cat([tensor[:, 1], tensor[:, 1] + relations]),
                 num_nodes=len(nodes), num_relations=2 * relations)
    graph = tasks.build_relation_graph(graph)
    official = util.load_config(str(UPSTREAM / "config/transductive/inference.yaml"), context={
        "dataset": "pilot", "gpus": "null", "epochs": 0, "bpe": "null", "ckpt": str(checkpoint)})
    model = Ultra(rel_model_cfg=official.model.relation_model, entity_model_cfg=official.model.entity_model)
    model.load_state_dict(torch.load(checkpoint, map_location="cpu")["model"], strict=True)
    model.eval()
    degree = np.bincount(triples[triples[:, 1] == target, 0], minlength=len(nodes))[candidates]
    output.mkdir()
    answer_rows = []
    with (output / "candidate_scores.csv").open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["disease", "chemical", "ultra_score", "visible_treatment_degree"])
        for disease in sorted({row["disease"] for row in labels}):
            batch = torch.tensor([[c, curies[disease], target] for c in candidates]).unsqueeze(0)
            with torch.no_grad():
                scores = model(graph, batch).squeeze(0).numpy()
            assert np.isfinite(scores).all()
            # Full-graph known positives are used only for filtered ranking, never as model edges.
            known = {positions[row["chemical"]] for row in reference
                     if row["disease"] == disease and row["chemical"] in positions}
            for row in evaluation:
                if row["disease"] == disease:
                    position = positions[row["chemical"]]
                    answer_rows.append({**row, "ultra_rank": filtered_rank(scores, position, known),
                                        "baseline_rank": filtered_rank(degree, position, known)})
            writer.writerows((disease, nodes[c]["id"], float(scores[i]), int(degree[i]))
                             for i, c in enumerate(candidates))
            print(f"Scored {disease}: {len(candidates):,} candidates", flush=True)
    assert len(answer_rows) == len(evaluation)
    with (output / "answer_ranks.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(answer_rows[0]))
        writer.writeheader()
        writer.writerows(answer_rows)
    metrics = {
        "split": args.split, "ultra": summarize(answer_rows, "ultra_rank"),
        "degree_baseline": summarize(answer_rows, "baseline_rank"),
        "scored_diseases": len({row["disease"] for row in labels}),
        "diseases_with_evaluated_answers": len({row["disease"] for row in answer_rows}),
        "candidates_per_disease": len(candidates), "coverage": 1.0,
        "runtime_seconds": time.perf_counter() - started,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024),
        "model": {"checkpoint": config["checkpoint"], "sha256": digest(checkpoint),
                  "ultra_commit": subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip(),
                  "training_epochs": 0, "device": "cpu", "ties": "pessimistic"},
        "evaluation_scope": config["evaluation_scope"],
        "known_filter": "All full-graph explicit treats answers for the disease; ranking only",
        "preparation_sha256": digest(prepared / "preparation.json"),
        "config_sha256": digest(prepared / "config.json"),
    }
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    shutil.copyfile(Path(__file__), output / "run_ultra.py")
    print(json.dumps(metrics, indent=2), flush=True)


if __name__ == "__main__":
    main()
