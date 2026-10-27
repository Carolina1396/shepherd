# Ten-disease Shepherd ARAGORN service comparison

Part of [Study 3: Sampling and retrieval](../README.md#study-3-sampling-and-retrieval). Retrieval follow-up.

Read the [consolidated findings report](report/README.md) for the masking and
recovery results, all 18 rules' observed contributions, service comparison,
supporting-graph attribution, and unresolved questions.

This isolated experiment compares exact chemical answer CURIE sets from the actual
Shepherd ARAGORN HTTP service with local native Gandalf execution of ARAGORN rules.
The first run finished all ten queries: **7 exact returned-answer matches, 3 differences**.
All service responses contain a rule-validation error, so none establishes error-free
execution of every rule.

## Protocol

- Ten disease IDs sampled from Experiment 11 validation diseases using seed 7317;
  selection does not depend on answer counts.
- Actual endpoint: `https://shepherd.renci.org/aragorn/query` (development service).
  Workflow is explicitly `aragorn.lookup`, avoiding subsequent scoring and top-500
  filtering. This is a retrieval comparison, not the complete default ranked workflow.
- Request: inferred chemical `biolink:treats` disease, with tier 0, Gandalf,
  `subclass=False`, cache bypass and 120-second timeout requested.
- Local side: the original unmasked `output/gandalf/full-store` graph, no 3,000-edge
  cap, subclass expansion disabled. Direct lookup plus all 18 rule queries are
  executed, then their chemical answer sets are unioned. This controls masking and
  capping differences; it intentionally differs from the earlier held-out evaluation.
- Each local rule has a 120-second deadline, a hard timeout guard and a 4 GiB
  additional virtual-memory guard. All 190 local lookups completed without reported errors.
- All 190 expanded query graphs are identical between the checkout's actual worker
  expansion helpers and the existing local experiment query builder. This does not
  verify the deployed worker's source version.
- Compare exact CURIE sets, ignoring result order and duplicate bindings. No synonym
  normalization. Retain full responses, errors and both directions of set differences.
- The earlier treats-only masked, capped retrieval is retained as a separate reference
  in each query's `baseline_reference.json` and `original_masked_capped_comparison`.

The local graph has 1,670,341 nodes and 28,709,074 evidence records (the latter is
not the count of unique directed connections). Local Biolink is 4.4.2; the service
reports 4.4.4. The remote graph snapshot is unverified, and echoed parameters do
not prove every backend setting was honored. These limits prevent interpreting
differences as demonstrated implementation defects.

## First run

| Disease | Local answers | Service answers | Local only | Service only | Exact set match |
|---|---:|---:|---:|---:|---|
| MONDO:0004277 | 36 | 36 | 0 | 0 | Yes |
| MONDO:0004995 | 346 | 325 | 21 | 0 | No |
| MONDO:0005087 | 4 | 4 | 0 | 0 | Yes |
| MONDO:0005480 | 105 | 76 | 29 | 0 | No |
| MONDO:0005885 | 145 | 118 | 27 | 0 | No |
| MONDO:0008399 | 6 | 6 | 0 | 0 | Yes |
| MONDO:0009662 | 1 | 1 | 0 | 0 | Yes |
| MONDO:0017278 | 5 | 5 | 0 | 0 | Yes |
| UMLS:C0474013 | 2 | 2 | 0 | 0 | Yes |
| UMLS:C3163829 | 6 | 6 | 0 | 0 | Yes |

All 77 local-only disease–chemical pairs are produced exclusively by **rule ID 10**
(zero-based, the eleventh template). Its pattern is:

```text
intermediate chemical --treats--> disease
biological entity --affects [decreased activity_or_abundance]--> answer chemical
biological entity --affects [decreased activity_or_abundance]--> intermediate chemical
```

Every service response logs rejection of `biolink:affects_response_to`, used by
rule ID 0. Local rule 0 returns no matches. The service still returns answers from
other rules with HTTP 200. `UMLS:C3163829` also logs a backend `httpx.ReadError`;
its observed answer set nevertheless matches. These errors are saved rather than
treated as successful empty rule results. The next diagnostic target is rule 10:
compare its backend query behavior, qualified edges and Biolink expansion against
the same graph snapshot. The present experiment does not establish a root cause.

## Run and inspect

From the repository root:

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover -s experiments/ultra/pilot/aragorn_service_parity -p 'test_*.py'
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/aragorn_service_parity/run.py --phase all
experiments/ultra/.venv/bin/python -B experiments/ultra/pilot/aragorn_service_parity/analyze.py
```

Use `--output /path/to/new/run` for a fresh run and `--endpoint URL` to choose
another deployment. Pass the same output to `analyze.py`. Existing records are
reused, including service responses with errors; a fresh output is required to retry.
Source/configuration hashes are checked on resume, so changed runner sources also
require a fresh output. The cohort remains fixed across deployments.

Artifacts are under `results/run_001/` (ignored by Git):

- `settings.json`, `local_graph.json`, `service_info.json`, `service_openapi.json`:
  configuration, hashes and reported versions.
- `expansion_parity.json`: checkout worker/local query-expansion agreement.
- `observed_comparison.json`, `per_query.csv`: verified returned-answer comparisons.
- `00/` through `09/`: exact requests, expansions, local rule responses, full service
  response and logs, answer lists, and `observed_comparison.json` with differing IDs
  and local rule attribution.
- `comparison.json`, `status.json`: the runner's stricter completeness check. These
  mark this run partial because of service errors; their zero accepted exact matches
  must not be confused with the seven observed returned-answer matches above.
- `source/`: source snapshot and file hashes retained after the completed run.

`analyze.py` verifies response checksums, re-extracts answer IDs from every saved raw
response and checks them against recorded answers before comparing sets. All ten
response pairs passed this verification. Four helper tests cover binding formats,
malformed responses, exact-set differences and timeout diagnostics.

## Reconstructing rules from service supporting graphs

`trace_support.py` follows each returned answer's analysis edge bindings, then
the inferred edge's `biolink:support_graphs` attribute, then the referenced
auxiliary graph's evidence edges. It compares that evidence with all 18 saved
expanded templates. This uses the existing responses; it submits no new service
queries and does not modify the original experiment.

Across the ten responses there are **579 disease–chemical answer pairs**:
151 have only direct evidence, 393 only inferred support, and 35 both. The 428
pairs with inferred support have **651 support graphs**. Every one matches
exactly one template when categories, predicates, directions, and qualifiers
are checked. There are no unmatched or ambiguous support graphs.

| Compatible rule ID (zero-based) | Supporting graphs | Distinct answer pairs supported |
|---|---:|---:|
| 5 | 489 | 288 |
| 10 | 14 | 12 |
| 16 | 148 | 143 |

Answer-pair counts overlap across rules. The other 15 templates have no compatible
support graphs in these ten saved responses. This does **not** show that those
rules were skipped: empty results, errors, and evidence deduplication can leave
no final support graph. The service merger deduplicates equivalent evidence sets
and does not preserve the originating rule ID.

For a concrete rule-10 example, the service returns nitric oxide (`CHEBI:16480`)
for cardiovascular disorder (`MONDO:0004995`) with this saved supporting pattern:

```text
MAPK8 (NCBIGene:5599) --affects [decreased activity]--> nitric oxide (CHEBI:16480)
MAPK8 (NCBIGene:5599) --affects [decreased activity]--> insulin human (CHEBI:5931)
insulin human (CHEBI:5931) --treats--> cardiovascular disorder (MONDO:0004995)
```

The support graph is `56caa5c0-79a2-4816-9f7b-1be18a547f3c`, in query `01`.
`activity` is accepted under rule 10's broader `activity_or_abundance` qualifier.
These are assertions in the returned graph, not an independent validation of
their biological interpretation. This evidence is compatible with rule 10; the
original generating rule remains inferred from the pattern rather than reported
by the service.

The audit runs with pinned Biolink 4.4.2 and 4.4.4 and obtains identical rule
assignments. It uses native Gandalf predicate/qualifier expansion, including
predicate descendants and valid symmetric/inverse traversal, and literal category
membership in the returned ancestor-inclusive categories. Answer and disease IDs
are pinned exactly. A full match requires every support edge to participate in
at least one complete, consistent template binding; merged parallel evidence is
allowed. Partial matches and matches without qualifier checks are saved separately.
Without qualifiers, all 162 affect-based support graphs are ambiguous among
rules 10, 11, 12, 14, 15, 16 and 17. Qualifiers resolve those ambiguities.

The `skipping unknown fields (constraints)` service warnings remain a concern,
but these returned evidence graphs do satisfy the reconstructed rules' qualifiers.
The warnings alone do not establish that qualifiers were lost at the final backend.
Matching the evidence cannot reveal whether the original query enforced them.

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/aragorn_service_parity/trace_support.py
```

Results are in `results/run_001/support_trace/`: `summary.json`, `answer_rules.csv`,
`examples.json`, and `00.json` through `09.json` with exact evidence IDs, compact
nodes/edges and matching witnesses. Compiled rules, complete pinned schema files,
source snapshots and hashes are retained. Schema imports and representative
predicate/qualifier expansions are checked before analysis to prevent silent
fallback to literal matching. The matcher has seven targeted tests in addition
to the four original comparison tests.
