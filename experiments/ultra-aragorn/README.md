# ULTRA ranking of Shepherd ARAGORN retrieval

## Objective and status

Use Shepherd's existing ARAGORN retrieval service to obtain candidate answers
and supporting evidence, then rank those candidates locally with pretrained
ULTRA. The first experiment covers the 48 treatment questions recovered from
`hyi/ranker`'s results workbook.

**Status: all 48 treatment queries processed.** Both scorers completed for **45
queries**, covering **16,519 query–candidate pairs**. Queries **28, 35, and 64**
returned no candidates; no failed stages remain. Query 0 reuses its previously
verified development retrieval and CI scores; the other 47 queries used CI
retrieval. All ARAGORN scoring used CI. Conflicting and unresolved labels remain
flagged, as agreed.

### Full cohort results

[Summary](reports/cohort_001/summary.json) ·
[All candidate scores and ranks](reports/cohort_001/comparison.csv) ·
[Expected-answer matches and flags](reports/cohort_001/label_matches.json) ·
[Per-query details, including empty responses](reports/cohort_001/per_query.json) ·
[Verification and artifact hashes](reports/cohort_001/verification.json)

| Matched-query metric | ARAGORN CI | ULTRA 4g |
|---|---:|---:|
| Answer-level MRR | 0.1635 | 0.1354 |
| Conditional answer MRR (retrieved positives only) | 0.2288 | 0.1895 |
| Query-macro answer MRR | 0.1858 | 0.1803 |
| TopAnswer recall@5 | 12/42 (28.6%) | 10/42 (23.8%) |
| TopAnswer recall@10 | 14/42 (33.3%) | 13/42 (31.0%) |
| TopAnswer recall@20 | 18/42 (42.9%) | 17/42 (40.5%) |
| NeverShow labels in top 10 | 2 | 4 |

These metrics cover **42 eligible TopAnswer labels across 16 matched queries**.
Both scorers receive the same candidates: 30 of those 42 positives were retrieved
(71.4% coverage); the other 12 contribute zero reciprocal rank. The 45 matched
queries contain 323 grouped labels, of which 23 stay flagged (17 source-label
issues and six name/identity mismatches). Queries without eligible positives,
including query 0, have undefined individual MRR. Empty queries are excluded from
this matched-ranking table; query 28 has one prepared TopAnswer label, so these
numbers must not be presented as end-to-end metrics over all 48 queries.

ARAGORN has higher aggregate answer MRR in this run. This is a descriptive result
on a small eligible benchmark, not a significance claim. It compares complete
scoring approaches on matched candidates: ARAGORN adds OmniCorp evidence, whereas
ULTRA uses predicate-only retrieved evidence with synthetic conclusions removed.
The live graph retains direct treatment evidence. All 45 matched retrievals
contain service warnings/errors; complete references and successful scoring do
not prove every internal retrieval rule succeeded.

Candidate counts range from 1 to 4,019 per nonempty query, without top-k truncation.
The initial CPU toolchain failure affected five local scoring attempts; forcing
CPU-only extension compilation fixed it, and all five resumed from cached graphs.
Original failure logs and the settings revision remain saved. Fifteen regression
tests passed, and independent checks verified all 45 comparisons' source hashes,
finite scores, pessimistic ranks, normalized-label uniqueness, and aggregate MRR.
Full raw graphs remain in ignored `results/`; compact reports are retained here.

### Top-10 correct-answer overlap

The two systems recover different subsets of the **42 eligible TopAnswers**.
Each count below represents a query–normalized-answer pair, using the existing
pessimistic ranks and excluding flagged labels. “Both” means the answer appears
somewhere in each system's top 10, **not necessarily at the same rank**.

| Top-10 membership | TopAnswers | Interpretation |
|---|---:|---|
| Both systems | 10 | Both rank the answer at 10 or better. |
| ARAGORN only | 4 | ARAGORN ranks it at 10 or better; ULTRA ranks it below 10. |
| ULTRA only | 3 | ULTRA ranks it at 10 or better; ARAGORN ranks it below 10. |
| Neither | 25 | Neither puts it in the top 10: 13 rank below 10 in both, and 12 are absent from the shared retrieved candidates. |

