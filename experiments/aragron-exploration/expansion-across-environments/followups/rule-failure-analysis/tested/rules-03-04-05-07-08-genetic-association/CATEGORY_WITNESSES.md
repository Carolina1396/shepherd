# Genetic-association witnesses across environments

We selected one actual forward genetic_association edge for each of nine category combinations from the downloaded Tier 0 graph. Both distinct endpoints and the requested categories were pinned. The same request was submitted sequentially to public Development, CI/Staging, Test, and Production Retriever, with Tier 0 requested, fallback disabled, cache bypass, and a named submitter. These were direct lookups, not ARAGORN inference workflows.

A witness is verified only when its expected subject ID, exact genetic_association predicate, and object ID occur in an edge bound to a returned result. An edge appearing only in the knowledge graph is insufficient. Reverse edges and other predicates are reported separately.

## Results

| Pattern | Subject category | Object category | Development | CI | Test | Production |
|---|---|---|---|---|---|---|
| p01 | BiologicalProcess | PhenotypicFeature | Verified | Verified | Verified | Verified |
| p02 | BiologicalProcess | Disease | Verified | Verified | Verified | Verified |
| p03 | Pathway | PhenotypicFeature | Verified | Verified | Verified | Verified |
| p04 | Pathway | Disease | Verified | Verified | Verified | Verified |
| p05 | MolecularActivity | PhenotypicFeature | Verified | Verified | Verified | Verified |
| p06 | MolecularActivity | Disease | Verified | Verified | Verified | Verified |
| p07 | CellularComponent | PhenotypicFeature | Verified | Verified | Verified | Verified |
| p08 | CellularComponent | Disease | Verified | Verified | Verified | Verified |
| p09 | BiologicalProcess | Procedure | Verified | Verified | Verified | Verified |

## Exact examples

| Pattern | Subject | Object |
|---|---|---|
| p01 | nail development (`GO:0035878`) | lean body mass (`EFO:0004995`) |
| p02 | intestinal hexose absorption (`GO:0106001`) | primary angle-closure glaucoma (`MONDO:0001868`) |
| p03 | SHC-related events triggered by IGF1R (Homo sapiens) (`REACT:R-HSA-2428933`) | platelet count (`EFO:0004309`) |
| p04 | Interleukin-1 family signaling (Homo sapiens) (`REACT:R-HSA-446652`) | inflammatory bowel disease (`MONDO:0005265`) |
| p05 | oxidoreductase activity, acting on a heme group of donors (`GO:0016675`) | FEV/FVC ratio (`EFO:0004713`) |
| p06 | kinase inhibitor activity (`GO:0019210`) | celiac disease (`MONDO:0005130`) |
| p07 | Schaffer collateral - CA1 synapse (`GO:0098685`) | Fatty fish intake (`UMLS:C0556218`) |
| p08 | presynaptic active zone membrane (`GO:0048787`) | spinal stenosis (`MONDO:0005965`) |
| p09 | response to starvation (`GO:0042594`) | Neutrophil percentage measurement (`UMLS:C1171400`) |

## Endpoint and version provenance

| Environment | Endpoint | Advertised TRAPI | Advertised Biolink | Reported metadata release | Metadata unchanged before/after |
|---|---|---|---|---|---|
| development | `https://dev.retriever.biothings.io/query` | 2.0.0 | 4.4.4 | 2026_06_21 | True |
| ci_staging | `https://retriever.ci.transltr.io/query` | 1.6.0 | 4.3.2 | 2026_06_21 | True |
| test | `https://retriever.test.transltr.io/query` | 1.6.0 | 4.3.2 | 2026_06_21 | True |
| production | `https://retriever.transltr.io/query` | 1.6.0 | 4.3.2 | 2026_06_21 | True |

## Interpretation and limits

These tests verify retrievability of selected genetic associations under nine category patterns. They do not demonstrate biological causality or treatment relevance, representative coverage of each category pair, or support for the Gene-to-condition pattern required by ARAGORN's rules. Public Development Retriever is not established as identical to ARAGORN's internal Development Retriever. Matching reported releases and metadata do not independently establish byte-for-byte graph identity. The nine examples were selected from the same downloaded release, not independently sampled per environment.

## Artifacts and reproduction

- [Frozen witness records and node categories](../../../../output/genetic-association-audit/category-witnesses_001/witnesses.json)
- [All requests, raw responses, submission markers and service snapshots](../../../../output/genetic-association-audit/category-witnesses_001/)
- [Detailed summary](../../../../output/genetic-association-audit/category-witnesses_001/summary.json)
- [Flat results CSV](../../../../output/genetic-association-audit/category-witnesses_001/summary.csv)
- [Reusable runner](verify_category_witnesses.py)

From the repository root, summarize saved results offline:

```bash
experiments/ultra/.venv/bin/python -B experiments/aragron-exploration/expansion-across-environments/followups/rule-failure-analysis/tested/rules-03-04-05-07-08-genetic-association/verify_category_witnesses.py
```

`--prepare` selects and freezes local witnesses when absent. `--submit` enables live requests and skips every previous attempt, including uncertain outcomes. Use a new `--output` directory for a deliberate new experiment. This run used 36 POSTs and 12 snapshot GETs; no scheduled repetition.
