# 01 — Examine Tier 0 drug–disease pairs

## Question

Which Tier 0 relationships and metadata could identify approved drug–disease treatment examples for a benchmark?

## Inputs and method

The baseline uses Tier 0 **1.0.4**, release date **2026-10-18**, Biolink 4.4.4. Drug-side nodes include `biolink:ChemicalEntity`; condition-side nodes include `biolink:DiseaseOrPhenotypicFeature`, so these counts include phenotypes. Counts distinguish source edges from unique normalized drug/condition pairs. Source means the edge's primary knowledge source.

The existing [extraction script](../../scripts/extract_drug_disease_edges.py) scans raw nodes and edges; the [description script](../../scripts/describe_drug_disease_edges.py) computes source/status and overlap summaries. The [benchmark overview](../../README.md) gives the broader model-evaluation context. Included CSVs are copies of the baseline outputs, not a new graph run.

## Findings

| Measure | Count |
|---|---:|
| Drug–disease/phenotype edges | 1,499,839 |
| Unique drug–condition pairs across predicates | 1,204,565 |
| Unique `treats` pairs | 53,176 |
| Unique `treats` pairs with `approved_for_condition` | 13,256 |
| DrugCentral approved treatment pairs | 7,903 |
| Multiomics approved treatment pairs | 5,095 |
| TTD approved treatment pairs | 2,419 |
| DrugCentral–Multiomics shared approved treatment pairs | 1,408 |

See [predicate counts](tables/top_predicates.csv), [node types](tables/node_types.csv), [source/status counts](tables/treats_approval.csv), and [approved-source overlaps](tables/approved_overlap.csv). The more detailed [predicate summary](tables/predicate_summary.csv) retains direction.

Useful fields include the predicate, `clinical_approval_status`, primary/supporting sources, FDA application metadata, and normalized node IDs. They identify source-asserted candidates. An application number identifies a regulatory application; its presence does not independently validate approval for the edge's condition. Source agreement also does not prove independent corroboration or correctness.

## Why investigate examples next?

Before treating approval metadata as a gold standard, we inspected individual source-asserted approved pairs. [Stage 02](../02-suspicious-pairs/README.md) follows the naproxen–heart failure edge to its cited DailyMed label and documents the discrepancy.

## Reproduce

The raw graph is external and is not committed. Set `TIER0_RAW` to a directory containing the release's `nodes.jsonl` and `edges.jsonl`, then run from the repository root:

```bash
TIER0_RAW=/path/to/tier0-1.0.4/raw
python experiments/drug-disease-benchmark/scripts/extract_drug_disease_edges.py "$TIER0_RAW" --out experiments/drug-disease-benchmark/results/tier0-1.0.4
python experiments/drug-disease-benchmark/scripts/describe_drug_disease_edges.py "$TIER0_RAW" --results experiments/drug-disease-benchmark/results/tier0-1.0.4
```

Compare those outputs with `tables/`. The scripts use Python's standard library. A fresh checkout can read the included summaries without downloading the graph.
