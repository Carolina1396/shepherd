# Retained experiment reports

Small reports copied byte-for-byte from the original local sampling, coverage,
4g evaluation, and verification outputs. [manifest.json](manifest.json) records
the original paths and SHA-256 checksums. Paths inside these original reports
may refer to local files; score hashes do not imply the score arrays are included.

The source graph, prepared tensors, and raw scores remain outside Git. The
[3g study record](../full_graph_ultra3g_bidirectional.json) separately preserves
its aggregate results; its original temporary raw outputs were deleted.

The completed 2026-10-16 treats-only full-graph 4g run has a separate
[report manifest](full-graph-ultra/treats_only_001/manifest.json), containing
checksums for its configuration, preparation, validation/test metrics, and
verification reports. Its [comparison record](../full_graph_treats_only_comparison.json)
preserves the exact differences from the original all-direct 4g results.
New raw scores and per-pair ranks remain local under
`output/full-graph-ultra/treats_only_001/`.

Variant 3, removing `treats` from visible target pairs as well, has its own
[report manifest](full-graph-ultra/treats_all_splits_001/manifest.json) and
[three-variant comparison](../full_graph_variant_3_comparison.json). Validation
and test completed on 2026-10-16 and passed independent verification. Raw
scores and ranks remain local under `output/full-graph-ultra/treats_all_splits_001/`.

Variant 4 removes visible target `treats` and all held-out direct edges. Its
validation run completed on 2026-10-16 and passed independent verification;
test was not evaluated. The [report/source manifest](full-graph-ultra/all_direct_no_visible_treats_001/manifest.json)
records checksums for the retained reports and analysis script snapshot. The
[four-way validation comparison](../full_graph_variant_4_comparison.json) includes
paired disease-bootstrap intervals and top-10 transitions. Raw scores and ranks
remain local under `output/full-graph-ultra/all_direct_no_visible_treats_001/`.
