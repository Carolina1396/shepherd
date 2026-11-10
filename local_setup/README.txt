AUTORESEARCH LOCAL SETUP

This checkout is on research/autoresearch. It starts from the existing Shepherd
code plus the verified Retriever workflow compatibility fix. No DrugMechDB or
Pathfinder analysis directories/results were copied. Pathfinder engine source
remains part of Shepherd; it is not the previous evaluation project.

Local Aragorn: http://127.0.0.1:55440/aragorn/query
Compose project: shepherd-autoresearch
Its PostgreSQL/Redis volumes, containers, and image tags are separate from the
original shepherd-creative-local project on port 55439.

Shared dependencies (already installed):
- Retriever: localhost:8080, project pathfinder-retriever-local.
- Gandalf: localhost:56429, graph release 1.0.4.
- Omnicorp enrichment: local aragorn_omnicorp worker (verified 2026-11-10).
  The hybrid runner still explicitly uses https://shepherd.renci.org/aragorn/query.
The downloaded graph and Python environment remain in the original folder.
Do not delete that folder: this checkout reuses its running retrieval services.
The new Aragorn services can be rebuilt independently. Changes to shared
Retriever/Gandalf affect both projects. This is not a fully offline setup.

Start/restart this checkout's services:
  docker compose -f compose.autoresearch.yml up -d --no-build
Stop only this checkout's services:
  docker compose -f compose.autoresearch.yml stop
After editing a worker (replace aragorn_score with the service you changed):
  docker compose -f compose.autoresearch.yml build aragorn_score
  docker compose -f compose.autoresearch.yml up -d --no-deps aragorn_score
These image tags belong to autoresearch; rebuilding won't replace the original
project's images. Initial images are reused from the verified local setup.

Run the hybrid lookup (use a fresh output directory each time):
  python3 local_setup/run_hybrid_lookup.py --query local_setup/smoke_query.json --out responses/smoke-001
Sequence: local Aragorn lookup -> development Omnicorp -> local Aragorn scoring.
The development server receives the retrieved query/graph/results. The normal
Aragorn endpoint's default workflow still expects local Omnicorp; use this
runner for the hybrid setup. Pathfinder ranking assets are not installed.

The runner also accepts single-edge inferred queries with exactly one endpoint
pinned to one identifier. Local aragorn.lookup performs AMIE expansion before
sending the patterns to Retriever. Example (use a new output directory):
  python3 local_setup/run_hybrid_lookup.py --query local_setup/inferred_disease_smoke_query.json --out responses/inferred-smoke-new --timeout 240
This example asks for inferred treatments for cystic fibrosis (MONDO:0009061).
The running baseline uses the original Gandalf graph on port 56429, not the
separately built filtered graph. Baseline rules include the direct lookup.

If the shared retrieval services are stopped:
  sh /Users/carolinagonzalez/shepherd-new-pathfinder/scripts/retriever_local.sh start
  sh /Users/carolinagonzalez/shepherd-new-pathfinder/scripts/gandalf_local.sh
Run the Gandalf command in a separate terminal and keep it running; it loads
the existing graph without downloading or rebuilding it. Do not start a second
instance while port 56429 is already occupied.

Private local configuration is in .env (ignored, permissions 0600). A template
is local_setup/env.example. Large graph data and test responses are not committed.

Verification: setup smoke query passed on 2026-11-09. All three stages returned
HTTP 200: local lookup 2.712s, dev Omnicorp 3.861s, local scoring 2.053s.
One result, four nodes, 25 lookup edges -> 26 enriched edges, one scored analysis.
Fresh responses are under responses/setup-smoke (ignored by Git).

LOCAL OMNICORP (working with archive data, verified 2026-11-10)

Published single-file databases (not archives):
  https://stars.renci.org/var/translator/shepherd/curies.lmdb
  https://stars.renci.org/var/translator/shepherd/shared_counts.lmdb
Historical single-file downloader: local_setup/download_omnicorp.py
Do not use it to provision the current dataset: the shared-count URL is incomplete.
Data, source headers, SHA-256 checksums, and validation reports are saved in
omnicorp_lmdb/ (ignored). Existing completed files are never overwritten.

