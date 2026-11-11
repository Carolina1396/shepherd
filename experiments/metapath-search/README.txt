METAPATH AUTORESEARCH SETUP

Purpose: search explicit two-hop graph templates for drug-disease treatment
recovery. This is not AMIE rule mining. Existing baseline experiments are
separate. The first ten-proposal checkpoint has completed; no validation winner
was selected and held-out test outcomes have not been evaluated.
verification.json records the earlier manual rehearsal, before that checkpoint.
Detailed run outputs and caches remain local and are excluded from Git.
The checkpoint found unsupported causal-qualifier queries and missing support
graph warnings in ranked evaluation; these remain unresolved. Symmetric edge
interpretation was repaired and covered by regression tests.

Entry points (run from repository root)
PYTHON = ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python

  python3 experiments/metapath-search/prepare.py
  PYTHON -m unittest discover -s experiments/metapath-search -p 'test_*.py'
  PYTHON experiments/metapath-search/evaluate.py --mode screen --batch train_a --out experiments/metapath-search/runs/UNIQUE-A
  PYTHON experiments/metapath-search/evaluate.py --mode screen --batch train_b --out experiments/metapath-search/runs/UNIQUE-B
  PYTHON experiments/metapath-search/evaluate.py --mode ranked --batch debug --out experiments/metapath-search/runs/UNIQUE-DEBUG
  PYTHON experiments/metapath-search/evaluate.py --mode ranked --batch validation --out experiments/metapath-search/runs/UNIQUE-VALIDATION
  python3 experiments/metapath-search/compare.py OLD-VALIDATION-DIRECTORY NEW-VALIDATION-DIRECTORY

--templates selects a saved candidate instead of templates.json. For manual
training-only debugging, --disease selects one training disease; these runs
are explicitly ineligible for model selection. Output directories must be new.
Use the existing Python environment; no new dependencies have been installed.
Both modes require Docker access for read-only runtime inspection and HTTP
access to local Shepherd :55440 and filtered Retriever :8081. Calls run serially. The existing
baseline may share these workers, so manual requests can queue behind it.

Files
program.md: instructions and capped agent loop; read before starting a search.
config.json: fixed graph, data, ranking endpoint, limits and selection metric.
batches.json: seed-42 training A (50 diseases), disjoint B (50), debug (3).
templates.json: editable initial candidate; one broad affects/Gene/association path.
templates.example.json: illustrative broad, decreased-activity and increased-activity variants.
template_format.py: structural validation, exact qualifier matching, query format.
service_execute.py: explicit Shepherd lookup requests and bound-path validation.
execute.py: historical direct-reader utility only; not imported by the evaluator.
build_candidates.py: supporting paths -> TRAPI inferred treatment results.
evaluate.py: screen/ranked evaluation, snapshots, caching, metrics, run ledger.
runtime.py: nonsecret retrieval/ranking images, routes, adapter hash and LMDB fingerprints.
compare.py: reject incomparable/incomplete evaluations; apply configured selection rule.
runs/: snapshots, manifests, results, evidence, ledger (ignored by Git).
cache/: complete lookup records only, keyed by template, disease, graph report,
        executor source hashes and fixed limits (ignored by Git).

Execution semantics (service-v1)
Both screen and ranked modes execute explicit multi-hop queries through local
Shepherd aragorn.lookup -> filtered Retriever :8081 -> filtered Gandalf :56430.
Every query edge is knowledge_type=lookup. Only aragorn.lookup is requested;
there is no AMIE expansion, standalone treatment lookup, or remote enrichment.
The evaluator does not import the direct graph reader. No local-reader fallback.
Live Retriever metadata must match the on-disk filtered graph metadata.
Runtime inspection checks the lookup worker's retrieval URL, Retriever's Gandalf
host/port, service images and the mounted compatibility adapter hash.
Service category/predicate expansion semantics apply. We additionally verify
exact requested qualifiers on every bound edge; mismatch invalidates evidence.
Paths are assembled only from edge bindings in the SAME result analysis and
joined on the same actual intermediate node. Distinct path nodes are required.
Raw requests and compressed responses are saved; cached records reference their
original source_artifacts directory. Old direct-index cache keys cannot collide
because backend, code, runtime, metadata and protocol enter the new cache key.
Client evidence/candidate caps apply AFTER service response, not as service
resource limits. Timeout and upstream service limits still apply. Warnings and
truncation are incomplete outcomes, not successful empty results.
Ranked mode assembles supported treatment candidates, then calls local
aragorn.omnicorp, followed by aragorn.score + sort + top500 + orphan filtering.
Retrieval, enrichment and scoring responses are retained for inspection.
No service configuration, worker code, graph or baseline changes were required.
Historical direct-index config/batches/code are under runs/direct-index-protocol/;
prior runs keep their original manifests and cannot be selected against service runs.
The training batch disease assignments have not changed.

