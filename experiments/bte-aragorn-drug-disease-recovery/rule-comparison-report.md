# BTE and ARAGORN treatment rules versus filtered-graph meta-paths

Analysis date: 2026-11-12. Scope: the local implementations in the
`research/autoresearch` worktree, not every deployed version of BTE or ARAGORN.

## Main finding

BTE uses four two-hop treatment templates, three of which remain structurally
possible after graph filtering. ARAGORN uses ten stored treatment rule templates,
all of which require a chemical–disease/phenotype edge somewhere in their supporting
pattern. The filter removes those required edges and therefore blocks all ten.

Both implementations also issue a direct lookup for the requested treatment
relationship. That lookup is blocked by the same filter.

This report inspects rule definitions and compares their structures with the
exploratory meta-path enumeration. It does not run a new service benchmark or
measure rule-matching coverage on the ten sampled pairs.

## Graph and comparison scope

The evidence graph is `artifacts/gandalf_no_drug_disease/`, containing 1,685,344
nodes and 27,435,282 edges. As specified in the
[graph-cleaning notes](../../graph_cleaning/existing_filtering/README.txt), it excludes every edge
between the drug/chemical and disease/phenotype category groups, in either
direction, regardless of predicate or source. This removes supporting treatment
evidence about other chemicals and other diseases too, not just the evaluated
drug–disease pair. Isolated nodes were removed afterward.

The exploratory comparison used ten DrugCentral benchmark pairs sampled from
`data_split/nonisolated/train.csv` with Python's `random.Random(42).sample(rows, 10)`
in CSV row order. It enumerated two- and three-hop connections with exact stored
predicates, full stored category sets, and both traversal directions. Edge arrows
retain the original assertion direction. Self-loops are excluded. Repeated nodes
after an intervening node are permitted, but cannot add two- or three-hop walks
between these distinct endpoints without a direct endpoint edge, which is absent.

Source-duplicate edges are collapsed. Qualifier-aware signatures retain all
stored qualifiers; unqualified signatures omit them. No predicate hierarchy
expansion was performed in that enumeration. These enumeration semantics should
not be assumed to reproduce all Retriever/service matching behavior.

## Notation

- `C`: candidate ChemicalEntity; `C2`: another ChemicalEntity.
- `G`: Gene; `P`: BiologicalProcess.
- `D`: target DiseaseOrPhenotypicFeature; `D2`: another Disease.
- `T`: the exact predicate `biolink:treats_or_applied_or_studied_to_treat`.
- Predicate and qualifier names below omit `biolink:` where unambiguous.

Every listed edge in a rule must be satisfied. A three-edge rule is not
necessarily a three-hop path: several ARAGORN rules require a triangle or an
additional constraint alongside a connecting path.

## BTE: four treatment templates

The [template group configuration](../../workers/bte_lookup/template_groups.json)
selects these four templates for a drug/chemical `treats` disease/phenotype query.

| Rule | Required pattern | Effect of graph filtering |
|---|---|---|
| 1. Treat a phenotype of the disease | `C —treats→ Phenotype ←has_phenotype— D` | Blocked: chemical–phenotype treatment edge removed |
| 2. Increase a gene implicated through loss of function | `C —affects→ G —associated_with→ D`, with qualifiers below | Structurally possible |
| 3. Decrease a gene implicated through non-loss of function | `C —affects→ G —associated_with→ D`, with qualifiers below | Structurally possible |
| 4. Affect a gene with a disease/phenotype annotation | `C —affects→ G —has_phenotype→ D`, with qualifiers below | Structurally possible |

Required qualifiers:

| Rule | Chemical–gene edge | Gene–disease edge |
|---|---|---|
| 2 | `object_aspect_qualifier=activity_or_abundance`; `object_direction_qualifier=increased` | `subject_form_or_variant_qualifier=loss_of_function_variant_form`; `qualified_predicate=contributes_to` |
| 3 | `object_aspect_qualifier=activity_or_abundance`; `object_direction_qualifier=decreased` | `subject_form_or_variant_qualifier=non_loss_of_function_variant_form`; `qualified_predicate=contributes_to` |
| 4 | `object_aspect_qualifier=activity_or_abundance`; no direction requirement | No qualifier requirement |

