# ULTRA analysis notebooks

Read the notebooks in order. Executed notebooks retain their outputs for inspection.

## 01 — Graph overview

[01_graph_overview.ipynb](01_graph_overview.ipynb) explains what is in the downloaded
Tier 0 release: node categories, predicates, sources, treatment-related category
combinations, qualifiers, and archive sizes.

It uses publisher metadata and a streaming archive inventory. It does not load
the full graph into memory. Tables are saved in `../output/overview/`.

## 02 — Treatment pairs

[02_treatment_candidates.ipynb](02_treatment_candidates.ipynb) examines actual
entity pairs in three sections:

1. Edge records versus unique subject–object pairs.
2. Which pairs the category filter excludes, and why.
3. One named pair and its separate evidence records.

Its preparation section lists all eight selected predicates. The category filter
accepts a subject labeled **ChemicalEntity, SmallMolecule, or Drug**, and an object
labeled **Disease**. Passing this filter does not establish a confirmed treatment.

The first code cell runs [the preparation script](../scripts/inspect_treatment_pairs.py).
It streams the raw graph and saves results in `../output/treatment_pairs/`:

- `summary.json`: counts and analysis metadata.
- `pairs.csv`: pairs passing the category filter.
- `evidence.sqlite`: complete selected edge records, endpoint information, and pair summaries.

Matching cached results are reused. The initial scan takes several minutes;
ordinary reruns do not repeat it. No model training or evaluation split is performed.

## 03 — Resources, relationships, and knowledge levels

[03_resources_and_edges.ipynb](03_resources_and_edges.ipynb) answers four questions:

1. Which primary sources contribute edges, and how many does each contribute?
2. Which relationship types does each source provide?
3. Which knowledge levels occur, including missing values and `not_provided`?
4. How do knowledge levels vary by source and predicate?

Sections 1–2 use metadata; sections 3–4 run a cached streaming scan via
[inspect_knowledge_levels.py](../scripts/inspect_knowledge_levels.py). The initial
scan takes several minutes. All sections cover the full graph without the
treatment-pair filter. Change `SOURCE` to explore a resource's predicates and
`PREDICATE` to inspect its knowledge levels across sources.

Full tables and cached counts are saved in `../output/resources/`. These describe
source contributions and recorded claim types; they do not establish evidence
quality or usefulness for link prediction.

## 04 — ARAGORN rules and Gandalf walk metapaths

[04_aragorn_gandalf_metapaths.ipynb](04_aragorn_gandalf_metapaths.ipynb) analyses
the frozen chemical-disease retrieval comparison under the **treats-only** mask.
It shows overall recovery and each method's top five patterns, ranked by distinct
expected answer pairs recovered. Gandalf rows show observed walk prefixes;
ARAGORN rows show complete rule motifs, including qualifiers and extra branches.

Change `SPLIT` or `TOP_N` to inspect another split or more patterns. Rule IDs are
zero-based and row counts overlap. Graph recovery is not ranked model accuracy.

The preparation script exactly replays all 1,707 frozen disease queries and
verifies their graph unions and completed-walk counts. Cached CSV/JSON analysis
is in `../pilot/results/chemical_metapaths_001/`, including all 18 templates and
the detailed audits. The short notebook reads verified cached results and needs
pandas and IPython; preparation uses the existing experiment `.venv`.
See [reproduction details](../pilot/metapath_analysis/README.md).

## 05 — Recovery after globally removing scoped treats edges

[05_global_treats_recovery.ipynb](05_global_treats_recovery.ipynb) compares Gandalf
and local ARAGORN on one graph with **every exact `biolink:treats` record between
Disease and Drug/ChemicalEntity/SmallMolecule removed in both directions**.
It evaluates all unique original chemical-to-Disease treatment pairs together,
including the former training pairs. Other predicates remain available.

The notebook shows mask verification, overall recovery, overlap, rule execution
status and contributions, and individual target outcomes. Run All starts or resumes
the complete experiment when results are missing; completed results are cached.
See the [protocol and reproduction commands](../pilot/global_treats_recovery/README.md).
