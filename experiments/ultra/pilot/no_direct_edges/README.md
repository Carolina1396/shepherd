# Remove all direct Drug–Disease connections

Part of [Study 2: direct edge context](../README.md#study-2-direct-edge-context). Original experiment ID: **6**.
Numbered experiment references below use the original IDs.

**Status: completed for both checkpoints.** This experiment measures how much the
pretrained and fine-tuned ULTRA 4g checkpoints depend on direct Drug–Disease
connections in their inference graph. Neither checkpoint is retrained.

| Fixed component | Setting |
|---|---|
| Evaluation pairs | Same 1,809 test pairs as Experiments 3 and 5 |
| Query direction | Given disease, predict Drug (977 disease queries) |
| Candidates | Same 5,326 explicit `biolink:Drug` nodes, including isolated nodes |
| Checkpoints | Original pretrained 4g; Experiment 5's validation-selected step 1,000 |
| Ranking | All-known answer filtering, pessimistic ties; Hits@k as fractions |
| Hardware / batch | One A6000, batch size 1 |

## Results

| Context | Checkpoint | Test MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---|---:|---:|---:|---:|---:|
| Original masked graph | Pretrained 4g | 0.1068 | 0.0575 | 0.1012 | 0.2007 | 363 / 1,809 |
| No direct Drug–Disease edges | Pretrained 4g | 0.0393 | 0.0149 | 0.0387 | 0.0697 | 126 / 1,809 |
| Original masked graph | Fine-tuned 4g | 0.1673 | 0.0879 | 0.1675 | 0.3350 | 606 / 1,809 |
| No direct Drug–Disease edges | Fine-tuned 4g | 0.0723 | 0.0376 | 0.0719 | 0.1404 | 254 / 1,809 |

Removing direct Drug–Disease context substantially reduced performance for both
checkpoints. Fine-tuned 4g still performed better, but its top-10 answers fell
from **606 to 254**; pretrained recovery fell from **363 to 126**. The original
context already masked every held-out pair, so this measures the value of
remaining connections for other pairs, not access to the exact held-out edges.
The fine-tuned model retains its earlier learning from treatment labels.

**Resources.** Test inference took **22.40 minutes** for pretrained and **22.41
minutes** for fine-tuned 4g, about **1.38 seconds per disease** each. Peak allocated
GPU memory was **7.61 GB** for each checkpoint on the A6000. Graph filtering took
20.9 seconds and rebuilding the relation graph took 242.8 seconds. These are
phase timings; they exclude additional loading, output, and ranking overhead.

[Exact results, provenance, and rank verification](../studies/full_graph_no_direct_edges.json).

## What changes

Start with the frozen full graph used by the pilot, which already excludes
held-out pair connections. Remove **every remaining connection between any
explicit Drug node and any explicit Disease node**, under all predicates and
in both directions. This includes visible training pairs and pairs without a
`treats` label, across all 51,707 Disease nodes. No nodes are removed; the number
of evaluation pairs and candidate drugs stays fixed.

ULTRA's relation graph is rebuilt from this modified context. Reusing the
original relation graph could retain information about removed connections.
The removed-edge counts are additional to the pilot's existing held-out mask.
`treats` edges between other category combinations can remain: this experiment
removes Drug–Disease connections, not every `treats` edge in the knowledge graph.

The fine-tuned checkpoint still contains what it learned from training labels.
This tests the effect of removing connections at inference, not training a
model without treatment supervision. Comparisons remain exploratory because
we have already inspected this test split.

## Removed connections

Removed **578,319 unique directed connections**, leaving **27,339,362** before
ULTRA adds inverse edges. All 1,670,341 nodes remain; 1,299 Drug nodes are isolated.
These counts are additional to the existing validation/test pair mask.

| Predicate | Removed connections |
|---|---:|
| `biolink:treats_or_applied_or_studied_to_treat` | 187,102 |
| `biolink:in_clinical_trials_for` | 145,914 |
| `biolink:has_side_effect` | 55,556 |
| `biolink:contributes_to` | 54,788 |
| `biolink:applied_to_treat` | 50,435 |
| `biolink:correlated_with` | 29,409 |
| `biolink:contraindicated_in` | 17,422 |
| `biolink:treats` | 14,463 |
| `biolink:related_to` | 7,357 |
| `biolink:causes` | 7,229 |
| `biolink:affects` | 4,925 |
| `biolink:disrupts` | 1,294 |
| `biolink:predisposes_to_condition` | 1,001 |
| `biolink:positively_correlated_with` | 975 |
| `biolink:negatively_correlated_with` | 128 |
| `biolink:studied_to_treat` | 101 |
| `biolink:produces` | 81 |
| `biolink:occurs_in` | 32 |
| `biolink:exacerbates_condition` | 27 |
| `biolink:coexists_with` | 23 |
| `biolink:has_part` | 23 |
| `biolink:in_preclinical_trials_for` | 19 |
| `biolink:located_in` | 13 |
| `biolink:diagnoses` | 2 |
| **Total** | **578,319** |

## Run and resume

Commands run from the repository root, with the existing Gandalf and GPU
environments, frozen full-graph inputs, and Experiment 5's `best.pt`. These
large inputs are local and excluded from Git. See [setup](../../SETUP.md).

The completed run is `pilot/results/no_direct_edges_001/`. To repeat it, use a
fresh directory:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/no_direct_edges/run.py \
  --output experiments/ultra/pilot/results/no_direct_edges_002
```

Add `--resume` for an existing run. Saved scores are verified and reused only
within this experiment with matching input, code, and checkpoint hashes.
`--max-queries 2` limits each checkpoint to a partial smoke evaluation; remove
the limit when resuming to finish. Partial runs do not write a final comparison.

## Outputs

- `settings.json`: frozen protocol, checkpoint hashes, and source hashes.
- `preparation.json`: removed edges by predicate, remaining graph size, and isolated nodes.
- `data/` and `categories.json`: modified triples and unchanged evaluation inputs/categories.
- `relation_graph.pt` and `.json`: rebuilt relation graph and input binding.
- `pretrained_4g/`, `finetuned_4g/`: scores, ranks, metrics, and provenance.
- `comparison.json`: both completed test evaluations alongside their original-context baselines.

The compact study record is retained for GitHub; full score files, ranks,
modified graph data, and checkpoints remain in the local run directory.
