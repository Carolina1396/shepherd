# Chemical/drug retrieval under held-out edge masking

Part of [Study 3: Sampling and retrieval](../README.md#study-3-sampling-and-retrieval). Retrieval follow-up.

These experiments use Experiment 11's frozen Experiment 10 labels: 18,334 visible,
2,291 validation and 2,293 test pairs, with 1,117,832 chemical/drug candidates.
The [consolidated report](../aragorn_service_parity/report/README.md) covers the
ARAGORN recovery experiments, actual service comparison and evidence tracing.

## Completed comparison

On the same chemical/drug labels and `treats_only` graph, native Gandalf walks
recovered more held-out answers than the saved ARAGORN retrieval:

| Method | Split | Recovered / expected | Recovery | Mean nodes | Mean connections |
|---|---|---:|---:|---:|---:|
| Gandalf walks | Validation | 1,533 / 2,291 | **66.91%** | 1,737.88 | 2,101.37 |
| ARAGORN rules | Validation | 455 / 2,291 | 19.86% | 91.71 | 217.42 |
| Gandalf walks | Test | 1,564 / 2,293 | **68.21%** | 1,746.14 | 2,112.89 |
| ARAGORN rules | Test | 506 / 2,293 | 22.07% | 99.24 | 236.04 |

The equal 3,000-edge ceiling does not equalize realized graph sizes: walks produce
substantially larger contexts. Their coverage advantage therefore does not isolate
retrieval strategy from graph size. Other direct evidence remains available under
this mask; this is missing-treatment-link recovery rather than evidence-free discovery.

| Answer overlap | Validation | Test |
|---|---:|---:|
| Both methods | 340 | 376 |
| Walks only | 1,193 | 1,188 |
| ARAGORN only | 115 | 130 |
| Neither | 643 | 599 |
| Either method | 1,648 (71.93%) | 1,694 (73.88%) |

The either-method row combines answer sets from two separate graphs. A combined
retrieval graph under one 3,000-edge cap has not been evaluated.

All 1,707 disease graphs completed, with 1,625,801 successful walks out of 1,707,000
attempts. No walk graph reached the cap; the maximum was 2,922 connections.
Sampling and capped union took **38.15 seconds**; the invocation took **132.88
seconds** including graph preparation, output and verification. Peak process RSS
was 7,431,634,944 bytes (about 6.92 GiB). Validation/test graph summaries overlap
in their disease cohorts and should not be added to count unique retrievals.

All 3,414 method/disease graphs were checked against the masked source, and saved
graph hashes, coverage and paired differences were verified. The reused ARAGORN
counts reproduced the earlier results exactly. No ULTRA scoring ran.

Sources: [retained study](../studies/chemical_walks_treats_only_001_results.json),
[run summary](../results/chemical_walks_treats_only_001/summary.json),
[per-disease table](../results/chemical_walks_treats_only_001/per_disease.csv).
The run summary and per-disease table are local-only artifacts excluded from
Git; use the retained study record when reading on GitHub.

## Gandalf walks versus ARAGORN on the same treats-only graph

`compare_walks.py` samples native Gandalf walks for all 1,707 distinct diseases
in the validation/test cohort and compares their graphs with the saved
`chemical_retrieval_001/treats_only` ARAGORN graphs. Diseases shared between splits
are sampled once, with recovery reported separately against each split's labels.

| Setting | Value |
|---|---|
| Mask | Remove exact `biolink:treats` edges for all validation/test pairs, both directions, before sampling |
| Retained evidence | Other predicates on those pairs and all visible training treatment edges |
| Source nodes | 1,670,341 |
| Source unique directed connections after masking | 27,922,705 |
| Unique connections removed | 4,584 |
| Walks | 1,000 attempts per disease, length 3 |
| Walk behavior | Native self-avoiding walk, traversing either direction, skipping `subclass_of`; incomplete walks discarded |
| Retrieval cap | 3,000 unique directed connections per disease, retaining whole walks |
| Seed | 7317 plus disease position in the frozen ARAGORN cohort |
| ARAGORN reference | All 18 templates plus direct lookup; original five-second rule budgets and same edge cap |
| Metric | Expected-answer chemicals present in each retrieved graph |

No labels are passed to the sampler or cap selection. The same candidate set and
expected answers are used for both strategies; missed answers remain in the
denominator. Source evidence multiplicity is preserved during sampling. The
edge cap is an upper bound, so realized graph sizes can differ substantially.

The runner verifies source hashes, the native Gandalf revision, candidate IDs,
and exact masking against the earlier ARAGORN graph statistics. After sampling,
it independently recomputes coverage from the saved graphs and checks every
retrieved edge against the masked source graph for both methods.

This measures retrieval coverage only. It does not run ULTRA, produce new MRR or
Hits@k, or select model checkpoints. Test coverage is exploratory. Results from a
single seed are not a repeated-seed estimate.

## Run and retained artifacts

From the repository root, use a new output name for a new experiment:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_retrieval/compare_walks.py \
  --output experiments/ultra/pilot/results/chemical_walks_treats_only_002
```

Add `--resume` to continue with the same settings and code, or `--verify-only`
to recheck saved artifacts without sampling. The original run uses suffix `_001`.

Outputs include:

- `settings.json`, `source_graph.json`, and `source/`: frozen inputs, mask statistics,
  budgets and source snapshots.
- `diseases/NNNN/graph.json` and `report.json`: sampled edges, walk completion counts,
  per-split coverage, timing and hashes.
- `summary.json` and `per_disease.csv`: recovery and graph sizes for both methods.
- `validation_paired_answers.json` and `test_paired_answers.json`: answer identities
  recovered by both, only walks, only ARAGORN, or neither.
- `status.json`: preparation, sampling, verification, failure or completion status.

The report also calculates recovery by **either method**, as a diagnostic union of
answer sets from two independently capped graphs. This is not the result of a
combined retrieval graph under one 3,000-edge cap.

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/chemical_retrieval -p 'test_*.py' -v
```

Eight tests cover masking, whole-match selection, candidate coverage and native
sampling on a graph where held-out treatment edges are hidden but other direct
evidence remains. The existing ARAGORN experiment commands are documented in the
[retrieval protocol](../retrieval/README.md#chemicaldrug-dataset-compare-direct-edge-masking-policies).
