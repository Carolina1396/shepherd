# Rule 2: `ChemicalEntity → similar_to → ChemicalEntity`

## Known from the main experiment

Retriever accepted `biolink:similar_to` as a predicate but logged that it could not find a MetaEdge for the exact typed relationship:

```text
ChemicalEntity → biolink:similar_to → ChemicalEntity
```

This establishes a planning-time typed-pattern failure for the saved requests. It does not establish that `similar_to` is globally absent.

## Original investigation questions (see pilot results below)

- Predicate counts across Tier 0 metadata and the local graph.
- Category combinations in which `similar_to` occurs.
- Whether category inheritance should make a narrower chemical type match the requested category.
- A pinned known-edge positive control.
- The exact typed query with categories relaxed one endpoint at a time.

## Original control plan (partially executed below)

1. Inventory all `similar_to` MetaEdges and record counts and endpoint categories.
2. Find and verify a concrete retrievable witness edge.
3. Replay the exact rule edge directly.
4. Relax only the subject category, then only the object category, then both.
5. Compare exact versus descendant category handling and preserve direction throughout.

## Production pilot — 22 October 2026

Full rule and controls retaining either ChemicalEntity category returned missing MetaEdges. Omitting both categories inferred NamedThing and traversed, returning zero edges for the same-node diagnostic pair.

| Control | HTTP | Status | Outcome | Results |
|---|---:|---|---|---:|
| rule_02_full | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_02_typed | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_02_omit_subject | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_02_omit_object | 200 | UnsupportedConstraint | missing_metaedge | 0 |
| rule_02_omit_both | 200 | Success | empty | 0 |

The full rule graph was extracted from the saved Production q01 callback (pheochromocytoma). Isolated probes preserve the failing edge and pin diagnostic nodes; they are not known positive witnesses. Category controls alter only endpoint categories. Rule 1 uses NCBIGene:6733 and CHEBI:28748; rule 2 uses CHEBI:28748 at both endpoints; rule 9 uses GO:0045721 and CHEBI:28748. Zero on these pairs cannot prove global absence.

All responses logged Tier 0 release `2026_06_21`, Biolink `4.3.2`, and TRAPI `1.6.0`. Metadata matched before and after; no exact entries for the three predicates appeared in its edge inventory. This inventory does not account for predicate descendants or establish absence of every retrievable related relationship. Only public Production was tested. No vocabulary substitutions were made.

- [Reusable runner](../../run_remaining_controls.py)
- [Summary](../../../../output/rules-01-02-09-controls/run_001/summary.json)
- [Exact requests, responses, and snapshots](../../../../output/rules-01-02-09-controls/run_001/)

Next: Explain why NamedThing planning succeeds; inspect descendant predicates and use distinct-node witnesses if available. No positive similar_to witness has been established.

## Versioned model and predicate expansion audit

Biolink 4.3.2 defines similar_to as symmetric, with chemically_similar_to and homology/orthology descendants. Metadata lists 76,519 orthologous_to records across gene/protein combinations, but no chemically_similar_to entries. A fresh orthologous_to lookup from NCBIGene:7157 found a real NCBIGene:7157 → NCBIGene:22059 edge. Querying similar_to on these two pinned Gene nodes returned that exact bound orthologous_to edge (c42a9f48-7ccd-4492-a4c8-eb2f2b23663b). Thus similar_to is supported through descendant expansion for gene orthology, without establishing chemical similarity coverage. Pinned reference Retriever code expands categories and predicates before matching metadata; this supports the explanation that NamedThing permits gene/protein operations while ChemicalEntity excludes them. The deployed source digest is unverified.

[Machine-readable model/metadata/local inventory findings](../../../../output/predicate-model-audit/findings.json), [source provenance](../../../../output/predicate-model-audit/provenance.json), and [saved witness queries](../../../../output/predicate-model-audit/) retain the evidence. [Offline audit runner](../../audit_predicate_model.py) recomputes the model/metadata comparison from saved artifacts. Two additional hosted queries were used for the orthology witness; no further full-rule expansion was submitted.

## Full raw similarity endpoint audit — 22 October 2026

To address whether the earlier doxorubicin-to-itself example missed a real chemical pair, we scanned the complete downloaded edge file for the Biolink 4.3.2 similar_to hierarchy, then scanned all 1,754,754 node records to inspect the actual categories of its 59,280 unique endpoints. The hierarchy included similar_to, chemically_similar_to, homologous_to, orthologous_to, paralogous_to, and xenologous_to. Input size and modification time were checked before and after.

All 76,519 matching records were orthologous_to. No endpoint was labeled ChemicalEntity or a descendant chemical class. Therefore there were zero chemical-to-chemical records in this predicate family under the stored categories. The raw node records include inherited categories, and the audit also derived chemical descendants from the pinned model.

Fourteen endpoints had DrugBank aliases (including INS and ALB), but all were typed Gene/Protein. No edge connected two of these alias-bearing endpoints. Drug identifiers alone do not establish that a normalized node has a ChemicalEntity type or represents a chemical-similarity edge. These cases are retained for possible normalization review.

No real chemical-similarity witness was found, so the planned real-chemical-pair category/predicate comparison could not be performed. This conclusion no longer rests on the arbitrary pinned chemical example: it rests on the full downloaded-release scan, consistent with the saved hosted metadata. It does not rule out incorrectly labeled source records, a different release, another environment, or chemical similarity modeled with another predicate. It also does not independently prove category inheritance works for a chemical-similarity edge when no such witness exists.

[Raw-scan findings](../../../../output/similarity-endpoint-audit/findings.json), [matching raw edges and endpoint nodes](../../../../output/similarity-endpoint-audit/), and [reusable offline scanner](../../scan_similarity_endpoints.py) preserve the evidence. No new hosted queries were needed for this scan.

## Four similarity category witnesses across environments

[Category-witness report](CATEGORY_WITNESSES.md) records 16 direct similar_to lookups using four real, distinctly typed Gene/Protein pairs across public Development, CI, Test, and Production. Each query is checked against its stored orthologous_to edge, keeping predicate expansion distinct from exact-predicate records.
