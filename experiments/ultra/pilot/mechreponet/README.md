# MechRepoNet reference with pretrained ULTRA 4g

Part of [Study 4: MechRepoNet reference](../README.md#study-4-mechreponet-reference). Original experiment ID: **8**.
Numbered experiment references below use the original IDs.

**Status: validation and test complete; scores and ranks independently verified.** Apply Experiment 3's
split, masking, and ranking rules to the original MechRepoNet graph. This is a
new comparison; Experiment 3's Tier 0 results remain unchanged.

| Setting | Value |
|---|---|
| Model | Same pretrained 4g checkpoint and unchanged ULTRA code as Experiment 3 |
| Training | None; checkpoint fixed before validation and test |
| Target | Unique `indication` edges from ChemicalSubstance to Disease |
| Target pairs | 3,439 |
| Split | 2,751 visible / 343 validation / 345 test; seed 731 |
| Disease queries | 232 validation / 244 test |
| Prediction | Given disease, rank candidate compounds |
| Candidate population | All 40,413 graph-connected ChemicalSubstance nodes, retained after masking |
| Context | Full original MechRepoNet graph; all direct held-out pair connections removed |
| Nodes / original predicates | 249,553 / 69 |
| Connections before / after masking | 9,650,411 / 9,649,723 |
| Held-out pairs / removed connections | 688 / 688; removed connections all use `indication` |
| Ranking | All-known answer filtering across splits, pessimistic ties |

**Candidate difference from Tier 0.** MechRepoNet's node metadata has no separate
Drug category. We therefore use its ChemicalSubstance category, which is broader
than Tier 0's 5,326 explicit Drug candidates. Graphs, targets, and candidate pools
differ: this follows the same evaluation procedure, but does not isolate graph
quality alone.

## Results

| Graph / split | Pairs | MRR | Hits@1 | Hits@3 | Hits@10 | Top-10 answers |
|---|---:|---:|---:|---:|---:|---:|
| MechRepoNet validation | 343 | 0.2727 | 0.1924 | 0.2974 | 0.4315 | 148 |
| MechRepoNet test | 345 | **0.2193** | 0.1391 | 0.2319 | **0.3797** | 131 |
| Tier 0 validation (Experiment 3) | 1,807 | 0.1057 | 0.0564 | 0.1035 | 0.1920 | 347 |
| Tier 0 test (Experiment 3) | 1,809 | 0.1068 | 0.0575 | 0.1012 | 0.2007 | 363 |

Both graphs use the same pretrained 4g checkpoint, disease-to-compound/drug
prediction, pair split rule, direct-pair masking, and filtered ranking. The new
MechRepoNet scores are higher even after direct held-out connections are removed.
Different target populations, graph relations, and candidate categories/counts
prevent attributing the gap solely to graph quality. This is a new split and
checkpoint; its change from the historical 3g result is not a masking-only effect.

**Resources.** On the A6000, validation inference took **44.92 seconds** and test
inference **46.62 seconds** (about **0.19 seconds per disease**). Peak allocated GPU
memory was **2.12 GB** for each split; peak reserved memory was **2.29 GB**. Data
preparation took 19.37 seconds and relation-graph construction 87.22 seconds.
These phase timings exclude additional process startup, file writes, and rank
calculation; a few initial queries include kernel warm-up.

**Verification.** Independently reconstructed the split and scanned all 9,649,723
remaining connections for hidden endpoint pairs in both directions. Checked
candidate/target categories, all 476 score-file hashes, and independently
recomputed every rank and metric for all 688 validation/test pairs. Three
preparation regression tests passed.

[Exact results, input hashes, and verification](../studies/mechreponet_ultra4g_masked.json).

**Context-removal follow-up:** removing the 89,300 non-`indication` direct
ChemicalSubstance–Disease edges while retaining visible indications gives
validation MRR **0.2554** / Hits@10 **0.4111**, and test MRR **0.2404** /
Hits@10 **0.3681**. Test MRR increases but top-10 recovery falls from 131 to 127;
validation also declines. [Protocol, matched results, and commands](NON_INDICATION_ABLATION.md).

## Data and masking

Use the same original background graph as the older MechRepoNet benchmark:
`/home/agonzalez/git/ULTRA/kg-datasets/MechRepoNet/raw/graph.txt.backup`.
Categories come from `/home/agonzalez/data_KG/MIND_nodes/nodes.csv`.
Source checksums are saved in `preparation.json`.

Enumerate every eligible indication pair in the graph, rather than reusing the
old `train00.txt` / `dev.txt` / `test.txt` split. Exclude the 226 indication records
whose endpoints do not have the required categories from evaluation targets;
they can remain context. Other predicates, including `treats_CtD`, remain context
unless they directly connect a held-out pair. They are not merged into indication
labels for this experiment.

Split sorted unique pairs with seed 731 and the same 80/10/10 allocation used in
Experiment 3. Remove **every direct connection of every validation/test pair**,
under any predicate and in either direction. Verify all visible target pairs
remain and no held-out direct connection survives. Retain all original nodes
and candidates, including any nodes isolated by masking. Rebuild ULTRA's
relation graph exclusively from the masked triples, then add no held-out edges
back for validation or test.

This fixes the direct-answer visibility in the original benchmark. It does not
exclude possible indirect clues through equivalent or related entities. This
remains an exploratory comparison on a previously examined graph.

## Run and resume

From the repository root, with the existing local source files, environments,
and checkpoint:

```bash
experiments/ultra/.venv/bin/python -B -u \
  experiments/ultra/pilot/mechreponet/prepare.py \
  --output experiments/ultra/pilot/results/mechreponet_4g_002

bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/mechreponet/run.py \
  --dataset experiments/ultra/pilot/results/mechreponet_4g_002
```

Preparation accepts `--graph` and `--nodes` for alternate source locations.
Use a new output directory for a new preparation; input and code hashes bind
each run. The original run uses suffix `_001`.

Evaluation runs validation and test with the same fixed checkpoint and settings.
Add `--max-queries 2` for a partial smoke check. Resume evaluation with `--resume`
and without that limit to finish; completed score files are hash-verified and
reused. No model selection or fine-tuning occurs between splits.

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/mechreponet -p 'test_*.py' -v
```

## Outputs

The local run retains the masked triples, node/category mapping, candidates,
labels, source hashes, and rebuilt relation graph. Under `evaluation/`, each
split retains every candidate score, answer ranks, complete/partial metrics,
and checkpoint/memory provenance. `evaluation/comparison.json` is written only
when both splits complete, alongside the original Tier 0 reference metrics.
Bulk graphs and scores stay in the ignored `pilot/results/` directory.
