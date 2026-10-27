# Tier 0 masking matrix: test results

**Status: 8/8 conditions verified.**

Fixed chemical/drug dataset: 22,918 labels (18,334 visible / 2,291 validation / 2,293 test),
1,117,832 candidates, pretrained ULTRA 4g, no training, A6000 GPU. Held-out means validation and test.
Only direct edges between labeled endpoints are changed, in both directions; unlabeled pairs remain unchanged.
Every new row rebuilds its relation graph and retains all nodes and candidates, including isolated nodes.

| Row | Visible treats | Visible other | Held-out treats | Held-out other | Test MRR | Test Hits@10 | Top-10 answers | Status |
|---|---|---|---|---|---:|---:|---:|---|
| 1 | Keep | Keep | Remove | Remove | 0.0825 | 16.18% | 371 / 2,293 | verified_existing_baseline |
| 2 | Keep | Keep | Remove | Keep | 0.1470 | 27.78% | 637 / 2,293 | verified |
| 3 | Keep | Remove | Remove | Remove | 0.0833 | 15.57% | 357 / 2,293 | verified |
| 4 | Keep | Remove | Remove | Keep | 0.1457 | 26.60% | 610 / 2,293 | verified |
| 5 | Remove | Keep | Remove | Remove | 0.0257 | 5.19% | 119 / 2,293 | verified |
| 6 | Remove | Keep | Remove | Keep | 0.0957 | 18.75% | 430 / 2,293 | verified |
| 7 | Remove | Remove | Remove | Remove | 0.0179 | 3.49% | 80 / 2,293 | verified |
| 8 | Remove | Remove | Remove | Keep | 0.0836 | 15.79% | 362 / 2,293 | verified |

[Protocol and commands](README.md) · [Exact results and provenance](../studies/tier0_masking_matrix_001_results.json).

Row 1 reuses the verified original baseline. New scores are listed only after all test score hashes and ranks pass independent verification.
Validation is masked but not rescored in this suite. Results are not comparable to older Drug-only or global edge-removal runs without accounting for their different scope.