Thus ARAGORN gets **10 + 4 = 14**, ULTRA gets **10 + 3 = 13**, and the union
contains **17/42 (40.5%)** correct query–answer pairs. ULTRA contributes three
additional hits over ARAGORN's **14/42 (33.3%)**, a 21.4% relative increase in
hits. The seven disagreements are:

| Query | TopAnswer | ARAGORN rank | ULTRA rank |
|---|---|---:|---:|
| 006 | Fingolimod | 44 | **6** |
| 020 | Rosuvastatin | 65 | **2** |
| 060 | Fluticasone | 73 | **2** |
| 017 | Rabeprazole | **3** | 83 |
| 020 | Lomitapide | **6** | 11 |
| 024 | Insulin detemir | **3** | 217 |
| 061 | Estradiol | **2** | 12 |

This shows complementary correct hits on this cohort and supports testing a
combined ranking. ULTRA's unique hits come from deep in ARAGORN's ranking,
rather than just across the cutoff. It does not establish that a combined
**top 10** would improve: the union can contain more than ten candidates per
query, and a fusion method must retain those complementary hits. Combining
rankers also cannot recover the 12 positives missing from retrieval.

Source: [expected-answer matches and ranks](reports/cohort_001/label_matches.json),
cross-checked against [candidate ranks](reports/cohort_001/comparison.csv).

### Running the full treatment cohort

