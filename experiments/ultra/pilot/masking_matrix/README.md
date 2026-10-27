# Controlled Tier 0 masking matrix

This follow-up fills the eight answer-hidden combinations of visible/held-out
direct-edge masking. [Live verified results](RESULTS.md) are updated after each
completed condition. This is full-graph pretrained ULTRA scoring, not Gandalf
walk retrieval or fine-tuning.

## Fixed protocol

- Dataset: the frozen Experiment 10 chemical/drug → `biolink:treats` → Disease labels.
- Split: seed 731; 18,334 visible / 2,291 validation / 2,293 test pairs.
- Candidates: all 1,117,832 original eligible nodes, including isolated candidates.
- Graph: all 1,670,341 indexed Tier 0 nodes and 60 original predicates.
- Checkpoint: the same pretrained ULTRA 4g weights, without training or selection.
- Hardware: A6000; same model architecture, seed 1024, batch size 1, and evaluator as Experiment 10.
- Evaluation: test only (1,122 disease queries), all-known-answer filtering, pessimistic ties.
- Held-out means validation and test together; both splits' `treats` edges are hidden in every row.
- Direct-edge masks cover both directions and only endpoint pairs in the frozen label set.
- All edges for unlabeled endpoint pairs remain unchanged. Other predicates are not relabeled as treatments.
- Rebuild the relation graph independently for every new context before inference.

| Row | Visible treats | Visible other direct edges | Held-out treats | Held-out other direct edges |
|---|---|---|---|---|
| 1 (existing baseline) | Keep | Keep | Remove | Remove |
| 2 | Keep | Keep | Remove | Keep |
| 3 | Keep | Remove | Remove | Remove |
| 4 | Keep | Remove | Remove | Keep |
| 5 | Remove | Keep | Remove | Remove |
| 6 | Remove | Keep | Remove | Keep |
| 7 | Remove | Remove | Remove | Remove |
| 8 | Remove | Remove | Remove | Keep |

"Visible" is a split label, not an assertion that its edges survive every mask.
No gradient updates occur. This suite differs from the historical Drug-only
global-removal ablation and the MechRepoNet global non-indication ablation:
neither supplies a matched missing row for this table.

## Prepared graph counts

Counts are unique directed triples before inverse edges are added. The original
source has 27,927,289 triples. Every row retains the same nodes and candidates.

| Row | Removed from original source | Remaining triples | Isolated candidates |
|---|---:|---:|---:|
| 1 | 11,133 | 27,916,156 | 54 |
| 2 | 4,584 | 27,922,705 | 35 |
| 3 | 37,904 | 27,889,385 | 54 |
| 4 | 31,355 | 27,895,934 | 35 |
| 5 | 29,467 | 27,897,822 | 202 |
| 6 | 22,918 | 27,904,371 | 183 |
| 7 | 56,238 | 27,871,051 | 317 |
| 8 | 49,689 | 27,877,600 | 280 |

The labeled pairs have 18,334 visible `treats` edges, 26,771 visible-pair other
edges, 4,584 held-out `treats` edges, and 6,549 held-out-pair other edges.
The remaining 27,871,051 source triples connect unlabeled endpoint pairs and
are preserved in every condition. Isolated candidates remain in ranking.

## Preparation and verification

Preparation verifies the frozen baseline hashes, target categories, candidate IDs,
and split against the unmasked Gandalf source. Applying row 1 to that source must
exactly reproduce the baseline triples. Every new row is then checked in full
using a separate directed-key membership implementation, including unchanged
unlabeled edges. The prepared graph, isolated-node annotations, and hashes are saved.

Before the seven runs, two baseline test queries are rescored on the same GPU.
Every candidate score must match within 1e-5 absolute/relative tolerance and
all answer ranks must match exactly. Each completed row saves every candidate
score and receives a separate verification of all 1,122 score files and 2,293
filtered ranks, including MRR, Hits@k, and disease-macro MRR. Partial results
never appear as final metrics in the results table.

These are exploratory results on previously inspected splits; this single-split
suite does not establish statistical significance or clinical efficacy.

## Commands

Run from the repository root. The current baseline and Gandalf store reside in
the main checkout; all new artifacts are written in this workspace. Use a fresh
output suffix to prepare another suite. Existing runtime setup is documented in
[setup](../../SETUP.md).

```bash
experiments/ultra/.venv-model-gpu/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/masking_matrix -p 'test_*.py' -v

/home/agonzalez/shepherd/experiments/ultra/.venv/bin/python -B -u \
  experiments/ultra/pilot/masking_matrix/prepare.py \
  --baseline /home/agonzalez/shepherd/experiments/ultra/pilot/results/chemical_disease_4g_001 \
  --store /home/agonzalez/shepherd/experiments/ultra/output/gandalf/full-store \
  --output experiments/ultra/pilot/results/tier0_masking_matrix_002

experiments/ultra/.venv-model-gpu/bin/python -B -u \
  experiments/ultra/pilot/masking_matrix/run_suite.py \
  --suite experiments/ultra/pilot/results/tier0_masking_matrix_002
```

Rerun the same suite command to resume unchanged inputs/code. Verified rows are
retained, score files are hash-checked before reuse, and current condition/query
progress is saved in `status.json`. Each row has `run.log`, `verification.log`,
its prepared graph, rebuilt relation cache, scores, ranks, and verification.
`results.json`, the retained `pilot/studies/<suite>_results.json`, and `RESULTS.md`
are refreshed after each verified completion. The current suite suffix is `_001`.
