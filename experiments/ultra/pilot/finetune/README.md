# Drug-only treatment prediction: fine-tuned 4g

Part of [Study 1: full graph treatment prediction](../README.md#study-1-full-graph-treatment-prediction). Original experiment ID: **5**.
Numbered experiment references below use the original IDs.

**Status: training, validation selection, and test evaluation completed.**
The objective is to improve disease→drug prediction over the pretrained 4g
baseline. This experiment uses the existing full graph, not Gandalf sampling.

| Setting | Initial run |
|---|---|
| Initial checkpoint | ULTRA 4g; all model parameters trainable |
| Training pool | 14,463 visible Drug–Disease treatment pairs |
| Validation / test | 1,807 / 1,809 pairs |
| Drug candidates | The same 5,326 as Experiment 3 |
| Optimizer | AdamW, learning rate `1e-5`, weight decay `0.01` |
| Training batch | 1 positive + 256 sampled Drug negatives |
| Training budget | 1,000 optimizer steps; validate every 250 |
| Selection | Best full-validation pair-weighted MRR; stop after 3 checks without improvement |
| Unchanged baseline | Validation MRR 0.105748; Hits@10 0.192031 |

[config.json](config.json) holds the starting settings. **1,000 steps are not
one epoch:** they visit 1,000 distinct pairs out of 14,463. Seeded permutations
cover the full pool before repeating if the step budget is increased. This is
an initial training budget, not a claim that the model has converged. Changing
settings requires a new output directory.

## Results

Step **1,000** was selected using validation MRR, then evaluated on the 1,809
test pairs. All metrics below are fractions. The graph, candidates, and ranking
rules match the pretrained baseline from Experiment 3.

| Checkpoint | Validation MRR | Validation Hits@10 |
|---|---:|---:|
| Pretrained | 0.1057 | 0.1920 |
| Step 250 | 0.1367 | 0.2557 |
| Step 500 | 0.1517 | 0.2950 |
| Step 750 | 0.1580 | 0.3060 |
| Step 1,000 | **0.1654** | **0.3210** |

| Test method | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|
| Pretrained 4g | 0.1068 | 0.0575 | 0.1012 | 0.2007 | 363 / 1,809 |
| Fine-tuned 4g | **0.1673** | **0.0879** | **0.1675** | **0.3350** | **606 / 1,809** |

Fine-tuning recovered **243 additional test answers** in the top 10. Validation
improved at every check; no convergence claim follows from this partial epoch.
[Exact study record](../studies/full_graph_ultra4g_finetuned.json) preserves
configuration, checkpoint/input hashes, validation trajectory, and test results.
The 977 test score-file hashes were checked, and all reported test MRR/Hits
metrics were recomputed from the 1,809 unique answer ranks.

## Training and evaluation protocol

The pinned upstream model is unchanged. Its native `remove_one_hop=True`
removes all direct connections, across predicates and directions, for the
positive and sampled negative pairs in each training batch. Validation/test
pair connections were already removed from the frozen context. The aggregate
relation graph stays fixed during fitting, following upstream ULTRA behavior;
it is built from the held-out-masked context, not rebuilt per training batch.

Training corrupts the Drug/head only to match our target task. Negative samples
come from the Drug candidate pool, excluding that disease's **visible training
positives only**. Held-out labels do not guide fitting or negative sampling;
some unlabeled negatives may be true treatments. The loss follows upstream
ULTRA's binary cross entropy with detached adversarial negative weights
(temperature 1). This differs from upstream's generic mixed head/tail,
all-entity negative sampler.

Validation ranks all 5,326 candidates, filters known answers across all splits,
and uses pessimistic ties, matching Experiment 3. Every validation check uses
all 986 disease queries / 1,807 pairs. The pretrained checkpoint is eligible
as step 0: worse fine-tuned checkpoints cannot replace it. Test inference is a
separate command after training finishes and remains exploratory because the
test split was previously inspected.

## Run

Commands run from the repository root. Follow [setup](../../SETUP.md) for the
Gandalf store, GPU environment, and pinned ULTRA checkout. This runner also
requires the original `output/full-graph-ultra/run_001/` frozen inputs, relation
graph cache, and original 4g validation metrics/settings. The smoke test uses
two original validation score arrays to check pretrained inference parity.
These large/local inputs are not included in GitHub.

Small setup check (two optimizer steps and two validation queries):

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/finetune/run.py \
  --output experiments/ultra/pilot/results/finetune_4g_smoke_003 --smoke-test
```

Repeat the experiment in a new directory (`finetune_4g_001` contains the completed run):

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/finetune/run.py \
  --output experiments/ultra/pilot/results/finetune_4g_002
```

Repeat with `--resume` after interruption; the runner checks input, code, and
configuration hashes. `--max-new-steps 10` deliberately pauses after ten new
updates. A checkpoint is saved after every optimizer step, including optimizer
and random-generator states. Validation scores already saved for that step are
verified and reused. Use the same `--smoke-test` flag when resuming a smoke run.

After training and validation selection finish, evaluate the selected model:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/finetune/run.py \
  --output experiments/ultra/pilot/results/finetune_4g_002 --test-only
```

The [setup verification record](../studies/finetune_4g_setup.json) records 19
passing protocol tests, exact pretrained-score parity on two queries, and a
one-step pause followed by successful resume to step 2. Both the relation and
entity model weights changed. Partial smoke metrics are not performance results.

## Outputs and cost

Each run retains `settings.json`, source snapshots, `last.pt`, per-step losses,
timings and memory, and validation scores/ranks. Completed training writes
`best.pt` and `completed.json`; test metrics are separate. Smoke runs write
`smoke.json` and partial validation reports, never a selected checkpoint or a
full evaluation result. No original experiment outputs are overwritten.

The completed run used one **NVIDIA RTX A6000**:

| Measurement | Recorded value |
|---|---:|
| 1,000 training updates | 66.8 minutes (4.01 seconds/update on average) |
| Four full validation checks | 91.3 minutes |
| Test inference, 977 disease queries | 22.5 minutes (1.38 seconds/query) |
| Peak allocated GPU memory during training | 29.1 GB |

Training plus validation totals **158.1 minutes of recorded compute**. These
measurements exclude loading, checkpoint/file writes, and ranking overhead;
they are not total wall-clock runtime. GPU memory uses decimal GB. Training
capacity on the V100 has not been verified.

The completed artifacts remain in `pilot/results/finetune_4g_001/`, relative to
`experiments/ultra/`. `completed.json` records training completion before the
separate test command; its `test_evaluated: false` is historical. The later
`test/metrics.json` and `test/result.json` record the completed test, and the
retained study record combines both phases. Raw checkpoints and scores remain
local; the compact study record is included for GitHub.
