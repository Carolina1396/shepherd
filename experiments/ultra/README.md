# ULTRA treatment-prediction study

We use **Gandalf** to access and sample the Translator knowledge graph, and
**ULTRA** to rank missing treatment links. The study asks how well known
Drug–Disease relationships can be recovered and whether a smaller sampled graph
can preserve useful prediction context.

## Start here

| Document | Contents |
|---|---|
| [Pilot study](pilot/README.md) | Four experiments, results, takeaways, run commands, and runtimes |
| [Setup](SETUP.md) | Dependencies, CPU/GPU environments, graph-store building, and a CPU benchmark check |
| [Technical guide](pilot/TECHNICAL.md) | Split/masking rules, output formats, resume, verification, and provenance |
| [Data notebooks](notebooks/README.md) | Graph overview, treatment-pair inventory, sources, and knowledge levels |

## Completed work

All ULTRA evaluations use pretrained checkpoints with **no fine-tuning**.
**MRR and Hits@k are fractions from 0 to 1.**

| Experiment | Scope | Main result |
|---|---|---|
| 1. Gandalf sampling and coverage | 1,000 three-step walk attempts from each of 20 diseases | 19,484 nodes; 46,868 distinct directed connections |
| 2. ULTRA 4g on the sampled graph | Disease → drug; 49 validation pairs | MRR **0.0949**, Hits@10 **0.1837**; test not evaluated |
| 3. ULTRA 4g on the full graph | Disease → drug; 1,809 test pairs | MRR **0.1068**, Hits@10 **0.2007** |
| 4. ULTRA 3g on the full graph | Both directions; the same 1,809 test pairs | Combined MRR **0.1037**, Hits@10 **0.1921** |

The 3g test results are **0.0765 MRR** for disease→drug and **0.1310 MRR** for
drug→disease. Its combined result averages 3,618 directional predictions over
1,809 unique pairs. See the [pilot results](pilot/README.md) and
[exact 3g study record](pilot/studies/full_graph_ultra3g_bidirectional.json).

The full-graph 4g run also completed validation: MRR **0.1057**, Hits@10
**0.1920** on 1,807 pairs. Its
[validation](pilot/studies/evidence/full-graph-ultra/run_001/validation/metrics.json) and
[test](pilot/studies/evidence/full-graph-ultra/run_001/test/metrics.json) metric reports are retained in the repository; their raw scores and ranks
remain available locally. Original temporary 3g scores were deleted; the
recorded aggregates and permanent rerun code are retained.

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
All direct connections between validation/test pairs are removed across
predicates and directions before inference. The masked graph contains
27,917,681 directed connections, or 55,835,362 after ULTRA adds inverses.

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
| `pilot/results/` | Sampling runs, sampled evaluations, and new bidirectional reruns |
| [pilot/studies/](pilot/studies/) | Retained aggregate study records |

Bulk data, run directories, vendor code, and virtual environments stay local
and are ignored by Git. Code, notebooks, documentation, aggregate records, and
[small original reports](pilot/studies/evidence/README.md) are included for GitHub. [Output formats and retention details](pilot/TECHNICAL.md#run-management-and-output-files).

## What we learned and next step

ULTRA 4g outperformed 3g for drug prediction on the same full graph and test
pairs. Comparing sampled and full-graph scores does not isolate graph size,
because targets and candidate pools changed.

Next, compare full and sampled context with **identical targets, candidates,
checkpoint, and ranking rules**, masking held-out pairs **before** Gandalf walks.
Use validation to choose settings; the inspected test split is exploratory.
These metrics measure recovery of graph assertions, not clinical efficacy.
