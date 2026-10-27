# MechRepoNet: remove other direct chemical–disease relationships

Follow-up to [Study 4](../README.md#study-4-mechreponet-reference) and the
[original MechRepoNet reference](README.md). This tests whether direct
chemical–disease relationships for other pairs help recover held-out indications.

**Status: validation and test complete and independently verified, 2026-10-21.**

## Results

MRR and Hits@k below are fractions. Each comparison uses the same pairs and
40,413 candidates, with the same frozen pretrained checkpoint.

| Context / split | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|
| Original, validation | 0.2727 | 0.1924 | 0.2974 | 0.4315 | 148 / 343 |
| Remove other direct edges, validation | 0.2554 | 0.1837 | 0.2945 | 0.4111 | 141 / 343 |
| Original, test | 0.2193 | 0.1391 | 0.2319 | 0.3797 | 131 / 345 |
| Remove other direct edges, test | 0.2404 | 0.1739 | 0.2812 | 0.3681 | 127 / 345 |

The result is mixed. Validation MRR decreases 6.36% relative, while test MRR
increases 9.64%. Top-10 recovery decreases in both splits. Test rank-1 answers
increase from 48 to 60, which helps explain why MRR rises despite fewer top-10
answers. Across all test answers, 91 ranks improve, 202 worsen, and 52 are
unchanged; 24 answers enter the top 10 and 28 leave it. The removal does not
consistently improve performance, and most aggregate performance remains with
visible indications and the remaining graph context. No statistical significance
claim is made from this single split.

All 476 score files were hash-verified and all 688 held-out ranks independently
recomputed. The raw-source graph reconstruction and four regression tests passed.
Baseline rank files were also checked against the retained reference hashes.
[Exact results, paired changes, and verification](../studies/mechreponet_non_indication_ablation_001_results.json).

On the A6000, test inference took 46.34 seconds (0.190 seconds per disease), with
2.10 GB peak allocated GPU memory and 2.26 GB reserved. Relation-graph rebuilding
took 86.23 seconds. Validation's 138.95 seconds includes first-call compilation
of the CUDA extension in this workspace, so it is not a steady-state inference
timing comparison with the baseline. Timings exclude other setup and file work.

## Protocol

Start from the verified `mechreponet_4g_001` prepared graph. Its 688 held-out
indication pairs already have every direct connection masked in both directions.
Remove every remaining **non-`indication` edge between a ChemicalSubstance and
a Disease**, in either direction, throughout the graph.

| Additional removed predicate | Unique directed edges |
|---|---:|
| `treats_CtD` | 65,009 |
| `marker_or_mechanism_CmD` | 20,924 |
| `palliates_CplD` | 2,087 |
| `prevents_CpvD` | 1,280 |
| **Total** | **89,300** |

Keep all **2,751 visible ChemicalSubstance → Disease indications**, all 226
other-category indications, and all remaining relationships. The graph has
**9,560,423 directed triples**, or 19,120,846 after ULTRA adds inverses, compared
with 9,649,723 before this additional removal. The relation graph is rebuilt
from the ablated triples; the original relation graph is not reused.

The checkpoint, split seed 731, 343 validation pairs, 345 test pairs, node and
predicate mappings, and all 40,413 candidates remain fixed. The model is
pretrained ULTRA 4g with no training, fine-tuning, or validation-based selection.
Both splits use the same context and all-known-indication filtering with
pessimistic ties, exactly as in the reference run.

Removal isolates **2,717 candidates**, all retained in ranking. One validation
answer and two test answers have isolated chemical endpoints; three validation
and three test pairs have isolated disease endpoints. They remain in evaluation.
These counts can overlap; they are not exclusions.

This is a controlled context ablation on previously inspected splits. It does
not remove visible indication context, and does not measure clinical efficacy.

## Run and verify

Use the existing environments, checkpoint, pinned ULTRA checkout, and historical
Tier 0 config required by the original runner; see [setup](../../SETUP.md).
Set `--baseline` to the original frozen MechRepoNet dataset. The commands below
assume it is in this checkout. On the current machine the source baseline is at
`/home/agonzalez/shepherd/experiments/ultra/pilot/results/mechreponet_4g_001`.
Use a fresh output suffix for a repeat run.

```bash
experiments/ultra/.venv-model-gpu/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/mechreponet -p 'test_*.py' -v

experiments/ultra/.venv-model-gpu/bin/python -B -u \
  experiments/ultra/pilot/mechreponet/prepare_ablation.py \
  --baseline experiments/ultra/pilot/results/mechreponet_4g_001 \
  --output experiments/ultra/pilot/results/mechreponet_non_indication_ablation_002

experiments/ultra/.venv-model-gpu/bin/python -B -u \
  experiments/ultra/pilot/mechreponet/verify_ablation.py \
  --dataset experiments/ultra/pilot/results/mechreponet_non_indication_ablation_002

bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/mechreponet/run.py \
  --dataset experiments/ultra/pilot/results/mechreponet_non_indication_ablation_002

experiments/ultra/.venv-model-gpu/bin/python -B -u \
  experiments/ultra/pilot/chemical_disease/verify_results.py \
  --dataset experiments/ultra/pilot/results/mechreponet_non_indication_ablation_002
```

`verify_ablation.py` reconstructs the entire expected graph directly from the
hash-verified raw sources and independently reconstructs the split. It checks
the retained indications and unchanged nodes, predicates, and candidate pool.
The generic score verifier recomputes every filtered rank from the saved score
vectors and checks their hashes and aggregate metrics.

The completed run uses suffix `_001`. Bulk graphs, relation-graph cache, score
vectors, ranks, preparation verification, and evaluation verification remain in
the ignored results directory. The runner supports `--resume` and optional
`--max-queries` smoke checks just like the reference; final comparisons require
both complete splits.
