# ULTRA analysis notebooks

Read the notebooks in order. All three have saved outputs from successful runs.

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
