# Chemical/drug treatment prediction: fine-tuned 4g

Part of [Study 1: full graph treatment prediction](../README.md#study-1-full-graph-treatment-prediction). Original experiment ID: **11**.
Numbered experiment references below use the original IDs.

Fine-tune a new model from the original pretrained 4g checkpoint on Experiment
10's frozen dataset. This permits a direct pretrained-versus-fine-tuned comparison
with the same labels, split, masked graph, and candidate pool. It does not reuse
Experiment 5's Drug-only fine-tuned weights.

| Setting | Value |
|---|---:|
| Visible training pairs | 18,334 |
| Validation pairs / diseases | 2,291 / 1,145 |
| Test pairs / diseases | 2,293 / 1,122 |
| Chemical/drug candidates per disease | 1,117,832 |
| Maximum optimizer steps | 1,000 |
| Batch size / negatives per positive | 1 / 256 |
| Validation interval | 250 steps |
| AdamW learning rate / weight decay | 0.00001 / 0.01 |
| Adversarial temperature / random seed | 1.0 / 1024 |

Use the same training schedule as Experiment 5: seed-shuffled training pairs,
uniform candidate sampling with replacement, and exclusion of visible positives
from negatives. Rejection sampling avoids allocating a separate million-node
array for every disease. Held-out labels do not filter training negatives.
One thousand updates visit 1,000 distinct training pairs, less than a full epoch.

All direct held-out pair connections remain globally masked, across all predicates
and both directions. During each training step, upstream ULTRA additionally masks
all direct connections for that batch's positive and sampled negative pairs
(`remove_one_hop=True`). Other training pairs remain graph context. The relation
graph stays fixed from Experiment 10's masked graph, following Experiment 5.

Choose the checkpoint with the highest full-validation MRR, retaining the
pretrained checkpoint if no validation check improves it. Stop after three
consecutive non-improving checks or 1,000 updates. Only then evaluate all test
pairs and independently recompute saved ranks. Ranking uses all-known-answer
filtering and pessimistic ties against the same full chemical/drug candidate pool.

Status: **completed and independently verified**. Validation selected step 1,000.
Eight protocol tests passed. A separate smoke run
matched Experiment 10's pretrained scores exactly on two queries, performed two
finite-gradient updates, confirmed changed weights, and ran two validation
queries. It did not select a checkpoint or evaluate test.

| Model / split | Pairs | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|---:|
| Pretrained / validation | 2,291 | 0.0868 | 0.0485 | 0.0808 | 0.1637 | 375 |
| Fine-tuned / validation | 2,291 | 0.1258 | 0.0725 | 0.1248 | 0.2270 | 520 |
| Pretrained / test | 2,293 | 0.0825 | 0.0414 | 0.0820 | 0.1618 | 371 |
| Fine-tuned / test | 2,293 | 0.1231 | 0.0685 | 0.1212 | 0.2202 | 505 |

Validation MRR improved at each check: 0.0991 at step 250, 0.1136 at step 500,
0.1184 at step 750, and 0.1258 at step 1,000. Training stopped at the configured
limit, not early. The selected checkpoint placed 134 more test answers in the
top 10 than pretrained 4g. It remains below MechRepoNet's test MRR 0.2193 and
Hits@10 0.3797, with different graph, labels, and candidate population.

The workflow took **212.12 minutes (3.54 hours)**, including verification.
Measured optimizer time was 66.65 minutes, four validation passes took 106.90
minutes of inference, and test inference took 26.14 minutes. The remaining wall
time includes setup, checkpoint/file writing, ranking, and verification; the
earlier smoke run is excluded. Peak allocated GPU memory was **29.07 GB** during
training and **7.76 GB** during test. Test inference averaged **1.40 seconds per
disease query** against all 1,117,832 candidates.

Independent verification confirmed validation-based checkpoint selection,
all selected-validation/test score hashes, and every rank and metric across
4,584 held-out pairs. Only 1,000 of the 18,334 visible pairs received a positive
training update; other visible pairs remained graph context.

The pretrained baseline is validation **MRR 0.0868 / Hits@10 0.1637** and test
**MRR 0.0825 / Hits@10 0.1618**. These are exploratory graph-recovery evaluations;
the previously inspected test set is not used to choose the checkpoint.

From the repository root, choose a fresh output directory. The complete workflow
trains, selects by validation, evaluates test, and verifies the results:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_finetune/workflow.py \
  --output experiments/ultra/pilot/results/chemical_finetune_4g_002
```

Use the same command with `--resume` after an interruption. For separate phases:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/pilot/chemical_finetune/run.py \
  --output experiments/ultra/pilot/results/chemical_finetune_4g_002
bash experiments/ultra/scripts/gpu_python.sh -B -u experiments/ultra/pilot/chemical_finetune/run.py \
  --output experiments/ultra/pilot/results/chemical_finetune_4g_002 --test-only
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_finetune/verify_results.py \
  --output experiments/ultra/pilot/results/chemical_finetune_4g_002
```

The workflow expects the verified Experiment 10 dataset at
`pilot/results/chemical_disease_4g_001/`. It saves checkpoints, per-step timing and
GPU memory, validation/test scores and ranks, and a verification report. The
active run's log and phase status are sibling files ending in `.log` and
`.status.json`. A result record is retained under `pilot/studies/` on completion.

[Setup and smoke evidence](../studies/chemical_finetune_4g_001_setup.json).
[Completed results and verification](../studies/chemical_finetune_4g_001_results.json).
