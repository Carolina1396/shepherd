# Systematic analysis of rules that did not return paths

This directory tracks dedicated follow-ups for the eleven ARAGORN treatment rules that were consistently rejected or empty in the ten-query comparison. The [main report](../../REPORT.md) remains the source for the original cross-environment observations.

The folders describe follow-up coverage:

- [`tested/`](tested/) contains patterns for which we ran additional controls beyond the original ARAGORN workflow.
- [`not-tested/`](not-tested/) contains patterns observed in the main logs but not yet subjected to a dedicated controlled follow-up.

“Tested” is always limited to the scope stated in the investigation README. It does not mean that every target, environment, graph release, or possible explanation has been exhausted.

## Coverage

| Rules | Main outcome | Shared edge or condition | Follow-up state | Current conclusion |
|---|---|---|---|---|
| 1 | Rejected | `affects_response_to` predicate validation | Tested with limited scope | Production full-rule and isolated controls reproduce invalid-predicate rejection; version history remains unresolved |
| 2 | Rejected | `ChemicalEntity → similar_to → ChemicalEntity` | Tested with limited scope | Production category controls completed; see individual investigation for outcomes and remaining questions |
| 3, 4, 5, 7, 8 | Rejected | `Gene → genetic_association → DiseaseOrPhenotypicFeature` | Tested | Predicate exists, but the required Gene-typed pattern was absent from checked metadata and the local inventory |
| 9 | Rejected | `BiologicalProcess → has_output → ChemicalEntity` | Tested with limited scope | Production category controls completed; see individual investigation for outcomes and remaining questions |
| 12, 13, 16 | Empty | Qualified `affects` paths | Tested with limited scope | Broad paths existed for one disease, but the requested qualifier combinations eliminated them in CI, Test, and Production |

The machine-readable, one-row-per-rule tracker is [status.csv](status.csv).

[BIOLINK_ROOT_CAUSE.md](BIOLINK_ROOT_CAUSE.md) traces each failure to a Biolink model change (rules 1, 3, 4, 5, 7, 8) or to graph coverage (rules 2, 9, 12, 13, 16).

## Required workflow for each investigation

Use [INVESTIGATION_TEMPLATE.md](INVESTIGATION_TEMPLATE.md) and change one condition at a time:

1. Copy the exact expanded query graph from a saved ARAGORN callback.
2. Record the original callback outcome and exact warning or error.
3. Identify the failure layer: query validation, MetaEdge planning, traversal, qualifier filtering, timeout, or ARAGORN post-processing.
4. Check predicate presence independently from the exact subject–predicate–object category combination.
5. Run a known-edge positive control when a suitable witness exists.
6. Relax one category, predicate, direction, pin, or qualifier at a time.
7. Record endpoint, environment, requested tier, observed tier, graph release, TRAPI version, and submitter.
8. Save the exact request, response, transport status, summary, and analysis code.
9. State what the evidence establishes, what it does not establish, and the next unresolved test.

The initial directory creation was offline. On 22 October 2026, the genetic-association investigation added a five-query Production pilot with named submissions, before/after metadata, and exact bound-edge controls. See its README and saved summary for scope and results.

On 22 October, the [rules 1/2/9 runner](run_remaining_controls.py) executed 15 sequential Production queries. These groups now reside in `tested/`, with limited scope. All eleven problematic rules now have some dedicated follow-up evidence, but investigations remain incomplete. Run the runner without arguments for offline summarization; `--submit --output <new-directory>` enables a fresh hosted run.
