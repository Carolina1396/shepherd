# Rules 12, 13, and 16: qualified `affects` paths

## Question

Do these rules return no paths because the broad graph pattern is absent, because Retriever ignores or rejects the qualifier syntax, or because the available edges do not satisfy the requested effects?

The rules share the same topology and differ in their effect qualifiers:

| Rule | Object aspect | Direction |
|---:|---|---|
| 12 | `metabolic_processing` | `decreased` |
| 13 | `transport` | `decreased` |
| 16 | `secretion` | `increased` |

## Tests completed

For pheochromocytoma in CI/Staging, Test, and Production, direct Tier 0 Retriever queries tested:

1. Each original qualified rule graph.
2. The shared graph with both qualifiers removed.
3. Each branch with only one qualifier retained.
4. A pinned real edge without qualifiers.
5. The same edge with its matching qualifiers.
6. The same edge with an opposite direction.
7. The same edge with each rule-required effect.

All 48 saved requests returned HTTP 200 and `Success`, logged Tier 0 execution, and returned matching query graphs without warnings or errors.

## Result

- Each original qualified rule returned zero results.
- Removing both qualifier requirements returned **27,984 raw result records** and 725 distinct candidate chemicals in every tested environment.
- A real pinned edge returned both unqualified and with its matching qualifier.
- The opposite direction and the three rule-required effects did not return that edge.
- Bound edges from the broad search used aspects such as `activity_or_abundance`, `activity`, `abundance`, and `stability`; none explicitly used the three required aspects.

For this target and these three environments, the broad paths exist but fail the rules' effect conditions. The controls demonstrate qualifier enforcement for the tested witness.

## Scope and remaining work

- Only pheochromocytoma was tested, not the other nine targets.
- Development was excluded from the hosted control because its TRAPI 2.0 qualifier-warning behavior needs a separate test.
- Raw Retriever records are not ARAGORN final answers and do not run ARAGORN merge filters.
- Missing annotations on these paths do not establish graph-wide or biological absence.

## Scripts and evidence

- [Hosted control runner](../../../../scripts/hosted_qualifier_controls.py)
- [Local qualifier diagnostic](../../../../scripts/inspect_qualifier_handling.py)
- [Findings](../../../../output/hosted-qualifier-controls/run_001/findings.json)
- [All 48 exact requests and responses](../../../../output/hosted-qualifier-controls/run_001/)
- [Local diagnostic results](../../../../output/qualifier-investigation/diagnostic.json)
- [Pinned source provenance](../../../../output/qualifier-investigation/source-provenance.json)

## Graph-wide qualifier inventory and hosted witnesses

The [graph-wide audit](GRAPH_QUALIFIER_AUDIT.md) establishes that the required qualifiers exist elsewhere: 126 decreased metabolic-processing records, 1,990 decreased-transport-family records, and 4,880 increased-secretion records, but none has the required ChemicalEntity object. Witnesses returned in public Development, Test, and Production; CI was empty even without qualifiers, with a subclass-join discrepancy visible in its logs. This updates the scope beyond the earlier one-disease control.
