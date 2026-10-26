# Development: remove tier controls, then explicitly request Tier 1

**Result:** Removing the Tier 0 controls did not broaden retrieval. All ten requests executed on Tier 0 and reproduced the baseline's exact final chemical IDs and all 19 raw callback counts per query. Explicit Tier 1 failed before callbacks for every target; its rule coverage remains unknown.

[Open the executed offline notebook](notebooks/01_development_default_vs_tier1.ipynb).

## Setup

- Endpoint: `https://shepherd.renci.org/aragorn/query` (Development).
- Advertised ARAGORN 2.0.2, TRAPI 2.0.0, Biolink 4.4.4. The release rule files match the previous Development snapshot byte for byte.
- Same ten disease/phenotype IDs and open chemical node as the earlier experiment. Each original edge is `biolink:treats` with `knowledge_type: inferred`.
- Workflow: `aragorn.lookup`. Hosted ARAGORN expands, retrieves and merges; we do not send the eighteen rules separately. No scoring or edge masking.
- Default variant: omit `tier`, `tiers`, and `tier_fallback` entirely.
- Tier 1 variant: `tier: 1`, `tiers: [1]`, `tier_fallback: false`. This prevents an unavailable Tier 1 backend from silently producing a Tier 0 comparison.
- Other parameters held fixed: timeout 120 seconds, DEBUG logs, `bypass_cache: true`. No explicit `dehydrated` parameter.
- Submitter: `aragorn-development-tier-selection-2026-10-20` on every request.
- Twenty sequential outer requests total; 380 downstream lookup dispatches observed. No CI/Test/Production queries, automatic retries or scheduled repetitions.
- UTC interval: 2026-10-20T17:35:07.086647+00:00 through 2026-10-20T17:39:46.794358+00:00.
- Prior comparison: [Development Tier 0 baseline](../../output/run_002/report.json). Internal graph release is unknown; temporal graph stability was not assumed.

## Why omission does not mean all tiers

The [public Development Retriever schema](https://dev.retriever.biothings.io/openapi.json) documents one tier per request, defaulting to Tier 0. `tiers` is deprecated and accepts at most one entry. Fallback selects another available backend when the requested backend is down; it is not triggered by a rejected rule or zero results. The advertised ARAGORN worker also inserts its configured default `tiers` value when absent.

This is verified for the default rerun by **190 Tier 0 execution log messages**, one per observed direct/rule callback. Public Retriever documentation alone does not prove ARAGORN's internal deployment configuration.

## Default rerun results

All ten queries completed with 18 identified rule callbacks plus one direct callback. Final chemical **ID sets**, not just counts, and all raw callback counts match the earlier Development Tier 0 run.

| Query | Target | Baseline chemicals | Default rerun chemicals | Rules returning raw paths |
|---|---|---:|---:|---|
| q01 | pheochromocytoma | 83 | 83 | 6, 10, 15, 18 |
| q02 | cafe au lait spots, multiple | 119 | 119 | 10 |
| q03 | biotinidase deficiency | 2 | 2 | 11 |
| q04 | Fever | 682 | 682 | 6, 11, 14, 15, 17, 18 |
| q05 | Halitosis | 36 | 36 | 11, 17 |
| q06 | COVID-19 | 101 | 101 | 11, 15, 17, 18 |
| q07 | osteoarthritis, hand | 7 | 7 | 11 |
| q08 | liver carcinoma | 482 | 482 | 6, 10, 11, 15, 17, 18 |
| q09 | mycosis fungoides | 28 | 28 | 11, 17 |
| q10 | Endotoxemia | 2 | 2 | None |

Across targets, rules **6, 10, 11, 14, 15, 17, 18** return paths at least once. Rules **1, 2, 3, 4, 5, 7, 8, 9** remain rejected; **12, 13, 16** remain empty for every target. Other positive rules are also empty for some targets.

| Variant | Rule graphs identified in callbacks | Returned | Rejected | Empty | Unknown |
|---|---:|---:|---:|---:|---:|
| default | 180 | 27 | 80 | 73 | 0 |
| tier1 | 0 | 0 | 0 | 0 | 180 |

Counts are rule–query evaluations (10 × 18 per variant), not unique edges or final chemical answers. Direct lookups are excluded.

## Explicit Tier 1: retrieval failures, not empty graph searches

All ten outer requests returned HTTP 200 and status `Completed`, but their logs show **19 failed lookup dispatches per query**, no retrieval callbacks, no logged tier execution, and no final results list. Thus neither rule coverage nor chemical counts are measurable for Tier 1.

Example from the first target, outer job `db7db903`:

```text
INFO [34f64815] Sending lookup query to http://retriever/asyncquery
ERROR [34f64815] Failed to do lookup, removing callback id: None
```

[Exact response and complete logs](output/run_001/tier1/q01/response.json).

The advertised worker records a non-200 downstream response as unsuccessful without retaining its HTTP status or body in this log. `None` is the missing error detail; it is not a statement about graph data. We can observe 19 dispatch attempts per target, but cannot match those failed attempts to individual rule graphs because callback graph logs are absent. The 180 numbered-rule outcomes are therefore **unknown**, with the request-level dispatch failures recorded separately.

The separate [public Development Retriever status](https://dev.retriever.biothings.io/status) reported both Tier 0/Gandalf and Tier 1/Elasticsearch healthy. Its snapshot is [saved here](output/preflight/public-retriever-status.json). ARAGORN calls **`http://retriever/asyncquery`**; we have not established that this is the same deployment as the public endpoint. Public health cannot diagnose the internal failure.

**Conclusion:** Additional rules might match another graph, but these runs do not establish that. Removing tier controls repeats Tier 0 behavior. The next diagnostic is to obtain the internal Retriever's rejected-submission HTTP status/body and verify its Tier 1 backend/configuration, then repeat the explicit Tier 1 comparison once retrieval works.

## Evidence and reproducibility

- [Exact requests, responses and per-query status](output/run_001/)
- [Per-query comparison, including exact-ID equality](output/run_001/comparison.csv)
- [Per-rule outcomes and rejection evidence](output/run_001/rule-outcomes.json)
- [Rule-by-query table](output/run_001/rule-outcomes-by-query.csv)
- [Full callback audit](output/run_001/report.json)
- [Saved service schemas and routing sources](output/preflight/)

From this directory, these commands are **offline**:

```bash
python scripts/run_comparison.py
python scripts/build_notebook.py --execute
```

`--submit` explicitly enables live submissions. Existing submission markers are skipped, including uncertain outcomes; rerunning the saved experiment does not send those twenty requests again. All analysis cells ran successfully. The existing 13 analysis tests passed, and artifact checks verified tier controls, named submitters, callback counts, baseline equality and failure classifications.
