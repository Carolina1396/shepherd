# Rule 1: `affects_response_to`

## Known from the main experiment

Retriever rejected the expanded graph during query validation in all tested environments:

```text
Validation Error: Edge `edge_0` has invalid predicates: ['biolink:affects_response_to']
```

This differs from a missing MetaEdge: validation stops before Retriever attempts to plan or traverse the typed relationship.

## Original investigation questions (see pilot results below)

- Whether each environment's current Retriever schema still rejects the predicate directly.
- Which Biolink model version removed, renamed, or otherwise excludes the predicate.
- Whether ARAGORN's rule source and Retriever's validation model use mismatched vocabularies.
- Whether a current predicate expresses the intended semantics; no replacement should be assumed without review.

## Original control plan (partially executed below)

1. Save each environment's Retriever and ARAGORN schemas and advertised versions.
2. Submit the exact isolated edge directly to Retriever.
3. Compare predicate validity across the relevant Biolink releases.
4. Identify candidate current predicates from authoritative model mappings.
5. If a candidate is semantically approved, change only the predicate and compare validation and retrieval.

## Production pilot — 22 October 2026

All five controls failed predicate validation (HTTP 422, QueryNotTraversable). Category removal did not change this.

| Control | HTTP | Status | Outcome | Results |
|---|---:|---|---|---:|
| rule_01_full | 422 | QueryNotTraversable | invalid_predicate | 0 |
| rule_01_typed | 422 | QueryNotTraversable | invalid_predicate | 0 |
| rule_01_omit_subject | 422 | QueryNotTraversable | invalid_predicate | 0 |
| rule_01_omit_object | 422 | QueryNotTraversable | invalid_predicate | 0 |
| rule_01_omit_both | 422 | QueryNotTraversable | invalid_predicate | 0 |

The full rule graph was extracted from the saved Production q01 callback (pheochromocytoma). Isolated probes preserve the failing edge and pin diagnostic nodes; they are not known positive witnesses. Category controls alter only endpoint categories. Rule 1 uses NCBIGene:6733 and CHEBI:28748; rule 2 uses CHEBI:28748 at both endpoints; rule 9 uses GO:0045721 and CHEBI:28748. Zero on these pairs cannot prove global absence.

All responses logged Tier 0 release `2026_06_21`, Biolink `4.3.2`, and TRAPI `1.6.0`. Metadata matched before and after; no exact entries for the three predicates appeared in its edge inventory. This inventory does not account for predicate descendants or establish absence of every retrievable related relationship. Only public Production was tested. No vocabulary substitutions were made.

- [Reusable runner](../../run_remaining_controls.py)
- [Summary](../../../../output/rules-01-02-09-controls/run_001/summary.json)
- [Exact requests, responses, and snapshots](../../../../output/rules-01-02-09-controls/run_001/)

Next: Review predicate validity/history in the advertised Biolink version; identify a semantically reviewed candidate before adaptation.

## Versioned model and predicate expansion audit

The official Biolink 4.3.2 YAML contains affects response to and its increases/decreases descendants. Production nevertheless rejected the predicate. The advertised version alone does not identify the validator’s actual loaded model; a deployment/model-loading or validation discrepancy remains unresolved. Do not describe this term as absent from Biolink 4.3.2.

[Machine-readable model/metadata/local inventory findings](../../../../output/predicate-model-audit/findings.json), [source provenance](../../../../output/predicate-model-audit/provenance.json), and [saved witness queries](../../../../output/predicate-model-audit/) retain the evidence. [Offline audit runner](../../audit_predicate_model.py) recomputes the model/metadata comparison from saved artifacts. Two additional hosted queries were used for the orthology witness; no further full-rule expansion was submitted.