Qualifier contract
constraints.qualifiers uses TRAPI 2-style OR across nonempty maps, AND within
one map. Omitted constraints or [] accepts qualified and unqualified edges.
An explicit requested value must exist on the SAME stored edge record.
Missing != decreased/increased/neutral. Extra stored qualifiers are allowed.
Exact matching, no implicit synonyms. Qualifiers remain relative to actual edge
subject/object; reversing an arrow does not invert biological effect direction.
Arbitrary Biolink qualifier names can be represented, but biological validity
and support should be inspected before proposing a candidate.
The retained edge IDs, sources, attributes, knowledge/agent types and qualifiers
are hydrated into support graphs and preserved for enrichment and scoring.

Protocol and metrics
Training A matches the original 50-disease pilot; B is disjoint by disease.
Only train/validation CSVs are read; no test runner is exposed here.
All original label pairs for selected diseases remain in denominators, including
missing graph endpoints. This is a pair split; diseases can overlap partitions.
Screening reports unranked pair and disease-average recovery and candidate volume.
Ranked primary metric: mean across diseases of fraction of labeled drugs in top10.
Also pair-weighted recovery@500 and MRR@500; other known positives stay in rankings.
Tie-breaking within returned scores is CURIE ascending; upstream top500 ties
are not recoverable. Positive-only labels do not yield precision or accuracy.
Client candidate/path caps and service timeouts are resource limits, NOT a relevance ranking.
Reached limits mark the disease incomplete. Observed metrics may still be saved,
but incomplete runs cannot be selected. Missing endpoints are valid zero recovery.
Historical direct-reader screens hit caps on the broad template. Full service
validation has not run; no complete ranked validation incumbent is established.

Full ranked validation is required for selection. Higher macro_hits_at_10 wins;
exact ties prefer fewer templates. compare.py also requires matching protocol,
code, data and worker fingerprints. Runtime fingerprints are checked before and
after ranked runs. Source data are assumed immutable; graph report hashes and
LMDB sizes/mtimes are drift checks, not full per-run rehashes of large databases.
Every request/response and candidate snapshot is saved. Supporting paths can be
inspected in enriched.request.json.gz, before literature overlay is added.

Scientific policy
Treatment/trial predicates and Procedure intermediates are allowed but flagged.
The agent should reason about generic-node shortcuts and broad candidate sets.
The pilot showed that removing chemical-disease edges does not remove every
representation of treatment knowledge. Never claim mechanism discovery solely
from recovery. A no-treatment-evidence experiment would be a separate protocol.

Starting the agent
Read program.md; first inspect manual rehearsal results and remaining limitations.
In search mode the agent edits templates.json and records hypotheses/decisions
in runs/. If an evaluator defect blocks trustworthy evaluation, program.md
authorizes autonomous repair of this experiment's evaluator and tests. Preserve
the reproducer, verify the fix, record a new code revision, and rerun the baseline
and affected comparisons before resuming. Scientific protocol changes still
require user approval. Repairs and unchanged-proposal reruns do not consume the
ten-proposal budget or reset it. Old run manifests and results remain unchanged.
A first explicitly started session is capped at ten candidate changes. Do not
silently start an indefinite loop. Retain rejected snapshots; never git reset
this shared workspace. Autonomous ranking evaluation will consume shared local
worker resources; schedule longer sessions around the baseline run.

Reference repository
/Users/carolinagonzalez/autoresearch-reference
https://github.com/karpathy/autoresearch
Reviewed commit 228791fb499afffb54b46200aca536f79142f117.
No reference dependencies installed or training started.
