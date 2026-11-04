# DrugCentral ground-truth candidates

This directory contains reproducible overlap statistics and an 80/10/10
benchmark builder for DrugCentral `treats` pairs in Tier 0 1.0.4. Approval is
source-asserted; the positive set has not been independently clinically validated.

## Build the split and blinded training graph

```bash
python experiments/drug-disease-benchmark/drugcentral-ground-truth/build_benchmark.py \
  /path/to/tier0-1.0.4/raw \
  --out experiments/drug-disease-benchmark/drugcentral-ground-truth/results/tier0-1.0.4-seed42 \
  --seed 42
```

The output directory must not exist. The full build copies the graph, requiring
roughly 26 GB of free space, and independently rereads the saved edges for the
leakage audit. Generated `results/` are ignored by Git.

Policy:

- Positives: every normalized DrugCentral `treats` pair with
  `clinical_approval_status=approved_for_condition`. Includes phenotype indications.
- Split: deterministic SHA-256 ranking using seed 42; floor 10% each for
  validation and test, with the remainder for training. For 7,903 pairs this
  produces **6,323 train / 790 validation / 790 test**.
- Remove all original direct `ChemicalEntity`–`DiseaseOrPhenotypicFeature`
  edges, regardless of predicate, source, or direction.
- Restore exactly one canonical approved DrugCentral `treats` edge per training
  pair. All other edges and all nodes are preserved. The canonical edges contain
  source and approval metadata; original evidence is kept separately.
- Validation and test pairs remain absent from the graph for both tuning and
  final evaluation. Individual drugs and conditions can appear across splits;
  **pairs cannot**. This is not an unseen-drug or unseen-disease split.

Outputs:

- `graph/nodes.jsonl`, `graph/edges.jsonl`: the only graph inputs to give systems.
- `labels/train.csv`, `labels/validation.csv`, `labels/test.csv`: pair assignments.
- `labels/positive_evidence.jsonl`: original source records for the positive set.
  This includes held-out answers and must not be ingested into the training graph.
- `manifest.json`: input/output checksums, split policy, counts and leakage audit.
  Written only after the saved-graph audit passes; absence means an incomplete build.

The audit checks all saved edges, not just DrugCentral edges or `treats`, for
validation/test pairs in either direction. It also verifies that the graph's
direct drug–condition edges equal the training set exactly, with no duplicates,
and reports held-out pairs with isolated endpoints. The checks use existing
normalized Tier 0 IDs; they do not establish absence of semantic leakage through
hierarchies, node attributes, or external services.

### Verified Tier 0 1.0.4 build

The seed-42 build at `results/tier0-1.0.4-seed42/` completed and passed its
independent saved-graph audit. It removed 1,499,839 original direct
drug–condition edges and added 6,323 canonical training edges, yielding
27,441,605 graph edges with all 1,791,278 nodes retained. No validation or test
pair appears as a direct edge under any predicate or direction. The saved split
CSVs were also checked for duplicates, disjointness and complete coverage of
all 7,903 positives.

The audit found **19 validation pairs and 19 test pairs with at least one
isolated endpoint** after blinding. These remain in the fixed splits and are
reported in `manifest.json`; they were not silently excluded. Evaluation should
report their coverage separately.

## Reproduce the overlap statistics

From the repository root, with Python 3.11+ (standard library only):

```bash
python experiments/drug-disease-benchmark/drugcentral-ground-truth/overlap_stats.py
```

