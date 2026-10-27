"""Independently audit prepared full-graph data and held-out answer ranks."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random

import numpy as np
from gandalf import CSRGraph

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "output/full-graph-ultra/run_001")
    parser.add_argument("--preparation-only", action="store_true")
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    args = parser.parse_args()
    run = args.dataset.resolve()
    prep = json.loads((run / "preparation.json").read_text())
    config = json.loads((run / "config.json").read_text())
    masking = config.get("masking", "all-direct")
    assert masking in ("all-direct", "treats-only", "treats-only-all-splits", "all-direct-no-visible-treats")
    remove_visible_treats = masking in ("treats-only-all-splits", "all-direct-no-visible-treats")
    remove_all_hidden_edges = masking in ("all-direct", "all-direct-no-visible-treats")
    assert prep.get("masking", "all-direct") == masking
    assert sha(run / "config.json") == prep["config_sha256"]
    for name, expected in prep["dataset_sha256"].items():
        assert sha(run / "data" / name) == expected
    labels = json.loads((run / "data/labels.json").read_text())
    candidates = json.loads((run / "data/candidates.json").read_text())
    predicates = json.loads((run / "data/predicates.json").read_text())
    triples = np.load(run / "data/triples.npy", mmap_mode="r")
    with (ROOT / "output/treatment_pairs/pairs.csv").open() as stream:
        expected_pairs = {(r["chemical_id"], r["disease_id"]) for r in csv.DictReader(stream)
                          if r["subject_is_drug"] == "1" and "biolink:treats" in json.loads(r["predicates"])}
    assert len(labels) == len(expected_pairs) == 18079
    assert {(r["drug"], r["disease"]) for r in labels} == expected_pairs
    ordered = sorted(expected_pairs)
    random.Random(731).shuffle(ordered)
    for split, segment in (("visible", ordered[:14463]), ("validation", ordered[14463:16270]), ("test", ordered[16270:])):
        assert {(r["drug"], r["disease"]) for r in labels if r["split"] == split} == set(segment)
    graph = CSRGraph.load_mmap(ROOT / "output/gandalf/full-store", mmap_mode="r")
    assert config["num_nodes"] == graph.num_nodes
    drug_indices = {i for i, props in graph.node_store.iter_properties() if "biolink:Drug" in props.get("categories", [])}
    assert {r["index"] for r in candidates} == drug_indices and len(candidates) == 5326
    for r in candidates:
        assert graph.get_node_id(r["index"]) == r["id"]
    for r in labels:
        assert graph.get_node_id(r["drug_index"]) == r["drug"]
        assert graph.get_node_id(r["disease_index"]) == r["disease"]
    n, p = graph.num_nodes, len(predicates)
    assert predicates == [graph.id_to_predicate[i] for i in range(p)]
    source_heads = np.repeat(np.arange(n, dtype=np.int64), np.diff(graph.fwd_offsets))
    original = np.unique((source_heads * p + graph.fwd_predicates) * n + graph.fwd_targets)
    del source_heads
    actual = (triples[:, 0] * p + triples[:, 1]) * n + triples[:, 2]
    assert np.all(actual[1:] > actual[:-1]), "Triples must be sorted and unique"
    assert not len(np.setdiff1d(actual, original, assume_unique=True))
    removed = np.setdiff1d(original, actual, assume_unique=True)
    assert len(removed) == prep["removed_connections"]
    target = predicates.index("biolink:treats")
    if masking == "all-direct":
        assert len(removed) == 9608
    elif masking == "all-direct-no-visible-treats":
        assert len(removed) == 9608 + 14463
    else:
        assert np.all((removed // n) % p == target)
    assert dict(Counter(predicates[int((k // n) % p)] for k in removed)) == prep["removed_connections_by_predicate"]
    hidden = {frozenset((r["drug_index"], r["disease_index"])) for r in labels if r["split"] != "visible"}
    masked_pairs = ({frozenset((r["drug_index"], r["disease_index"])) for r in labels}
                    if remove_visible_treats else hidden)
    assert all(frozenset((int(k // (n * p)), int(k % n))) in masked_pairs for k in removed)
    # Non-treats removals are allowed only for hidden pairs under all-direct masking.
    assert all(remove_all_hidden_edges and frozenset((int(k // (n * p)), int(k % n))) in hidden
               for k in removed if int((k // n) % p) != target)
    # Search both source adjacency slices, independently of the preparation mask.
    for pair in masked_pairs:
        h, t = tuple(pair)
        for source, neighbor in ((h, t), (t, h)):
            left, right = np.searchsorted(triples[:, 0], [source, source + 1])
            pair_edges = triples[left:right][triples[left:right, 2] == neighbor]
            if remove_all_hidden_edges and pair in hidden:
                assert not len(pair_edges)
            else:
                assert not np.any(pair_edges[:, 1] == target)
    reference_visible = {(r["drug_index"], r["disease_index"]) for r in labels if r["split"] == "visible"}
    target = predicates.index("biolink:treats")
    treatment_edges = triples[triples[:, 1] == target]
    actual_pairs = set(map(tuple, treatment_edges[:, [0, 2]]))
    if remove_visible_treats:
        assert not (reference_visible & actual_pairs)
    else:
        assert reference_visible <= actual_pairs
    visible_diseases = set() if remove_visible_treats else {r["disease"] for r in labels if r["split"] == "visible"}
    assert all(r["disease_has_visible_treatment"] == (r["disease"] in visible_diseases) for r in labels)
    expected_degree = np.bincount(treatment_edges[:, 0], minlength=n)[[r["index"] for r in candidates]]
    np.testing.assert_array_equal(expected_degree, np.load(run / "data/candidate_degree.npy"))
    report = {"passed": True, "split_counts": dict(Counter(r["split"] for r in labels)),
              "exact_seeded_global_split_verified": True, "candidate_pool_matches_native_drug_categories": True,
              "model_graph_is_exact_source_subset": True, "masking": masking,
              "masking_policy_verified": True,
              "connections_removed": len(removed), "visible_targets_retained": not remove_visible_treats,
              "visible_target_treats_removed": remove_visible_treats,
              "degree_baseline_recomputed": True, "test_metrics_computed": (run / "test/metrics.json").exists()}
    if masking == "all-direct":
        report["all_and_only_hidden_direct_connections_removed"] = True
    elif masking == "treats-only":
        report["all_and_only_hidden_treats_connections_removed"] = True
        report["other_direct_connections_retained"] = True
    elif masking == "treats-only-all-splits":
        report["all_and_only_target_pair_treats_connections_removed"] = True
        report["other_direct_connections_retained"] = True
        report["treats_outside_target_pairs_retained"] = True
    else:
        report["all_hidden_direct_connections_removed"] = True
        report["all_visible_target_treats_removed"] = True
        report["visible_other_direct_connections_retained"] = True
        report["treats_outside_target_pairs_retained"] = True
    if not args.preparation_only:
        output = run / args.split
        metrics = json.loads((output / "metrics.json").read_text())
        assert metrics["split"] == args.split and metrics["complete"]
        assert metrics["config_sha256"] == sha(run / "config.json")
        assert metrics["preparation_sha256"] == sha(run / "preparation.json")
        assert metrics["answer_ranks_sha256"] == sha(output / "answer_ranks.csv")
        with (output / "answer_ranks.csv").open() as stream:
            answers = list(csv.DictReader(stream))
        selected = [r for r in labels if r["split"] == args.split]
        expected = {(r["drug"], r["disease"]) for r in selected}
        assert len(answers) == len(expected) and {(r["drug"], r["disease"]) for r in answers} == expected
        assert all(r["split"] == args.split for r in answers)
        positions = {r["index"]: i for i, r in enumerate(candidates)}
        known = defaultdict(set)
        for r in labels:
            known[r["disease_index"]].add(positions[r["drug_index"]])
        for filename, expected_hash in metrics["score_files_sha256"].items():
            assert sha(output / "scores" / filename) == expected_hash
        expected_files = {f'{r["disease_index"]}.npz' for r in selected}
        assert {f.name for f in (output / "scores").glob("*.npz")} == expected_files
        assert set(metrics["score_files_sha256"]) == expected_files
        reuse_path = output / "reused_validation_scores.json"
        if reuse_path.exists():
            reuse = json.loads(reuse_path.read_text())
            assert sha(reuse_path) == metrics["reuse_manifest_sha256"]
            assert sha(run / "validation/metrics.json") == reuse["validation_metrics_sha256"]
            assert sha(run / "validation/settings.json") == reuse["validation_settings_sha256"]
            for filename, expected_hash in reuse["files"].items():
                assert sha(output / "scores" / filename) == expected_hash
                assert sha(run / "validation/scores" / filename) == expected_hash
            report["reused_queries_verified"] = len(reuse["files"])
        for row in answers:
            idx, drug = int(row["disease_index"]), int(row["drug_index"])
            with np.load(output / "scores" / f"{idx}.npz") as saved:
                scores = saved["scores"]
            pos = positions[drug]
            competitors = [i for i in range(len(candidates)) if i not in known[idx]]
            for values, field in ((scores, "ultra_rank"), (expected_degree, "baseline_rank")):
                rank = 1 + sum(values[i] >= values[pos] for i in competitors)
                assert int(row[field]) == rank
        for method, field in (("ultra", "ultra_rank"), ("degree_baseline", "baseline_rank")):
            ranks = np.array([int(r[field]) for r in answers])
            assert np.isclose(np.mean(1 / ranks), metrics[method]["mrr"], rtol=0, atol=1e-14)
            for k in (1, 3, 10):
                assert np.isclose(np.mean(ranks <= k), metrics[method][f"hits_at_{k}"], rtol=0, atol=1e-14)
        report[f"{args.split}_pairs_independently_ranked"] = len(answers)
        report[f"{args.split}_diseases"] = len(expected_files)
    destination = run / ("preparation_verification.json" if args.preparation_only else f"{args.split}_verification.json")
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
