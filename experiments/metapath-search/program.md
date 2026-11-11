# Treatment-recovery template research

This is automated search over explicit graph templates, not AMIE mining.
The authoritative evaluator uses local Shepherd lookup -> filtered Retriever/
Gandalf, then local enrichment and scoring. Direct-reader pilot results are
discovery evidence only; they cannot determine selected winners.
Read README.txt, config.json, batches.json, template_format.py and prior run
summaries before proposing experiments. The existing BTE/Aragorn baseline is
an external comparison; do not edit it or reconfigure shared services.

## Objective and immutable protocol
Improve full-validation disease-averaged Hits@10 using fixed local Omnicorp and
Aragorn scoring. Report pair-weighted recovery@500 and MRR@500, macro recovery,
candidate volume, runtime, missing endpoints and incomplete queries.
A disease's Hits@10 is the fraction of its labeled drugs found in the top ten;
the primary metric averages this fraction equally over diseases.
This is raw ranking: do not remove other known positive treatments.
Only complete ranked evaluation on ALL validation diseases can establish a
selected winner. Use test data only in a separately authorized final assessment.
No test runner exists in this directory.

In search mode, edit templates.json only and keep the evaluator fixed. Verified
implementation repairs are allowed through the repair mode below, without
asking for permission. Keep config, batches, graph, label files, scoring workers
and services fixed in both modes. Changes to the scientific protocol require
user approval. Write experiment reasoning and decisions inside runs/. Do not
change these instructions to improve scores.
Do not install dependencies. Use the existing Gandalf Python environment.

## Proposal grammar
Use the version-1 two-hop format. Propose one addition, removal, or replacement
per experiment. Supported predicates, directions and intermediate categories
may vary. Optional qualifier constraints may vary independently per edge.
Missing qualifiers do not satisfy explicit constraints. All qualifiers in a set
must hold on the same edge record. No memorized drug/disease IDs in templates.
Treatment predicates and Procedure intermediates are allowed and flagged.
Inspect generic intermediates and broad candidate sets; do not interpret their
recovery as proof of biological mechanism or clinical utility.

Use graph metadata, training-path evidence, and prior experiments to reason.
For each proposal write: hypothesis; exact change; expected benefit; possible
failure mode. A plausible explanation is not a measured improvement.
Do not read test files or baseline test outcomes to propose candidates.

## Iteration schedule
1. Establish the starting collection's train_a and train_b screening results.
2. Snapshot the collection and record its hash and hypothesis.
3. Screen one change on train_a. Compare it with the incumbent on the same batch.
4. Every third proposal, and for every proposed promotion, screen train_b too.
   Do not wait for perfect performance on train_a before using train_b.
5. Use screening to prioritize, not declare winners. Prefer complementary
   recovery or reduced candidate volume, but allow explicit coverage/volume
   tradeoffs to proceed to ranking. Explain the tradeoff and inspect example
   paths. Resource-limited results are lower bounds, never complete evaluations.
   Do not silently alter limits or select only easy diseases to avoid failures.
6. Run ranked training rehearsals for promising collections. Inspect full paths,
   qualifier matches, candidate count and ranked outcomes. A retrieval gain alone
   is not a ranked gain.
7. Compare finalists with the incumbent on full ranked validation. Accept only
   complete evaluations under the same frozen protocol. Higher macro_hits_at_10
   wins; exact ties prefer fewer templates. Log all diagnostics and paired changes.
8. Record decision and rationale in runs/decisions.jsonl with run paths and hashes.
   Preserve rejected snapshots. Restore only templates.json when discarding;
   never git reset the shared workspace or alter another experiment's files.

Budget: at most config.search_budget candidate changes (initially 10) per
explicitly started session. Stop and report at that budget; do not run forever.
Repairs and reruns of unchanged proposals do not consume candidate-change slots.
Keep the original proposal count when resuming after a repair; a repair does not
start a fresh ten-proposal budget. Do not treat failures as negative biology.

## Autonomous repair mode
If an implementation defect blocks trustworthy evaluation, suspend new candidate
evaluations and autonomously repair the evaluator. Preserve the failing request,
response, template and run manifest first. Distinguish a demonstrated defect from
ordinary resource limits or weak recovery: caps, timeouts and low scores do not
justify changing the protocol or weakening checks.

1. Record the diagnosis and intended repair under runs/, including the old code
   hashes. Add a regression case that reproduces the defect before the fix.
2. Make the smallest justified change to this experiment's evaluator code and
   tests. Do not modify the original shepherd-new-pathfinder project, shared
   services, graph, splits, metrics, scoring, limits or selection criteria.
   Do not use held-out test outcomes to diagnose or choose a repair.
3. Verify the fix with the reproducer and relevant existing tests, including
   negative cases that must still fail. For reversed edges, establish which
   predicates permit reversal from the service's model; preserve stored edge
   direction and qualifier meaning, and reject genuinely mismatched bindings.
4. Record changed files, test results and new evaluator hashes in the repair log.
   Freeze a new evaluator revision before resuming evaluation. Preserve old
   manifests and outputs; use new output directories and code-keyed caches.
   Never rewrite an old session's frozen hashes to conceal a revision.
5. Rerun the baseline and affected candidate comparisons under the new revision.
   All measurements used in a selection comparison must share that revision;
   old measurements remain historical evidence, not comparable selection scores.
   Complete the normal ranked rehearsal and validation requirements, then resume
   search automatically within the remaining proposal budget.

Stop and report if the repair cannot be verified or would require a scientific
protocol change. An implementation repair is not permission to redefine success.

## Commands (from repository root)
Use ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python as PYTHON below.

PYTHON experiments/metapath-search/evaluate.py --mode screen --batch train_a --out experiments/metapath-search/runs/UNIQUE-NAME
PYTHON experiments/metapath-search/evaluate.py --mode screen --batch train_b --out experiments/metapath-search/runs/UNIQUE-NAME
PYTHON experiments/metapath-search/evaluate.py --mode ranked --batch debug --out experiments/metapath-search/runs/UNIQUE-NAME
PYTHON experiments/metapath-search/evaluate.py --mode ranked --batch validation --out experiments/metapath-search/runs/UNIQUE-NAME

No automated search is started by reading this file. Begin iterations only after
the manual rehearsal has passed and the user explicitly starts the search.
