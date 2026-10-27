# ARAGORN / Gandalf metapath analysis

Part of [Study 3: Sampling and retrieval](../README.md#study-3-sampling-and-retrieval). Retrieval follow-up.

Open the executed [analysis notebook](../../notebooks/04_aragorn_gandalf_metapaths.ipynb).
It analyses the existing `chemical_walks_treats_only_001` comparison against
`chemical_retrieval_001`; it does not train ULTRA or submit new service queries.

The notebook now contains only overall recovery and the top patterns for each
method, ranked by distinct expected answer pairs recovered. Change `SPLIT` or
`TOP_N` to explore. Full templates, zero-match audits, named witnesses, and
provenance remain in the cached files described below. Implementation cells
are collapsed in supporting viewers.
All 32,433 local query executions succeeded, with no timeouts and a maximum
recorded execution time of 1.22 seconds. The 24 executions with bounded results
are a separate result/connection-limit issue, not a timeout issue.

## Findings from the replay

All **1,707 disease graph unions** and their completed-walk counts reproduced
exactly: **1,625,801 completed walks** out of 1,707,000 attempts. Both methods
use the same source with exact held-out `biolink:treats` pairs masked in both
directions, retaining other predicates and visible training edges.

| Diagnostic | Validation | Test (exploratory) |
|---|---:|---:|
| Expected answer pairs | 2,291 | 2,293 |
| ARAGORN graph recovery | 455 (19.86%) | 506 (22.07%) |
| Gandalf graph recovery | 1,533 (66.91%) | 1,564 (68.21%) |
| Minimum observed prefix: 1 hop | 1,252 | 1,258 |
| Minimum observed prefix: 2 hops | 60 | 73 |
| Minimum observed prefix: 3 hops | 221 | 233 |
| Recovered by Gandalf with no retained direct source edge | 201 | 213 |
| Gandalf-only answers | 1,193 | 1,188 |
| Gandalf-only answers encountered in one hop | 960 | 929 |

Thus **81.7% of recovered validation answers** were encountered in one hop.
The most common answer-reaching one-hop patterns include
`Disease <-[in_clinical_trials_for]- ChemicalEntity` (786 validation pairs),
`Disease <-[treats_or_applied_or_studied_to_treat]- ChemicalEntity` (534), and
`Disease <-[applied_to_treat]- ChemicalEntity` (361). These counts overlap.
Retained direct evidence explains much of the recovery advantage; the result
does not isolate multihop reasoning or control for graph size. Mean retrieved
validation edges are about 2,101 for Gandalf versus 217 for ARAGORN.

All 18 ARAGORN rules were attempted. IDs 0, 1, 2, 3, 4, 6, 7, 8, 11, 12, and 15
returned zero raw matches; the notebook includes the earlier per-edge audit of
missing predicates, category combinations, and qualifiers. They were not
manually excluded. Full motifs matter: rule 5 requires a triangle, including a
direct candidate-to-query treatment-related edge. It is not just a two-hop path.

## Method and interpretation

`prepare.py` loads the original CSR graph, applies the frozen mask, and replays
the unchanged native sampler using each original seed. Each resulting union
must exactly equal its saved graph. The original cap cannot discard a walk in
this protocol: 1,000 attempts × 3 edges is at most 3,000 distinct connections.
The replay never passes expected answers into the sampler.

Only after sampling do we label path categories and examine expected answers.
An answer can occur at step 1, 2, or 3. A minimum observed prefix length is not
the shortest source-graph distance or a path assembled from multiple walks.
The source-direct diagnostic independently checks any retained predicate
between each expected pair.

Full-walk frequencies count occurrences, including duplicates. Answer metapath
frequencies count distinct chemical–disease pairs within each split and pattern;
a pair can contribute to multiple patterns. Category priority is explicit in
the notebook and summary. It is a descriptive grouping, not a sampling filter.
The sampler ignores qualifiers and returns triples without evidence-record
IDs; the analysis therefore does not claim record-specific qualifier provenance
for a sampled edge. Exact template compatibility cannot be inferred from these
coarse walk signatures alone.

Paths can contain retained `treats` edges on other pairs. The prohibited edges
are the exact held-out chemical–disease pairs, not all `treats` edges everywhere.
Adverse or generic relationships can also recover a benchmark chemical as a
graph node. Connectivity alone is not evidence of treatment effectiveness.

## Reproduction

From the repository root:

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover -s experiments/ultra/pilot/metapath_analysis -v
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/metapath_analysis/prepare.py
python experiments/ultra/pilot/metapath_analysis/build_notebook.py
python -u experiments/ultra/pilot/metapath_analysis/execute_notebook.py
```

Preparation uses the experiment environment. Notebook execution uses the
available Python 3 Jupyter kernel with pandas, matplotlib, and networkx.
`jupyter_client` saves actual IPython outputs without requiring nbclient.
Rebuilding the notebook resets outputs; run the execution command afterward.

Preparation took about 68 seconds on this workspace. Cached preparation verifies
its input manifest and derived output hashes without loading the graph again.
Input changes fail instead of silently mixing runs. The original graph and
experiment results must remain available for a new replay.

Derived files in `../results/chemical_metapaths_001/`:

- `full_walk_metapaths.csv`: full three-edge pattern frequencies and disease counts.
- `answer_metapaths.csv`: observed answer-prefix patterns and distinct pair counts.
- `answer_diagnostics.csv`: all 4,584 held-out pairs, method overlap, prefix lengths,
  source direct predicates, retained ARAGORN rule bindings, and witness index.
- `witnesses.json`: one shortest observed prefix per recovered pair, with named
  nodes, original categories, and directed predicates.
- `rule_catalog.json`: all 18 full templates, per-split contributions, and audited blockers.
- `verified_graphs.json`: hashes of every compared saved graph.
- `summary.json`, `manifest.json`: aggregate results and provenance.

The notebook defaults to validation. Test is available for descriptive inspection;
this analysis does not select parameters or claim a final independent test result.
