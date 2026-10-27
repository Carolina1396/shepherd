# Historical sampling and full-graph run commands

Return to the [four-study index](README.md). This guide preserves the protocols,
results, and commands for original experiments 1–4. The numbers below are
historical IDs, not the current study numbering.

- Original 1–2 belong to **Study 3: Sampling and retrieval**.
- Original 3–4 belong to **Study 1: Full-graph treatment prediction** and use the
  older Drug-only definition. For the current chemical/drug comparison, use the
  [pretrained](chemical_disease/README.md) and [fine-tuning](chemical_finetune/README.md) guides.

Run from the repository root with the [required local inputs](TECHNICAL.md#setup-and-required-inputs).
Choose fresh run IDs where examples already exist. Metrics are fractions.

## 1. Gandalf sampling and coverage

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

## 2. ULTRA 4g on the sampled graph

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

**Run after experiment 1:**

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

## 3. ULTRA 4g on the full graph

**Purpose and setup.** Given a disease, rank **5,326 Drug candidates** using the
full Gandalf graph. Split all 18,079 explicit Drug–Disease treatment pairs into
**14,463 visible, 1,807 validation, and 1,809 test** pairs. Remove every direct
held-out pair connection across predicates and directions. The resulting graph
has **1,670,341 nodes and 27,917,681 directed connections** before inverse edges.

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

## 4. ULTRA 3g on the full graph, both directions

**Purpose and setup.** Use the same frozen full graph and **1,809 test pairs**
from experiment 3, with the 3g checkpoint. Given a disease, rank 5,326 drugs;
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

### Run both directions

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

