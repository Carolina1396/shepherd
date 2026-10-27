# Pilot technical guide

Return to the [four-study index and run guides](README.md).
This guide primarily documents the **historical sampling and Drug-only runs**
(original experiments 1–5). Numbered experiment references use those original
IDs. It contains setup, sampling rules, output formats, verification, and provenance.

For the current 22,918-pair / 1,117,832-candidate task, use the
[chemical/drug baseline](chemical_disease/README.md) and
[fine-tuning guide](chemical_finetune/README.md). Later retrieval protocols are
in the [Study 3 guides](README.md#study-3-sampling-and-retrieval).

## Setup and required inputs

Run commands from the repository root. Required local resources are under
`experiments/ultra/`:

| Resource | Used by |
|---|---|
| `.venv/` and `output/gandalf/full-store/` | Gandalf sampling, graph preparation, candidate categories |
| `.venv-model/` and `vendor/ULTRA/ckpts/ultra_4g.pth` | Sampled-graph CPU evaluation |
| `.venv-model-gpu/`, ULTRA checkpoints, and CUDA toolchain | Full-graph GPU evaluations |
| `output/full-graph-ultra/run_001/` | Frozen inputs for the bidirectional 3g reference |

See [CPU/Gandalf installation](../SETUP.md#cpu-and-gandalf-environments),
[GPU installation and toolchain](../SETUP.md#gpu-environment), and
[graph-store preparation](../SETUP.md#build-and-verify-the-gandalf-store).
The GPU launcher defaults to the A6000 and requires the documented local CUDA
11.8 toolchain; a fresh machine needs those dependencies and the graph data.

Sampling imports Gandalf's `GraphSampler` directly from
`vendor/gandalf/scripts/benchmarks/generate_queries.py` at commit
`3fbaded1c922de3d61ff2af17694264d13b221f5`, without changing its implementation.
It calls `walk(disease_node, length)` for each attempt; it does not call
`GraphSampler.anchor()`. The fixed cohort is in [cohort.json](cohort.json).

## Sampling rules

One `random.Random(0)` instance is used across diseases in sorted CURIE order,
with 1,000 attempts per disease before moving to the next. A failed attempt
consumes its normal random draws and is recorded, not retried until successful.

Gandalf chooses stored incoming or outgoing edges, skips `biolink:subclass_of`,
and avoids revisiting nodes within a walk. It uses bounded retries and returns
`None` when it cannot complete a walk; a failed attempt has no returned partial
path. Duplicate source records keep their native sampling weight. Separate
walks can repeat or overlap.

The full graph is available, including treatment edges. There are no additional
predicate filters, hidden-pair masks, custom sampling indices, or edge caps.
Sampling itself does not split or mask treatment links. A separate downstream
stage prepares a masked graph for ULTRA, described below.
The original cohort selection still conditions which diseases are studied:
these were 20 diseases sampled from 237 with 20–100 eligible explicit treats
pairs, using seed 20261006. New sampling uses the fixed IDs only.

## Sampling output format

Each run writes `results/<run-id>/`:

| File | Contents |
|---|---|
| `walks/01.jsonl` … `walks/20.jsonl` | One file per disease, with every successful or failed attempt |
| `per_disease.csv` | Disease/file mapping, success counts, nodes reached, drugs reached, and distinct connections |
| `overlap.csv` | All 190 disease pairs: shared reached nodes/drugs and Jaccard overlap |
| `nodes.json` | Gandalf node index, CURIE, name, and categories for completed walks and disease anchors |
| `predicates.json` | Gandalf predicate-index lookup |
| `cohort.json`, `sample.py` | Input cohort and entry-point snapshots |
| `summary.json` | Settings, provenance, output hashes, aggregate/per-disease coverage, predicates, and timings |

Each walk record contains `disease`, zero-based `attempt`, `anchor`, `nodes`, and
`edges`. Failed attempts have null nodes and edges. Successful nodes are Gandalf
indices in visit order. An edge is `[subject_position, predicate_index,
object_position]`, with positions into that walk's node list, retaining the
stored edge direction. These are Gandalf's returned arrays, not source edge IDs
or evidence references. Every successful walk is retained without deduplication.

Coverage is calculated after sampling. `distinct_nodes_reached` and pairwise
overlap exclude each disease's own starting node. Drug counts require
`biolink:Drug`; the separate chemical-or-drug count accepts Drug, SmallMolecule,
or ChemicalEntity. Overlapping categories count a node once. Predicate counts
are traversal occurrences, while distinct connections deduplicate only for
reporting. Jaccard is intersection size divided by union size, blank for two
empty sets. None of these summaries influence the sampled walks.

## Recovery definitions and detailed counts

[analyze_recovery.py](analyze_recovery.py) compares nodes reached by each disease's
completed walks with incoming treatment edges retrieved from the full Gandalf
graph. Run it once for a sampling run:

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/pilot/analyze_recovery.py --run-id disease_001
```

The analysis is already saved for `disease_001`; existing `recovery/` directories
are protected. Outputs are `recovery/summary.json`, `per_disease.csv`, and
`pairs.csv`. The pair file includes recovered/missed known treatments and all
additional reached chemical/drug candidates, names, categories, recorded
treatment predicates, contraindication flags, and walk occurrence counts.

Known means an explicit `chemical/drug —biolink:treats→ disease` connection in
the full graph, from any source, without clinical adjudication. Recovered means
the node appeared anywhere in a completed walk from that disease. Counts below
are **distinct disease–chemical/drug pairs**, not unique drugs across diseases.

| Node categories | Known pairs | Recovered | Recovery | Additional reached pairs without explicit treats |
|---|---:|---:|---:|---:|
| Drug | 629 | 562 | 89.3% | 6,635 |
| Drug, SmallMolecule, or ChemicalEntity | 777 | 671 | 86.4% | 12,995 |

The 562 recovered Drug pairs involve **381 distinct drugs**. The 6,635 additional
Drug pairs involve **1,971 distinct drugs**. These node sets overlap: 330 drugs
are recovered known treatments for one disease and additional candidates for
another. Their combined union is the 2,022 distinct Drug nodes reached overall.

Of the 6,635 additional Drug pairs, **2,303** already have another tracked
treatment-family predicate and **4,332** have none of the eight tracked
predicates. The former group includes **61** pairs marked `contraindicated_in`.
For the broader chemical/drug set, the corresponding counts are 3,690, 9,305,
and 65. The tracked predicates are treats, treats_or_applied_or_studied_to_treat,
applied_to_treat, studied_to_treat, in_clinical_trials_for,
in_preclinical_trials_for, ameliorates_condition, and contraindicated_in.
Absence of these predicates does not imply absence of other graph connections
or external knowledge.

These are sampling coverage statistics. Known treatment edges were visible
during walking, and additional reached nodes are not validated treatment
predictions. Of the 562 recovered Drug pairs, the explicit treats edge itself
was traversed for 435; the remaining 127 were reached through other paths.

All 777 reference pairs match the archived cohort labels exactly. Recovery was
independently recomputed from saved walks and those labels, and the pair-export
classifications were checked. See
[`recovery/verification.json`](studies/evidence/sampling/disease_001/recovery/verification.json)
and [`recovery/per_disease.csv`](studies/evidence/sampling/disease_001/recovery/per_disease.csv).

## Split and ranking protocols

### Sampled graph: experiment 2

Only the 535 explicit cohort treatment edges actually traversed by the walks
are split. Although 741 of 777 reference pairs have both endpoints somewhere
in the sample, endpoint presence alone does not make them split targets.
Splitting occurs within each disease with seed 731: the visible count is rounded
to the nearest integer (halves upward); the remainder is split between
validation and test, with an odd extra pair assigned to test. This produces
425 visible, 49 validation, and 61 test pairs. Small groups can lack holdouts.

Masking removes all 209 direct connections between held-out pairs, across
predicates and directions. The model retains 46,659 original directed
connections, including 425 visible cohort treatment edges and 1,049 treatment
edges outside the cohort. ULTRA adds inverse edges and builds its relation graph
after masking. Other known answers from all 777 full-graph cohort reference
pairs are filtered during ranking. Ties receive pessimistic ranks. The baseline
uses outgoing visible treatment degree.

[prepare_ultra.py](prepare_ultra.py) retains the walks and sampled nodes;
[run_ultra.py](run_ultra.py) uses unchanged pretrained ULTRA on CPU, without
training. The sampled study's test split remains unevaluated.

### Full graph: experiments 3 and 4

The source is Translator KG `2026_06_21`, accessed through Gandalf. The full
model vocabulary has 1,670,341 nodes and 60 original predicates. Sort all 18,079
unique explicit Drug–Disease `treats` pairs by CURIE, shuffle with
`random.Random(731)`, take `floor(0.8*N)` visible pairs and `floor(0.1*N)`
validation pairs, and reserve the remainder for test. This gives
14,463 / 1,807 / 1,809 pairs. It is a pair split, not a disease-disjoint split.

Remove every direct connection between validation/test pairs under all
predicates and in both directions. This removes 9,608 connections, leaving
27,917,681 before inverse augmentation and 55,835,362 afterward. Build the
relation graph from that masked graph. All candidates remain eligible,
including those isolated by masking. Other known answers across all splits
are excluded from competitors during ranking; they are not restored to the
graph. Ties use pessimistic ranks.

Experiment 3 evaluates disease→drug with 4g, using 5,326 Drug candidates.
Experiment 4 uses 3g and adds drug→disease, using 51,707 Disease candidates.
The 1,809 test pairs span 977 disease queries and 910 drug queries. The combined
result equally weights both directions: 3,618 directional predictions over
1,809 unique pairs. Validation was not evaluated in the retained 3g reference.

All of these ULTRA runs use zero training epochs. The source/checkpoint hashes
and exact 3g metrics are in the
[study record](studies/full_graph_ultra3g_bidirectional.json); the original
full-graph inputs are under `../output/full-graph-ultra/run_001/`.

## Run management and output files

Use fresh run IDs/directories for new experiments. Sampler, recovery, and
preparation scripts refuse to overwrite existing outputs. Output data and local
environments are ignored by Git; code, README files, and the aggregate study
record can be versioned.

| Stage | Outputs |
|---|---|
| Sampling | Walks, sampled nodes, predicates, per-disease/overlap tables, cohort and script snapshots, summary |
| Recovery | `recovery/summary.json`, `per_disease.csv`, `pairs.csv` |
| Sampled ULTRA preparation | `config.json`, `preparation.json`, source snapshots, masked data and references |
| Sampled ULTRA evaluation | `validation/` or `test/`: candidate scores, answer ranks, metrics |
| Full-graph 4g | Separate `validation/` and `test/` scores, ranks, progress, metrics, timings and source snapshots |
| Full-graph 3g rerun | Candidates, settings and source snapshots; both directions' `scores/`, `answer_ranks.csv`; progress and final combined metrics |

### Resume full-graph 4g

Repeat the relevant command with `--resume` and the same `--dataset` and other
options. Test score reuse also requires `--reuse-validation-scores` on resume.
Reusing validation scores is valid only for identical disease queries, graph,
checkpoint, candidates, and recorded runtime settings. The original test run
reused 452 validation queries and computed 525 new ones.

To regenerate only the original 4g reports from existing scores:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B \
  experiments/ultra/scripts/run_full_graph_ultra.py --resume --summarize-only
bash experiments/ultra/scripts/gpu_python.sh -B \
  experiments/ultra/scripts/run_full_graph_ultra.py --split test --resume --summarize-only
```

### Resume or smoke-test full-graph 3g

Repeat the [experiment 4 command](HISTORICAL_RUNS.md#run-both-directions) with `--resume`.
The runner checks input/checkpoint/code/runtime settings and saved score hashes;
changed settings require a new output directory. It reconstructs category-based
candidates using [reference_candidates.py](reference_candidates.py) in the
Gandalf environment, and runs inference in the GPU environment.

For a short check, use a separate output directory and add
`--max-new-queries-per-direction 4`. This saves an explicitly incomplete run;
final `metrics.json` is written only when both directions finish. Remove the
limit and add `--resume` to complete it. `--batch-size` defaults to 4; a resume
must retain the same batch size. Saved score sidecars record checksums, batch
query IDs, batch timing, and allocated GPU memory. Inference outputs are retained
until explicitly removed.

## Verification

The original sampling run was independently replayed against upstream Gandalf,
including failed walks, edge directions, cohort/category checks, overlaps, and
hashes. Coverage was recomputed from walks and reference pairs. See
[sampling verification](studies/evidence/sampling/disease_001/verification.json),
[recovery verification](studies/evidence/sampling/disease_001/recovery/verification.json), and
[sampled ULTRA verification](studies/evidence/sampling/disease_001/ultra_001/verification.json).

Full-graph verification scripts check the source-to-model transformation,
held-out masking, split membership, score reuse, ranks, and aggregate metrics.
Commands for the existing original dataset:

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py --split test
```

Unit checks cover sampled splitting/masking and bidirectional filtering, tied
ranks, incomplete runs, corrupted scores, and resume settings. These 22 checks
run with the CPU model environment and pinned ULTRA checkout, without graph
data or model inference:

```bash
experiments/ultra/.venv-model/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot -p 'test_*.py' -v
experiments/ultra/.venv-model/bin/python -B -m unittest discover \
  -s experiments/ultra/scripts -p 'test_*.py' -v
```

The restored 3g runner was GPU smoke-tested on four queries per direction,
then resumed for one more per direction. Existing scores remained unchanged,
and incomplete runs did not publish final metrics. This check did not repeat
the full 3g evaluation.

## Timing and evidence retention

The original sampling run took 18.5 seconds including loading/export; its walk
and walk-export phase took 0.53 seconds. The sampled 4g evaluation's measured
section took 4.2 seconds on CPU, excluding earlier loading/checks. Neither number
is a promise for another machine or a cold cache.

Full-graph 4g used one A6000, batch size 1, about 1.386 seconds per disease
query, and a recorded first-query peak of 7.71 GB allocated GPU memory. Validation
plus new test queries took 34.9 minutes of GPU inference; building the relation
graph took another 322.8 seconds before caching. See
[detailed measurements](#full-graph-4g-query-time-and-gpu-requirements).

The 3g reference used batches of four: 469.9 seconds GPU inference / 483.4
seconds elapsed for disease→drug, and 437.5 / 450.3 seconds for drug→disease.
Both reused the prepared relation graph. Peak allocated GPU memory was about
20.12 GB. Batched scores matched checked single-query scores within tolerance
and preserved the checked ranks. Exact floating-point results may vary slightly
across hardware/software versions.

During execution, the frozen dataset and checkpoint hashes, split membership,
and absence of all direct held-out pair connections were checked. Every new
answer rank was checked by two calculations; all per-direction ranks and
aggregate metrics were then independently recomputed from the temporary scores.
The combined metrics reuse the verified disease→drug aggregate and were checked
arithmetically.

The study record preserves the protocol and exact aggregate results from the
verified execution outputs in this conversation. **Temporary score arrays,
per-pair rank files, runner scripts, and caches were deleted at the user's
request before this experiment was selected for retention.** They are not
reconstructed or presented as retained artifacts. The original full-graph
[prepared inputs](studies/evidence/full-graph-ultra/run_001/preparation.json) remain
available locally. Repeating inference is required to obtain new raw outputs;
the [permanent rerun entry point](run_full_graph_reference.py) now reconstructs
both directions. It is
new code implementing the recorded protocol, not a recovered copy of the
deleted temporary scripts.

These are exploratory results on an already inspected test split. They measure
graph-assertion recovery, not clinically validated efficacy. Use validation for
future model selection and a separately reserved holdout for confirmatory claims.

## Full-graph 4g query time and GPU requirements

One query means **one disease scored against all 5,326 candidate drugs**, using
the full masked graph. It is not one drug–disease pair: the same score array
serves every held-out answer for that disease. Queries ran sequentially at
batch size 1 on **one NVIDIA RTX A6000 (48 GiB VRAM)**, without fine-tuning.

Measured timings from the saved per-disease score files:

| Queries actually computed | Query count | Mean seconds/query | Median seconds/query | 95th percentile seconds/query | Total inference time |
|---|---:|---:|---:|---:|---:|
| Validation | 986 | 1.387 | 1.388 | 1.409 | 22.80 minutes |
| New test queries | 525 | 1.383 | 1.384 | 1.405 | 12.10 minutes |
| All unique queries | 1,511 | 1.386 | 1.386 | 1.408 | 34.90 minutes |

Across all 1,511 computed queries, observed times ranged from **1.329 to 1.507
seconds**. Another 452 test queries reused identical validation score arrays
and required no new model inference. These are elapsed GPU inference times,
including CUDA synchronization; they exclude graph loading, relation-graph
construction, transfer of scores to CPU, file writes, and rank computation.

| GPU/resource measurement | Observed result |
|---|---:|
| GPUs used | 1 RTX A6000 |
| Peak PyTorch-allocated GPU memory in each recorded first-query benchmark | 7.71 GB |
| Peak PyTorch-reserved GPU memory in those benchmarks | 7.90 GB |
| Relation-graph construction, cached for subsequent runs | 322.8 seconds |

Memory figures use decimal GB and include the graph, model, and inference
tensors; they are not additional memory per answer or a measurement of total
device usage. Peak memory was saved for the first validation and first new test
query, not for every query. The full graph has 1,670,341 nodes and 55,835,362
directed/inverse connections during inference. GPU utilization percentage,
energy consumption, and monetary cost were not recorded.

See the [validation benchmark](studies/evidence/full-graph-ultra/run_001/validation/benchmark.json),
[test benchmark](studies/evidence/full-graph-ultra/run_001/test/benchmark.json), and per-query
`seconds` values in the validation and test `scores/*.npz` files.

## Full-graph 4g audit and subgroup results

The [source audit](studies/evidence/full-graph-ultra-inspection/summary.json) verified
all eligible explicit treatment pairs against the independent raw-data inventory.
Strict Drug targets comprise 18,079 pairs across 3,538 diseases. The broader
Drug/SmallMolecule/ChemicalEntity population has 22,918 pairs across 3,901 diseases;
it was not used for this historical Drug-only split. It is now the target
population for the [current chemical/drug baseline](chemical_disease/README.md)
and its fine-tuning follow-up. Counts use graph IDs without a new entity-resolution
procedure. The subgroup results below describe the historical Drug-only run.

The pair split permits diseases with few treatments: 1,657 Drug-treated diseases
have one known pair and 544 have two. Masking isolates 64 graph nodes, including
six Drug candidates. Validation retains 27 pairs with an isolated disease and
one with an isolated drug. Indirect clues through related/equivalent entities
may remain after removing direct pair connections.

| 4g result | Validation | Test |
|---|---:|---:|
| ULTRA disease-macro MRR | 0.10278 | 0.10406 |
| Degree-baseline disease-macro MRR | 0.06166 | 0.05298 |
| Pairs whose disease has no visible Drug treatment | 184 | 178 |
| ULTRA MRR on those pairs | 0.07579 | 0.08466 |
| ULTRA Hits@10 on those pairs (fraction) | 0.1576 | 0.1404 |

Exact metrics, answer ranks, and verification reports remain under
`../output/full-graph-ultra/run_001/`:
[preparation verification](studies/evidence/full-graph-ultra/run_001/preparation_verification.json),
[validation metrics](studies/evidence/full-graph-ultra/run_001/validation/metrics.json),
[validation verification](studies/evidence/full-graph-ultra/run_001/validation_verification.json),
[test metrics](studies/evidence/full-graph-ultra/run_001/test/metrics.json), and
[test verification](studies/evidence/full-graph-ultra/run_001/test_verification.json).

## Historical work

The earlier treatment-prediction workflow remains archived at
`../output/archive/treatment-pilot-20261008/`. The intervening graph-wide sampling
pilot was removed. This pilot reuses only the earlier cohort's disease IDs and
names; all new walks use Gandalf's native implementation and the full graph.

## Fine-tuning protocol

[Experiment 5](finetune/README.md) adds training-only Drug negatives, native
all-direct-connection masking, optimizer-state resume, and validation-based
selection with the pretrained model eligible. The completed 1,000-step run
selected step 1,000, reaching test MRR 0.1673 and Hits@10 0.3350 on the same
1,809 pairs as Experiment 3. See the
[retained study record](studies/full_graph_ultra4g_finetuned.json) for exact
metrics, timing scopes, artifact hashes, and the exploratory-test limitation.
