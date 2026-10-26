# Similarity witnesses across public Retriever environments

One real stored orthologous_to edge was selected for each of Gene → Gene, Gene → Protein, Protein → Gene, and Protein → Protein. Endpoints were selected with exclusive Gene/Protein typing (rather than dual Gene+Protein labels), and each pair has distinct IDs. Selection used the saved raw-graph endpoint scan and froze source hashes.

All requests use similar_to, with both IDs and categories pinned, against public Development, CI/Staging, Test, and Production Retriever. The expected returned predicate is orthologous_to, a descendant of similar_to. A verified result must bind the exact expected forward subject–predicate–object triple. Presence of an unrelated edge in the response graph or a positive count alone is insufficient.

## Results

| Pattern | Development | CI | Test | Production |
|---|---|---|---|---|
| Gene → Gene | Verified orthology witness | Verified orthology witness | Verified orthology witness | Verified orthology witness |
| Gene → Protein | Verified orthology witness | Verified orthology witness | Verified orthology witness | Verified orthology witness |
| Protein → Gene | Verified orthology witness | Verified orthology witness | Verified orthology witness | Verified orthology witness |
| Protein → Protein | Verified orthology witness | Verified orthology witness | Verified orthology witness | Verified orthology witness |

## Exact examples

| Pattern | Subject | Object |
|---|---|---|
| p01 | TRAV12-2 (`HGNC:12106`) | Trav7-3 (`MGI:3649556`) |
| p02 | IGKV1-9 (`HGNC:5744`) | KV5AM_MOUSE Ig kappa chain V-V region NQ5-89.4 (sprot) (`UniProtKB:P04946`) |
| p03 | KV5AE_MOUSE Ig kappa chain V-V region HP 124E1 (sprot) (`UniProtKB:P01647`) | ENSRNOG00000064662 (`RGD:150345035`) |
| p04 | IGHDM_MOUSE Ig delta chain C region membrane-bound form (sprot) (`UniProtKB:P01882`) | IGHD_RAT Ig delta chain C region (Fragment) (sprot) (`UniProtKB:P01883`) |

## Provenance

| Environment | Endpoint | Advertised TRAPI / Biolink | Metadata release | Metadata unchanged |
|---|---|---|---|---|
| development | `https://dev.retriever.biothings.io/query` | 2.0.0 / 4.4.4 | 2026_06_21 | True |
| ci_staging | `https://retriever.ci.transltr.io/query` | 1.6.0 / 4.3.2 | 2026_06_21 | True |
| test | `https://retriever.test.transltr.io/query` | 1.6.0 / 4.3.2 | 2026_06_21 | True |
| production | `https://retriever.transltr.io/query` | 1.6.0 / 4.3.2 | 2026_06_21 | True |

## Interpretation

These controls evaluate whether similar_to queries retrieve real orthology records across node types and environments. They do not test chemical similarity or claim that stored records have the exact predicate similar_to. One witness per pattern is not a coverage estimate or independent biological validation. Public Development Retriever has not been established as the same deployment used internally by Development ARAGORN. Requests were direct lookups, with Tier 0, fallback disabled, cache bypass, and a named submitter; no ARAGORN inference expansion was invoked.

## Evidence and reproduction

- [Frozen witnesses](../../../../output/similarity-category-witnesses/run_001/witnesses.json)
- [Exact requests, responses, and snapshots](../../../../output/similarity-category-witnesses/run_001/)
- [Detailed summary](../../../../output/similarity-category-witnesses/run_001/summary.json)
- [Flat CSV](../../../../output/similarity-category-witnesses/run_001/summary.csv)
- [Reusable verifier](verify_category_witnesses.py)

From the repository root:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/followups/rule-failure-analysis/tested/rule-02-similar-to/verify_category_witnesses.py
```

Default execution summarizes existing results offline. `--prepare` freezes witnesses from the saved raw scan. `--submit` sends live requests, skipping all previously attempted POSTs, including uncertain attempts. Use a new output directory for a deliberate new experiment. This run submitted 16 POSTs and captured 12 schema/metadata snapshots.
