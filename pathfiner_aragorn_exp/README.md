# Aragorn Pathfinder analysis

Local analysis of saved Aragorn **TEST** responses from November 7, 2026.
The notebooks make no service requests and publish nothing.

## What we did

- Reproduced TestHarness checks: **79 assets across 17 query cases; 26 passed, 53 failed**.
- Calculated each passing asset's first matching path rank.
- Summarized metapaths: node type — predicate — node type, with separate direction-aware exports.
- Focused on **32 drug/chemical–disease assets across six cases**: 10 passed, 22 failed. Analyzed all **3,000 returned paths**.
- Checked the candidate Imatinib → KIT → histamine → mast cell → asthma sequence: no match in the 500 returned paths.

A harness pass requires the configured minimum of expected nodes **together in one path**; it does not check node order or predicates. All six combined drug–disease checks failed. Exact relationship evaluation still needs reference pathways: `missing_reference` is not a failed retrieval.

## Notebooks

Run with the repository's `.local/TestHarness/.venv/bin/python` interpreter, in this order:

1. [Asset ranks](notebooks/passing_asset_ranks.ipynb) — reproduce all 79 checks and rank the 26 passes.
2. [Drug–disease metapaths](notebooks/drug_disease_metapaths.ipynb) — main analysis of all returned drug–disease paths and all 32 assets.
3. [Exact-path evaluation](notebooks/exact_path_evaluation.ipynb) — asset audit, Imatinib sequence check, and evaluator awaiting reference definitions.

Optional, after notebook 1: [Metapaths of matching paths](notebooks/matching_path_metapaths.ipynb) covers the **331 paths matching all 26 passing assets**, including other query types.

## Files

- `references/`: editable expected-path definitions; preserve these.
- `data/`: generated intermediate data used by later notebooks.
- `exports/`: generated tables and chart, grouped by analysis.
- Original responses: `../test_results/pathfinder-test-full-20261107T192900Z/`.

Keep the notebooks, references, and original responses. Data and exports can be regenerated. All four notebooks were rerun after reorganizing the folder; results were unchanged.
