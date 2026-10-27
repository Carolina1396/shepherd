# ULTRA treatment-prediction study

We use **Gandalf** to access and sample the Translator knowledge graph, and
**ULTRA** to rank missing treatment links. The study asks how well known
Drug–Disease relationships can be recovered and whether a smaller sampled graph
can preserve useful prediction context.

## Start here

| Document | Contents |
|---|---|
| [Pilot study](pilot/README.md) | Two experiments: sampled graph and full graph, with results, run commands, and runtimes |
| [Experiment plan](pilot/README.md#plan-for-informative-experiments) | Prioritized questions, controlled comparisons, run budget, and decision criteria |
| [Setup](SETUP.md) | Dependencies, CPU/GPU environments, graph-store building, and a CPU benchmark check |
| [Technical guide](pilot/TECHNICAL.md) | Split/masking rules, output formats, resume, verification, and provenance |
| [Data notebooks](notebooks/README.md) | Graph overview, treatment-pair inventory, sources, and knowledge levels |

## Completed work

We organize the study into **two experiments: sampled graph and full graph**.
Sampling and coverage are stages of the sampled-graph experiment; checkpoint,
direction, and masking comparisons are variants within the full-graph experiment.
All ULTRA evaluations use pretrained checkpoints with **no fine-tuning**.
**MRR and Hits@k are fractions from 0 to 1.**

| Experiment | Scope | Main result |
|---|---|---|
| 1. Sampled graph | Gandalf sampling and coverage around 20 diseases; ULTRA 4g disease → drug on 49 validation pairs | Validation MRR **0.0949**, Hits@10 **0.1837**; test not evaluated |
| 2. Full graph | ULTRA 4g validation with four masking rules (variants 1–3 also tested); ULTRA 3g test in both directions | 4g test MRR: **0.1068** (variant 1), **0.1807** (variant 2), **0.1411** (variant 3); variant 4 validation MRR **0.0344** |

The sampled graph contains **19,484 nodes and 46,868 distinct directed
connections**, from 1,000 three-step walk attempts per disease across 20 diseases.

The 3g test results are **0.0765 MRR** for disease→drug and **0.1310 MRR** for
drug→disease. Its combined result is **0.1037 MRR**, **0.1921 Hits@10**, averaging
3,618 directional predictions over 1,809 unique pairs under all-direct masking.
See the [pilot results](pilot/README.md) and
[exact 3g study record](pilot/studies/full_graph_ultra3g_bidirectional.json).

The original all-direct full-graph 4g run also completed validation: MRR **0.1057**, Hits@10
**0.1920** on 1,807 pairs. Its
[validation](pilot/studies/evidence/full-graph-ultra/run_001/validation/metrics.json) and
[test](pilot/studies/evidence/full-graph-ultra/run_001/test/metrics.json) metric reports are retained in the repository; their raw scores and ranks
remain available locally. Original temporary 3g scores were deleted; the
recorded aggregates and permanent rerun code are retained.

The treats-only 4g variant completed validation (**0.1872 MRR**, **0.3376 Hits@10**)
and test (**0.1807 MRR**, **0.3350 Hits@10**). Both splits passed independent
verification. [Masking comparison and retained reports](pilot/README.md#ultra-4g-treats-only-masking).

Variant 3 additionally removes `treats` from visible target pairs. It completed
validation (**0.1452 MRR**, **0.2800 Hits@10**) and test (**0.1411 MRR**,
**0.2786 Hits@10**). [Variant 3 comparison and retained reports](pilot/README.md#variant-3-remove-treats-from-all-target-splits).

## Graph and evaluation data

Source: **Translator KG `2026_06_21`**, also called `tier0-20260621` in the xDTD
configuration. Source URLs and checksums are in [download.json](download.json).

| Measurement | Count |
|---|---:|
| Raw node records | 1,754,754 |
| Connected nodes indexed by Gandalf | 1,670,341 |
| Stored edge/evidence records | 28,709,074 |
| Unique directed triples before masking | 27,927,289 |
| Original predicates | 60 |
| Explicit Drug–Disease `treats` pairs | 18,079 |

The full-graph split has **14,463 visible, 1,807 validation, and 1,809 test pairs**.
We track four masking variants **within experiment 2 (full graph)**:

| Full-graph variant | Visible pairs ("train" graph context) | Validation and test pairs | 4g test MRR | 4g test Hits@10 |
|---|---|---|---:|---:|
| 1. Remove all direct edges | Keep `treats` and all other direct edges unchanged | Remove `treats` and every other direct edge between each held-out drug and disease | 0.1068 | 0.2007 |
| 2. Remove only `treats` | Keep `treats` and all other direct edges unchanged | Remove `treats`; preserve every other direct edge between each held-out drug and disease | 0.1807 | 0.3350 |
| 3. Remove `treats` from all target splits | Remove `treats`; preserve every other direct edge | Remove `treats`; preserve every other direct edge | 0.1411 | 0.2786 |
| 4. Remove visible `treats` and all held-out direct edges | Remove `treats`; preserve every other direct edge | Remove `treats` and every other direct edge | Not evaluated | Not evaluated |

Variant 1 is called `all-direct` in the code and earlier reports; variant 2 is
called `treats-only`. Variant 3 is `treats-only-all-splits`: it removes `treats`
from all 18,079 target pairs, including the visible split, while preserving
`treats` edges outside those pairs. **"Train" means graph context, with no training or
fine-tuning.** Each variant uses one graph with validation and test masked
together, in both directions. The nodes remain, and connections to other nodes
are retained unless they also match that variant's held-out masking rule.
Validation edges are not restored for test evaluation.

Variant 1 contains 27,917,681 connections before inverses (55,835,362 afterward).
Variant 2 contains 27,923,673 before inverses (55,847,346 afterward).
Variant 3 contains 27,909,210 before inverses (55,818,420 afterward), using the
same split, candidates, and ULTRA 4g checkpoint. See
[variant 3 results](pilot/README.md#variant-3-remove-treats-from-all-target-splits).

Variant 4 completed **validation only**, following the experiment plan, using
`--masking all-direct-no-visible-treats`: **0.0344 MRR**, **0.0647 Hits@10**,
and **117 of 1,807 answers in the top 10**. It retains 27,903,218 connections
before inverses (55,806,436 afterward). Test was not evaluated. See
[variant 4 results and four-way validation comparison](pilot/README.md#variant-4-remove-visible-treats-and-all-held-out-direct-edges).

Disease→drug evaluation ranks **5,326 Drug candidates**. The 3g reverse task
ranks **51,707 Disease candidates**. Known answers across all splits are filtered
from ranking competitors. The sampled experiment uses its own smaller split
and a broader chemical/drug candidate population; see the [protocols](pilot/TECHNICAL.md#split-and-ranking-protocols).

## Run an experiment

Commands run from the repository root. The graph, environments, and checkpoints
are already available on the current machine. For a fresh machine, follow
[setup instructions](SETUP.md) first. The exact 3g reference additionally needs
the original frozen inputs; see [fresh-clone limits](SETUP.md#fresh-clone-reproducibility).

To rerun the full-graph 3g reference in both directions and retain raw outputs:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/run_full_graph_reference.py \
  --output experiments/ultra/pilot/results/full_graph_3g_001
```

Choose a new output directory, or add `--resume` to continue that run. Expected
runtime is **15–16 minutes on the A6000**, based on the original runs. The runner
saves scores, per-pair ranks, and final metrics. Commands for sampling, sampled
ULTRA, and full-graph 4g are in the [pilot README](pilot/README.md).

## Files and outputs

Paths below are relative to `experiments/ultra/`.

| Location | Contents |
|---|---|
| `data/tier0-20260621/` | Source archive, metadata, and extracted graph |
| `output/gandalf/full-store/` | Verified Gandalf graph and properties |
| `output/overview/`, `output/treatment_pairs/`, `output/resources/` | Data-inspection outputs |
| `output/full-graph-ultra/run_001/` | Frozen full-graph inputs and original 4g validation/test results |
| `output/full-graph-ultra/treats_only_001/` | Treats-only masked inputs, 4g scores/ranks, metrics, and verification reports |
| `output/full-graph-ultra/treats_all_splits_001/` | Variant 3 inputs with visible target treats removed, 4g scores/ranks, metrics, and verification |
| `output/full-graph-ultra/all_direct_no_visible_treats_001/` | Variant 4 inputs, validation scores/ranks, verification, and four-way comparison; no test run |
| `pilot/results/` | Sampling runs, sampled evaluations, and new bidirectional reruns |
| [pilot/studies/](pilot/studies/) | Retained aggregate study records |

Bulk data, run directories, vendor code, and virtual environments stay local
and are ignored by Git. Code, notebooks, documentation, aggregate records, and
[small original reports](pilot/studies/evidence/README.md) are included for GitHub. [Output formats and retention details](pilot/TECHNICAL.md#run-management-and-output-files).

## What we learned and next step

ULTRA 4g outperformed 3g for drug prediction on the same full graph and test
pairs. Comparing sampled and full-graph scores does not isolate graph size,
because targets and candidate pools changed.

The new evaluation variant within **experiment 2 (full graph)** uses
**treats-only masking**: visible pairs remain unchanged, while validation/test
pairs lose only their `biolink:treats` edges in both directions and retain all
other direct edges. With the same split, 4g checkpoint, candidates, and ranking
rules, retaining **5,992 other direct edges** increased test top-10 answers from
**363 to 606**. These include treatment-related predicates, so the improvement
measures the value of available direct clues. See
[results, protocol, and commands](pilot/README.md#ultra-4g-treats-only-masking).

Variant 3 removes the **14,463 visible treatment edges** as well, keeping all
other edges identical to variant 2. Test MRR falls from **0.1807 to 0.1411** and
top-10 answers fall from **606 to 504**, showing that those visible treatment
edges contribute useful context in this setup. Variant 3 still outperforms
variant 1, which removes other direct edges from held-out pairs. See the
[exact three-variant comparison](pilot/studies/full_graph_variant_3_comparison.json).

Variant 4 completes the four-way validation comparison. Removing visible
treatment edges from variant 1 lowers validation MRR from **0.1057 to 0.0344**;
removing other held-out direct edges from variant 3 lowers it from **0.1452 to
0.0344**. Both sources of context contribute in this setup. The
[paired comparison](pilot/studies/full_graph_variant_4_comparison.json) includes
disease-bootstrap intervals and top-10 transitions.

The [next-work plan](pilot/README.md#plan-for-informative-experiments) prioritizes
subgroup analysis of saved scores and a grouped removal of direct treatment-related
clues, requiring **one remaining full-graph validation run**. Then compare full
and sampled context with **identical
targets, candidates, checkpoint, and ranking rules**, masking held-out pairs
**before** Gandalf walks.
Use validation to choose settings; the inspected test split is exploratory.
These metrics measure recovery of graph assertions, not clinical efficacy.
