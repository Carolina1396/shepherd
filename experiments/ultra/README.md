# ULTRA treatment-prediction pilot

We use **Gandalf** to access and sample the Translator knowledge graph, and
**ULTRA** to rank missing treatment links. The pilot is organized into four
studies, with follow-up runs grouped under the question they address.

## Studies

| Study | Scope | Main finding |
|---|---|---|
| [1. Full-graph treatment prediction](pilot/README.md#study-1-full-graph-treatment-prediction) | Target definitions, pretrained checkpoints, and fine-tuning | On the current chemical/drug task, fine-tuning improves test MRR from **0.0825 to 0.1231** and Hits@10 from **0.1618 to 0.2202** |
| [2. Direct-edge context](pilot/README.md#study-2-direct-edge-context) | Remove all direct Drug–Disease connections; reuse both 4g checkpoints | On the older Drug-only task, fine-tuned test MRR falls from **0.1673 to 0.0723** |
| [3. Sampling and retrieval](pilot/README.md#study-3-sampling-and-retrieval) | Native Gandalf walks, ARAGORN-style rules, model scoring, and retrieval diagnostics | Retrieved graphs underperform the full graph in validation; later coverage analyses explain what context is available |
| [4. MechRepoNet reference](pilot/README.md#study-4-mechreponet-reference) | Pretrained 4g with proper held-out pair masking | Test MRR **0.2193**, Hits@10 **0.3797**, with different targets and candidates from Tier 0 |

**MRR and Hits@k are fractions.** The [pilot index](pilot/README.md) contains
all result tables, follow-ups, original experiment IDs, and links to run commands.
The inspected test sets remain exploratory; these metrics measure recovery of
graph assertions, not clinical efficacy.

## Current graph and evaluation

Source: **Translator KG `2026_06_21`** (`tier0-20260621`). Source URLs and
checksums are in [download.json](download.json).

| Measurement | Count |
|---|---:|
| Raw node records | 1,754,754 |
| Connected nodes indexed by Gandalf | 1,670,341 |
| Stored edge/evidence records | 28,709,074 |
| Unique directed triples before masking | 27,927,289 |
| Original predicates | 60 |
| Deduplicated chemical/drug → `treats` → Disease pairs | 22,918 |
| Visible / validation / test pairs | 18,334 / 2,291 / 2,293 |
| Chemical/drug candidates ranked per disease | 1,117,832 |

Subjects must have a Drug, ChemicalEntity, or SmallMolecule category; targets
must have a Disease category. Every direct connection between a held-out pair
is masked across predicates and directions, leaving **27,916,156 directed
connections** before ULTRA adds inverses. Other known answers are filtered from
ranking competitors. Candidates include eligible nodes without known treatments.

The current pretrained and fine-tuned runs share this graph, split, and pool
(original experiments 10 and 11). Earlier Drug-only runs used **18,079 pairs
and 5,326 candidates**; those historical settings are explicitly labeled in the
pilot index. Their scores are not a matched comparison with the current task.

## Run and inspect

| Document | Use |
|---|---|
| [Setup](SETUP.md) | Dependencies, CPU/GPU environments, graph building, and fresh-clone requirements |
| [Current pretrained baseline](pilot/chemical_disease/README.md) | Prepare, run, and verify the chemical/drug evaluation |
| [Current fine-tuning workflow](pilot/chemical_finetune/README.md) | Train, select by validation, evaluate test, and verify |
| [Pilot index](pilot/README.md) | All four studies and their run guides |
| [Historical commands](pilot/HISTORICAL_RUNS.md) | Initial sampling and original full-graph pretrained runs |
| [Technical guide](pilot/TECHNICAL.md) | Historical protocols, output formats, resume, and provenance |
| [Notebooks](notebooks/README.md) | Graph inventories and executed retrieval/metapath analysis |

Commands run from the repository root. Choose new output directories unless
resuming. The current fine-tuned test run takes about **1.40 seconds per disease
query** against all candidates and **7.76 GB** peak allocated GPU memory on an
A6000. The full fine-tuning workflow takes **3.54 hours**, including validation,
test, and verification, with **29.07 GB** peak training memory.

## Files and outputs

Paths are relative to `experiments/ultra/`. Script and result paths retain their
original names so previous runs remain reproducible.

| Location | Contents |
|---|---|
| `data/tier0-20260621/` | Source graph archive and metadata |
| `output/gandalf/full-store/` | Verified Gandalf graph and properties |
| `output/overview/`, `output/treatment_pairs/`, `output/resources/` | Data-inspection outputs |
| `output/full-graph-ultra/run_001/` | Historical Drug-only frozen inputs and pretrained 4g outputs |
| `pilot/results/` | Prepared datasets, checkpoints, scores, ranks, and diagnostics |
| `pilot/aragorn_service_parity/results/` | Captured service responses and support traces |
| [pilot/studies/](pilot/studies/) | Retained aggregate result records and provenance |

Bulk data, raw run outputs, vendor code, and environments are ignored by Git.
Documentation, code, notebooks, aggregate records, and
[small original reports](pilot/studies/evidence/README.md) are retained for GitHub.
A fresh clone needs the local inputs described in [setup](SETUP.md#fresh-clone-reproducibility).
