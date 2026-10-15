# Drug-only retrieval coverage and ULTRA evaluation

Part of [Study 3: Sampling and retrieval](../README.md#study-3-sampling-and-retrieval). Original experiment ID: **7a and 7b**.
Numbered experiment references below use the original IDs.

**Status:** 7a completed on 50 validation diseases; **7b completed on all 986
validation diseases**. The 7a results below measure retrieval coverage only.
[Full-validation evaluation and commands](#full-validation-model-comparison-7b)
describe the next stage.

## Results

| Output | Gandalf walks | ARAGORN-style rules |
|---|---:|---:|
| Validation diseases | 50 | 50 |
| Validation answer pairs | 85 | 85 |
| Mean nodes per graph | 1,711.12 | 136.20 |
| Mean directed connections per graph | 2,095.08 | 262.28 |
| Mean Drug nodes per graph | 286.48 | 71.10 |
| Held-out answer drugs reached | 45 / 85 | 1 / 85 |
| Answer coverage (fraction) | **0.5294** | **0.0118** |
| Mean retrieval seconds per disease | 0.0435 | 3.2536 |
| Total retrieval seconds | 2.17 | 162.68 |

**Interpretation.** Under these settings, native walks supplied broader context
and reached more validation answers. The rule graphs were much smaller: this
comparison does not isolate retrieval strategy from graph size. It does not
establish which graphs would yield better ULTRA rankings. A useful next check
is coverage across several retrieval budgets before model evaluation.

All **950 rule queries succeeded**; one query's returned matches were capped.
Walks produced nonempty graphs for 49 diseases; rules did so for 39. One rule
graph reached the 3,000-connection cap. The one covered rule answer was also
explicitly bound as an answer drug.

The independently verified input has **27,917,681 unique directed connections**,
identical to Experiment 5's inference context. The mask removed 11,521 evidence
records representing 9,608 unique connections. All 100 saved output graphs were
checked for hidden-pair absence, artifact hashes, and recomputed coverage.

This was a CPU-only run. Parent peak RSS was **5.44 GB**, and the largest rule
child peak RSS was **4.49 GB**; these share memory and must not be added. Timings
above exclude graph loading/masking and Biolink startup; rule times include
isolated process overhead. The final resumed invocation took 182 seconds,
including its loading and 49 remaining diseases; the initial one-disease check
was separate. No GPU or model checkpoint was used.

[Retained results, cohort, settings, and verification](../studies/retrieval_comparison_001.json).
Raw per-disease graphs remain locally in `pilot/results/retrieval_001/`.

## Fixed protocol

| Setting | Value |
|---|---|
| Cohort | 50 validation diseases, sampled from sorted CURIEs with seed 7317 |
| Evaluation labels | All 85 validation treatment pairs for those diseases |
| Candidate population | Original 5,326 explicit Drug nodes |
| Source | Original full Gandalf graph, with validation/test pairs masked before retrieval |
| Output size | At most 3,000 unique directed connections per disease per strategy |
| Gandalf walks | Unchanged native `GraphSampler.walk`; 1,000 attempts, length 3 |
| ARAGORN-style rules | Actual 18 treatment templates plus direct lookup, run by native Gandalf `lookup` |
| Rule budget | 5 seconds per query; hard process limit after 2 extra seconds |
| Rule memory guard | At most 4 GiB additional virtual allocation per isolated query process |
| Pinned-node subclass expansion | Disabled to keep the requested disease exact |

Both strategies use the same masked graph. The mask removes all direct
connections for **all 3,616 validation/test pairs**, across predicates and both
directions. Visible training relationships remain. The original store is
read-only: a separate CSR view remaps surviving edge records and properties.
Duplicate evidence records retain their native random-walk sampling weight.
The sampler and lookup implementations are not modified.

ARAGORN templates retain their predicates, directions, categories, and qualifier
constraints. Gandalf supplies its native predicate/category matching. This is
**ARAGORN-style retrieval on the masked Gandalf graph**, not a call to the live
ARAGORN/ Retriever service, and not a claim of backend parity. Eight templates
require a direct answer-pair connection; such a match cannot recover a held-out
pair after masking. The remaining ten have no direct answer-pair edge.

The edge cap retains whole walks or whole rule matches. Rule groups are merged
round-robin with seeded ordering; neither strategy receives validation answer
labels during retrieval or budget selection. The caps are upper limits, not a
promise of equal realized graph sizes. Runtime and matched-result truncation
are reported because the search budgets differ.

## What we measure

For each disease and strategy:

- Number of nodes, directed connections, and Drug nodes in the saved graph.
- **Answer coverage:** fraction of its validation drugs that appear as endpoints
  of retained graph edges. Missing answers stay in the denominator.
- For rules, additionally count correct drugs explicitly bound to the answer
  node; appearing elsewhere in a supporting path is recorded separately through
  graph coverage.
- Retrieval time, rule successes/timeouts/errors, and process memory measurements.

The overall report includes pair-weighted coverage and mean disease coverage.
Coverage measures whether a graph contains the right drugs; it does not show
whether ULTRA would rank them highly. A timeout/error is an incomplete search,
not evidence that a rule has no matches. Reported coverage reflects the actual
bounded run. Saved graphs do not pad in absent candidates; a later model
comparison can add missing candidates as isolated nodes.

## Run

From the repository root, with the existing Gandalf environment and data:

```bash
experiments/ultra/.venv/bin/python -B -u \
  experiments/ultra/pilot/retrieval/run.py \
  --output experiments/ultra/pilot/results/retrieval_002
```

The initial run uses `retrieval_001`. To pause after one completed disease,
add `--max-new-diseases 1`; continue with the same output and `--resume` without
the limit. Settings, rule file, source code, graph metadata, and label hashes
must match. Completed diseases are verified and skipped on resume. Use a new
output directory for a different configuration.

Verification tests run without the real graph or network:

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/retrieval -p 'test_retrieval.py' -v
```

## Outputs

`settings.json`, `cohort.json`, `mask_verification.json`, the copied rule file,
source snapshots, and `biolink.json` identify the protocol and input versions.
Each `diseases/NNN/` directory contains both graphs, per-rule diagnostics, and a
coverage report. `per_disease.csv` and `summary.json` give the comparison; a
paused run writes `partial.json` instead of final results. Graph files use
original Gandalf indices and predicate IDs. Bulk outputs stay local under the
ignored `pilot/results/` directory.

This first comparison uses CPU retrieval only. Parent and per-rule child RSS
include shared/memory-mapped pages and must not be added together as if they
were disjoint allocations. Cold-cache loading and Biolink startup are separate
from per-disease retrieval time. No GPU memory measurement is applicable yet.

## Full-validation model comparison (7b)

**Completed.** Evaluated all **986 validation diseases / 1,807 treatment pairs**
with pretrained 4g and Experiment 5's selected fine-tuned 4g. Each checkpoint
scores both the walk graph and rule graph for each disease. Retrieval settings
remain those above: 1,000 native length-three walk attempts, all 19 rule queries,
and at most 3,000 unique connections per strategy. This is a fresh full-cohort
retrieval, with seed 7317 plus each disease's position in the sorted cohort.

All **5,326 Drug candidates** remain in every query. Candidates absent from a
retrieved graph are added as isolated nodes; no answer pairs are dropped. Node
IDs are compacted locally, original predicate IDs and inverses are preserved,
and ULTRA's relation graph is rebuilt from each retrieved graph. Ranking uses
the original all-known filtering and pessimistic ties. No training occurs.

Empty retrievals remain in the evaluation. ULTRA's fused kernel cannot accept
zero edges, so a narrowly scoped adapter returns the mathematically correct
zero message sum. Native boundary conditions and node updates remain unchanged;
no synthetic edges are added. Tests compare compact versus original node IDs
and empty-graph scores versus native inference with disconnected context.

The runner saves MRR, Hits@1/3/10, answer ranks, scores for all candidates,
retrieval time, relation-graph preparation time, inference time, and peak GPU
allocated/reserved memory. Full-graph validation results from Experiments 3 and
5 are reused as the reference. Preparation/retrieval work is shared between
checkpoints and attributed to each method for comparison; do not add those
shared costs twice. GPU peaks include both loaded checkpoints; reserved memory
can include cached allocations. Total wall time with `--follow` also includes
waiting for retrieval.

### Validation results

| Context | Checkpoint | MRR | Hits@10 | Top-10 answers / 1,807 |
|---|---|---:|---:|---:|
| Full graph | Pretrained 4g | 0.1057 | 0.1920 | 347 |
| Full graph | Fine-tuned 4g | 0.1654 | 0.3210 | 580 |
| Gandalf walks | Pretrained 4g | 0.0413 | 0.0797 | 144 |
| Gandalf walks | Fine-tuned 4g | 0.0466 | 0.0847 | 153 |
| ARAGORN-style rules | Pretrained 4g | 0.0020 | 0.0055 | 10 |
| ARAGORN-style rules | Fine-tuned 4g | 0.0019 | 0.0055 | 10 |

The full graph performed better. Walks reached 837/1,807 answer drugs; rules
reached 63/1,807. All 18,734 rule lookups succeeded. Retrieval took 51.8 minutes
including loading and export; combined GPU inference took 59.4 seconds,
excluding graph preparation. These results motivate checking walk length and
coverage before further model evaluation.
[Exact validation results](../studies/retrieval_validation_results.json).

### Run or resume full validation

Run retrieval in one terminal and evaluation in another; the latter follows
completed disease reports. Both commands use new example output names:

```bash
experiments/ultra/.venv/bin/python -B -u \
  experiments/ultra/pilot/retrieval/run.py \
  --diseases 986 \
  --output experiments/ultra/pilot/results/retrieval_validation_002

bash experiments/ultra/scripts/gpu_python.sh -B -u \
  experiments/ultra/pilot/retrieval/evaluate.py \
  --retrieval experiments/ultra/pilot/results/retrieval_validation_002 \
  --output experiments/ultra/pilot/results/retrieval_validation_scoring_002 \
  --follow
```

The completed runs use suffix `_001`. Add `--resume` to each command to reuse
verified completed outputs. The evaluator waits up to 1,200 seconds for each
next retrieval report, then exits with an error that can be resumed. Omit
`--follow` when retrieval has already completed. Add `--max-queries 2` to the
evaluator for a partial smoke check; resume without it for the entire cohort.

Each strategy/checkpoint directory retains per-disease score files, hashes,
`answer_ranks.csv`, and partial/final metrics. `progress.json` updates every 25
diseases; individual score files are saved immediately. Final `comparison.json`
is written only after all 1,807 validation pairs have been scored in all four
combinations. Test evaluation remains a separate stage after validation settings
are finalized; **no new test evaluation is running**.

GPU regression checks:

```bash
bash experiments/ultra/scripts/gpu_python.sh -B -m unittest discover \
  -s experiments/ultra/pilot/retrieval -p 'test_evaluate.py' -v
```

[Retained launch protocol](../studies/retrieval_validation_setup.json).

## Walk-length coverage check

Compare **3 versus 6 hops** on the same **986 validation diseases / 1,807 pairs**,
with 1,000 attempts per disease and a 3,000-connection cap. Both lengths use
unchanged native Gandalf walks, the same per-disease seed, and the same masked
source graph. Completed walks are retained whole under the cap. Random-number
consumption differs by walk length, so six-hop samples are not extensions of
the saved three-hop samples. This is one seed comparison, not a repeated-seed
estimate. No ARAGORN lookup, ULTRA scoring, or test evaluation runs here.

The comparison reruns the three-hop control and requires exact equality with
every saved Experiment 7b walk graph. Output includes coverage, graph sizes,
completed walks, sampling time, and answer pairs gained/lost at six hops.

```bash
experiments/ultra/.venv/bin/python -B -u \
  experiments/ultra/pilot/retrieval/compare_walk_lengths.py \
  --output experiments/ultra/pilot/results/walk_length_coverage_002
```

The original run uses `_001`; add `--resume` to continue interrupted runs.
The runner reads the frozen `retrieval_validation_001` baseline by default;
use `--baseline` to specify another equivalent full-validation run.

### Coverage result

| Output | 3 hops | 6 hops |
|---|---:|---:|
| Validation answer drugs reached | **837 / 1,807** | **781 / 1,807** |
| Answer coverage | **0.4632** | **0.4322** |
| Mean nodes per graph | 1,740.75 | 2,454.73 |
| Mean connections per graph | 2,106.36 | 2,897.81 |
| Mean Drug nodes per graph | 291.65 | 316.64 |
| Graphs reaching the 3,000-edge cap | 0 | 498 |
| Completed walks / 986,000 attempts | 932,018 | 884,575 |
| Sampling and capped-union time (seconds) | 22.45 | 49.17 |

Six-hop sampling gained **214** answer pairs but lost **270**, a net loss of
**56**. Both lengths reached 567 of the same answer pairs. Longer walks produced
larger graphs and reached more Drug nodes overall, but fewer held-out answers
under this cap. This does not establish that longer walks are always worse;
random realizations, completion rates, and budget truncation all differ. A
larger-cap comparison could test whether the cap limits the six-hop results.

The three-hop control reproduced all 986 earlier graphs exactly. Independent
checks verified all 1,972 graph hashes, masking, coverage, and answer gains/losses.
Total wall time was 156 seconds; parent peak RSS was 5.43 GB. Sampling times
exclude graph loading, verification, and output writes and are from this rerun,
not the original Experiment 7b timing. No GPU or model scoring was used.
[Exact results and verification](../studies/walk_length_coverage_001.json).

## Chemical/drug dataset: compare direct-edge masking policies

This follow-up uses Experiment 11's frozen Experiment 10 dataset, with 18,334
visible pairs, 2,291 validation pairs, 2,293 test pairs, and 1,117,832 chemical/drug
candidates. It evaluates ARAGORN retrieval coverage on all validation and test
diseases, reporting the splits separately. A disease occurring in both splits is
retrieved once per policy and measured against each split's answers.

Both policies mask validation and test pairs globally before retrieval:

- `all_direct`: remove all direct held-out pair connections, across predicates
  and both directions. Unique connections must exactly match Experiment 11's
  saved `triples.npy`.
- `treats_only`: remove only exact `biolink:treats` connections for held-out pairs,
  in both directions. Retain other direct evidence, including broader treatment
  predicates, clinical trials, and effects. This measures missing-label recovery
  with other direct evidence available.

Visible training treatment connections remain in both graphs. Native Gandalf
categories, edge qualifiers, and duplicate evidence records are preserved. All
18 original ARAGORN templates are unchanged. The additional direct lookup uses
Drug OR ChemicalEntity OR SmallMolecule instead of the original Drug-only query.
This direct lookup cannot bind held-out `treats` answers under either policy.

The same seed, 3,000-connection cap, five-second rule budget, two-second hard
timeout grace, and four-GiB additional allocation guard apply to both policies.
Whole matches are merged round-robin without using answer labels. Eight CPU
workers process disease/policy queries; no GPU or model training is involved.
Timeouts, errors, and match truncation are retained as diagnostics. More available
edges can change which matches survive the cap, so recovery need not increase
for every disease under the less restrictive mask.

Outputs under `pilot/results/chemical_retrieval_001/` include:

- `source_graphs.json`: total/active/isolated source nodes, unique directed
  connections, evidence records, removed predicates, and candidate counts.
- Each policy's `diseases/NNNN/`: retrieved graph, retained matches by rule,
  per-rule diagnostics, answer identities, and checksums.
- `per_disease.csv`: retrieved nodes, edges, candidate chemicals, answer counts,
  coverage, and time, separately for validation and test.
- `per_rule.csv`: explicitly bound and graph-present answers contributed by each
  rule after the shared union cap. Contributions overlap and must not be summed
  to obtain unique overall recovery.
- `summary.json`: final pair-weighted coverage, mean/median/min/max graph sizes,
  empty/capped graphs, rule contributions, and answers gained/lost between
  policies. Incomplete runs write `partial.json` and `status.json`.

Graph coverage counts correct chemicals anywhere in the retained graph; bound
coverage counts correct chemicals explicitly assigned to the answer variable.
Both keep missed answers in the denominator and deduplicate within each disease.
Saved graph coverage and retained-rule contributions are independently recomputed
before completion. This stage does not produce MRR or Hits@k. Test coverage is
exploratory and does not select retrieval settings or model checkpoints.

Run from the repository root with a fresh output directory:

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_retrieval/run.py \
  --output experiments/ultra/pilot/results/chemical_retrieval_002
```

Use `--max-new-diseases 2` for a resumable smoke check, and `--resume` to continue
the same run. Use `--verify-only` to recompute saved results without retrieval.
Settings, source code, rule templates, and dataset hashes must match on resume.

The completed comparison is retained in
`pilot/studies/chemical_retrieval_001_results.json`. Under `treats_only`, validation
recovery was 455/2,291 (19.86%) and test recovery was 506/2,293 (22.07%). All
recovered answers were also explicitly bound as rule answers.

The current follow-up focuses on `treats_only`. `chemical_retrieval/analyze_existing.py`
recomputes visible-pair coverage on the existing query cohort and audits cap
losses. All 14,340 visible pairs on the 1,293 already-queried training diseases
were recovered. The other 3,994 visible pairs span 2,194 training-only diseases;
`chemical_retrieval/train_recovery.py` retrieves these with the original budgets,
reuses existing graphs, and independently verifies the combined training metric.
The completed training extension uses `pilot/results/chemical_retrieval_002_train/`
and recovered all 18,334/18,334 visible pairs across 3,487 diseases (100%). Both
graph coverage and explicitly bound answer coverage were independently verified;
66,253 rule lookups succeeded. The result is retained in
`pilot/studies/chemical_retrieval_001_train_recovery.json`;
the earlier `_001_train` attempt failed during worker startup before new queries
ran. Visible training evidence remains present, so its coverage is not a measure
of held-out predictive performance.

The final union cap excluded seven validation and seven test answers that were
present in the bounded per-rule results; earlier per-rule truncation is a separate
limit. Eleven templates produced no matches. A validation-only evidence audit
(`chemical_retrieval/audit_evidence.py`) found retained direct broader-treatment
evidence for 1,647/2,291 answers. Its union with current recovered answers is
1,651/2,291 (72.06%). This is evidence availability, not a measured retrieval
result: adding a broader-treatment lookup would still be subject to retrieval
budgets. The audit is saved as `chemical_retrieval_001/validation_evidence_audit.json`.

```bash
experiments/ultra/.venv/bin/python -B -u experiments/ultra/pilot/chemical_retrieval/train_recovery.py \
  --output experiments/ultra/pilot/results/chemical_retrieval_002_train --resume
```

```bash
experiments/ultra/.venv/bin/python -B -m unittest discover \
  -s experiments/ultra/pilot/chemical_retrieval -p 'test_protocol.py' -v
```
