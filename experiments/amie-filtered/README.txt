AMIE MINING ON THE FILTERED GRAPH

Purpose
Learn exact two- and three-edge path rules for treatment, then measure validation
recovery. This experiment does not change the graph, services, existing ARAGORN
rules, or split assignments. It does not evaluate test predictions.

Use the existing Python environment from the repository root:
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python -m unittest discover -s experiments/amie-filtered -p 'test_*.py' -v
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/amie-filtered/workflow.py export --out experiments/amie-filtered/runs/export-001
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/amie-filtered/workflow.py mine --export experiments/amie-filtered/runs/export-001 --out experiments/amie-filtered/runs/mining-001
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/amie-filtered/workflow.py validate --export experiments/amie-filtered/runs/export-001 --mined experiments/amie-filtered/runs/mining-001 --out experiments/amie-filtered/runs/validation-001

Every output directory must be new. Existing runs are never overwritten. See
STATUS.txt for directories already used. Dependencies (numpy, lmdb, msgpack,
psutil) are already installed in the environment above; Java 17 is available.
Commands request low CPU priority. Some sandboxes require elevated execution
permission to set that priority; this does not change the scientific protocol.

Executable provenance
Repository: https://github.com/dig-team/AMIE
Pinned commit: add2b6a7e36a68fc85c9d004a089b264e138ff62
Download the bundled executable into vendor/amie.jar:
  mkdir -p experiments/amie-filtered/vendor
  curl -L --fail https://raw.githubusercontent.com/dig-team/AMIE/add2b6a7e36a68fc85c9d004a089b264e138ff62/amie-dev.jar -o experiments/amie-filtered/vendor/amie.jar
SHA256: bfdb11577fc5404f29eb30b3e16b1002f3b8e38fb53717eccc790a22f63763ca
Upstream licensing: https://github.com/dig-team/AMIE/blob/add2b6a7e36a68fc85c9d004a089b264e138ff62/LICENSE.txt
This pins the actual bundled binary, which may predate the repository's current
source. We do not claim it is an AMIE 4 build or the binary used by ARAGORN.
The runner verifies its checksum and saves its own help output and Java version.
The binary prints usage with exit code 1 for -h; the runner checks advertised
flags, not that help exit code. Real-binary fixture tests verify mining behavior.

Export and supervision
- Input graph: artifacts/gandalf_no_drug_disease/ (27,435,282 source edges).
- Labels: data_split/nonisolated/{train,val,test}.csv; 6,684/831/830 pairs.
- All partitions are checked for missing/duplicate/overlapping pairs and valid
  surviving endpoints. Test labels are read only for these integrity checks.
- Evidence contains NO chemical--disease/phenotype edge in either direction.
  The exporter checks this invariant against the shared explicit category sets.
- Only training labels enter train.tsv as benchmark:treats. That relation is
  head-targeted and body-excluded. No target label can be used for traversal.
- evidence.tsv uses numeric node/relation tokens; nodes.tsv and relations.json
  reverse these tokens to CURIEs, predicates, and complete qualifier sets.
- Qualifier order and exact duplicate qualifiers are normalized. Different full
  sets remain different relations: missing qualifiers are not wildcards.
- Assertion direction is preserved. Identical triples across sources collapse
  in an on-disk SQLite unique index. No sources, entity types, inverse edges,
  hierarchy expansions, or target labels are added to the evidence relation set.
- Intermediates are not category-constrained. Only chemical/disease endpoints
  are restricted in validation. All retained evidence predicates remain allowed;
  treatment-related predicates are flagged in readable rules.
- The manifest records graph file hashes (including LMDB data files), export
  hashes, split hashes, code hash, counts, and state. SQLite is an export scratch
  artifact retained in the ignored run directory, not a changed knowledge graph.

Mining protocol
Two sequential runs use -maxad 3 and 4 (head atom included), -mins 10,
-minis 10, -minc 0.001, -minpca 0, -pm support, -nc 2. Constants remain
disabled. AMIE's other built-in pruning defaults remain in effect; even a
completed run is a result under these settings, not every conceivable rule.
Each process gets one hour including loading, then SIGTERM and at most five
seconds of shutdown grace before SIGKILL. Streams and exit status are preserved.
The JVM is restricted to two active processors. Heap is min(16 GiB, half physical
RAM). Preflight requires that heap plus 1 GiB native/process headroom to be
available; it is repeated before each run. Insufficient memory records a blocked
state. The runner never silently samples the graph or reduces the heap/budget.

Post-processing retains exactly two/three-edge simple paths from head subject to
head object, in any assertion direction. It rejects constants, loops, branches,
cycles, disconnected patterns, and target relations in bodies. Variable names
are canonicalized by path order. Numeric confidence/support determine ordering.
All retained rules are saved with AMIE metrics, readable qualified steps, and
stable IDs. Counts distinguish emitted rows, rejected rows, duplicates, and
retained rules. A capped run is partial; streaming output may contain few or no
rules even if many candidates were explored internally.

Validation protocol
Select the top 100 retained rules per length by training standard confidence,
then support, then canonical path text. No validation label influences selection
or candidate enumeration. Evaluate all validation diseases using read-only graph
indexes, separately from Shepherd and its ranking/enrichment services.
Walk backward from disease with exact relation/qualifier matching. Distinct path
nodes are required. Output chemical IDs are selected by category, never by
looking at which drugs are validation positives. AMIE training statistics can
allow repeated variable bindings; validation deliberately requires distinct
nodes, so training confidence is not a validation performance estimate.

Per rule/disease query: 10 seconds, 2 million examined adjacency records,
100,000 distinct candidates. Caps return explicitly partial results. Duplicate
source records count toward work but not distinct candidates. Validation has a
one-hour budget. All 831 validation pairs remain in the denominator, including
unexecuted or incomplete queries. Candidate lists, states, and up to five node
path witnesses per query are saved in queries.jsonl. Witness arrows/qualifiers
are specified by selected_rules.json and can be matched to the immutable graph.

report.json contains individual-rule recovery/candidate totals and two-edge,
three-edge, and combined union recovery; disease-average recovery; mean/median/
maximum candidate counts; timings; completion states; and provenance. There is
no precision estimate, learned candidate ranker, clinical claim, automatic rule
promotion, or test evaluation. Capped query recoveries are lower bounds. A
partial mining run is also explicitly distinguished from completed mining.

Tests
The suite covers export deduplication, qualifier distinctions, split isolation,
invalid rule shapes, distinct-node traversal, both body lengths, process failure
and timeout artifact preservation, end-to-end validation, and actual AMIE mining
on two small 12-positive datasets. The binary tests skip only if vendor/amie.jar
is absent. No graph downloads or full mining jobs run inside tests.