The default inputs are `../results/tier0-1.0.4/drug_disease_edges.tsv.gz`
and the matching `treats_approval.csv` in the same directory.
These generated inputs are ignored by Git. To regenerate them from the pinned
Tier 0 raw graph, follow [stage 01](../troubleshooting-drug-disease-pairs/01-tier0-pair-analysis/README.md#reproduce).
To use another extract or output directory:

```bash
python experiments/drug-disease-benchmark/drugcentral-ground-truth/overlap_stats.py \
  --edges /path/to/drug_disease_edges.tsv.gz \
  --out /tmp/drugcentral-overlap
```

Both plain TSV and gzip-compressed TSV are supported. The script makes two
streaming passes, then hashes both inputs for provenance. With custom inputs,
provide `treats_approval.csv` from the same graph beside the edge extract, or
specify its location using `--approval-summary /path/to/treats_approval.csv`.
Output is deterministic
for a given input. Default outputs are saved in `tables/`:

- `summary.json`: scope, input SHA-256, and all counts.
- `overlap_summary.csv`: overall counts and percentages.
- `treats_source_overlap.csv`: additional treatment support by primary source.
- `predicate_overlap.csv`: other predicates linking the same pairs.
- `approval_status.csv`: DrugCentral source-asserted status counts and percentages.

### Approved and off-label overlaps

To calculate overlaps separately for DrugCentral `approved_for_condition` and `off_label_use` pairs,
provide the matching raw graph edges. This scans the raw graph because the
compact extract and status summary do not identify which pairs are approved:

```bash
python experiments/drug-disease-benchmark/drugcentral-ground-truth/overlap_stats.py \
  --raw-edges /path/to/tier0-1.0.4/raw/edges.jsonl
```

This reads the raw graph once for both subsets, adds `approved_only` and
`off_label_only` to `summary.json`, and writes
`approved_overlap_summary.csv`, `approved_treats_source_overlap.csv`, and
`approved_predicate_overlap.csv`, plus the corresponding three `off_label_*.csv`
tables. Each subset uses its own percentage denominator (7,903 approved and
1,704 off-label pairs in this snapshot). The script checks both pair counts
against the status summary. Use this option when regenerating subset outputs; the default
command only regenerates the all-status summaries.

Run the small offline status-filtering and overlap check with:

```bash
python -m unittest discover -s experiments/drug-disease-benchmark/drugcentral-ground-truth -p 'test_*.py'
```

## Counting rules

The denominator is **all 9,608 DrugCentral `treats` pairs**, including off-label
uses and phenotype conditions, rather than only the 7,903 source-asserted
approved pairs. The extract does not retain approval status.
The status breakdown therefore comes from the separate summary generated by
`describe_drug_disease_edges.py`. Status counts are unique within each status;
across other snapshots, a pair could carry multiple statuses. The JSON reports
whether the status count sum matches the overlap denominator, but this alone
does not establish that statuses are mutually exclusive. Approval assertions
are not independent validation of condition-specific approval.

Pairs use existing Tier 0 normalized identifiers, with drug and condition
ordered consistently in either edge direction. No additional synonym or
ontology expansion is performed. Duplicate edges count once per pair.
An overlap is another predicate from any source or a `treats` record whose
source is not DrugCentral. Unknown-source treatment records, if present,
are reported separately as `unknown`; they are not confirmed independent sources.

Source and predicate breakdowns overlap and must not be summed. A warning or
side-effect edge does not by itself invalidate a treatment indication.

## Expected Tier 0 1.0.4 results

| Measure | Unique pairs |
|---|---:|
| DrugCentral `treats` | 9,608 |
| Additional `treats` evidence | 2,541 |
| Other predicate | 5,169 |
| Either overlap | 5,281 |
| Both overlap types | 2,429 |
| No other edge | 4,327 |

| DrugCentral status | Unique pairs | Share of 9,608 |
|---|---:|---:|
| `approved_for_condition` | 7,903 | 82.25% |
| `off_label_use` | 1,704 | 17.74% |
| `not_provided` | 1 | 0.01% |
| **Total status counts** | **9,608** | **100.00%** |

The additional treatment sources are Multiomics (1,469), clinicaltrials-kp
(1,161), Drug Repurposing Hub (737), and TTD (606).

For a held-out pair, blinding must remove evidence from every source. Removing
only the DrugCentral edge is insufficient.
