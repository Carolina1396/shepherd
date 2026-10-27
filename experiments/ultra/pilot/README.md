# Gandalf sampling and ULTRA pilot study

We are testing how well ULTRA recovers known treatment links, and whether
Gandalf sampling can provide a smaller graph with useful prediction context.
The study has **two experiments: sampled graph and full graph**. Sampling and
coverage are stages of experiment 1; checkpoint, masking, and prediction-direction
comparisons are evaluation variants within experiment 2.

| Experiment | Question | Completed evaluation |
|---|---|---|
| 1. Sampled graph | What do walks from 20 diseases reach, and can ULTRA rank treatments within that sample? | Sampling and treatment coverage; ULTRA 4g validation only |
| 2. Full graph | How do checkpoint, masking, and prediction direction affect treatment prediction? | ULTRA 4g validation for four masking variants (variants 1–3 also tested); ULTRA 3g test in both directions with all-direct masking |

All ULTRA runs use pretrained checkpoints with **no fine-tuning**. **MRR and
Hits@k are fractions from 0 to 1.** These are exploratory graph-recovery results.

For proposed work, see the [prioritized experiment plan](#plan-for-informative-experiments).

## Before running

Run commands from the repository root and choose new run IDs if the examples
already exist. The existing local environments are `.venv` for Gandalf,
`.venv-model` for CPU inference, and `.venv-model-gpu` for GPU inference, under
`experiments/ultra/`. The graph store and checkpoints must already be present.
See [setup and required inputs](TECHNICAL.md#setup-and-required-inputs).

## 1. Sampled graph

### Gandalf sampling and coverage

**Purpose and setup.** Use unchanged Gandalf sampling to make 1,000 three-step
walk attempts from each of 20 fixed diseases, then measure treatment coverage.

| Output | Count |
|---|---:|
| Completed walks / attempts | 19,512 / 20,000 |
| Sampled nodes | 19,484 |
| Distinct directed connections | 46,868 |
| Known Drug–Disease pairs reached / available | 562 / 629 |
| Additional reached Drug–Disease pairs without explicit `treats` | 6,635 |

**Takeaway.** Walks reach many known treatments, but treatment edges were visible
during sampling. This measures coverage; additional candidates are not validated
treatment predictions. [Definitions and broader chemical counts](TECHNICAL.md#recovery-definitions-and-detailed-counts).

**Run sampling and coverage analysis:**

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/pilot/sample.py \
  --run-id disease_002 --attempts-per-disease 1000 --length 3 --seed 0
experiments/ultra/.venv/bin/python -B experiments/ultra/pilot/analyze_recovery.py \
  --run-id disease_002
```

**Outputs:** `experiments/ultra/pilot/results/disease_002/` contains walks,
summary tables, and `recovery/`. The measured sampling run took **18.5 seconds**
including loading/export; recovery analysis is additional.
[Original sampling](studies/evidence/sampling/disease_001/summary.json) · [Original coverage](studies/evidence/sampling/disease_001/recovery/summary.json).

### ULTRA 4g evaluation

**Purpose and setup.** Given a disease, rank **6,227 chemical/drug candidates**
on the sampled graph. Split its 535 treatment pairs into **425 visible,
49 validation, and 61 test** pairs. Remove all direct held-out pair connections
before inference. The model graph retains 46,659 directed connections before
ULTRA adds inverse edges.

| Validation method | MRR | Hits@10 | Answers in top 10 |
|---|---:|---:|---:|
| ULTRA 4g | 0.0949 | 0.1837 | 9 / 49 |
| Treatment-degree baseline | 0.0839 | 0.1224 | 6 / 49 |

**Takeaway.** Recovery is modest. The **61 test pairs have not been evaluated**,
and sampling occurred before masking, so this is exploratory evaluation within
a fixed sample.

**Run after the sampling and coverage stage above:**

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/pilot/prepare_ultra.py \
  --source-run disease_002 --run-id ultra_001 --visible-fraction 0.8 --seed 731
experiments/ultra/.venv-model/bin/python -B experiments/ultra/pilot/run_ultra.py \
  --dataset experiments/ultra/pilot/results/disease_002/ultra_001 --split validation
```

**Outputs:** the `ultra_001/` directory contains the masked data and
`validation/` scores, ranks, and metrics. The original measured evaluation phase
took **4.2 seconds on CPU**, excluding earlier loading/checks.
[Original validation results](studies/evidence/sampling/disease_001/ultra_001/validation/metrics.json).

## 2. Full graph

**Purpose and setup.** Given a disease, rank **5,326 Drug candidates** using the
full Gandalf graph. Split all 18,079 explicit Drug–Disease treatment pairs into
**14,463 visible, 1,807 validation, and 1,809 test** pairs.
We track the masking rules as four variants within this full-graph experiment:

| Full-graph variant | Visible pairs ("train" graph context) | Validation and test pairs | Code/report name |
|---|---|---|---|
| 1. Remove all direct edges | Keep `treats` and all other direct edges unchanged | Remove `treats` and every other direct edge between each held-out drug and disease | `all-direct` |
| 2. Remove only `treats` | Keep `treats` and all other direct edges unchanged | Remove `treats`; preserve every other direct edge between each held-out drug and disease | `treats-only` |
| 3. Remove `treats` from all target splits | Remove `treats`; preserve every other direct edge | Remove `treats`; preserve every other direct edge | `treats-only-all-splits` |
| 4. Remove visible `treats` and all held-out direct edges | Remove `treats`; preserve every other direct edge | Remove `treats` and every other direct edge | `all-direct-no-visible-treats` |

**"Train" means visible graph context; ULTRA is not trained or fine-tuned.**
In each variant, validation and test are masked together in one graph, in both
directions. Nodes remain, along with connections to other nodes unless those
connections also match that variant's held-out masking rule. Validation edges
are not restored for test evaluation.

The original 4g and 3g evaluations below use **variant 1: remove all direct
edges**, leaving **1,670,341 nodes and 27,917,681 connections** before inverses.
The later [4g evaluation](#ultra-4g-treats-only-masking) uses **variant 2: remove
only `treats`**.

### ULTRA 4g: disease → drug

| Split | MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---:|---:|---:|---:|
| Validation | 0.1057 | 0.0564 | 0.1035 | 0.1920 |
| Test | 0.1068 | 0.0575 | 0.1012 | 0.2007 |

**Takeaway.** ULTRA recovered **363 / 1,809** test answers in the top 10,
compared with 155 for the degree baseline. The sampled and full-graph runs use
different targets and candidates, so their difference does not isolate sampling.

**Run with a new prepared dataset:**

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/prepare_full_graph_ultra.py \
  --output experiments/ultra/output/full-graph-ultra/run_002
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/run_002
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/run_002 --split test --reuse-validation-scores
```

**Outputs:** `run_002/` contains prepared data plus separate `validation/` and
`test/` scores, ranks, and metrics. On the A6000, validation plus new test queries
took **about 35 minutes of GPU inference**, plus **about 5 minutes** to build an
uncached relation graph. [Resume instructions](TECHNICAL.md#resume-full-graph-4g).
[Original validation](studies/evidence/full-graph-ultra/run_001/validation/metrics.json) · [Original test](studies/evidence/full-graph-ultra/run_001/test/metrics.json).

### ULTRA 3g: both directions

**Purpose and setup.** Use the same frozen full graph and **1,809 test pairs**
from the 4g evaluation above, with the 3g checkpoint. Given a disease, rank 5,326 drugs;
given a drug, rank **51,707 diseases**. Masking and filtered ranking are unchanged.

| Query direction | Test MRR | Hits@1 | Hits@3 | Hits@10 |
|---|---:|---:|---:|---:|
| Given drug → predict disease | 0.1310 | 0.0708 | 0.1426 | 0.2543 |
| Given disease → predict drug | 0.0765 | 0.0459 | 0.0746 | 0.1299 |
| Both directions combined | 0.1037 | 0.0583 | 0.1086 | 0.1921 |

**Takeaway.** On the same drug-prediction task, 4g outperformed 3g. The combined
3g result averages **3,618 directional predictions over 1,809 unique pairs**.
The directions have different candidate pools. No 3g validation metrics were
computed. [Exact study record](studies/full_graph_ultra3g_bidirectional.json).

#### Run both directions

This runner uses the retained `output/full-graph-ultra/run_001/` inputs. Both
the Gandalf and GPU environments are needed; no new split is created. A fresh
clone does not contain these frozen inputs; see the
[reproducibility requirements](../SETUP.md#fresh-clone-reproducibility).

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/run_full_graph_reference.py \
  --output experiments/ultra/pilot/results/full_graph_3g_001
```

**Outputs:** `full_graph_3g_001/` retains candidates, settings, scores and ranks
for both directions, and final combined metrics. Expected runtime is **15–16
minutes on the A6000**, based on the original runs. Add `--resume` if interrupted.
[Smoke tests and resume details](TECHNICAL.md#resume-or-smoke-test-full-graph-3g).

### ULTRA 4g: treats-only masking

**Question.** How do predictions change when held-out pairs retain their other
direct relationships? This is another evaluation variant of experiment 2,
using ULTRA 4g for comparison with the completed 4g results above.
**Completed on 2026-10-16:** validation and test, with independent verification
of all ranks, aggregate metrics, masking, and score reuse.

| Pair split | Variant 1: remove all direct edges | Variant 2: remove only `treats` |
|---|---|---|
| Visible | Keep `treats` and every other direct edge | Keep `treats` and every other direct edge |
| Validation/test | Remove every direct edge between each held-out drug and disease | Remove only `biolink:treats` edges between each held-out drug and disease; keep every other predicate |

Both masking rules apply in both directions, before ULTRA adds inverse edges.
Keep the same 14,463 / 1,807 / 1,809 pair split (seed 731), 5,326 Drug candidates,
4g checkpoint, filtered pessimistic ranking, and zero training epochs. Validation
and test share the newly masked graph; validation treatment edges are not
restored for test. Rebuild the relation graph and recompute scores for this
variant because the graph context changes.

| Split | Masking | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---|---:|---:|---:|---:|---:|
| Validation | 1. Remove all direct edges | 0.1057 | 0.0564 | 0.1035 | 0.1920 | 347 / 1,807 |
| Validation | 2. Remove only `treats` | **0.1872** | 0.1134 | 0.1954 | **0.3376** | **610 / 1,807** |
| Test | 1. Remove all direct edges | 0.1068 | 0.0575 | 0.1012 | 0.2007 | 363 / 1,809 |
| Test | 2. Remove only `treats` | **0.1807** | 0.1045 | 0.1863 | **0.3350** | **606 / 1,809** |

The variant removes **3,616 `treats` connections** and retains **5,992 other
direct connections** removed by all-direct masking. These extra edges connect
1,408 validation pairs and 1,411 test pairs; visible pairs are unchanged.
The masked graph has **27,923,673 connections before inverses**. Exact split
membership, candidates, checkpoint, runtime settings, and degree-baseline results
match the original 4g run. Test MRR increased by **69.2%** relative to all-direct
masking, with a **net gain of 243 test answers** in the top 10.

The run used one A6000: **22.8 minutes** of validation inference and **12.2 minutes**
for 525 new test queries, reusing 452 validation queries from this variant.
Initial graph/model setup took **361 seconds**. First-query peak allocated GPU
memory was **7.71 GB**.

[Exact comparison](studies/full_graph_treats_only_comparison.json) ·
[Validation metrics](studies/evidence/full-graph-ultra/treats_only_001/validation/metrics.json) ·
[Test metrics](studies/evidence/full-graph-ultra/treats_only_001/test/metrics.json) ·
[Verification and provenance](studies/evidence/full-graph-ultra/treats_only_001/manifest.json).

Other retained predicates may directly reveal treatment-related information.
The comparison therefore measures the effect of those available direct clues.
The already inspected test split remains exploratory.

**Prepare and verify a new dataset, then evaluate:**

These commands describe the completed run. Choose a new output directory to rerun;
the preparation script refuses to overwrite existing results.

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/prepare_full_graph_ultra.py \
  --masking treats-only --output experiments/ultra/output/full-graph-ultra/treats_only_001
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_only_001 --preparation-only
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_only_001
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_only_001 --split test --reuse-validation-scores
```

Score reuse here is only from this variant's validation run into its test run.
After evaluation, run `verify_full_graph_ultra.py` with the same `--dataset`
and `--split validation` or `--split test` to verify each set of results.
The preparation reports record the masking mode and removed edges by predicate.
The default preparation mode remains `--masking all-direct`.

### Variant 3: remove `treats` from all target splits

**Completed on 2026-10-16:** validation and test. Compare with variant 2 to measure the contribution of
explicit treatment edges from the visible split. Remove `biolink:treats` in
both directions for all 18,079 Drug–Disease target pairs, including the 14,463
visible pairs, while retaining every other predicate. Treatment edges outside
these target pairs remain; this is not global removal of the `treats` predicate.

The pair split, ULTRA 4g checkpoint, 5,326 Drug candidates, filtered pessimistic
ranking, and zero training epochs remain fixed. Both validation and test use
the same newly masked graph. The treatment-degree baseline is recomputed from
that graph and can change. The `disease_has_visible_treatment` subgroup flag
is false for all targets because visible target treatment edges are removed;
the original visible split membership is still retained in the labels.

| Split | Variant 2 MRR | Variant 3 MRR | Variant 2 Hits@10 | Variant 3 Hits@10 | Variant 2 → 3 top-10 answers |
|---|---:|---:|---:|---:|---:|
| Validation | 0.1872 | **0.1452** | 0.3376 | **0.2800** | 610 → 506 / 1,807 |
| Test | 0.1807 | **0.1411** | 0.3350 | **0.2786** | 606 → 504 / 1,809 |

Removing visible treatment edges reduced test MRR by **21.9%** and Hits@10 by
**5.64 percentage points**, with a net loss of **102 top-10 answers**. These
edges provide useful context in this setup. Variant 3 remains above variant 1's
test MRR of 0.1068 and Hits@10 of 0.2007, but that comparison changes both
visible treatment edges and other direct edges for held-out pairs.

Preparation removed **18,079 `treats` connections**, leaving **27,909,210 total
connections before inverses** and **10,904 `treats` connections outside the
target pairs**. The exact graph comparison confirmed that only the 14,463
visible target treatment edges differ from variant 2; all other edges, split
membership, candidates, checkpoint, and runtime settings match. Independent
verification checked all validation/test ranks and the 452 reused test queries.
The recomputed degree baseline has test MRR **0.0281**, Hits@10 **0.0426**.

On the A6000, validation inference took **26.4 minutes**, and the 525 new test
queries took **14.0 minutes**. Initial graph/model setup took **270 seconds**;
first-query peak allocated GPU memory was **7.71 GB**. The inspected test split
remains exploratory, and other direct treatment-related clues remain visible.

[Exact three-variant comparison](studies/full_graph_variant_3_comparison.json) ·
[Validation metrics](studies/evidence/full-graph-ultra/treats_all_splits_001/validation/metrics.json) ·
[Test metrics](studies/evidence/full-graph-ultra/treats_all_splits_001/test/metrics.json) ·
[Verification and provenance](studies/evidence/full-graph-ultra/treats_all_splits_001/manifest.json).

The run saves raw scores, per-pair ranks, and reports under
`output/full-graph-ultra/treats_all_splits_001/`. Choose a fresh output directory
to repeat preparation, or use `--resume` to continue existing inference.

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/prepare_full_graph_ultra.py \
  --masking treats-only-all-splits --output experiments/ultra/output/full-graph-ultra/treats_all_splits_001
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_all_splits_001 --preparation-only
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_all_splits_001
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/treats_all_splits_001 --split test --reuse-validation-scores
```

Verify each completed split with `verify_full_graph_ultra.py --dataset` pointing
to this run and `--split validation` or `--split test`. Reused test scores must
come from this variant's validation run, since removing visible treatments
changes the graph and relation graph.

### Variant 4: remove visible `treats` and all held-out direct edges

**Status: validation completed and independently verified on 2026-10-16; test not evaluated.** Keep the original split,
ULTRA 4g checkpoint, 5,326 Drug candidates, filtering, and pessimistic ranks.
For visible target pairs remove only `treats`, preserving every other direct
edge. For validation/test pairs remove all direct connections, including
`treats`. Apply both masks in both directions before building inverse edges and
the relation graph. Treatment edges outside the target pairs remain.

This completes the planned two-factor comparison on validation. Compare with
variant 1 to measure the contribution of visible treatment edges when held-out
pairs have no direct clues, and with variant 3 to measure the contribution of
other held-out direct clues without visible treatment edges. As in variant 3,
recompute the degree baseline and mark all target rows as lacking visible
target treatment edges; retain their original split membership.

All rows below use the same **1,807 validation pairs**, 986 diseases, and 5,326
candidate drugs. These are validation results, including for variants 1–3.

| Variant | Visible pairs | Validation/test pairs | MRR | Hits@10 | Top-10 answers |
|---|---|---|---:|---:|---:|
| 1 | Keep all edges | Remove all direct edges | 0.1057 | 0.1920 | 347 |
| 2 | Keep all edges | Remove only `treats` | 0.1872 | 0.3376 | 610 |
| 3 | Remove only `treats` | Remove only `treats` | 0.1452 | 0.2800 | 506 |
| 4 | Remove only `treats` | Remove all direct edges | **0.0344** | **0.0647** | **117** |

Variant 4 removes **24,071 connections**: 18,079 target `treats` and 5,992
other held-out direct edges. The graph retains **27,903,218** connections before
inverses and 10,904 `treats` outside the target pairs. Its degree baseline has
MRR **0.0321**, Hits@10 **0.0493**, and 89 top-10 answers, identical to variant 3's.
Validation inference took **22.8 minutes**, after **257.2 seconds** of graph/model
setup, with **7.71 GB** peak allocated GPU memory on the A6000.

The paired comparisons show contributions from both types of context:

| Validation comparison | MRR difference | 95% paired disease-bootstrap interval |
|---|---:|---:|
| Visible treatments, without other held-out direct edges: V1 − V4 | +0.0713 | [0.0587, 0.0849] |
| Visible treatments, with other held-out direct edges: V2 − V3 | +0.0420 | [0.0264, 0.0572] |
| Other held-out direct edges, with visible treatments: V2 − V1 | +0.0815 | [0.0718, 0.0929] |
| Other held-out direct edges, without visible treatments: V3 − V4 | +0.1108 | [0.0994, 0.1245] |

The MRR interaction `(V2 − V3) − (V1 − V4)` is **−0.0294**
(95% interval [−0.0377, −0.0209]): the benefit of visible treatment edges is
smaller when other held-out direct clues remain. Relative to variant 1,
variant 4 loses 248 top-10 answers and gains 18; relative to variant 3, it loses
389 and gains none. Intervals use 2,000 paired disease-cluster resamples, seed
20261016, with pair-weighted metrics. They are exploratory, conditional on this
graph and split, and unadjusted for multiple comparisons.

Retained evidence: [four-way comparison](studies/full_graph_variant_4_comparison.json),
[validation metrics](studies/evidence/full-graph-ultra/all_direct_no_visible_treats_001/validation/metrics.json),
[independent verification](studies/evidence/full-graph-ultra/all_direct_no_visible_treats_001/validation_verification.json),
and [report/source manifest](studies/evidence/full-graph-ultra/all_direct_no_visible_treats_001/manifest.json).
The archived `compare_validation.py` is a byte-identical snapshot of the analysis
script; run it from the local output directory below, where it resolves its raw inputs.

The run uses `output/full-graph-ultra/all_direct_no_visible_treats_001/`.
Choose a fresh output directory for new preparation, or add `--resume` to
continue inference in the existing directory.

```bash
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/prepare_full_graph_ultra.py \
  --masking all-direct-no-visible-treats --output experiments/ultra/output/full-graph-ultra/all_direct_no_visible_treats_001
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/all_direct_no_visible_treats_001 --preparation-only
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/scripts/run_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/all_direct_no_visible_treats_001
experiments/ultra/.venv/bin/python -B experiments/ultra/scripts/verify_full_graph_ultra.py \
  --dataset experiments/ultra/output/full-graph-ultra/all_direct_no_visible_treats_001 --split validation
```

## Plan for informative experiments

**Status: variant 4 validation and the paired four-way comparison are complete; other new evaluations remain proposed.**
Keep two experiment families: sampled graph and full graph. The next runs should
answer specific questions about available prediction context, then test whether
sampling preserves that context. Use validation for the planned comparisons;
the repeatedly inspected test split is exploratory and is not a fresh final test.

### Priority 0: learn more from the scores already saved

The [four-way comparison](studies/full_graph_variant_4_comparison.json) now reports
paired MRR/Hit@10 differences and disease-bootstrap intervals for all four variants,
plus rank and top-10 transitions for variant 4 versus variants 1 and 3.
The remaining saved-score analysis is to separate
held-out pairs with and without other direct edges in the unmasked source graph,
and break down results by retained predicate groups and original visible
treatment support. Freeze these subgroup definitions across variants; the
current `disease_has_visible_treatment` field changes meaningfully in variant 3
and cannot define comparable groups on its own.

Use paired bootstrap intervals by disease, resampling diseases together with
all their answer pairs, for MRR and Hits@10 differences. These intervals describe
variation across the evaluated diseases; they do not establish robustness to a
new graph release or split. Report disease-macro MRR as well as pair-weighted MRR
so heavily labeled diseases do not hide a different pattern.

**Decision:** identify whether gains are concentrated in particular direct
predicates, diseases, or a small number of answers. This analysis needs no new
ULTRA inference. A pair without extra direct edges can still change rank because
the surrounding graph changes; do not interpret it as an unaffected control.

### Priority 1: complete the full-graph comparison with variant 4

**Completed on validation.** Results and uncertainty are recorded above.

The two factors are whether visible target `treats` edges remain, and whether
other direct edges remain for held-out pairs. All variants remove held-out
`treats`; all retain non-`treats` edges for visible pairs.

| Variant | Visible target `treats` | Other direct edges for validation/test pairs | Status | Validation MRR |
|---|---|---|---|---:|
| 1 | Keep | Remove | Completed | 0.1057 |
| 2 | Keep | Keep | Completed | 0.1872 |
| 3 | Remove | Keep | Completed | 0.1452 |
| 4 | Remove | Remove | Validation completed; test not evaluated | 0.0344 |

For variant 4, remove only `treats` from the 14,463 visible pairs, and remove
every direct connection between each validation/test drug–disease pair. Apply
both rules in both directions. Preserve all other edges, including `treats`
outside the target pairs, and rebuild the relation graph after masking.

| Controlled comparison | Question |
|---|---|
| 2 versus 3 | Do visible treatment edges help when held-out pairs retain other direct clues? Already measured. |
| 1 versus 4 | Do visible treatment edges help when held-out pairs have no direct clues? Yes: +0.0713 validation MRR. |
| 2 versus 1 | How much do other held-out direct edges help when visible treatment edges remain? Already measured. |
| 3 versus 4 | How much do other held-out direct edges help without visible treatment edges? +0.1108 validation MRR. |

For each metric, compare `(V2 - V3)` with `(V1 - V4)` to determine whether the
benefit of visible treatment edges depends on retaining other held-out direct
edges. This completed the two-factor comparison with **one new validation run**.
The preparation mode is `--masking all-direct-no-visible-treats`.

**Decision:** distinguish useful treatment context from the contribution of
direct clues, including whether they work together. Do not choose a masking
protocol merely because it produces a higher score: the mask defines what
information the prediction task allows.

### Priority 2: identify which direct clues explain the improvement

Keep visible pairs unchanged, starting from variant 2. Add a targeted masking
variant that removes `treats` plus the following positive treatment-related
predicates between held-out pairs, while retaining their other direct edges:

- `treats_or_applied_or_studied_to_treat`
- `applied_to_treat`
- `studied_to_treat`
- `in_clinical_trials_for`
- `in_preclinical_trials_for`
- `ameliorates_condition`

Freeze this list before scoring and report which predicates actually occur and
how many connections/pairs are affected. Leave `contraindicated_in` in the other
direct-edge group for this first comparison because it records a different kind
of relationship; report its presence separately. These groups describe recorded
predicates, not clinical validation of their assertions.

Compare the new variant with both variant 2 (remove only `treats`) and variant 1
(remove all direct edges). This asks how much of the gain comes from explicit
treatment-related clues and how much remains from other direct relationships.
Group removal can change global context, so do not treat these differences as
independent additive contributions of individual predicates.

Also evaluate a simple direct-edge baseline under the same candidate pool and
filtered ranking: score each candidate by whether a retained positive
treatment-related edge connects it to the query disease. Use the same pessimistic
tie rule and report how many candidates tie. Do not use held-out `treats` labels
as features or fit weights on the evaluation labels. This checks whether direct
relationships alone already explain much of the recovered signal.

**Decision:** only run finer predicate removals if this grouped comparison and
the saved-score analysis identify a specific unresolved question. This stage
needs **one additional full-graph validation run**, plus a cheap baseline.

### Priority 3: make the sampled-versus-full comparison controlled

Return to the study's original sampling question using variant 1's masking
protocol: visible pairs retain all edges; held-out pairs lose all direct edges.
Apply the mask to the full graph **before any Gandalf walks**, including the
adjacency used to choose walk steps. The existing sampled pilot masked after
sampling and cannot answer this question on its own.

Use exactly the full-graph validation queries and target pairs, ULTRA 4g,
5,326 Drug candidates, known-answer filters, and pessimistic ties. Sample a
shared context graph from the validation disease queries, without using their
hidden answers to guide walks. Preserve every query, target, and candidate in
the evaluation vocabulary even when walks do not reach it; report missing or
isolated context rather than dropping those evaluations. Build each relation
graph from its masked sampled context.

Start with **100, 300, and 1,000 three-step walk attempts per query disease**
under one fixed seed. Select the two useful budgets from validation, then repeat
those budgets with two additional seeds: **seven sampled runs in total**, with
the existing full-graph variant 1 scores as the reference. Validate identical
target membership and candidates before comparing metrics.

Measure MRR, Hits@10, uncertainty across diseases and sampling seeds, sampled
nodes/connections, candidate isolation, GPU memory, and end-to-end time including
sampling and relation-graph preparation. Separate cold setup from repeated
inference. Report the accuracy–cost tradeoff first; choose a practical accuracy
tolerance before declaring a sampled configuration acceptable.

**Decision:** determine whether a smaller graph preserves useful prediction
context at lower cost. Do not infer this from the historical sampled/full scores,
which use different targets and candidate populations.

### Robustness and execution rules

Keep the source graph, split seed 731, checkpoint, direction, candidates, filters,
and ranking implementation fixed for the immediate full-graph comparisons.
Retain paired raw scores, answer ranks, graph/checkpoint hashes, edge-removal
counts, preparation audits, and runtime settings. Recompute the degree baseline
from each graph and label it as graph-dependent.

The remaining immediate GPU budget is **one new full-graph validation run**:
the grouped predicate removal. Variant 4 is complete. Past runs suggest roughly 23–27 minutes of
validation inference plus 4–6 minutes of setup per graph on the A6000; this is
a planning estimate, not a measured runtime for the proposed variants. Analyse
existing scores first, and defer more checkpoint/direction sweeps until these
comparisons resolve what graph information is driving the results.

After selecting a focused protocol, repeat its key comparison on additional
split seeds. For a claim about diseases with no visible treatment history,
design a separate disease-disjoint holdout; the current pair split does not test
that claim. Graph nodes and non-target context can still be present in such a
holdout, so it would not imply completely unseen entities.

Before making a confirmatory performance claim, freeze the protocol and obtain
a genuinely uninspected holdout, such as a suitable later graph release with
careful entity and label alignment. A new random partition of these already
explored pairs measures split sensitivity; it does not erase prior test use.
Run status is recorded above; the remaining priorities are proposed work.
