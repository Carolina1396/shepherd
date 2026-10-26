# Rules 3, 4, 5, 7, and 8: `genetic_association`

## Question

Does Retriever reject these rules because `biolink:genetic_association` is absent, or because the exact typed edge is unsupported?

All five rules require this edge:

```text
Gene → biolink:genetic_association → DiseaseOrPhenotypicFeature
```

## Tests completed

1. Reused the downloaded Tier 0 inventory to count predicate records and exact typed pairs.
2. Retrieved fresh Tier 0 metadata from CI/Staging, Test, and Production.
3. Inspected category combinations reported for `genetic_association`.
4. Sent a pinned Production lookup for a known `BiologicalProcess → genetic_association → PhenotypicFeature` edge.

## Result

- The local inventory contained **415,530** `genetic_association` records.
- Fresh hosted metadata reported the same predicate count and 79 category combinations.
- No checked metadata combination had a Gene endpoint for this predicate.
- The local inventory found zero distinct pairs for the rule-required typed pattern.
- The pinned Production control returned the expected `genetic_association` edge.

The predicate exists and is retrievable. The evidence supports a mismatch in typed-pattern coverage rather than global predicate absence.

## Scope and remaining work

- The public Development Retriever was not tested in this follow-up.
- Hosted metadata counts were not replaced by independent full scans.
- The live control proves predicate presence; it does not independently prove global absence of every possible Gene association.
- The original historical audit commands were not retained as a standalone runner. The new controlled pilot has a reusable runner; it does not reconstruct the historical metadata audit.
- `biolink:gene_associated_with_condition` appears in the graph but has not been established as a valid semantic replacement.

## Evidence

- [Findings](../../../../output/genetic-association-audit/run_001/findings.json)
- [Hosted metadata and summaries](../../../../output/genetic-association-audit/run_001/)
- [Exact Production request](../../../../output/genetic-association-audit/run_001/production-example/request.json)
- [Exact Production response](../../../../output/genetic-association-audit/run_001/production-example/response.json)
- [Clearer pinned example](../../../../output/genetic-association-audit/clearer-example_001/)
- [Local Tier 0 pattern notebook](../../../../../01_tier0_rule_patterns.ipynb)

## Controlled Production pilot — 22 October 2026

[run_controls.py](run_controls.py) implements the bounded pilot. It summarizes saved evidence by default; `--submit` enables sequential requests with a named submitter and persistent attempt markers. Existing attempted requests are not repeated. Each run captures exact requests, raw responses, transport status, schema, timestamps, runner hash, and before/after metadata.

| Control | Result | Bound witness |
|---|---|---|
| Original BiologicalProcess subject | Success; 1 result | Expected association returned |
| Same pinned nodes; subject category Gene | UnsupportedConstraint; missing MetaEdge | None |
| Same pinned nodes; subject category BiologicalEntity | Success; 1 result | Same association returned |
| Same pinned nodes; subject category omitted | Success; 1 result | Same association returned |
| Gene subject unpinned; DiseaseOrPhenotypicFeature object pinned to MONDO:0005148 | UnsupportedConstraint; missing MetaEdge | None |

All five returned HTTP 200 and logged Tier 0 execution. Reported graph release was `2026_06_21`; canonical metadata hashes were identical before and after. The three positive controls returned the same bound edge identifier, not merely the same count. All response query graphs matched their requests.

The exact rejection was `MetaEdges could not be found for the following QEdge(s): ['e']`. This is a planning rejection, not a successful empty traversal. The original witness is a BiologicalProcess, so deliberately requesting Gene is a diagnostic of category-sensitive planning, not a biological claim that this node is a gene. The fifth query independently tests the exact rule-required category combination with an open Gene node; it is not a one-variable comparison against the witness.

[Saved pilot summary](../../../../output/genetic-association-audit/controlled-pilot_001/summary.json) and [all requests, responses, and snapshots](../../../../output/genetic-association-audit/controlled-pilot_001/) retain the evidence.

From the repository root, reproduce the summary offline:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/followups/rule-failure-analysis/tested/rules-03-04-05-07-08-genetic-association/run_controls.py
```

For an intentional new hosted run, add `--submit --output <new-run-directory>`. This pilot sent five POSTs and three snapshot GETs. It did not replay the complete ARAGORN workflow, test another environment, or substitute a predicate.

## Next evidence gates

1. Review the semantic relationship between the original predicate and candidate alternatives using pinned Biolink definitions/mappings.
2. Obtain a real Gene–condition witness for a candidate predicate and compare predicates while preserving pins and categories.
3. If justified, test an experimental complete rule, then partial paths to locate any remaining failure.
4. Compare through ARAGORN only after establishing how to submit the adapted rule; verify internal deployment identity before claiming equivalence to this public endpoint.
5. Broaden environments and targets only when they address an unresolved question. Preserve rejection, empty, incomplete, error, and unknown outcomes separately.

## Nine category witnesses across four environments

[Category-witness results](CATEGORY_WITNESSES.md) document 36 new direct lookups, exact examples, endpoints, and limitations. This extends positive-presence evidence to nine category combinations; it does not repair the Gene-to-condition rule pattern.
