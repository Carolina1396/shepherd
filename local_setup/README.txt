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
- Omnicorp enrichment: https://shepherd.renci.org/aragorn/query.
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