Rules 2 and 3 do not explicitly require `qualified_predicate=causes` on the first
edge. Rule 1 has no qualifier requirements. Extra stored qualifiers and the
query's required qualifier subset are different concepts: a rule specifies the
constraints to satisfy, whereas our qualified signatures record the full set.

None of these four templates uses a chemical intermediate. “Structurally
possible” means the filter does not prohibit the edge types; it does not establish
that a matching path exists for any particular benchmark pair.

Exact template sources:

1. [Phenotype treatment](../../workers/bte_lookup/templates/Drug-treats-Disease/Chem-treats-PhenoOfDisease.json)
2. [Increase/loss-of-function](../../workers/bte_lookup/templates/Drug-treats-Disease/Chem-affects_increases-Gene-loss_function-Disease.json)
3. [Decrease/non-loss-of-function](../../workers/bte_lookup/templates/Drug-treats-Disease/Chem-affects_decreases-Gene-non_loss_function-Disease.json)
4. [Gene phenotype](../../workers/bte_lookup/templates/Drug-treats-Disease/Chem-affects-Gene-has_phenotype-DoP.json)

## ARAGORN: ten stored treatment rules

These follow the order of the `{"predicate": "biolink:treats"}` list in
[the stored AMIE rule file](../../workers/aragorn_lookup/rules_with_types_cleaned_finalized.json).

| Rule | Required evidence | Required qualifiers |
|---|---|---|
| 1. Similar chemical | `C —similar_to→ C2`, plus both `C —T→ D` and `C2 —T→ D` | None |
| 2. Gene interaction | `C —interacts_with→ G —genetic_association→ D`, plus `C —T→ D` | None |
| 3. Gene affects chemical | `C ←affects— G —genetic_association→ D`, plus `C —T→ D` | Affects edge: `object_aspect_qualifier=activity_or_abundance` |
| 4. Increase secretion | `C —affects→ G —genetic_association→ D`, plus `C —T→ D` | Affects edge: `object_aspect_qualifier=secretion`; `object_direction_qualifier=increased` |
| 5. Related disease phenotype | `C —T→ D2 —has_phenotype→ D`, plus `C —T→ D` | None |
| 6. Decrease transport | `C —affects→ G —genetic_association→ D`, plus `C —T→ D` | Affects edge: `object_aspect_qualifier=transport`; `object_direction_qualifier=decreased` |
| 7. Decrease molecular interaction | `C —affects→ G —genetic_association→ D`, plus `C —T→ D` | Affects edge: `object_aspect_qualifier=molecular_interaction`; `object_direction_qualifier=decreased` |
| 8. Shared process outputs | `C ←has_output— P —has_output→ C2 —T→ D` | None |
| 9. Reciprocal phenotype links | `C —T→ D2 —has_phenotype→ D`, plus `D —has_phenotype→ D2` | None |
| 10. Correlated disease | `C —treats→ D2 —positively_correlated_with→ D` | None |

Rule 3's gene-to-chemical direction is exactly how the template is stored; it has
not been reinterpreted as a chemical-to-gene assertion.

All ten rules are structurally blocked in this filtered graph:

- Rules 1–7 require `C —T→ D` directly.
- Rule 8 requires `C2 —T→ D`.
- Rule 9 requires `C —T→ D2`.
- Rule 10 requires `C —treats→ D2`.

Rules 1 and 8 explicitly use another chemical. Removing chemical intermediates
would prohibit these structures independently, but the graph's existing edge
filter already blocks them.

## Comparison with observed meta-paths

The most frequent unqualified three-hop signature in the ten-pair sample was:

```text
Chemical —affects→ Gene —related_to→ Disease ancestor ←subclass_of— Target disease
```

