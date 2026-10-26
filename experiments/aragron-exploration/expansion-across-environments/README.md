# ARAGORN expansion across environments

This experiment submitted the same ten inferred `ChemicalEntity → treats → DiseaseOrPhenotypicFeature` questions to Development, CI/Staging, Test, and Production. Hosted ARAGORN expanded each original query through its eighteen treatment rules and sent the resulting lookups to Retriever.

Start with [REPORT.md](REPORT.md). It is the authoritative account of the setup, submitted queries, rule-identification method, log evidence, follow-up controls, results, and limitations.

## Directory guide

| Location | Purpose |
|---|---|
| [REPORT.md](REPORT.md) | Complete experiment report and source of truth |
| [notebooks/](notebooks/) | Executed notebooks for interactive review |
| [scripts/](scripts/) | Query runners, offline analysis, diagnostics, and notebook builders |
| [tests/](tests/) | Regression tests for classifications and evidence parsing |
| [followups/](followups/) | Controlled studies prompted by the main experiment |
| `output/` | Raw requests, responses, logs, snapshots, and generated tables |
| [config.json](config.json) | Frozen targets, environments, workflow, and query parameters |

The two main notebooks have distinct purposes:

- [Cross-environment comparison](notebooks/01_ten_queries_all_environments.ipynb) compares queries, environments, callback counts, and final answers.
- [Rule outcomes](notebooks/02_rule_outcomes.ipynb) classifies every expanded rule evaluation as returned, rejected, empty, incomplete, error, or unknown and exposes the supporting log evidence.

The [rule-failure analysis](followups/rule-failure-analysis/README.md) separates patterns with completed controls from those that still need testing. The [Development tier-selection follow-up](followups/development-tier-selection/README.md) tests omitted tier controls and an explicit Tier 1 request.

## Main result snapshot

The main run contains 40 original queries and 760 observed callbacks: one direct lookup plus eighteen rule lookups for each query. All 720 rule evaluations were observed as expanded. Across the four environments, the outcome totals were 108 returned, 320 rejected, and 292 empty. Each environment produced the same 27 returned, 80 rejected, and 73 empty evaluations.

- Rule 1 was rejected for an invalid predicate.
- Rules 2, 3, 4, 5, 7, 8, and 9 were rejected because Retriever could not find required MetaEdges.
- Rules 12, 13, and 16 returned empty callbacks for all ten targets.
- Rules 6, 10, 11, 14, 15, 17, and 18 returned paths for at least one target.

These are raw retrieval outcomes before ARAGORN filtering and merging. The report explains the evidence and the limits of each classification.

## Evidence distribution

Source, reports, executed notebooks, tests, and compact result tables in
[evidence/](evidence/) belong in Git. Raw evidence is distributed separately as
`aragorn-environments-evidence.tar.gz`; publish it as a companion release asset.
The archive has been prepared locally under the ignored `publication/` directory;
it has **not yet been uploaded**. Its checksum and per-file inventory are recorded
in [evidence/manifest.json](evidence/manifest.json).

After downloading the archive, verify its SHA-256 against the manifest, then
extract it from the repository root:

```bash
tar -xzf /path/to/aragorn-environments-evidence.tar.gz
```

The archive restores the experiment's original `output/` paths, including
follow-up outputs, plus the earlier inventory and response fixture used by the
report and tests. Links into those directories require extraction and will not
resolve in GitHub's source browser. No graph store or model checkpoint is included.
Re-running graph scans additionally requires the original graph release; supply
`--raw` instead of relying on the original machine's default path.

## Offline reproduction

Use Python 3.10 or newer. Install this folder's `requirements.txt` in a virtual
environment and restore the evidence archive first. The commands below use the
original workspace's Python environment; substitute your environment's `python`
on another machine. They read saved evidence and make no HTTP requests:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/run.py
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/rule_outcomes.py
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/diagnose_filters.py
python -B experiments/aragron-exploration/expansion-across-environments/scripts/build_notebook.py --execute
python -B experiments/aragron-exploration/expansion-across-environments/scripts/build_rule_outcomes_notebook.py --execute
experiments/ultra/.venv/bin/python -B -m unittest discover \
  -s experiments/aragron-exploration/expansion-across-environments/tests \
  -p 'test_*.py' -v
```

The qualifier-control runner also summarizes existing evidence offline:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/hosted_qualifier_controls.py
```

## New hosted run

`--submit` explicitly enables hosted queries. Use a new output directory so the historical evidence remains unchanged:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/scripts/run.py \
  --submit \
  --output experiments/aragron-exploration/expansion-across-environments/output/run_003
```

Existing submission markers are never retried automatically, including uncertain transport outcomes. The parent experiment ignores `output/` in Git; retain or archive it with the report because notebook re-execution and evidence links depend on it.
