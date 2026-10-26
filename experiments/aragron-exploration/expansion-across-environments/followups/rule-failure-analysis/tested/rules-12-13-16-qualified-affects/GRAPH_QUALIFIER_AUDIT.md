# Graph-wide qualifier investigation: rules 12, 13, and 16

## Main finding

The required qualifier values are **not globally absent from the downloaded graph**. They occur on affects records whose objects are Gene/Protein nodes. None of the matching records has the BiologicalEntity → ChemicalEntity endpoint combination required by these rules. This extends the earlier one-disease observation: the annotations are unavailable on the required typed edges in the checked local release, even though they exist elsewhere.

## Local inventory method

The audit searched the complete downloaded `2026_06_21` raw edge file for the requested aspect values and their Biolink descendants, then parsed explicit qualifiers rather than treating textual mentions as annotations. It inspected top-level qualifier fields, TRAPI qualifier arrays, and qualifier-typed attributes, including subject/object variants and alternative aspect/direction field names. It counted the affects predicate family and other predicates separately, joined actual endpoint categories, and checked unchanged input file sizes/mtimes across the scan.

Biolink 4.3.2 defines transport descendants secretion and uptake; increased/decreased include upregulated/downregulated respectively. The relevant descendants agree with the locally packaged 4.4.4 model. Model expansion was used to identify candidate records, with hosted witnesses checking actual retrievability separately.

The scan found 13,686 records bearing the target aspects or descendants. All used the affects predicate and explicit object_aspect_qualifier fields. It found no target-value occurrences under subject qualifiers or alternative qualifier fields in the parsed records. This does not treat unstructured text as equivalent to a structured qualifier.

| Rule | Required effect | Exact aspect/direction records | Records including descendant values | Records with required BiologicalEntity → ChemicalEntity types |
|---|---|---:|---:|---:|
| 12 | metabolic_processing + decreased | 126 | 126 | 0 |
| 13 | transport + decreased | 69 | 1,990 | 0 |
| 16 | secretion + increased | 4,880 | 4,880 | 0 |

Rule 13's 1,990 records comprise 69 transport, 1,813 secretion, and 108 uptake records, all with decreased direction. All matching objects in these three groups carry Gene/Protein types. Most subjects are chemicals; some are proteins. These counts are raw records, not distinct pairs or rule paths. Changing qualifier values or reversing edges is not established as a semantically appropriate rule correction.

## Direct hosted witnesses

We selected three real witnesses plus an additional exact-transport witness. Requests preserve their actual SmallMolecule → Gene categories and pins, and request affects with the rule's object aspect/direction. Development used its advertised TRAPI 2.0 constraints.qualifiers syntax; CI/Test/Production used qualifier_constraints. An offline check confirmed identical qualifier semantics across encodings.

| Query | Requested effect | Stored aspect | Subject → object | Development | CI | Test | Production |
|---|---|---|---|---|---|---|---|
| p01 | metabolic_processing / decreased | metabolic_processing | Pregnenolone (`CHEBI:16581`) → GHRL (`NCBIGene:51738`) | Exact edge returned | empty | Exact edge returned | Exact edge returned |
| p02 | transport / decreased | transport | potassium atom (`CHEBI:26216`) → SCT (`NCBIGene:6343`) | Exact edge returned | empty | Exact edge returned | Exact edge returned |
| p03 | transport / decreased | secretion | Ethinylestradiol (`CHEBI:4903`) → TNF (`NCBIGene:7124`) | Exact edge returned | empty | Exact edge returned | Exact edge returned |
| p04 | secretion / increased | secretion | Astemizole (`CHEBI:2896`) → HEXB (`NCBIGene:3074`) | Exact edge returned | empty | Exact edge returned | Exact edge returned |

All sixteen responses were HTTP 200 / Success, matched the requested query graph, and logged no warnings/errors. Development, Test, and Production returned one result per query, binding the original witness edge IDs and carrying the expected annotations. CI returned zero for all four. All responses reported Tier 0 release 2026_06_21; each environment's metadata was unchanged before/after. Identical release labels do not establish identical deployed behavior or graph contents.

The transport query on the stored decreased-secretion witness verifies descendant matching for that example in Development, Test, and Production. These positive examples demonstrate retrieval of the required annotations; they alone do not prove qualifier enforcement against incorrect values. The earlier positive/negative controls for one different witness remain the evidence for that narrower enforcement claim.

## CI diagnostic controls

We repeated the four CI requests with only qualifier_constraints removed. All four still returned zero, with HTTP 200 / Success and no warnings/errors. Thus qualifier requirements alone do not explain this CI discrepancy.

In the first unqualified control, CI logged:

```text
Rewriting query graph for subclass expansion (depth=1)
Processing edge 'e': s -> o
  Found 4 matching edges
Reconstructing complete paths...
  Join 2/2: Adding edge 'o_subclass_edge' (4 paths)...
 -> 0 paths (0.00s)
  No valid paths found after joining edge 'o_subclass_edge'
```

This identifies an observed point where the search loses paths. It does not establish that a specific deployment defect caused it, nor prove the expected witness was among the four intermediate matches. The saved CI schema did not expose a subclass parameter in its Parameters definitions, so no undocumented toggle was used. A separate investigation of subclass rewriting, pin normalization, and backend state is needed if CI parity matters.

## Scope and interpretation

- The inventory is a full search of the relevant explicit values in the downloaded release, not an independent scan of every hosted graph.
- A qualified edge with a Gene/Protein object cannot establish a full rule path that requires effects on two ChemicalEntity objects.
- No global absence of the qualifiers should be inferred from the earlier pheochromocytoma result. The new evidence establishes presence elsewhere and a typed-edge mismatch locally.
- Public Development Retriever identity relative to ARAGORN's internal Retriever remains unverified. These were direct lookups, not a rerun of the entire ARAGORN workflow.
- The original 48 qualifier controls and main cross-environment experiment remain historical observations. This new run exposed a CI difference; it does not retroactively change their recorded results.
- This follow-up made 16 qualified POSTs, four additional unqualified CI POSTs, and twelve schema/metadata GETs. It made no rule substitutions.

## Reproduction and evidence

- [Offline graph auditor](audit_graph_qualifiers.py)
- [Graph findings and raw aspect-bearing records](../../../../output/qualifier-graph-audit/run_001/)
- [Selected raw witnesses](../../../../output/qualifier-graph-audit/run_001/witnesses.json)
- [Hosted witness runner](verify_graph_witnesses.py)
- [Hosted requests, responses, versions, and summary](../../../../output/qualifier-graph-audit/hosted-witnesses_001/)
- [CI unqualified-control runner](check_ci_witness_controls.py)
- [CI unqualified requests and logs](../../../../output/qualifier-graph-audit/ci-unqualified_001/)

Both hosted runners summarize saved evidence by default and require --submit to send requests. Existing POST markers prevent automatic retries, including uncertain attempts. The graph auditor runs offline; repeat it only when a new scan is intended.
