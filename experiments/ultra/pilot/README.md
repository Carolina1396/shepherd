# ULTRA pilot: four studies

We test recovery of known treatment links with ULTRA, and whether Gandalf
retrieval can provide smaller graphs with useful prediction context. Runs are
grouped by question; original experiment IDs remain in records and guides.

| Study | Question | Original experiments |
|---|---|---|
| [1. Full-graph treatment prediction](#study-1-full-graph-treatment-prediction) | How do target definitions, checkpoints, and fine-tuning affect ranking? | 3, 4, 5, 9, 10, 11 |
| [2. Direct-edge context](#study-2-direct-edge-context) | How much does prediction depend on other direct Drug–Disease connections? | 6 |
| [3. Sampling and retrieval](#study-3-sampling-and-retrieval) | What context do walks and rules retrieve, and can ULTRA use it? | 1, 2, 7a, 7b, and follow-ups |
| [4. MechRepoNet reference](#study-4-mechreponet-reference) | How does pretrained 4g perform on another properly masked graph? | 8 |

**Current comparison:** chemical/drug → `treats` → Disease on full Tier 0,
pretrained versus fine-tuned 4g. Test MRR improves from **0.0825 to 0.1231**;
Hits@10 from **0.1618 to 0.2202** (371 to 505 of 2,293 answers in the top 10).

**MRR and Hits@k are fractions.** Coverage means an answer node appears in a
retrieved graph; it is not a ranking metric. These are exploratory evaluations
of graph assertions, and the test splits have already been inspected.

## Study 1: Full-graph treatment prediction

The current target definition is **(Drug OR ChemicalEntity OR SmallMolecule)
→ `biolink:treats` → Disease**. After deduplication, 22,918 pairs are split into
**18,334 visible / 2,291 validation / 2,293 test** pairs. Each disease query ranks
**1,117,832 chemical/drug candidates**, including candidates without a known
treatment. All direct held-out pair connections are removed across predicates
and directions. Ranking filters other known answers and uses pessimistic ties.

| Current run | Original ID | Split | MRR | Hits@10 | Top-10 answers |
|---|---|---|---:|---:|---:|
| [Pretrained 4g](chemical_disease/README.md) | 10 | Validation | 0.0868 | 0.1637 | 375 / 2,291 |
| [Fine-tuned 4g](chemical_finetune/README.md) | 11 | Validation | 0.1258 | 0.2270 | 520 / 2,291 |
| Pretrained 4g | 10 | Test | 0.0825 | 0.1618 | 371 / 2,293 |
| Fine-tuned 4g | 11 | Test | 0.1231 | 0.2202 | 505 / 2,293 |

Fine-tuning starts from the original 4g checkpoint, visits 1,000 distinct
training pairs, and selects step 1,000 by full-validation MRR. During each
update, ULTRA also masks all direct connections for that batch's positive and
negative pairs; other training pairs remain context. Convergence is not established.

On the A6000, fine-tuned test inference takes **26.14 minutes**, or **1.40 seconds
per disease query**, with **7.76 GB** peak allocated GPU memory. The fine-tuning
workflow takes **3.54 hours**, including four validation passes, test, and
verification; peak training memory is **29.07 GB**.
[Exact pretrained results](studies/full_graph_chemical_disease_4g_results.json) ·
[Exact fine-tuned results](studies/chemical_finetune_4g_001_results.json).

Earlier variants explain how we reached this definition. Their different
targets and candidate pools prevent a direct comparison with the current task.

| Historical run / guide | Original ID | Test pairs | Candidates | Test MRR | Test Hits@10 |
|---|---|---:|---|---:|---:|
| [Drug-only, pretrained 4g](HISTORICAL_RUNS.md#3-ultra-4g-on-the-full-graph) | 3 | 1,809 | 5,326 drugs | 0.1068 | 0.2007 |
| [Drug-only, pretrained 3g: predict drug](HISTORICAL_RUNS.md#4-ultra-3g-on-the-full-graph-both-directions) | 4 | 1,809 | 5,326 drugs | 0.0765 | 0.1299 |
| Drug-only, pretrained 3g: predict disease | 4 | 1,809 | 51,707 diseases | 0.1310 | 0.2543 |
| Drug-only, pretrained 3g: both directions | 4 | 1,809; 3,618 predictions | Separate pools above | 0.1037 | 0.1921 |
| [Drug-only, fine-tuned 4g](finetune/README.md) | 5 | 1,809 | 5,326 drugs | 0.1673 | 0.3350 |
| [All `treats` endpoints, pretrained 4g](all_treats/README.md) | 9 | 2,899 | 1,417,973 chemicals/drugs/proteins | 0.0828 | 0.1538 |

The all-endpoint run includes non-disease targets and proteins; it is a
historical definition check. Code and output paths remain unchanged.

## Study 2: Direct-edge context

Using the historical Drug-only task, remove **all direct Drug–Disease
connections globally**, across 24 predicates and both directions. This removes
578,319 additional connections beyond the held-out pair mask. Keep the same
1,809 test pairs and 5,326 candidates. Both checkpoints are evaluated without
retraining; the fine-tuned checkpoint comes from the Drug-only run (original 5).

| Context / checkpoint | Test MRR | Test Hits@10 | Top-10 answers |
|---|---:|---:|---:|
| Full context, pretrained 4g | 0.1068 | 0.2007 | 363 |
| No direct Drug–Disease edges, pretrained 4g | 0.0393 | 0.0697 | 126 |
| Full context, fine-tuned 4g | 0.1673 | 0.3350 | 606 |
| No direct Drug–Disease edges, fine-tuned 4g | 0.0723 | 0.1404 | 254 |

Direct context for **other pairs** matters: held-out pairs were already masked
in both conditions. This ablation has not been repeated on the current broader
chemical/drug task. [Protocol, all removed predicates, resources, and commands](no_direct_edges/README.md)
(original **6**) · [Exact results](studies/full_graph_no_direct_edges.json).

## Study 3: Sampling and retrieval

The stages below use different label populations and masking policies. Only
the sampled-graph and full-validation ranking stages produce ULTRA metrics.

| Stage / guide | Scope and result | Original ID |
|---|---|---|
| [Initial Gandalf sampling](HISTORICAL_RUNS.md#1-gandalf-sampling-and-coverage) | 20 diseases, 1,000 three-hop attempts each; 19,484 nodes, 46,868 connections; 562/629 Drug answers reached with treatments visible | 1 |
| [Sampled-graph ranking](HISTORICAL_RUNS.md#2-ultra-4g-on-the-sampled-graph) | 49 validation pairs, 6,227 candidates; pretrained 4g MRR **0.0949**, Hits@10 **0.1837**; test not scored; sampling preceded masking | 2 |
| [Initial retrieval coverage](retrieval/README.md) | 50 diseases, 85 validation answers; walks reach 45/85, ARAGORN-style rules 1/85; all direct held-out connections masked before retrieval | 7a |
| [Full-validation ranking](retrieval/README.md#full-validation-model-comparison-7b) | 986 diseases, 1,807 validation pairs, fixed 5,326 candidates; results below | 7b |
| [Three versus six hops](retrieval/README.md#walk-length-coverage-check) | Same attempt/edge budget; coverage falls from 837/1,807 to 781/1,807; further work discontinued, no six-hop model scoring | Follow-up |
| [Chemical/drug retrieval](chemical_retrieval/README.md) | Current 22,918-pair labels; masking comparison, visible-training recovery, and walks versus rules; coverage only | Follow-up |
| [Actual ARAGORN service comparison](aragorn_service_parity/README.md) | Ten diseases; seven observed answer sets match exactly, three differ; service errors prevent a clean parity conclusion | Follow-up |
| [Metapath analysis](metapath_analysis/README.md) | Exact replay of 1,625,801 walks across 1,707 diseases; describes how answers are reached; no ULTRA scoring | Follow-up |

Full-validation ranking reuses pretrained 4g and the **already fine-tuned
Drug-only model**. It performs no new training, and no test ranking has run.
Missing retrieved candidates remain in the fixed evaluation pool.

| Context | Checkpoint | Validation MRR | Validation Hits@10 |
|---|---|---:|---:|
| Full graph | Pretrained 4g | 0.1057 | 0.1920 |
| Full graph | Fine-tuned 4g | 0.1654 | 0.3210 |
| Gandalf walks | Pretrained 4g | 0.0413 | 0.0797 |
| Gandalf walks | Fine-tuned 4g | 0.0466 | 0.0847 |
| ARAGORN-style rules | Pretrained 4g | 0.0020 | 0.0055 |
| ARAGORN-style rules | Fine-tuned 4g | 0.0019 | 0.0055 |

The chemical/drug follow-up masks only exact held-out `treats` edges for its
walks-versus-rules comparison, retaining other direct predicates. Walk coverage
is **0.6691 validation / 0.6821 test**, versus **0.1986 / 0.2207** for rules.
Walk graphs are larger, and many answers are reached through retained direct
evidence. These are coverage results, not improved ULTRA performance.
[Consolidated retrieval and service report](aragorn_service_parity/report/README.md) ·
[Executed metapath notebook](../notebooks/04_aragorn_gandalf_metapaths.ipynb).

## Study 4: MechRepoNet reference

Use pretrained 4g with the same pair-split, all-direct-held-out-edge masking,
and filtered drug-prediction procedure as the Tier 0 reference. MechRepoNet has
**3,439 indication pairs**: 2,751 visible / 343 validation / 345 test, with
**40,413 ChemicalSubstance candidates**.

| Split | MRR | Hits@10 | Top-10 answers |
|---|---:|---:|---:|
| Validation | 0.2727 | 0.4315 | 148 / 343 |
| Test | 0.2193 | 0.3797 | 131 / 345 |

Scores exceed the Tier 0 runs, but the graphs, target relations, and candidate
populations differ. This comparison does not isolate graph quality. Older
external MechRepoNet/PrimeKG benchmark runs are background references, not
additional pilot studies.
[Protocol, resources, and commands](mechreponet/README.md) (original **8**) ·
[Exact results](studies/mechreponet_ultra4g_masked.json).

## Run and locate outputs

Start with [setup](../SETUP.md), then use the linked guide for the desired run.
Commands run from the repository root. Choose fresh output directories unless
resuming. The current workflow is [prepare/evaluate the chemical/drug baseline](chemical_disease/README.md),
then [fine-tune and test](chemical_finetune/README.md) using those frozen inputs.

| Location | Purpose |
|---|---|
| Linked run guides | Protocols, commands, dependencies, resource measurements |
| [Historical commands](HISTORICAL_RUNS.md) | Original sampling and full-graph pretrained runners |
| [Technical guide](TECHNICAL.md) | Historical protocols, verification, formats, and resume details |
| [Study records](studies/) | Retained aggregate results and provenance; `*_setup.json` files are setup snapshots, not final result reports |
| `results/`, `../output/` | Local datasets, checkpoints, scores, and ranks; excluded from Git |
| `aragorn_service_parity/results/` | Local captured service responses and support traces; excluded from Git |

Original experiment IDs and artifact names remain unchanged for reproducibility.
New follow-ups should be listed under their study with a descriptive name.
