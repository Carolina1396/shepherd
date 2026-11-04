# Drug–disease benchmark

A drug–disease benchmark under development for comparing ARAGORN, ARAX and ULTRA on a blinded Translator Tier 0 graph, intended to replace the Sprint 6 test set.

**Current status:** graph analysis, a reproducible label-extraction investigation,
and a [DrugCentral 80/10/10 benchmark builder](drugcentral-ground-truth/README.md#build-the-split-and-blinded-training-graph)
are available. The builder uses source-asserted approved indications, removes all
direct drug–condition edges, and restores only training `treats` pairs. It audits
the saved graph for validation/test leakage before writing its completion manifest.
Independent clinical validation and comparative model evaluation remain unfinished.

## Start here

| Purpose | Entry point |
|---|---|
| Understand the candidate pairs and follow the investigation | [Five-stage troubleshooting guide](troubleshooting-drug-disease-pairs/README.md) |
| Reproduce DrugCentral overlap statistics or build the 80/10/10 benchmark | [DrugCentral ground-truth directory](drugcentral-ground-truth/README.md) |
| Read the saved counts without downloading Tier 0 | [Baseline summary tables](troubleshooting-drug-disease-pairs/01-tier0-pair-analysis/tables/) |
| Reproduce the DAKP warning-text extraction issue | [Original parser and two-label test](troubleshooting-drug-disease-pairs/04-parser-investigation/README.md) |
| Regenerate graph-level analysis | [Inputs and commands](troubleshooting-drug-disease-pairs/01-tier0-pair-analysis/README.md#reproduce) |

The parser test deliberately fails for naproxen and passes for donepezil on the pinned upstream version. That failure documents the issue; it is not a successful test of corrected behavior.

## Check the analysis locally

These checks use small fixtures and do not require the full Tier 0 graph:

```bash
python -m unittest discover -s experiments/drug-disease-benchmark/scripts -p test_analysis.py
python -m unittest discover -s experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/03-dailymed-screening -p test_audit.py
```

The baseline test uses the standard library and checks counts, direction, source overlap and JSON-spacing invariance. The screening tests require `requests`; the separate upstream parser test requires the environment documented in stage 04. The full graph is external, generated `results/` are ignored, and saved summary tables are included in stage 01.

## Initial benchmark proposal

The plan discussed with Andrew Su on 2026-10-28 was:

- **Gold standard:** DrugCentral indications plus off-label pairs. The off-label source was transcribed as "Medicare"; it is probably MEDI (see below).
- **Blinding:** remove every drug–disease edge that is not `treats`. Split the `treats` gold standard 80/20 and remove the `treats` edges of the held-out 20%.
- Remove held-out treatment evidence across all contributing sources to prevent direct leakage.

Subsequent investigation identified label validity as another unresolved risk. The source choice and 80/20 split above are recorded design intentions, not completed validation or split artifacts. In particular, an FDA application number and `approved_for_condition` do not independently verify approval for a specific condition.

The available work covers graph characterization, selected source checks, DailyMed screening and the parser reproduction. A systematic source survey covering regulatory scope, curation, licensing and identifier mapping remains unfinished.

## Tier 0 version

All reported counts refer to the pinned **1.0.4** snapshot: `release_date` 2026-10-18, Biolink 4.4.4, Babel `2025sep1`, build `1bc59421ea9c`. They are not automatically updated when newer releases appear.

- Archive: `~/shepherd/experiments/ultra/data/tier0-1.0.4/translator_kg.tar.zst` (3.3 GB; SHA-256 in `translator_kg.tar.zst.sha256`), extracted to `raw/` (`nodes.jsonl` 1.1 GB, `edges.jsonl` 25.8 GB, 28,935,121 edges).
- Earlier investigation recorded Tier 0 **1.0.2** for the Translator 2.1 deployment. Check the actual service version when evaluating hosted ARAGORN/ARAX; their graph may differ from this local snapshot.
- Earlier experiments in this repo used the `2026_06_21` build.

## Definitions

- **Drug side:** nodes whose category list includes `biolink:ChemicalEntity` (1.17 M nodes; mostly SmallMolecule, plus Drug, mixtures and a few Protein+Drug biologics). Tier 0 node categories carry the full Biolink ancestry.
- **Disease side:** nodes whose category list includes `biolink:DiseaseOrPhenotypicFeature` (91k nodes: Disease and PhenotypicFeature).
- An edge is a drug–disease edge if one end is drug-side and the other disease-side, in either direction.
- Primary knowledge source: the `sources` entry with `resource_role: primary_knowledge_source`.

### Node types counted as drug or disease

Node type is the most specific Biolink category on the node (ancestors dropped). Source: `results/tier0-1.0.4/node_types.csv`.

| Side | Node type | Nodes in Tier 0 | In a drug–disease edge | In a `treats` edge |
|---|---|---:|---:|---:|
| Drug | SmallMolecule | 1,096,016 | 16,509 | 2,564 |
| Drug | ChemicalEntity | 53,178 | 13,720 | 983 |
| Drug | MolecularMixture | 10,701 | 2,296 | 447 |
| Drug | Drug | 3,833 | 3,708 | 846 |
| Drug | Drug + SmallMolecule | 2,049 | 2,036 | 1,868 |
| Drug | ChemicalMixture | 504 | 72 | 21 |
| Drug | ComplexMolecularMixture | 123 | 101 | 14 |
| Drug | MolecularMixture + SmallMolecule | 86 | 76 | 34 |
| Drug | NucleicAcidEntity | 77 | 50 | 0 |
| Drug | Protein + Drug (biologics) and other Protein combinations | 30 | 29 | 16 |
| Drug | Odd combinations (with OrganismTaxon, AnatomicalEntity, CellularComponent) | 9 | 6 | 0 |
| Disease | Disease | 52,643 | 20,238 | 4,616 |
| Disease | PhenotypicFeature | 38,617 | 4,464 | 1,094 |
| Disease | DiseaseOrPhenotypicFeature | 8 | 5 | 0 |

- Only 1.5% of SmallMolecule nodes have any drug–disease edge. Nodes typed Drug almost all do (97% of Drug, 99% of Drug + SmallMolecule).
- Drug + SmallMolecule (2,049 nodes) is the largest group in `treats` edges: 1,868 nodes.

## Results: Tier 0 1.0.4

`scripts/extract_drug_disease_edges.py` streams every edge. Outputs are in `results/tier0-1.0.4/` (gitignored):

- `drug_disease_edges.tsv.gz`: one row per edge
- `predicate_summary.csv`: edges and unique pairs per predicate and direction, with sources
- `node_categories.csv`: node counts by category

`scripts/metadata_drug_disease_edges.py` gives the same table from `graph-metadata.json` alone (`reports/tier0-1.0.4/metadata_predicates.csv`); it agrees within 0.1%.

**1,499,839 drug–disease edges** link **1,204,565 unique drug–disease pairs**, across 39 predicate/direction groups.

### Top 10 edge types

Both directions combined. Source: `results/tier0-1.0.4/top_predicates.csv` (all 28 predicates); `predicate_summary.csv` splits them by direction.

| # | Predicate | Edges | Share | Unique pairs | Drugs | Diseases | Main primary sources |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | `in_clinical_trials_for` | 620,245 | 41.4% | 618,762 | 25,403 | 18,340 | clinicaltrials-kp 616k, TTD 3.9k |
| 2 | `treats_or_applied_or_studied_to_treat` | 354,731 | 23.7% | 329,934 | 13,222 | 8,932 | text-mining-provider-targeted 273k, SemMedDB 44k, CTD 37k |
| 3 | `has_side_effect` | 138,291 | 9.2% | 138,291 | 1,446 | 4,029 | SIDER |
| 4 | `contributes_to` | 99,992 | 6.7% | 99,983 | 5,063 | 4,590 | text-mining-provider-targeted |
| 5 | `correlated_with` | 69,290 | 4.6% | 69,181 | 6,110 | 2,639 | CTD 66k, ICEES 3.2k |
| 6 | `applied_to_treat` | 65,254 | 4.4% | 65,254 | 1,475 | 1,520 | FAERS |
| 7 | **`treats`** | **58,848** | **3.9%** | **53,176** | **6,793** | **5,710** | clinicaltrials-kp 38k, DrugCentral 9.6k, multiomics-drugapprovals 5.1k, drug-repurposing-hub 3.6k, TTD 2.5k |
| 8 | `related_to` | 23,437 | 1.6% | 23,254 | 1,716 | 2,296 | SemMedDB |
| 9 | `contraindicated_in` | 22,859 | 1.5% | 22,125 | 1,798 | 1,329 | DrugCentral 19k, MEDI 3.9k |
| 10 | `causes` | 20,260 | 1.4% | 20,260 | 2,759 | 1,987 | SemMedDB |

The other 18 predicates together hold 1.8% of edges (largest: `affects`, 13,699).

### `treats` in detail

- **53,176 pairs**, covering 6,793 drugs and 5,710 diseases.
- **49,196 pairs rest on a single source:** clinicaltrials-kp 35,864, DrugCentral 7,067, multiomics-drugapprovals 2,605, drug-repurposing-hub 2,261, TTD 1,399. Only 3,980 pairs have two or more sources.
- **Excluding pairs supported only by clinicaltrials-kp leaves 17,312 `treats` pairs.**
- **DrugCentral supports 9,608 `treats` pairs.** A DrugCentral gold standard therefore overlaps the graph's own `treats` edges.

### Sources with approved drugs

Approval status is recorded on the `treats` edges: `clinical_approval_status` (DrugCentral, multiomics-drugapprovals, TTD) or `max_research_phase` (clinicaltrials-kp). Source: `results/tier0-1.0.4/treats_approval.csv`, `approved_overlap.csv`.

| Primary source | Status on the edge | `treats` pairs | Notes |
|---|---|---:|---|
| DrugCentral | `approved_for_condition` | 7,903 | Source-asserted approved indications |
| DrugCentral | `off_label_use` | 1,704 | Off-label uses |
| multiomics-drugapprovals | `approved_for_condition` | 5,095 | Source-asserted approvals; each edge lists FDA application numbers (NDA/ANDA/BLA): 1,673 distinct |
| TTD | `approved_for_condition` | 2,419 | Plus 34 at phase 4 |
| clinicaltrials-kp | `clinical_trial_phase_4` | 34,744 | Phase 4 is post-marketing: the drug is approved, but not necessarily for this condition |
| clinicaltrials-kp | none | 3,385 | |
| drug-repurposing-hub | none | 3,563 | No approval attribute |

**Source-asserted approved pairs across sources** (`approved_for_condition`):

| | DrugCentral | multiomics-drugapprovals | TTD | Only this source |
|---|---:|---:|---:|---:|
| DrugCentral | 7,903 | 1,408 | 590 | 6,197 |
| multiomics-drugapprovals | 1,408 | 5,095 | 455 | 3,524 |
| TTD | 590 | 455 | 2,419 | 1,666 |

- **Union: 13,256 source-asserted approved drug–condition pairs**, covering 3,273 drugs and 2,025 conditions. Of those conditions, 258 are phenotypes, in 1,528 pairs.
- The three sources overlap little: most approved pairs come from a single source. DrugCentral and Multiomics share only 1,408 approved-flagged pairs.
- Only multiomics-drugapprovals ties each edge to a specific FDA application. DrugCentral's approvals may include non-US agencies (to check in the source survey).

### What blinding removes

- 1,151,389 of the 1,204,565 drug–disease pairs (96%) have no `treats` edge. Andrew's rule removes all of them.
- After blinding, at most 53,176 drug–disease pairs stay directly connected (17,312 without the clinical-trial-only pairs), before the 20% held-out removal.

## What this means for the benchmark

1. **The gold standard and the graph share sources.** DrugCentral already supplies 9,608 `treats` pairs. For each held-out pair, *every* `treats` edge between that drug and disease must be removed, whatever its source.
2. **"Medicare" is probably MEDI.** `infores:medi` is in Tier 0, but only as `contraindicated_in` (3,905 edges), which is unexpected for an indication source. Check this in the source survey.
3. **Two thirds of `treats` comes from clinical trials.** 35,864 pairs are supported only by clinicaltrials-kp, which reflects trials rather than approvals.

## Open decisions

- [ ] Specify the target: source-asserted treatment, label-supported indication, or FDA-approved indication. Keep off-label evidence distinguishable from approved indications.
- [ ] Define how unresolved mappings and disputed label evidence affect eligibility; absence of approval support must not automatically become a negative label.
- [ ] Specify validation/test roles, random seed and split unit. Keep every source edge for the same normalized pair in the same partition.
- [ ] Define evaluation metrics and candidate-ranking/filtering rules before comparing systems; audit the actual graph used by each system for held-out evidence.
- [ ] Do the 35,864 clinicaltrials-kp-only `treats` pairs count as `treats` (kept in training), or are they removed like `in_clinical_trials_for`? *(ask Andrew)*
- [ ] Phenotypes in the gold standard: keep PhenotypicFeature indications (e.g. pain, fever), or restrict to Disease and report phenotypes separately?
- [ ] Candidate set for ranking: all 1.17 M chemicals, or drug-like nodes only (Drug category or in DrugCentral)?
- [ ] Borderline predicates: confirm `treats_or_applied_or_studied_to_treat`, `applied_to_treat`, `studied_to_treat` and `ameliorates_condition` are removed.

## Related investigation

The [drug–disease troubleshooting investigation](troubleshooting-drug-disease-pairs/README.md) follows approval candidates through label checks, broader screening, and a reproduced parser issue. Application metadata does not by itself verify condition-specific approval.

## Next

- Characterize the blinded graph: drugs and diseases still connected, and the main 2-hop shortcuts (e.g. through genes, clinical trials or side effects).
- `node_categories.csv` (from the extract script) labels nodes by the first category in their list; use `node_types.csv` (from `scripts/describe_drug_disease_edges.py`) instead.