The individually published shared_counts.lmdb was incomplete: 437,898,240
bytes versus 9,060,515,840 required by its metadata. A full local query failed
with HTTP 500 and SIGBUS in shared_count_query. Original downloads and reports
are preserved under omnicorp_lmdb/individual-downloads-backup-20261110/.

Working source:
  https://stars.renci.org/var/translator/shepherd/omnicorp_data_05_05_2026.tar.gz
Archive: 2,682,377,716 bytes; SHA-256:
  4677d7da3c4fd24251155372055fd9fe62f415f6ad0d7655a409c4a657b278ad
IMPORTANT: archive members are under omnicorp_lmdb/, not at its top level.
The upstream auto-downloader preserves that folder, so setting this URL with
its normal target directory would nest the files one level too deeply.
We manually extracted the two databases and placed them directly in the host
omnicorp_lmdb/ directory. No .env change or automatic download was needed.
Archive, member sizes, and checksums are saved in omnicorp_lmdb/archive_candidate/.
The active validation report is omnicorp_lmdb/validation.json.

Active file sizes:
  curies.lmdb:           42,352,640 bytes
  shared_counts.lmdb: 9,060,515,840 bytes
Both match the page bounds recorded in their LMDB metadata.

The aragorn_omnicorp service is running behind the local-omnicorp profile.
It reuses shepherd-autoresearch-aragorn_omnicorp:baseline; no rebuild or install.
The data mount is read-only and automatic downloading remains disabled.
The added startup check remains removed at the user's request; the validator
is a manual diagnostic only. CPU/pool concurrency are limited to 1.

Manual validation:
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python local_setup/validate_omnicorp.py
Start only this worker:
  docker compose -f compose.autoresearch.yml up -d --no-build --no-deps aragorn_omnicorp

Full local inferred-query verification (no workflow override, no remote Omnicorp):
  responses/full-local-omnicorp-archive-20261110-122205/
  POST http://127.0.0.1:55440/aragorn/query with inferred_smoke_query.json
  HTTP 200 in 2.57s; 2 results, 3 nodes, 5 edges.
  Omnicorp added 2 literature edges with publication counts 7 and 768.
  Local scoring completed, scores 0.30543678092265497 and 0.30409193024661424.
  No error logs or SIGBUS. Seven existing retrieval MetaEdge warnings remain.
This uses the original graph on 56429, not the separately filtered graph.
The hybrid runner's remote-enrichment default has not changed.

REPRODUCING THE ARCHIVE INSTALL ON ANOTHER MACHINE

Use a NEW staging directory; do not overwrite an existing dataset. The archive
contains an enclosing omnicorp_lmdb/ directory. For example, from the repo root:
  mkdir -p omnicorp_lmdb/staging
  curl -fL --retry 3 -o omnicorp_lmdb/staging/omnicorp.tar.gz https://stars.renci.org/var/translator/shepherd/omnicorp_data_05_05_2026.tar.gz
  shasum -a 256 omnicorp_lmdb/staging/omnicorp.tar.gz
Compare against the checksum above before extracting:
  tar -xzf omnicorp_lmdb/staging/omnicorp.tar.gz -C omnicorp_lmdb/staging omnicorp_lmdb/curies.lmdb omnicorp_lmdb/shared_counts.lmdb
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python local_setup/validate_omnicorp.py --data-dir omnicorp_lmdb/staging/omnicorp_lmdb
After validation, preserve any existing active files in a separate backup
folder, then move the two validated LMDBs directly into ./omnicorp_lmdb/.
Do not move the archive's folder into that directory (which would nest it).

This checkout references machine-local baseline Docker images and a sibling
checkout's Python environment, Retriever service, and graph. Cloning Git alone
does not provide them. See baseline-images.json and compose build definitions;
provision equivalent dependencies on a new machine before starting services.
On this machine, reuse the existing dependencies without reinstalling.

For a full local query (fresh output location; no hybrid runner):
  curl -sS -H 'Content-Type: application/json' --data-binary @local_setup/inferred_smoke_query.json http://127.0.0.1:55440/aragorn/query
The query requests the normal Aragorn workflow, including local Omnicorp.
The hybrid runner intentionally continues to call remote Omnicorp.
