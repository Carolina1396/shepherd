# ARAGORN retrieval and Shepherd service: findings so far

Part of [Study 3: Sampling and retrieval](../../README.md#study-3-sampling-and-retrieval).
Links into `results/` below refer to local-only artifacts excluded from Git.

This report consolidates the chemical/drug retrieval experiments, the ten-disease
comparison with the actual Shepherd ARAGORN service, and the reconstruction of
rule assignments from returned supporting graphs. It also includes the completed
Gandalf-versus-ARAGORN comparison on the same `treats_only` graph. Service responses were captured
on October 14, 2026 UTC (October 13 in Los Angeles).

## Main findings

- **All 18 treatment rules were included**, plus a direct lookup: 19 queries per
  disease. A rule returning no matches was not deliberately excluded.
- With only held-out `treats` connections removed, local retrieval recovered
  **19.86% of validation answers and 22.07% of test answers**. These measure
  ARAGORN retrieval coverage, not ULTRA ranking performance.
- On the same dataset and mask, **Gandalf three-hop walks recovered 66.91% of
  validation answers and 68.21% of test answers**. Both methods used a 3,000-edge
  ceiling, but walks produced much larger graphs on average.
- For ten unmasked disease queries, the service and local implementation returned
  identical answer sets for **7/10 diseases**. The local implementation returned
  **77 additional disease–chemical pairs**, all produced exclusively by local
  rule 10. There were no service-only answers.
- The service returned **579 disease–chemical answer pairs**. Its **651 supporting
  graphs** each matched exactly one of rules **5, 10, or 16**, including qualifiers.
- Rule assignments were reconstructed from evidence. The service does not explicitly
  report the generating rule IDs, and we have not established full implementation
  equivalence or the cause of the missing service answers.

## 1. The two experiments answer different questions

| Setting | Held-out recovery experiment | Service/local comparison |
|---|---|---|
| Question | Do the rules recover known answers after hiding their treatment edges? | Do the service and local code return the same answer IDs? |
| Diseases | 1,707 distinct validation/test diseases | 10 diseases sampled from validation, seed 7317 |
| Graph | Validation/test pairs masked before retrieval | Original unmasked local graph; remote snapshot unverified |
| Mask policies | All direct connections; or exact `treats` only | No masking requested |
| Rules | All 18 plus direct lookup | All 18 plus direct lookup |
| Retrieval cap | 3,000 unique directed connections per disease | No experiment cap on local retrieval |
| Per-rule deadline | 5 seconds plus hard timeout grace | 120 seconds plus hard timeout guard |
| Outputs | Expected-answer coverage and graph sizes | Exact returned-answer sets and supporting evidence |

The ten-query comparison does not measure held-out recovery. Agreement between
implementations does not imply either can recover every expected treatment.
The completed walk follow-up uses the held-out experiment's `treats_only` graph,
1,000 native three-hop attempts per disease, and the same 3,000-connection cap.
It reuses the saved ARAGORN graphs; detailed paired results are in section 8.

The actual service endpoint was `https://shepherd.renci.org/aragorn/query`, using
the `aragorn.lookup` workflow. This omits subsequent scoring and top-500 filtering
from the default ranked workflow. Tier 0, Gandalf, `subclass=False`, cache bypass,
and the timeout were requested. The response echoes these settings, but that alone
does not verify their effect at every backend stage.

## 2. Dataset, masking, and graph sizes

The retrieval follow-up uses Experiment 11's frozen Experiment 10 labels:

| Split | Expected treatment pairs |
|---|---:|
| Train/visible | 18,334 |
| Validation | 2,291 |
| Test | 2,293 |

There are **1,117,832 chemical/drug candidates**. The source graph has **1,670,341
nodes**, **27,927,289 unique directed connections**, and **28,709,074 evidence
records**. Multiple evidence records can describe one unique connection.

Both masking policies apply only to the **4,584 held-out validation/test pairs**,
globally before retrieval, and check both directions. Other pairs, including
visible training treatment edges, remain available.

| Policy | Connections remaining | Connections removed |
|---|---:|---:|
| Original unmasked graph | 27,927,289 | 0 |
| Remove all direct held-out connections, across predicates | 27,916,156 | 11,133 |
| Remove only exact held-out `biolink:treats` connections | 27,922,705 | 4,584 |

The all-direct graph matches Experiment 11's saved inference triples. The
`treats_only` graph intentionally differs: other direct evidence, including
broader treatment and clinical-trial relationships, remains available. We selected
`treats_only` for further investigation.

The **3,000-connection cap applies to each retrieved disease graph**, not the full
source graph and not the number of returned answers. Whole rule matches are
retained and merged under that cap.

Sources: [masking and recovery results](../../studies/chemical_retrieval_001_results.json),
[retrieval protocol](../../retrieval/README.md),
[Experiment 11 protocol](../../chemical_finetune/README.md).

## 3. Recovery of expected answers

The following table describes the original **ARAGORN** retrieval experiment.

| Mask policy | Split | Recovered / expected | Recovery |
|---|---|---:|---:|
| All direct connections | Validation | 57 / 2,291 | 2.49% |
| All direct connections | Test | 68 / 2,293 | 2.97% |
| Exact `treats` only | Validation | 455 / 2,291 | 19.86% |
| Exact `treats` only | Test | 506 / 2,293 | 22.07% |
| Exact `treats` only | Train/visible | 18,334 / 18,334 | 100% |

For these results, graph-present recovery and explicitly bound answer recovery
agree. Missed answers stay in the denominator.

Training's 100% coverage is explained by visible training `treats` edges remaining
in the graph. It is not evidence of perfect predictive performance. Experiment 11
separately removes easy direct edges during each model training step; the training
coverage audit did not simulate those per-step masks.

All 18 templates were attempted in local retrieval. **Eleven returned zero raw
matches before the final union cap**: 0, 1, 2, 3, 4, 6, 7, 8, 11, 12, and 15.
The graph audit found missing predicates or missing required combinations of
endpoints, categories, directions, and qualifiers:

| Rules | Observed obstacle |
|---|---|
| 0 | `affects_response_to` absent; required gene–disease association also unavailable |
| 1 | No qualifying chemical-to-chemical `similar_to` pattern under native expansion |
| 2, 3, 4, 6, 7 | No required gene `genetic_association` to the evaluated target diseases; rule 7 also lacks its required qualifier pattern |
| 8 | No records for the expanded `has_output` predicate family |
| 11, 12, 15 | Required qualified BiologicalEntity-to-ChemicalEntity patterns unavailable |

Rules are pattern requirements, not guarantees that every known treatment has a
matching explanation. The direct lookup cannot recover held-out exact `treats`
answers after those edges are removed. The final graph cap additionally excluded
seven validation and seven test answers present in bounded per-rule results;
earlier per-rule limits may also affect coverage.

Sources: [training coverage](../../studies/chemical_retrieval_001_train_recovery.json),
[zero-match audit](../../results/chemical_retrieval_001/zero_rule_audit.json).

## 4. Actual service comparison: ten disease queries

The ten top-level service queries produced **190 lookup submissions**: 180 rule
queries and ten direct lookups. Logs record 19 submissions and 19 returned
callbacks for every disease; callback completion does not imply successful rule
execution. The local comparison also executed 190 lookups.

| Disease | Local answers | Service answers | Local only | Exact answer set |
|---|---:|---:|---:|---|
| MONDO:0004277 | 36 | 36 | 0 | Yes |
| MONDO:0004995 | 346 | 325 | 21 | No |
| MONDO:0005087 | 4 | 4 | 0 | Yes |
| MONDO:0005480 | 105 | 76 | 29 | No |
| MONDO:0005885 | 145 | 118 | 27 | No |
| MONDO:0008399 | 6 | 6 | 0 | Yes |
| MONDO:0009662 | 1 | 1 | 0 | Yes |
| MONDO:0017278 | 5 | 5 | 0 | Yes |
| UMLS:C0474013 | 2 | 2 | 0 | Yes |
| UMLS:C3163829 | 6 | 6 | 0 | Yes |
| **Total answer pairs** | **656** | **579** | **77** | **7/10 diseases** |

Every service answer was present locally. All 77 local-only pairs were produced
exclusively by local rule 10. Counts are disease–chemical pairs, not globally unique
chemicals, and are not counts of expected validation answers recovered.

Exact comparison uses returned CURIE sets, ignoring ordering and duplicates,
without synonym normalization. All saved response checksums and extracted answer
sets were verified. The checkout worker and local query builder produced identical
expanded query graphs, but the deployed worker's source version is unverified.

Source: [verified answer comparison](../results/run_001/observed_comparison.json).

## 5. What the service returns and how we reconstructed rules

The response includes answer bindings, knowledge-graph nodes and edges, source
provenance, auxiliary supporting graphs, and diagnostic logs. It contains no
explicit per-answer rule ID or structured per-rule execution report.

We followed:

```text
answer -> analysis edge binding -> inferred treats edge
       -> biolink:support_graphs -> auxiliary graph -> evidence edges
       -> comparison against all 18 rule templates
```

Of the **579 answer pairs**, 151 have only direct evidence, 393 only inferred
support, and 35 both. Thus **428 pairs** have inferred support, represented by
**651 supporting graphs**.

Every supporting graph matched exactly one template after checking node
categories, predicate expansion, direction, shared intermediate nodes, and
qualifiers. The assignments were identical under Biolink 4.4.2 and 4.4.4.

| Reconstructed rule ID | Pattern | Supporting graphs | Answer pairs supported |
|---|---|---:|---:|
| 5 | Candidate has treatment-related connections to the queried disease and another disease; the other disease `has_phenotype` the queried disease | 489 | 288 |
| 10 | A biological entity decreases activity/abundance of the candidate and another chemical that `treats` the disease | 14 | 12 |
| 16 | A biological entity increases the candidate's activity and another chemical's activity/abundance; the other chemical `treats` the disease | 148 | 143 |

Rule IDs are **zero-based**: rule 10 is the eleventh template. Rule 5's two
treatment edges use `biolink:treats_or_applied_or_studied_to_treat`, with native
predicate expansion. Rules 10 and 16 use `biolink:affects` with explicit aspect
and direction qualifiers.

Answer counts overlap across rules and must not be summed as unique answers.
All reconstructed rule–answer combinations were also found in the corresponding
local rule's results. The other 15 templates have no compatible supporting graphs
in these responses. This does not establish that they were skipped: empty results,
errors, and evidence deduplication can leave no final supporting graph.

### A concrete rule-10 answer

For nitric oxide (`CHEBI:16480`) and cardiovascular disorder (`MONDO:0004995`),
the service supplies this supporting evidence:

```text
MAPK8 (NCBIGene:5599) --affects [decreased activity]--> nitric oxide (CHEBI:16480)
MAPK8 (NCBIGene:5599) --affects [decreased activity]--> insulin human (CHEBI:5931)
insulin human (CHEBI:5931) --treats--> cardiovascular disorder (MONDO:0004995)
```

`activity` matches the broader `activity_or_abundance` qualifier in rule 10.
The support graph ID is `56caa5c0-79a2-4816-9f7b-1be18a547f3c`, in query `01`.
This describes the graph's recorded evidence, not an independent validation of
the biological assertions.

Sources: [support-tracing summary](../results/run_001/support_trace/summary.json),
[per-answer assignments](../results/run_001/support_trace/answer_rules.csv),
[concrete examples](../results/run_001/support_trace/examples.json).

## 6. All 18 rules: observed coverage versus service evidence

The first three data columns below concern the full **masked local recovery
experiment**. The last column concerns the **ten unmasked service queries**.
They have different cohorts and graph policies; the counts are not direct
performance comparisons. Rule contributions overlap.

| Rule ID | Local raw matches | Validation answers recovered | Test answers recovered | Compatible service support graphs |
|---|---|---:|---:|---:|
| 0 | Zero | 0 | 0 | 0 |
| 1 | Zero | 0 | 0 | 0 |
| 2 | Zero | 0 | 0 | 0 |
| 3 | Zero | 0 | 0 | 0 |
| 4 | Zero | 0 | 0 | 0 |
| 5 | Nonzero | 421 | 485 | 489 |
| 6 | Zero | 0 | 0 | 0 |
| 7 | Zero | 0 | 0 | 0 |
| 8 | Zero | 0 | 0 | 0 |
| 9 | Nonzero | 109 | 127 | 0 |
| 10 | Nonzero | 31 | 40 | 14 |
| 11 | Zero | 0 | 0 | 0 |
| 12 | Zero | 0 | 0 | 0 |
| 13 | Nonzero | 14 | 18 | 0 |
| 14 | Nonzero | 0 | 3 | 0 |
| 15 | Zero | 0 | 0 | 0 |
| 16 | Nonzero | 14 | 9 | 148 |
| 17 | Nonzero | 0 | 3 | 0 |

No rule was intentionally excluded. Zero matches, backend rejection, lack of
compatible final evidence, and deliberate exclusion are different outcomes.

## 7. Service errors and remaining uncertainty

- Every service response logs rejection of rule 0's `biolink:affects_response_to`
  predicate. HTTP 200 and a nonempty answer list do not mean every rule succeeded.
- Every response logs seven queries without a supported metadata edge pattern.
  Such queries can stop before graph lookup.
- Every response contains 18 `skipping unknown fields (constraints)` warnings.
  The returned supporting graphs nevertheless satisfy the reconstructed templates'
  qualifiers. This does not establish whether the original queries enforced those
  qualifiers at every stage. Ignoring qualifiers during reconstruction makes all
  162 affect-based support graphs ambiguous among seven templates.
- The response for `UMLS:C3163829` also reports a backend `httpx.ReadError`, despite
  its final answer set matching the local one.
- Local lookup uses Biolink 4.4.2; the service reports 4.4.4. Rule reconstruction
  agrees under both versions, but that does not establish identical execution.
- The remote graph snapshot, deployed worker version, and exact backend behavior
  remain unverified. The cause of the 77 missing service answers is unresolved.

The runner's original `comparison.json` and `status.json` mark the service run
partial because of rule errors. Use `observed_comparison.json` for the **7/10
returned-answer matches**; the stricter report accepts zero error-free matches.

## 8. Gandalf sampling on the same dataset and treats-only graph

This comparison is now complete for all **1,707 distinct validation/test diseases**.
It uses the same labels, chemical/drug candidates, masked source graph, and
3,000-connection ceiling as ARAGORN. The graph was independently verified to match
the earlier `treats_only` context exactly, including retention of visible training
edges and removal of all exact held-out `treats` connections in both directions.

Native Gandalf sampling makes **1,000 self-avoiding three-hop walk attempts per
disease**, traverses stored edges in either direction, and skips `subclass_of`.
Incomplete walks are discarded; cap selection retains whole walks. Seeds use
7317 plus each disease's position in the frozen cohort. Expected answer labels
are used only after retrieval to measure coverage.

| Method | Split | Recovered / expected | Recovery | Mean nodes | Mean connections |
|---|---|---:|---:|---:|---:|
| Gandalf walks | Validation | 1,533 / 2,291 | **66.91%** | 1,737.88 | 2,101.37 |
| ARAGORN rules | Validation | 455 / 2,291 | 19.86% | 91.71 | 217.42 |
| Gandalf walks | Test | 1,564 / 2,293 | **68.21%** | 1,746.14 | 2,112.89 |
| ARAGORN rules | Test | 506 / 2,293 | 22.07% | 99.24 | 236.04 |

Gandalf recovered 1,078 more validation pairs and 1,058 more test pairs in total.
It did not recover every ARAGORN answer:

| Answer overlap | Validation | Test |
|---|---:|---:|
| Both methods | 340 | 376 |
| Gandalf only | 1,193 | 1,188 |
| ARAGORN only | 115 | 130 |
| Neither | 643 | 599 |
| Either method | 1,648 (71.93%) | 1,694 (73.88%) |

The either-method counts are a union of answers from **two separate graphs**,
each capped independently. They do not establish coverage for a merged graph
under one 3,000-connection budget.

There were 1,625,801 completed walks from 1,707,000 attempts. No sampled graph
hit the cap; the largest had 2,922 connections. Sampling and capped union took
38.15 seconds; the full invocation, including preparation and verification, took
132.88 seconds. All saved graphs from both methods were checked against the masked
source, with coverage recomputed and original ARAGORN counts reproduced exactly.

**Interpretation:** walks supply substantially broader answer coverage, but also
much larger contexts. This compares methods under an equal maximum budget, not
equal realized graph size. Other direct evidence remains available under
`treats_only`; these results do not measure recovery without all direct clues.
This is a single-seed retrieval experiment, and ULTRA ranking has not run on these
new graphs. The older 46.32% walk result used different labels and masking and
is not a direct control for this result.

Sources: [comparison protocol and results](../../chemical_retrieval/README.md),
[retained study](../../studies/chemical_walks_treats_only_001_results.json),
[paired answer identities](../../results/chemical_walks_treats_only_001/validation_paired_answers.json).

## 9. Implications for ULTRA and next checks

These retrieval experiments have not produced new ULTRA MRR or Hits@k results.
Full-graph results from other experiments must not be presented as scores for
these retrieved contexts.

Our current interpretation is that ARAGORN-only retrieval supplies limited
coverage after hiding held-out treatment edges. Restricting ranking to returned
candidates makes missing answers unreachable; retaining all candidates as isolated
nodes preserves the evaluation denominator but supplies them no supporting edges.

The next useful checks, not completed work, are:

1. Match the service graph snapshot and execution settings, then inspect the
   specific rule-10 queries and evidence behind the 77 local-only pairs.
2. Trace the constraint warnings through the retriever/backend boundary and
   distinguish rejection, empty matches, and deduplicated evidence per rule.
3. Use the completed walk comparison to develop combined retrieval on validation,
   measuring whether complementary ARAGORN evidence helps under a single shared
   graph budget. Preserve the agreed `treats_only` masking and frozen labels.
4. Evaluate retrieval coverage and ULTRA ranking separately, keeping missed answers
   in the denominator. If training on retrieved contexts, hide the training target
   before retrieval as well as before model scoring.

An earlier validation audit found broader-treatment evidence for 1,647/2,291
expected answers; its union with current retrieval covers 1,651/2,291 (72.06%).
This is **available evidence, not achieved retrieval performance**. A broader
lookup would need to be implemented and measured under its retrieval budget.
See the [evidence audit](../../results/chemical_retrieval_001/validation_evidence_audit.json).

## Reproducibility and retained artifacts

The [experiment README](../README.md) contains commands, limits, and artifact
descriptions. Raw responses, per-rule local results, exact set differences,
support-tracing witnesses, source hashes, and pinned schemas are retained under
`../results/run_001/`. Bulk results are ignored by Git and require the local
workspace or a separately copied artifact bundle.

Response checksums and answer sets were independently verified. Evidence tracing
checks schema imports and expansion behavior before matching. **Eleven tests passed**:
four response/comparison tests and seven evidence-matching tests. The Gandalf
follow-up additionally passed **eight masking, coverage and sampling tests**.
It ran local sampling and verification while reusing the existing ARAGORN graphs;
it did not rerun the service or evaluate a model.
