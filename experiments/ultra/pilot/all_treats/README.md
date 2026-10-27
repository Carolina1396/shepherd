# All treats endpoints: historical pretrained 4g comparison

Part of [Study 1: full graph treatment prediction](../README.md#study-1-full-graph-treatment-prediction). Original experiment ID: **9**.
Numbered experiment references below use the original IDs.

This run expands Experiment 3 to every unique directed `biolink:treats` pair,
without requiring Drug or Disease endpoint labels. It uses the same pretrained
4g checkpoint, with no fine-tuning. Earlier experiment outputs are preserved.

| Output | Count |
|---|---:|
| Source `treats` records | 33,634 |
| Unique treatment pairs | 28,983 |
| Visible context pairs | 23,186 |
| Validation pairs | 2,898 |
| Test pairs | 2,899 |
| Distinct subjects with recorded treatments | 5,037 |
| Distinct treatment target objects | 5,065 |
| Candidates ranked per target | 1,417,973 |
| Validation target queries | 1,429 |
| Test target queries | 1,458 |

Candidates are every connected node with at least one of `Drug`,
`SmallMolecule`, `ChemicalEntity`, or `Protein` in its Biolink categories.
The union contains 1,117,832 chemical/drug nodes and 300,141 protein nodes.
All recorded treatment subjects are included. Candidates are not restricted to
subjects with known treatment edges. Targets include diseases, phenotypes and
a few other node types, so this evaluates treatment-subject prediction more
broadly than disease-to-drug prediction.

The 28,983 pairs comprise:

| Endpoint types | Unique pairs |
|---|---:|
| Chemical/drug → Disease | 22,918 |
| Chemical/drug → PhenotypicFeature | 5,546 |
| Protein → Disease | 400 |
| Protein → PhenotypicFeature | 110 |
| Chemical/drug → OrganismTaxon | 8 |
| Chemical/drug → BiologicalProcess | 1 |

Pairs are deduplicated by source graph subject/object IDs, sorted, shuffled with
seed 731, and split 80/10/remaining. All direct connections between each held-out
pair are removed, across every predicate and both directions, before building
ULTRA's inverse edges and relation graph. Other visible pairs remain context.
The masked context retains 27,913,363 directed triples (55,826,726 including
inverses); 13,926 direct triples were removed. All-known-answer filtering and
pessimistic ties match Experiment 3. The
inherited `drug`/`disease` label fields mean subject/object in this experiment.

Status: **completed** on validation and test, using the fixed pretrained 4g
checkpoint with no fine-tuning or model selection.

| Split | Pairs | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|---:|
| Validation | 2,898 | 0.0810 | 0.0445 | 0.0794 | 0.1515 | 439 |
| Test | 2,899 | 0.0828 | 0.0414 | 0.0814 | 0.1538 | 446 |

GPU inference took **33.35 minutes** for validation and **34.05 minutes** for
test, averaging **1.40 seconds per target query** across 1,417,973 candidates.
Peak allocated GPU memory was **7.77 GB**, with **10.16 GB reserved**, on an
RTX A6000. These inference timings exclude graph preparation, ranking, and file
writing. Dataset preparation took 46.67 seconds; relation-graph construction
added 250.91 seconds. The resumed validation/test workflow took 74.34 minutes
wall time, including its setup and output overhead, and excluding the earlier
preparation and smoke run. The saved inference totals include the two reused
smoke queries.

Independent verification checked all **2,887 score-file hashes**, recomputed
every held-out rank, and reproduced the metrics for all **5,797 evaluated pairs**.
Preparation verification also confirmed complete treats coverage and removal
of all direct held-out pair connections.

The test result is below Experiment 3's MRR 0.1068 / Hits@10 0.2007, but this
changes the labels, split membership, and candidate pool together. It does not
isolate the effect of any single change. These remain exploratory graph-recovery
results, including the non-Disease targets listed above.

Run from the repository root, using a fresh output directory:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/all_treats/prepare.py \
  --scope all --candidates chemical-protein \
  --output experiments/ultra/pilot/results/all_treats_4g_002
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/pilot/all_treats/run.py \
  --dataset experiments/ultra/pilot/results/all_treats_4g_002
```

`--max-queries 1` checks one query per split; `--resume` continues the same run.
Partial results are not final metrics. Local output retains configuration,
prepared graph, file hashes, score vectors, ranks, timing and peak GPU memory.

[Verified setup and launch record](../studies/full_graph_all_treats_4g_setup.json).
The local `run.log` records progress and `run_status.json` records the exit status.
[Completed results and resource measurements](../studies/full_graph_all_treats_4g_results.json).