From a fresh clone, use Linux, Python 3.11, and a working C++ compiler (for
ULTRA's native extension). Run these commands from the repository root; skip
cloning or creating environments that already exist:

```bash
mkdir -p experiments/ultra/vendor
git clone https://github.com/DeepGraphLearning/ULTRA.git experiments/ultra/vendor/ULTRA
git -C experiments/ultra/vendor/ULTRA checkout --detach 427966ad8ed60420eef034063d44f3153addff90
python3.11 -m venv experiments/ultra/.venv-model
experiments/ultra/.venv-model/bin/python -m pip install torch==2.1.0 --index-url https://download.pytorch.org/whl/cpu
experiments/ultra/.venv-model/bin/python -m pip install -r experiments/ultra/requirements-model.txt torch-scatter==2.1.2 -f https://data.pyg.org/whl/torch-2.1.0+cpu.html
```

The pinned upstream checkout includes `ckpts/ultra_4g.pth`; the scorer verifies
its SHA-256 before loading. This experiment uses hosted retrieval, so it does
not require the full Tier 0 archive or a local Gandalf store. Benchmark labels,
prepared queries, and frozen preparation normalization are committed here.

Run the offline regression checks, then start a one-query live smoke run:

```bash
experiments/ultra/.venv-model/bin/python -m unittest discover -s experiments/ultra-aragorn/scripts -p 'test_*.py' -v
experiments/ultra/.venv-model/bin/python -B -u experiments/ultra-aragorn/scripts/run_cohort.py --output experiments/ultra-aragorn/results/cohort_new --max-new 1
```

The live run sends requests to Shepherd CI and Node Normalizer and requires
network access to both services. Resume the same output to process the remaining
queries:

```bash
experiments/ultra/.venv-model/bin/python -B -u experiments/ultra-aragorn/scripts/run_cohort.py --output experiments/ultra-aragorn/results/cohort_new
```

The runner processes the 48 prepared treatment queries sequentially and resumes
cached work. It uses the current Python interpreter for model scoring by default;
`--model-python /path/to/python` selects another environment. Query 0 is retrieved
normally on a fresh run. The optional `--reuse-query0` flag requires the historical
local `results/smoke_002/` artifacts and reproduces the original run's exception.
Each new query uses CI retrieval, then submits that exact cached
message to CI with only `aragorn.omnicorp` and `aragorn.score`, using the verified
legacy binding format. ULTRA scores the converted retrieval graph locally on CPU
with the frozen 4g checkpoint. Neither scoring path uses benchmark labels.

Per-query requests, responses, hashes, logs, normalization results, and comparisons
are under `results/cohort_001/query_NNN/`. The runner records at most two attempts
per hosted stage, retains failed requests, and skips completed or empty queries
on resume. Its `summary.json`, `comparison.csv`, and `label_matches.json` aggregate
completed comparisons. Empty retrievals and failed stages remain explicit; their
queries are excluded from the matched-ranking metric denominator.

The committed reports preserve the original results, but the full raw retrieval
cache is not committed. A fresh live run can differ as hosted graphs and services
change. Use a new output directory after code or settings changes; historical
`cohort_001` settings intentionally will not match the updated runner.

Answer MRR averages reciprocal rank over eligible **TopAnswer labels**, assigning
zero to eligible answers missing from a matched query's candidates. It is not the
usual first-relevant-answer MRR per query. Conditional answer MRR includes only
retrieved positives; query-macro answer MRR first averages labels within each query.
All metrics retain pessimistic ties and exclude flagged labels. The historical
`hyi/ranker` results are context, not a matched baseline.

### Query 0 retrieval check

The retrieval-only request returned HTTP 200 in 39.56 seconds: **25 candidates,
30 nodes, 113 edges, and 34 auxiliary graphs**. All bound nodes, bound edges,
edge endpoints, and support-graph references exist. The response uses TRAPI
**2.0.0** (`{"ids": [...]}` bindings) and Biolink **4.4.4**.

There are 25 edges carrying support-graph references and three bound edges
without such references. These are edge counts, not disjoint candidate counts.
The response contains two error log entries for one invalid
`biolink:affects_response_to` rule query and seven warnings about missing
MetaEdges. HTTP success therefore does not mean every rule succeeded.

Sirolimus appears by name as `CHEBI:9168`, but this ID does not match the frozen
expected-answer alias set. Joint normalization confirmed the identity mismatch described below; the label
remains flagged and no name-only match is counted.

See [the compact retrieval report](reports/query_0_retrieval.json). Full request,
response, timestamps, hashes, and inspection are cached locally in
`results/smoke_002/`. `smoke_001` records a sandbox DNS failure before the
successful submission. Only one request reached the hosted service.

Inspect the cached response without another service request:

```bash
python experiments/ultra-aragorn/scripts/retrieve.py --qid 0 --output experiments/ultra-aragorn/results/smoke_002
```

For a new request, choose a fresh output directory and add `--send`. The runner
does not automatically retry submitted requests; failed attempts remain saved.
### Query 0 graph conversion

[convert_graph.py](scripts/convert_graph.py) converts the cached response without
reading benchmark labels or making service requests. It preserves all 30 nodes
and 25 returned candidate IDs. These are CURIE-level model inputs; the subsequent comparison normalizes
candidate aliases consistently for both rankers.

| Conversion | Count |
|---|---:|
| Generated conclusion edges removed | 25 |
| Evidence records retained | 88 |
| Unique directed evidence triples | 80 |
| Model edges including inverses | 160 |
| Predicates / relations including inverses | 7 / 14 |
| Isolated candidates | 0 |
| Candidates with retained direct `treats` evidence | 2 |

Support-graph conclusions and edges explicitly marked `logical_entailment` are
excluded, including nested conclusions. Their underlying evidence is retained.
A genuine evidence edge is retained even when its triple matches a removed
conclusion. All 113 source edges are accounted for as retained or removed, and
deduplicated triples retain their original edge IDs in `triple_provenance.json`.
Eight retained records have qualifiers; the predicate-only model representation
does not encode those qualifiers. Original TRAPI remains cached.

Arrays and mappings are saved in `results/smoke_002/ultra_input/`:
`triples.npy` uses `[head, relation, tail]`; `edge_index.npy` and `edge_type.npy`
include inverses. `config.json` identifies the disease and target relation.
`nodes.json`, `predicates.json`, and `candidates.json` provide index mappings.
`removed_edges.json` records exclusion reasons. Conversion refuses incomplete
references, changed source hashes, and ambiguous disease identity.

Reproduce into a fresh output directory:

```bash
python experiments/ultra-aragorn/scripts/convert_graph.py --retrieval experiments/ultra-aragorn/results/smoke_002 --output experiments/ultra-aragorn/results/smoke_002/ultra_input_new
python -m unittest discover -s experiments/ultra-aragorn/scripts -p test_convert_graph.py -v
```

[Conversion and verification report](reports/query_0_conversion.json): four
conversion regression tests passed. Independent checks verified source-edge
accounting, triple provenance, inverse arrays, and artifact hashes. The existing
ULTRA environment successfully built the relation graph on CPU (14 relation
nodes, 312 relation-graph edges).

### Query 0 ULTRA scoring

[score_ultra.py](scripts/score_ultra.py) loaded the original pretrained 4g
checkpoint with a strict state-dict match and verified its SHA-256 against the
existing ULTRA baseline. It scored all **25 returned CURIE candidates** on CPU
without training. All scores are finite. Reversing candidate order preserved
entity scores, and pessimistic ranks were independently recomputed from the
saved CSV. Model inputs and checkpoint hashes are recorded in the
[scoring report](reports/query_0_ultra_scoring.json).

The returned node **Sirolimus (`CHEBI:9168`) ranks 1**, followed by
**Everolimus (`CHEBI:68478`) at rank 2**. See the
[complete ranking](reports/query_0_ultra_ranking.csv). Scores are uncalibrated
model outputs, not probabilities. Sirolimus retains direct treatment evidence;
this is not a masked treatment-discovery result. The subsequent comparison normalizes candidate aliases. The benchmark's
Sirolimus identifier remains flagged because joint normalization did not equate it
with the returned identifier.

The run took 29.16 seconds including loading and verification; the first forward
pass took 26.19 seconds **including lazy CPU extension compilation**. These
timings are not steady-state inference measurements. CPU was sufficient for
this small graph; the GPU driver was inaccessible in the execution environment.

Reproduce with the existing ULTRA environment and a fresh output directory:

```bash
experiments/ultra/.venv-model-gpu/bin/python -B -u experiments/ultra-aragorn/scripts/score_ultra.py --dataset experiments/ultra-aragorn/results/smoke_002/ultra_input --output experiments/ultra-aragorn/results/smoke_002/ultra_scores_new --device cpu
```

No additional Shepherd requests were needed for conversion or scoring.

### Matched ARAGORN versus ULTRA comparison

The comparison uses exactly the cached retrieval response as the starting point
for both scorers. [score_aragorn.py](scripts/score_aragorn.py) submits its complete
TRAPI message to the same Shepherd endpoint with only `aragorn.omnicorp` and
`aragorn.score`. It does not retrieve again, truncate results, or sort remotely.
It preserves TRAPI schema metadata and checks that returned candidate IDs match.
The standard ARAGORN workflow adds literature evidence via OmniCorp; ULTRA uses
the converted predicate-only graph. This compares complete scoring approaches
on matched retrieval, not identical feature inputs.

Two hosted attempts returned HTTP 503 with:

> Unable to accept query: failed to persist initial query state (datastore unavailable). Please retry shortly.

The earlier sandbox DNS failure and both rejected service attempts are retained
in [scoring_attempts.json](reports/query_0_matched_comparison/scoring_attempts.json).
Those attempts produced no scores; the earlier pending comparison report retains
empty ARAGORN columns. The subsequent CI comparison below supersedes that status.

A subsequent [default-workflow check](reports/query_0_default_workflow_attempt.json)
submitted the original query with `workflow` omitted, asking Shepherd to perform
its normal retrieval and ranking. This also returned HTTP 503 with the same
intake error. Thus the failure is not specific to the cached graph or custom
scoring workflow. The underlying server exception is still unknown; the public
error alone does not establish that the ranking worker itself is broken.

[compare_rankers.py](scripts/compare_rankers.py) applies the same rules to both:

- Match candidate identity using cached Node Normalizer results, preserving
  unresolved IDs and flagging uncertain labels.
- For multiple ARAGORN analyses or equivalent candidate IDs, use the maximum
  score per identity; use that aggregation for both scorers.
- Rank full-precision scores with pessimistic ties, without filtering known
  positive answers out of the candidate pool.
- Calculate answer-level MRR and TopAnswer recall at 1/5/10/20, with zero credit
  for missing eligible positives; report conditional MRR separately.
- Report NeverShow exposure separately. Conflicting or ambiguous labels stay
  flagged and are excluded from metrics with explicit denominator counts.

Fresh joint normalization of query 0's candidates and labels resolves all 25
candidate IDs but does not merge any of them. Crucially, `CHEBI:9168` and the
benchmark's `PUBCHEM.COMPOUND:5284616` both have the name Sirolimus but are in
different normalizer groups, with different InChIKeys. The label remains
flagged, without a name-based override. Query 0 therefore currently has **zero
eligible TopAnswer labels and undefined MRR**, not MRR=1 or MRR=0.

See the [pending comparison summary](reports/query_0_matched_comparison/summary.json),
[candidate ranking table](reports/query_0_matched_comparison/comparison.csv), and
[label matches](reports/query_0_matched_comparison/label_matches.json). Three
regression tests cover alias aggregation, pessimistic ties, absent positives,
flagged-label exclusion, and missing ARAGORN scores.

### Successful CI scoring comparison

CI (`https://shepherd.ci.transltr.io/aragorn/query`) accepted the cached graph.
The initial version-preserving TRAPI 2.0 request returned HTTP 200 but **zero
scored results**. A compatibility request using legacy binding lists and omitting
top-level version metadata returned **25 finite scores for the same 25 candidates**.
That request also enabled DEBUG logging, so the exact cause was not isolated
to one changed field. Original knowledge graph, auxiliary graphs, query graph,
and binding identities were verified unchanged in the submitted message.

The successful workflow was still only `aragorn.omnicorp` → `aragorn.score`:
no new retrieval or top-k truncation. CI added 29 literature co-occurrence edges,
retained all original triples, and returned no missing graph references or
warning/error logs. ULTRA's cached scores were reused.

| Returned candidate | ULTRA rank | ARAGORN CI rank |
|---|---:|---:|
| Sirolimus (`CHEBI:9168`) | 1 | 1 |
| Everolimus | 2 | 4 |
| Phosphatidylinositol | 25 | 2 |
| D-glucose | 25 | 3 |

Both columns use unrounded scores and pessimistic ties. Raw ARAGORN and ULTRA
scores are on different scales and should not be compared numerically.
The Sirolimus benchmark identity mismatch remains flagged, so **MRR remains
undefined for query 0**; matching ranks do not resolve the label issue.

- [Full matched ranking](reports/query_0_matched_ci/comparison.csv)
- [Comparison summary](reports/query_0_matched_ci/summary.json)
- [Evidence preservation and CI request verification](reports/query_0_matched_ci/service_verification.json)
- [Label matches and flags](reports/query_0_matched_ci/label_matches.json)

Reproduce the successful CI format using a fresh output directory:

```bash
python experiments/ultra-aragorn/scripts/score_aragorn.py --retrieval experiments/ultra-aragorn/results/smoke_002 --output experiments/ultra-aragorn/results/smoke_002/aragorn_ci_retry --endpoint https://shepherd.ci.transltr.io/aragorn/query --legacy-bindings --send
python experiments/ultra-aragorn/scripts/compare_rankers.py --retrieval experiments/ultra-aragorn/results/smoke_002 --ultra experiments/ultra-aragorn/results/smoke_002/ultra_scores --normalization experiments/ultra-aragorn/reports/query_0_matched_comparison/normalization_response.json --aragorn experiments/ultra-aragorn/results/smoke_002/aragorn_ci_retry --output experiments/ultra-aragorn/reports/query_0_matched_ci_retry
```

### Historical context from hyi/ranker

[Retained historical metrics and pinned source links](reports/hyi_historical_context.json)
come from the repository's ARS workbook analysis. Its all-edge report gives
TopAnswer recall@10 of **81.69% for ARAGORN** and **75.70% for ARAX**, using
284 positive edge rows. It does not report MRR. These are contextual numbers:
the retrieval sources, cohort, edge-row counting, rounded scores, and optimistic
ties differ from our protocol. They must not be treated as a matched baseline
for ULTRA or copied into the new comparison's metric table.

Prepared artifacts are in [prepared/](prepared/):

- [queries.json](prepared/queries.json): 48 retrieval-only requests ready for Shepherd.
- [expected_answers.json](prepared/expected_answers.json): 334 answer groups from
  348 source records, retaining all source asset IDs; malformed identifiers remain
  separate rather than merging unrelated answers.
- [report.json](prepared/report.json): checksums, correction, counts, and limitations.
- [conflicts.json](prepared/conflicts.json): six groups with contradictory source
  labels; no label was selected automatically.
- [unresolved_answers.json](prepared/unresolved_answers.json): 12 answer records
  requiring identifier review, including incomplete PubChem IDs.
- [identities.json](prepared/identities.json): preferred IDs, aliases, and resolution status.
- [normalization_cache.json](prepared/normalization_cache.json) and
  [raw response](prepared/normalization_response.json): frozen normalization provenance.

The old `hyi` CI normalization endpoint returned HTTP 404. Preparation used
`https://nodenormalization-sri.renci.org/get_normalized_nodes` with the same
`conflate=true` and `drug_chemical_conflate=true` options. Six of 317 requested
identifiers were unresolved, including disease `MONDO:0800029` (qid 28).
Disease IDs in submitted questions remain unchanged. Conflicts and unresolved
labels must be reviewed before aggregate evaluation; preparation made no
Shepherd retrieval requests and does not claim the labels are fully resolved.

Rebuild from the frozen normalization cache and run regression checks:

```bash
python experiments/ultra-aragorn/scripts/prepare_inputs.py
python -m unittest discover -s experiments/ultra-aragorn/scripts -p test_prepare_inputs.py -v
```

Use `--fetch` only when the normalization cache is absent. Existing cache inputs
and response hashes must match; normal reruns make no network requests.

```text
48 treatment questions
    → Shepherd aragorn.lookup
    → cache candidate bindings and complete supporting graphs
    → convert evidence graph to ULTRA input
    → score retrieved candidates with pretrained ULTRA
    → evaluate against benchmark labels
```

## Questions and expected answers

[queries/hyi_all.json](queries/hyi_all.json) contains 85 requests extracted from
the `input_query` sheet of
[`hyi/ranker`'s ARS workbook](https://github.com/hyi/ranker/blob/c245eaa8778c06879c59e9a0c90e63e48cd5fa75/results/ars/ranker_comparison_test_queries.xlsx).
We retain the original `qid` values and request bodies, with the source commit
and workbook checksum. The first run uses
[queries/hyi_treats.json](queries/hyi_treats.json): **48 `biolink:treats`
questions, each anchored on a Disease**. The other 37 `biolink:affects`
questions are outside this first run; their direction and qualifiers require
separate conversion and evaluation decisions.

The treatment requests ask for ChemicalEntity answers, except source
request **qid=25** with a null answer category. Preflight must identify that request and
record an explicit correction to `biolink:ChemicalEntity` in the submitted copy;
the extracted source file remains unchanged. Report the correction with results.

Expected answers come from
[`TranslatorSRI/Tests`' Sprint 6 suite](https://github.com/TranslatorSRI/Tests/blob/90d4c7b497427850665971d9fad62d3fdbdc178f/test_suites/sprint_6_tests.json),
the suite filename referenced by `hyi/ranker`'s query generator. We checked
query order, predicates, categories, and qualifiers. All treatment input IDs
match. One input ID in the deferred `affects` set differs and remains flagged.
The exact historical suite revision used by `hyi` is not confirmed.

| Treatment label | Intended interpretation | Source asset records |
|---|---|---:|
| `TopAnswer` | Desirable answer that should rank highly | 47 |
| `Acceptable` | Acceptable answer; report separately | 36 |
| `BadButForgivable` | Undesirable answer; report separately | 13 |
| `NeverShow` | Answer that should not be returned | 252 |
| Total | | 348 |

These are asset records, not necessarily distinct answers: nine records repeat
a query/output-ID/label combination even before identifier normalization.
Only **19 of the 48 treatment questions have a `TopAnswer` asset**.
The labels are benchmark judgments, not an exhaustive list of treatments or
independent evidence of clinical efficacy. Unlabeled candidates are unknown,
not negative examples.

For example, the suite labels Sirolimus `TopAnswer`, Ridaforolimus `Acceptable`,
and ESTROSTEP Fe `NeverShow` for lymphangioleiomyomatosis (`qid=0`).

Available label files:

- [Original suite](labels/sprint_6_tests.json)
- [Treatment answer records](labels/expected_answers_treats.csv)
- [All answer records](labels/expected_answers_all.csv)
- [Provenance and matching checks](labels/provenance.json)
- [Extraction script](scripts/extract_expected_answers.py)

Rebuild the CSV files and provenance locally from the saved suite:

```bash
python experiments/ultra-aragorn/scripts/extract_expected_answers.py
```

## How ARAGORN will be used

Submit each question to **`https://shepherd.renci.org/aragorn/query`**, the
endpoint used by
[`hyi/ranker/run_pipeline.py`](https://github.com/hyi/ranker/blob/c245eaa8778c06879c59e9a0c90e63e48cd5fa75/run_pipeline.py).
Keep the inferred query and `parameters.gandalf: true`, and explicitly set:

```json
{
  "workflow": [{"id": "aragorn.lookup"}]
}
```

This workflow is added to the existing request containing `message.query_graph`.
Shepherd expands the inferred question using its ARAGORN rules, executes the
graph lookups, and assembles the returned answers and supporting evidence.
Its retrieval includes the direct lookup as well as applicable rule expansions.
We use that deployed behavior rather than implementing a local rule executor.

The request omits `aragorn.omnicorp` and `aragorn.score`. ULTRA supplies the
ranking stage. There is one initial retrieval submission per question: **48
submissions** for the full cohort, excluding retries and internal rule lookups.
The first run is sequential, starting with one smoke-test request, and reuses
the cached successful response when continuing the cohort.

Save exact submitted requests, raw responses, timestamps, endpoint, parameters,
HTTP status, service logs, response hashes, and any exposed graph/version
metadata. Use explicit timeouts and bounded retries; report failed, empty, and
partial responses individually. Do not silently omit them from evaluation.
Cache successful responses so model comparisons use the same retrieved data.
The hostname alone does not establish whether this deployment is dev, test,
or production, nor which graph release it serves.

## How ULTRA will be used

1. **Select candidates from answer bindings.** Use the unpinned query node's
   `node_bindings`; intermediate chemicals in supporting paths are not extra
   candidates. Deduplicate equivalent answer entities after normalization.
2. **Preserve evidence.** Retain the returned knowledge graph and resolve
   auxiliary/support graph references, including nested references. Check that
   referenced nodes and edges exist. Preserve originals for audit.
3. **Remove generated conclusions from model context.** Exclude synthetic
   inferred answer edges carrying support graphs, while retaining their
   underlying evidence paths. Keep genuine direct lookup evidence and flag
   direct versus inferred support separately. Never inject expected answers
   or benchmark labels into retrieval or model inputs.
4. **Convert the graph.** Map entity IDs to local indices and predicates to
   relation IDs, deduplicate triples, add inverse relations, and rebuild
   ULTRA's relation graph. Keep every retrieved candidate, even if isolated
   after conversion. The initial representation uses predicate-only triples;
   qualifiers and provenance remain in the saved TRAPI but are not model
   features. Report that limitation and unsupported/empty graph cases.
5. **Score locally.** Reuse the pretrained ULTRA 4g checkpoint and model-loading
   approach from `../ultra`. Record checkpoint hash, vendor commit, device,
   software versions, runtime, and graph sizes. No fine-tuning in the first run.
   Score `(candidate, biolink:treats, disease)` for all retrieved candidates
   using the retrieved evidence graph, not the full Tier 0 graph.
6. **Save rankings.** Retain raw scores and candidate identifiers; rank higher
   scores first with pessimistic ties. Scores are not calibrated probabilities.

This evaluates ranking after live retrieval. It is **not** a held-out-edge
recovery experiment: direct treatment evidence may already exist in the hosted
graph. Report direct-supported and inferred-only candidates separately, and
do not compare these metrics directly with the masked full-graph ULTRA studies.

## Evaluation

Normalize expected-answer and returned-candidate IDs using the same recorded
Node Normalizer configuration, caching the mappings. Preserve source IDs and
asset IDs. Deduplicate query/normalized-answer labels, flag conflicts, and
report normalization failures rather than treating them as missing answers.
Freeze the resolved label table before computing ranking metrics.

Report two separate stages:

| Stage | Measures |
|---|---|
| Retrieval | Expected labeled answers present among returned candidates; coverage by label; failures, empty responses, candidate counts, and evidence sizes |
| ULTRA ranking | `TopAnswer` Hits/Recall@1, @5, @10, @20 and reciprocal ranks; `NeverShow` counts/rates in the same windows; separate results for the other labels |

Define denominators explicitly. Primary positive recovery uses all deduplicated
`TopAnswer` labels, including those not retrieved (zero hits and reciprocal
rank zero). Also report ranking conditional on retrieval, clearly labeled.
Compute macro positive metrics only over queries with positive labels, alongside
pooled answer metrics. Queries without positives still contribute negative-label
and operational diagnostics. Report service failures separately from successful
queries with zero coverage. Do not filter other positive candidates out of the
ranking: this evaluates a returned answer list, rather than filtered KG ranks.

The first experiment evaluates ULTRA alone. A later controlled comparison may
send the **same cached retrieval responses** to ARAGORN's scorer. Historical
`hyi` scores are context, not a matched baseline against a new live retrieval.

## Execution milestones and outputs

1. Validate all 48 requests, record the null-category correction, and resolve
   benchmark identifiers and duplicate/conflicting labels.
2. Implement one-query retrieval and verify the real response's bindings and
   support-graph structure before completing the cached retrieval cohort.
3. Implement and test TRAPI conversion and ULTRA scoring, including synthetic
   edge exclusion, inverse edges, isolated candidates, and missing evidence.
4. Run the frozen cohort, independently recompute ranks from saved scores,
   and produce per-query and aggregate evaluation reports.

Planned `results/<run_id>/` artifacts: run settings, submitted queries, raw TRAPI
responses, normalization mappings, converted model inputs, candidate scores,
ranked answers, label matches, failure diagnostics, and aggregate metrics.
Large raw outputs should be ignored by Git; retain code, source inputs,
provenance, and compact reports. No service requests are made by the extraction
script above.

## Treatment query inventory

The following table retains the workbook query IDs. Names come from the source
test assets; the saved query bodies are authoritative for submission.

| qid | Disease ID | Source disease name |
|---:|---|---|
| 0 | MONDO:0011705 | Lymphangioleiomyomatosis |
| 1 | MONDO:0016063 | Cowden Disease |
| 3 | MONDO:0018493 | Malignant Hyperthermia Of Anesthesia |
| 6 | MONDO:0005301 | Multiple Sclerosis |
| 10 | MONDO:0010808 | Fatal familial insomnia |
| 12 | MONDO:0001505 | alcoholic hepatitis |
| 14 | MONDO:0011426 | Aceruloplasminemia |
| 16 | MONDO:0018911 | Maturity-onset Diabetes Of The Young |
| 17 | MONDO:0007186 | Gastroesophageal Reflux Disease |
| 20 | MONDO:0018328 | Homozygous Familial Hypercholesterolemia |
| 21 | MONDO:0006497 | Cerebral Palsy |
| 22 | MONDO:0004260 | Peptic Ulcer Perforation |
| 23 | MONDO:0009265 | Gaucher Disease type1 |
| 24 | MONDO:0005015 | Diabetes Mellitus |
| 25 | MONDO:0020333 | Aggressive Systemic Mastocytosis |
| 27 | MONDO:0005260 | Autism |
| 28 | MONDO:0800029 | Interstitial lung disease 2 |
| 31 | MONDO:0008251 | familial pityriasis rubra pilaris |
| 32 | MONDO:0043233 | Exfoliative Dermatitis |
| 33 | MONDO:0001475 | Neutropenia |
| 34 | MONDO:0015364 | Hereditary Sensory And Autonomic Neuropathy Type |
| 35 | MONDO:0009746 | Hereditary sensory and autonomic neuropathy type 4 |
| 36 | MONDO:0019173 | Rabies |
| 37 | MONDO:0016575 | Primary ciliary dyskinesia |
| 38 | MONDO:0004784 | Allergic Asthma |
| 40 | MONDO:0015564 | Castleman Disease |
| 44 | MONDO:0018982 | Niemann-Pick type C |
| 46 | MONDO:0010794 | NARP Syndrome |
| 47 | MONDO:0100096 | COVID-19 |
| 48 | MONDO:0100345 | Lactose intolerance |
| 49 | MONDO:0018956 | Idiopathic bronchiectasis |
| 52 | MONDO:0004975 | Alzheimer Disease |
| 54 | MONDO:0018958 | Nemaline myopathy |
| 55 | MONDO:0009061 | Cystic fibrosis |
| 57 | MONDO:0005575 | Colorectal Cancer |
| 60 | MONDO:0004979 | Asthma |
| 61 | MONDO:0001119 | Premature Menopause |
| 62 | MONDO:0007743 | ADHD |
| 63 | MONDO:0005393 | Gout |
| 64 | MONDO:0017314 | Ehlers-Danlos Syndrome |
| 67 | MONDO:0005361 | Eosinophilic Esophagitis |
| 69 | MONDO:0019600 | Xeroderma Pigmentosum |
| 72 | MONDO:0005799 | Hookworm Infectious Disease |
| 76 | MONDO:0009290 | Glycogen Storage Disease Ii |
| 77 | MONDO:0004758 | scotoma |
| 80 | MONDO:0005357 | Creutzfeldt Jacob Disease |
| 81 | MONDO:0007147 | Obstructive Sleep Apnea |
| 82 | MONDO:0005267 | Heart Disorder |
