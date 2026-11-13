TRAINING RULE-STRUCTURE FREQUENCY

OVERALL SUMMARY — training-001

IMPORTANT: ENDPOINT AVAILABILITY AFTER FILTERING

All training endpoints existed in the original graph. Filtering removed every
chemical–disease/phenotype edge, then removed nodes left with no remaining edges.
Consequently 1,002 training pairs are structurally unreachable in the filtered
graph; this is not a traversal failure or missing data in the benchmark CSV.

| Endpoint status in the filtered graph | Training pairs |
|---|---:|
| Both endpoints present (searchable) | 6,684 |
| Disease only missing | 922 |
| Drug only missing | 61 |
| Both missing | 19 |
| Total with at least one missing endpoint | 1,002 |
| Total training pairs | 7,686 |

The 1,002 affected pairs involve 34 distinct missing drug nodes and 203 distinct
missing disease nodes. A node may occur in several pairs. Searchable means both
endpoints are present, not that a connecting path is guaranteed. Retaining the
isolated nodes would not restore paths: their remaining degree would be zero.

Unique training pairs connected by a 2-hop OR a 3-hop path. Each pair is
counted once in the overall columns. Both denominators are shown below.

| Chemical intermediates | Qualifier handling | 2 hops | 3 hops | Overall: 2 or 3 hops / all training pairs | Overall / searchable pairs |
|---|---|---:|---:|---:|---:|
| Allowed | Ignored | 4,470 | 6,502 | 6,502 / 7,686 = 84.60% | 6,502 / 6,684 = 97.28% |
| Allowed | Retained in signatures | 4,470 | 6,502 | 6,502 / 7,686 = 84.60% | 6,502 / 6,684 = 97.28% |
| Excluded | Ignored | 4,470 | 6,335 | 6,335 / 7,686 = 82.42% | 6,335 / 6,684 = 94.78% |
| Excluded | Retained in signatures | 4,470 | 6,335 | 6,335 / 7,686 = 82.42% | 6,335 / 6,684 = 94.78% |

All 4,470 pairs connected in 2 hops also connect in 3 hops in both chemical
conditions. Three-hop paths add 2,032 pairs when chemicals are allowed and
1,865 when excluded. These are connectivity totals, not prediction accuracy.
Qualifiers distinguish signatures; they do not filter paths in this analysis.
Consequently retaining versus ignoring qualifiers leaves pair coverage unchanged.
The connectivity totals are exact: every capped pair already connects in both
conditions. Some 3-hop signature counts and frequencies remain lower bounds.
See report.md for the complete results, methods, and hub analysis.
See dual-ranking-tables.md for top-five tables ranked separately by pair coverage
and by node-sequence frequency across all eight conditions. Top-20 details are
in runs/training-001/dual_rankings/top20.tsv and top20.json. Both rankings report
pair support, path count, and average paths per supported pair. These tables
re-sort the existing results; they do not run new graph searches.

Purpose
Measure observed exact 2/3-hop meta-path frequency among DrugCentral training
pairs in the filtered Tier 0 graph. These are candidate rule structures, not
validated treatment rules. No validation/test labels are used. No services or
graph stores are modified.

Inputs
- data_split/train.csv, including missing endpoints in the full denominator.
- artifacts/gandalf_no_drug_disease/, opened read-only using its Gandalf
  mmap adjacency indexes and LMDB node store, not the Gandalf query service.
- Every run freezes label, graph-filter-report and script hashes.

Semantics
- Exact stored predicates and complete stored category sets; no hierarchy expansion.
- Traverse both directions; preserve assertion direction and original qualifiers.
- No self-loops. Repeated nonadjacent nodes are permitted. For distinct endpoints
  without a direct edge, they cannot add a 2/3-hop walk.
- Collapse source-duplicate edges; retain distinct predicate/qualifier alternatives.
- Compare chemical intermediates allowed vs excluded, with vs without qualifiers.
- Chemical membership means any of Drug, ChemicalEntity, SmallMolecule,
  MolecularMixture, ChemicalMixture, ComplexMolecularMixture. Endpoints are exempt
  from the intermediate exclusion. There is no chemical-containing-only report.

Run from repository root (use a new run directory for changed code or inputs)
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/test_analysis.py
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py enumerate --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 2
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py summarize --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 2
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py enumerate --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 3 --selection pilot
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py enumerate --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 3
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py summarize --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 3
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py audit --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 2
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/analyze.py audit --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --hops 3
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/verify_run.py --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python experiments/metapath-feasibility/training-rule-frequency/report.py --run experiments/metapath-feasibility/training-rule-frequency/runs/training-001 --out experiments/metapath-feasibility/training-rule-frequency/report.md

Resume behavior and bounds
Pair checkpoints are atomic gzip/msgpack records. Enumerate skips existing
records, including partial ones. Resuming does not silently retry partial pairs.
Use a new run if increasing limits; do not remove prior checkpoints to imply
they were never partial. The 3-hop pilot checkpoints are reused by the full run.
The pilot samples eight pairs in each endpoint-degree-product quartile, seed 42.
It estimates cost across degree ranges; it is not a random performance sample.

2-hop bounds: 30 seconds, 20m examined edges, 1m node sequences, 500k signatures
per qualifier form and pair. 3-hop bounds: 5 seconds, 5m edges, 100k node sequences,
100k signatures per qualifier form and pair. Bounds are checked between operations,
not hard process timeouts. Only whole node sequences are committed.
Complete, missing_endpoint, time_limit, edge_limit, walk_limit and signature_limit
remain separate states. Summaries also count not_processed pairs.

Ranking and denominators
Rank by observed distinct pair support, then observed node-sequence count, then
exact signature. Report full-training and surviving-endpoint coverage, distinct
drug/disease counts, and support from complete pairs separately. All observed
support is a lower bound when any pairs are incomplete. No absence or exact
rank is inferred from capped searches. Distinct node sequences are counted
once per signature; summing over signatures is not a unique-path count.
Both chemical views use the same traversal/checkpoint. For a capped pair,
the no-chemical view is a subset of the observed prefix, not an independently
exhausted restricted search.

Hub audits
Re-enumerate pairs supporting the union of the top 20 signatures in the four
views. Only fully completed audits contribute hub statistics. At each intermediate
position, report the node used by the most supporting pairs (lexical tie break),
and how many audited pairs would lose support if that node were excluded at that
position. A pair loses support only if that node is its sole alternative at the
position. Exclusion is position-specific, not a global node deletion.
Audit limits: 20 seconds / 20m examined edges per pair. Partial audits are counted
and excluded from hub denominators; audit completion is reported per signature.

Artifacts under runs/training-001/ (ignored by Git)
- manifest.json: frozen inputs, pair IDs and pilot sample.
- dictionaries.json: category-set, predicate and qualifier decoding tables.
- {2,3}hop/pairs/: resumable per-pair compressed signature counts and witnesses.
- {2,3}hop/progress.json and pair_status.json: execution/completion accounting.
- {2,3}hop/summary.json: all four views and denominators.
- {2,3}hop/*tsv.gz: complete observed signature rankings, including qualified
  signatures' unqualified-parent IDs.
- {2,3}hop/*top20.json: detailed leading signatures, supporting pair IDs,
  examples and (after audit) hub metrics.
- 3hop/pilot.json: pilot costs and completion states.
- {2,3}hop/hub_audit.json: audit coverage.

The report in this directory summarizes the completed run and limitations.
