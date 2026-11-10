FILTERED EVIDENCE GRAPH

Build from the existing, immutable Gandalf 1.0.4 graph:
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python graph_cleaning/build_filtered_graph.py

Validate loading and querying with the installed Gandalf library:
  PYTHONDONTWRITEBYTECODE=1 ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python graph_cleaning/verify_gandalf.py

The second command may require network access for Biolink Model 4.4.4.
It calls Gandalf's real lookup implementation in-process, without starting or
changing services. Query responses are saved under the output graph directory.

Output: artifacts/gandalf_no_drug_disease/ (ignored by Git).
The builder refuses an existing output or .building directory. For a repeat,
use --out with a new directory. A failed build remains in .building for inspection.

FILTER
- Remove every edge joining the drug/chemical category group to the
  disease/phenotype category group, in either direction, regardless of source
  or predicate. Explicit category sets are shared with data_split/analyze_graph.py.
- Match any of a node's categories; do not infer additional categories.
- Remove all nodes with no incident retained edges.
- Preserve remaining node properties/IDs and edge IDs/attributes byte-for-byte.
  Retain source, qualifier, knowledge-level and agent-type pools unchanged;
  unused pool entries are harmless and are not traversable edges.
- Rebuild forward/reverse adjacency offsets, remap all node and edge positions,
  and regenerate metadata and representative edges from retained records.

EXPECTED OUTPUT
  Nodes: 1,685,344 (21,552 removed)
  Edges: 27,435,282 (1,499,839 removed)
  Label pairs: 8,345 across data_split/nonisolated/{train,val,test}.csv

AUDIT FILES IN OUTPUT
- filtering_report.json: counts, category policy, label hashes, source build,
  complete raw edge-store digest checks and index/preservation checks.
- original_node_to_filtered.npy and original_edge_to_filtered.npy:
  old-to-new indexes (-1 means removed), for reproducibility and traceability.
- edge_metadata_triples.npy: encoded category/predicate triple for each edge,
  used during metadata construction; Gandalf ignores this auxiliary file.
- gandalf_verification.json and smoke_queries/: Gandalf load/query validation.

These labels are not inserted into the evidence graph. All original graph
files, original split CSVs, and running services remain unchanged.
Non-isolated label endpoints do not guarantee a connecting multi-hop path.

SMALL FIXTURE TEST
  ../shepherd-new-pathfinder/.local/gandalf-venv/bin/python graph_cleaning/test_build_filtered_graph.py