It had support from four pairs and 373 node sequences. The qualified version
requiring `qualified_predicate=causes`,
`object_aspect_qualifier=activity_or_abundance`, and
`object_direction_qualifier=decreased` on the first edge had support from four
pairs and 182 node sequences, with no qualifiers on the other two edges.
Category names in this display are shortened; counts use full stored category
sets, not a merger of category variants.

Another frequent structure was:

```text
Chemical ←has_input— Procedure —treats_or_applied_or_studied_to_treat→ Disease
```

This two-hop signature had support from two pairs and eight node sequences.
Procedure–disease treatment edges can survive the chemical–disease filter.

The differences are substantive:

| Aspect | BTE treatment templates | ARAGORN treatment rules | Exploratory enumeration |
|---|---|---|---|
| Structure | Four two-hop paths | Ten patterns, often with additional required edges | All observed two-/three-hop paths under the stated semantics |
| Gene–disease evidence | Specific variant qualifiers or `has_phenotype` in the three gene templates | `genetic_association` in several rules, together with treatment-related evidence | Any stored predicate, including `related_to` |
| Chemical intermediates | Absent from these four templates | Present in rules 1 and 8 | Compared with chemicals allowed versus excluded |
| Dependence on chemical–disease evidence | One template and the direct lookup | Every treatment rule and the direct lookup | No such edges available in the graph |
| Meaning of a match | Satisfies a selected treatment template | Satisfies all required rule-body edges | Demonstrates connectivity, not treatment efficacy |

Excluding chemical intermediates did not alter the five highest-ranked patterns
in either the qualified or unqualified three-hop ranking. Frequency was ranked by
supporting benchmark pairs, then supporting node sequences.

| Sample result | Chemical intermediates allowed | Chemical intermediates excluded |
|---|---:|---:|
| Two-hop signatures without qualifiers | 53 | 53 |
| Two-hop signatures with qualifiers | 65 | 65 |
| Pairs connected in two hops | 5/10 | 5/10 |
| Three-hop signatures without qualifiers | 12,531 | 8,702 |
| Three-hop signatures with qualifiers | 19,720 | 13,411 |
| Pairs connected in three hops | 9/10 | 9/10 |

Chemical exclusion used the explicit categories in
[analyze_graph.py](../../data_split/analyze_graph.py): `Drug`, `ChemicalEntity`,
`SmallMolecule`, `MolecularMixture`, `ChemicalMixture`, and
`ComplexMolecularMixture`. Matching any stored category excludes an intermediate;
this also excludes endogenous metabolites and broad chemical classes.

The sample's detailed enumeration and ranking artifacts were written to temporary
directories `/tmp/tier0-metapaths-20261112/` and
`/tmp/tier0-chemical-comparison-20261112/`; they are not archived with this report
and may not persist. The local rule definitions linked above are the primary
sources for the rule comparison.

## Interpretation and limitations

BTE's surviving templates impose more specific biological constraints than the
frequent generic association paths. ARAGORN's stored treatment rules depend on
evidence that this filter deliberately removes. A chemical–gene–disease path
alone does not satisfy an ARAGORN rule that also requires treatment-related
evidence.

The graph filter therefore changes the available reasoning strategies, not merely
the difficulty of recovering one withheld treatment edge. Performance comparisons
on this graph also measure compatibility with that filtering policy.

The frequent exploratory signatures often pass through broad disease ancestors
or procedures. Their recurrence does not establish causal mechanisms, treatment
efficacy, or generalization beyond the ten-pair sample. No exact sample-level BTE
or ARAGORN match counts are inferred from the structural comparison, and no
production service behavior is inferred solely from stored template predicates.

For the separately conducted recovery baseline and its runtime limitations, see
the [experiment README](README.txt). The code that expands queries into templates
and includes direct lookups is in
[BTE's worker](../../workers/bte_lookup/worker.py) (`expand_bte_query`) and
[ARAGORN's worker](../../workers/aragorn_lookup/worker.py) (`expand_aragorn_query`).
