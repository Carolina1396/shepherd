# Rule 9: `BiologicalProcess → has_output → ChemicalEntity`

## Known from the main experiment

Retriever accepted `biolink:has_output` as a predicate but logged that it could not find a MetaEdge for the exact typed relationship:

```text
BiologicalProcess → biolink:has_output → ChemicalEntity
```

This establishes a planning-time typed-pattern failure for the saved requests. It does not establish that `has_output` is globally absent.

## Original investigation questions (see pilot results below)

- Predicate counts across Tier 0 metadata and the local graph.
- Category combinations in which `has_output` occurs.
- Whether direction or endpoint category modeling differs from the rule.
- A pinned known-edge positive control.
- The exact typed query with categories or direction changed one at a time.

## Original control plan (partially executed below)

1. Inventory all `has_output` MetaEdges and record counts and endpoint categories.
2. Find and verify a concrete retrievable witness edge.
3. Replay the exact rule edge directly.
4. Relax one endpoint category at a time.
5. Test reverse direction separately without treating it as equivalent to the rule.

## Production pilot — 22 October 2026

Full rule and all four isolated controls returned missing MetaEdges, including when both categories were omitted.

| Control | HTTP | Status | Outcome | Results |
|---|---:|---|---|---:|
| rule_09_full | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_09_typed | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_09_omit_subject | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_09_omit_object | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_09_omit_both | 200 | UnsupportedConstraint | missing_metaedge | 0 |

The full rule graph was extracted from the saved Production q01 callback (pheochromocytoma). Isolated probes preserve the failing edge and pin diagnostic nodes; they are not known positive witnesses. Category controls alter only endpoint categories. Rule 1 uses NCBIGene:6733 and CHEBI:28748; rule 2 uses CHEBI:28748 at both endpoints; rule 9 uses GO:0045721 and CHEBI:28748. Zero on these pairs cannot prove global absence.

All responses logged Tier 0 release `2026_06_21`, Biolink `4.3.2`, and TRAPI `1.6.0`. Metadata matched before and after; no exact entries for the three predicates appeared in its edge inventory. This inventory does not account for predicate descendants or establish absence of every retrievable related relationship. Only public Production was tested. No vocabulary substitutions were made.

- [Reusable runner](../../run_remaining_controls.py)
- [Summary](../../../../output/rules-01-02-09-controls/run_001/summary.json)
- [Exact requests, responses, and snapshots](../../../../output/rules-01-02-09-controls/run_001/)

Next: Inspect descendant/inverse predicates and source modeling; establish a real has_output witness if available. No positive witness has been established.

## Versioned model and predicate expansion audit

Biolink 4.3.2 defines has_output, with inverse is_output_of and no proper descendants found through is_a/mixins. Fresh metadata lists neither direction. The existing local inventory also supports exact-predicate absence for this downloaded release; it is not an independent scan of the currently hosted graph. This is a graph-vocabulary coverage issue in the checked evidence, not an invalid Biolink term. No positive has_output witness could be selected from this inventory.

[Machine-readable model/metadata/local inventory findings](../../../../output/predicate-model-audit/findings.json), [source provenance](../../../../output/predicate-model-audit/provenance.json), and [saved witness queries](../../../../output/predicate-model-audit/) retain the evidence. [Offline audit runner](../../audit_predicate_model.py) recomputes the model/metadata comparison from saved artifacts. Two additional hosted queries were used for the orthology witness; no further full-rule expansion was submitted.
