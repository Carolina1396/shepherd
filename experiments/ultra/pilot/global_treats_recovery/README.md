# Global scoped treats removal and all-pair recovery

[Notebook 05](../../notebooks/05_global_treats_recovery.ipynb) compares native
Gandalf walks with the existing local ARAGORN rule executor after removing every
exact `biolink:treats` record between Disease and Drug/ChemicalEntity/SmallMolecule
nodes, in either direction. Category matching uses explicit stored memberships.
Other predicates and treatment edges outside this category scope remain.

Targets are rediscovered from the original CSR graph: all unique directed
chemical-to-Disease `treats` pairs. There is no split or subsampled disease cohort.
Reverse-only records are removed but are not relabeled as chemical-to-Disease
treatment claims. Multiple evidence records count as one target pair.
All expected answers, including isolated chemicals, stay in the denominator.

Both methods receive the same masked graph. Gandalf uses 1,000 native three-edge
walk attempts per disease, retaining only completed self-avoiding walks. ARAGORN
runs all 18 original templates plus the direct query, with the direct chemical
category union broadened as in notebook 04. Original categories, qualifiers and
directions in rule templates are unchanged; query predicates may expand through
Biolink. Each rule query has the existing five-second timeout plus two-second
hard-timeout grace. Each method has a 3,000-connection ceiling. This ceiling does
not equalize realized graph sizes. Sampling and whole-match selection never use
expected answer labels. The seed is 7317 plus the disease's position in sorted IDs.

The primary metric is pair-weighted graph-present recovery: an expected chemical
appears anywhere in the disease's retrieved graph. Explicit ARAGORN bindings and
per-rule contributions are separate diagnostics. This is a single-seed retrieval
experiment, not model training, ranked evaluation or evidence of treatment efficacy.
Notebook 04 has a different mask and target population, so its percentages are not
a controlled estimate of the mask's effect alone.

## Completed result

All **22,918 pairs across 3,901 diseases** were evaluated. The mask removed
27,236 evidence records, leaving zero scoped `treats` records and 6,398 exact
`treats` records outside the requested categories.

| Method | Recovered pairs | Recovery | Mean graph connections |
|---|---:|---:|---:|
| Gandalf walks | 14,483 / 22,918 | 63.19% | 1,828.14 |
| Local ARAGORN | 4,571 / 22,918 | 19.95% | 80.07 |

Both methods recovered 3,415 pairs; 11,068 were Gandalf-only, 1,156 ARAGORN-only,
and 7,279 were recovered by neither. Gandalf completed 3,536,161 of 3,901,000
walk attempts. All 74,119 local rule queries succeeded without errors or timeouts;
25 queries had bounded results. Every saved graph and recovery count passed the
final audit. The notebook contains actual executed outputs.

Source: [retained result](../studies/global_treats_recovery_001_results.json).

## Run and inspect

From the repository root:

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover -s experiments/ultra/pilot/global_treats_recovery -v
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/global_treats_recovery/experiment.py
python experiments/ultra/pilot/global_treats_recovery/build_notebook.py
python experiments/ultra/pilot/global_treats_recovery/execute_notebook.py
```

Use `--resume` on the experiment command after interruption, or `--verify-only`
to recompute coverage and validate saved graphs without new retrieval. For a new
configuration or implementation, select a fresh `--output` directory. `--workers`
controls local process concurrency without changing the disease cohort. Notebook
Run All starts/resumes missing results and loads a completed cache otherwise.
Rebuilding a notebook clears its outputs; execute it afterward.

## Validation and artifacts

The runner independently compares the mask against a category-and-predicate scan
of every source evidence position; verifies all retained edges and source,
qualifier and knowledge-level indices; checks that no scoped treatment records
remain; and uses the existing mask's reverse-index verification. It hashes actual
graph files, implementation files and rule templates. Resuming refuses changed
inputs. At completion it verifies each retrieved edge against the masked source
and independently recomputes coverage from saved graphs. Failed or timed-out rule
queries are reported explicitly, and all target pairs remain in the denominator.

`../results/global_treats_recovery_001/` contains:

- `settings.json`, `source/`, `aragorn_rules.json`: provenance and frozen code.
- `targets.json`, `cohort.json`: complete source-derived targets and disease cohort.
- `mask_verification.json`: counts and exact mask verification.
- `diseases/NNNNN/graph.json`, `rules.json`, `report.json`: both graphs, retained
  rule matches, rule execution status, completion counts and metrics.
- `pair_recovery.csv`: every expected pair, with recovery by each method.
- `per_disease.csv`, `per_rule.csv`: full metrics and rule contributions.
- `summary.json`: complete verified results; `partial.json` is not a final result.
- `status.json`: execution progress.

A compact complete result is also retained in `../studies/`. Large per-disease
artifacts remain local under the repository's existing results ignore rules.
