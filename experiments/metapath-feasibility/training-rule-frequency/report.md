# Training drug–disease meta-path frequency

Run: `training-001`. Analysis date: 2026-11-12.

This is a descriptive study of candidate rule structures on known training pairs. It is not a candidate-retrieval, precision, or held-out prediction evaluation.

## Important: endpoint availability after filtering

Graph filtering removed chemical–disease/phenotype edges and then removed nodes with no remaining edges. Missing endpoints here mean nodes absent from the filtered graph, not missing benchmark CSV fields or a traversal failure.

| Endpoint status in the filtered graph | Training pairs |
|---|---:|
| Both endpoints present (searchable) | 6,684 |
| Disease only missing | 922 |
| Drug only missing | 61 |
| Both missing | 19 |
| Total with at least one missing endpoint | 1,002 |
| Total training pairs | 7,686 |

These affected pairs involve 34 distinct missing drug nodes and 203 distinct missing disease nodes. Pairs with an absent endpoint in the original graph: **0**. A missing node can affect multiple pairs. Searchable means both endpoints survive, not that a connecting path is guaranteed. Keeping isolated nodes would not restore connectivity because they have no retained edges.

[Read-only endpoint audit](runs/training-001/endpoint_audit.json)

## Overall summary: connected in 2 or 3 hops

Count each training pair once if it has a two-hop OR a three-hop path under the same conditions. Show both all-training and surviving-endpoint denominators.

| Chemical intermediates | Qualifier handling | 2 hops | 3 hops | Overall: 2 or 3 hops / all training pairs | Overall / searchable pairs |
|---|---|---:|---:|---:|---:|
| Allowed | Ignored | 4,470 | 6,502 | **6,502 / 7,686 = 84.60%** | **6,502 / 6,684 = 97.28%** |
| Allowed | Retained in signatures | 4,470 | 6,502 | **6,502 / 7,686 = 84.60%** | **6,502 / 6,684 = 97.28%** |
| Excluded | Ignored | 4,470 | 6,335 | **6,335 / 7,686 = 82.42%** | **6,335 / 6,684 = 94.78%** |
| Excluded | Retained in signatures | 4,470 | 6,335 | **6,335 / 7,686 = 82.42%** | **6,335 / 6,684 = 94.78%** |

Chemicals allowed: 4,470 pairs connect at both hop lengths; 2,032 additional pairs connect at three hops; 0 connect only at two hops.
Chemicals excluded: 4,470 pairs connect at both hop lengths; 1,865 additional pairs connect at three hops; 0 connect only at two hops.

Qualifier handling changes how signatures are distinguished, not which paths are retained. All qualifier variants, including empty qualifier sets, remain available; no qualifier constraints are imposed. These are connectivity totals, not prediction accuracy. See completion details below for exactness and bounds.

## Inputs and traversal

- All **7,686** DrugCentral training pairs were scheduled; **6,684** have both endpoints in the filtered graph and **1,002** have a missing endpoint.
- Graph: `artifacts/gandalf_no_drug_disease/` (1,685,344 nodes; 27,435,282 edges). Every chemical–disease/phenotype edge has been removed, regardless of direction, source, or predicate.
- Read-only Gandalf mmap/LMDB indexes; custom traversal, not the Gandalf HTTP service. No validation or test labels, entity normalization, predicate hierarchy expansion, or inference.
- Both edge directions are traversed, with original assertion arrows retained. No self-loops. Repeated nonadjacent nodes are allowed, but cannot add 2/3-hop walks here without a direct endpoint edge.
- Signatures preserve complete stored category sets. Source duplicates are collapsed. Qualified signatures preserve the full qualifier set; unqualified signatures omit qualifiers.
- Chemical exclusion matches any stored Drug, ChemicalEntity, SmallMolecule, MolecularMixture, ChemicalMixture, or ComplexMolecularMixture category on intermediate nodes only. This includes metabolites and broad chemical classes.
- [Frozen manifest](runs/training-001/manifest.json), [method and commands](README.txt), [analysis script](analyze.py), [fixture checks](test_analysis.py).

## Completion and coverage

| Hops | Complete surviving pairs | Missing endpoints | Incomplete/unprocessed pairs |
|---|---:|---:|---:|
| 2 | 6,684 | 1,002 | 0 |
| 3 | 6,592 | 1,002 | 92 |

Bounds: 2-hop searches allow 30 s, 20 million scanned edges, 1 million node sequences, and 500,000 signatures per qualifier form per pair. Three-hop searches allow 5 s, 5 million edges, 100,000 node sequences, and 100,000 signatures. Checks occur between operations; these are not hard process timeouts. Partial pairs are preserved as lower bounds.

| Hops | Chemical intermediates | Qualifiers | Observed signatures | Connected training pairs | All training coverage | Surviving-endpoint coverage |
|---|---|---|---:|---:|---:|---:|
| 2 | allowed | without | 2,134 | 4,470 | 58.16% | 66.88% |
| 2 | excluded | without | 2,134 | 4,470 | 58.16% | 66.88% |
| 2 | allowed | with | 28,372 | 4,470 | 58.16% | 66.88% |
| 2 | excluded | with | 28,372 | 4,470 | 58.16% | 66.88% |
| 3 | allowed | without | 336,928 | 6,502 | 84.60% | 97.28% |
| 3 | excluded | without | 238,539 | 6,335 | 82.42% | 94.78% |
| 3 | allowed | with | 4,760,206 | 6,502 | 84.60% | 97.28% |
| 3 | excluded | with | 3,783,175 | 6,335 | 82.42% | 94.78% |

Signature counts and individual-pattern support are exact when all surviving pairs completed; otherwise they are observed lower bounds. The full TSVs distinguish support from complete pairs from support observed across all processed pairs. Rankings may change if incomplete searches are completed.

Two-hop chemical exclusion makes no difference: a chemical intermediate would require an edge to the disease endpoint, which graph cleaning removed.

All 92 incomplete three-hop pairs already have a connection in both chemical views, and every other surviving pair was exhaustively searched. Therefore pair-level existence totals (6,502 allowed; 6,335 excluded) are exact despite incomplete signature enumeration. The difference is 167 pairs whose three-hop connectivity requires a chemical intermediate under these semantics.

## Three-hop cost pilot

The 32-pair pilot sampled eight pairs from each quartile of endpoint degree product (seed 42). States: `{'complete': 32}`. Pair enumeration median: 0.0229 s; maximum: 0.9121 s. This is a stratified cost probe, not a random performance sample. Its checkpoints were reused in the full pass.

## Leading patterns

Rank: distinct observed training-pair support, then observed node-sequence count, then exact signature. The tables show five patterns per condition; artifacts contain the top 20 with witnesses and the full ranked catalog. Category labels below are shortened for display only; distinct complete category sets remain distinct signatures.

For a partial run, the pair-support interval is [observed support, observed support plus every unfinished pair not already observed supporting that signature]. It is a conservative uncertainty bound, not a statistical confidence interval.

`T` = `biolink:treats_or_applied_or_studied_to_treat`. `Q1`, `Q2`, etc. identify exact qualifier sets defined at the end of this section. An edge without a Q label in a qualified table has no stored qualifiers.

### 2 hops; unqualified; chemical allowed

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2335 | 755 | 533 | 5,972 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1588 | 664 | 281 | 2,292 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease` | 1415 | 709 | 271 | 11,491 |
| 4 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1340 | 600 | 305 | 12,441 |
| 5 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1226 | 424 | 364 | 3,199 |

[Top 20, support IDs, and witnesses](runs/training-001/2hop/unqualified-chemical_allowed-top20.json) · [Full ranked TSV, gzip](runs/training-001/2hop/unqualified-chemical_allowed.tsv.gz)

### 2 hops; unqualified; chemical excluded

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2335 | 755 | 533 | 5,972 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1588 | 664 | 281 | 2,292 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease` | 1415 | 709 | 271 | 11,491 |
| 4 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1340 | 600 | 305 | 12,441 |
| 5 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1226 | 424 | 364 | 3,199 |

[Top 20, support IDs, and witnesses](runs/training-001/2hop/unqualified-chemical_excluded-top20.json) · [Full ranked TSV, gzip](runs/training-001/2hop/unqualified-chemical_excluded.tsv.gz)

### 2 hops; qualified; chemical allowed

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2335 | 755 | 533 | 5,972 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1588 | 664 | 281 | 2,292 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1233 | 601 | 244 | 8,241 |
| 4 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1226 | 424 | 364 | 3,199 |
| 5 | `ChemicalEntity ←has_input— Procedure —in_clinical_trials_for→ Disease` | 1019 | 530 | 205 | 2,053 |

[Top 20, support IDs, and witnesses](runs/training-001/2hop/qualified-chemical_allowed-top20.json) · [Full ranked TSV, gzip](runs/training-001/2hop/qualified-chemical_allowed.tsv.gz)

### 2 hops; qualified; chemical excluded

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2335 | 755 | 533 | 5,972 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1588 | 664 | 281 | 2,292 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1233 | 601 | 244 | 8,241 |
| 4 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1226 | 424 | 364 | 3,199 |
| 5 | `ChemicalEntity ←has_input— Procedure —in_clinical_trials_for→ Disease` | 1019 | 530 | 205 | 2,053 |

[Top 20, support IDs, and witnesses](runs/training-001/2hop/qualified-chemical_excluded-top20.json) · [Full ranked TSV, gzip](runs/training-001/2hop/qualified-chemical_excluded.tsv.gz)

### 3 hops; unqualified; chemical allowed

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 4073–4082 | 1,097 | 885 | 477,284 |
| 2 | `ChemicalEntity —affects→ Gene/Protein —causes→ Disease ←subclass_of— Disease` | 3770–3779 | 955 | 865 | 78,487 |
| 3 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3750–3759 | 930 | 841 | 45,574 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3731–3740 | 933 | 844 | 58,467 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —affects→ Disease ←subclass_of— Disease` | 3727–3736 | 943 | 856 | 87,188 |

[Top 20, support IDs, and witnesses](runs/training-001/3hop/unqualified-chemical_allowed-top20.json) · [Full ranked TSV, gzip](runs/training-001/3hop/unqualified-chemical_allowed.tsv.gz)

### 3 hops; unqualified; chemical excluded

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 4073–4082 | 1,097 | 885 | 477,284 |
| 2 | `ChemicalEntity —affects→ Gene/Protein —causes→ Disease ←subclass_of— Disease` | 3770–3779 | 955 | 865 | 78,487 |
| 3 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3750–3759 | 930 | 841 | 45,574 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3731–3740 | 933 | 844 | 58,467 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —affects→ Disease ←subclass_of— Disease` | 3727–3736 | 943 | 856 | 87,188 |

[Top 20, support IDs, and witnesses](runs/training-001/3hop/unqualified-chemical_excluded-top20.json) · [Full ranked TSV, gzip](runs/training-001/3hop/unqualified-chemical_excluded.tsv.gz)

### 3 hops; qualified; chemical allowed

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 3809–3818 | 984 | 847 | 297,178 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3750–3759 | 930 | 841 | 45,574 |
| 3 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3731–3740 | 933 | 844 | 58,467 |
| 4 | `ChemicalEntity ←has_input— Procedure —causes→ Disease ←subclass_of— Disease` | 3668–3679 | 892 | 826 | 32,847 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein —causes[Q2]→ Disease ←subclass_of— Disease` | 3548–3557 | 867 | 831 | 50,717 |

[Top 20, support IDs, and witnesses](runs/training-001/3hop/qualified-chemical_allowed-top20.json) · [Full ranked TSV, gzip](runs/training-001/3hop/qualified-chemical_allowed.tsv.gz)

### 3 hops; qualified; chemical excluded

| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |
|---|---|---:|---:|---:|---:|
| 1 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 3809–3818 | 984 | 847 | 297,178 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3750–3759 | 930 | 841 | 45,574 |
| 3 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3731–3740 | 933 | 844 | 58,467 |
| 4 | `ChemicalEntity ←has_input— Procedure —causes→ Disease ←subclass_of— Disease` | 3668–3679 | 892 | 826 | 32,847 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein —causes[Q2]→ Disease ←subclass_of— Disease` | 3548–3557 | 867 | 831 | 50,717 |

[Top 20, support IDs, and witnesses](runs/training-001/3hop/qualified-chemical_excluded-top20.json) · [Full ranked TSV, gzip](runs/training-001/3hop/qualified-chemical_excluded.tsv.gz)

### Qualifier key

- **Q1**: `{"biolink:object_aspect_qualifier": "activity_or_abundance", "biolink:object_direction_qualifier": "decreased", "biolink:qualified_predicate": "biolink:causes"}`.
- **Q2**: `{"biolink:subject_form_or_variant_qualifier": "genetic_variant_form"}`.

## Hub participation and position-specific exclusion

For each selected pattern, the audit re-enumerates its supporting pairs. Only fully completed audits enter hub denominators. “Pairs using hub” means at least one witness uses it; “pairs lost” means there is no alternative node at that position. This is position-specific exclusion, not global deletion of the node.

| Hops | Pattern rank (unqualified, chemicals allowed) | Position | Hub | Pairs using hub / audited support | Pairs lost | Pairs remaining |
|---|---:|---:|---|---:|---:|---:|
| 2 | 1 | 1 | Therapeutic procedure (`UMLS:C0087111`) | 1,211 / 2,335 | 710 | 1,625 |
| 2 | 2 | 1 | Therapeutic procedure (`UMLS:C0087111`) | 1,457 / 1,588 | 1,101 | 487 |
| 2 | 3 | 1 | TNF (`NCBIGene:7124`) | 833 / 1,415 | 160 | 1,255 |
| 2 | 4 | 1 | IL10 (`NCBIGene:3586`) | 162 / 1,340 | 13 | 1,327 |
| 2 | 5 | 1 | liver (`UBERON:0002107`) | 353 / 1,226 | 56 | 1,170 |

2-hop hub audit states: `{'complete': 3375}`. Selected distinct signatures: 40.

| Hops | Pattern rank (unqualified, chemicals allowed) | Position | Hub | Pairs using hub / audited support | Pairs lost | Pairs remaining |
|---|---:|---:|---|---:|---:|---:|
| 3 | 1 | 1 | TNF (`NCBIGene:7124`) | 3,356 / 4,073 | 11 | 4,062 |
| 3 | 1 | 2 | disease (`MONDO:0000001`) | 4,047 / 4,073 | 504 | 3,569 |
| 3 | 2 | 1 | TNF (`NCBIGene:7124`) | 3,356 / 3,770 | 228 | 3,542 |
| 3 | 2 | 2 | disease (`MONDO:0000001`) | 3,737 / 3,770 | 955 | 2,815 |
| 3 | 3 | 1 | Therapeutic procedure (`UMLS:C0087111`) | 3,088 / 3,750 | 763 | 2,987 |
| 3 | 3 | 2 | disease (`MONDO:0000001`) | 3,722 / 3,750 | 255 | 3,495 |
| 3 | 4 | 1 | Therapeutic procedure (`UMLS:C0087111`) | 2,936 / 3,731 | 736 | 2,995 |
| 3 | 4 | 2 | disease (`MONDO:0000001`) | 2,504 / 3,731 | 47 | 3,684 |
| 3 | 5 | 1 | TNF (`NCBIGene:7124`) | 3,356 / 3,727 | 230 | 3,497 |
| 3 | 5 | 2 | disease (`MONDO:0000001`) | 3,673 / 3,727 | 813 | 2,914 |

3-hop hub audit states: `{'complete': 4399}`. Selected distinct signatures: 40.


## Relation to BTE and ARAGORN

The leading frequent paths are observations of connectivity, not automatically BTE or ARAGORN treatment rules. BTE’s gene templates require specific variant-form and qualified-predicate constraints or a `has_phenotype` edge. Generic `related_to` or ancestor paths do not establish those conditions. ARAGORN’s ten stored treatment patterns all require a chemical–disease/phenotype edge somewhere in the rule body, so the filtered graph blocks them structurally. Several are conjunctive patterns rather than simple paths. No service-level matching or recovery result is inferred here.

See the [local rule comparison](../../bte-aragorn-drug-disease-recovery/rule-comparison-report.md) for exact templates, qualifiers, directions, and source links.

## Limitations and interpretation

- Broad disease ancestors, procedures, chemical classes, and other hubs can create high pair coverage without providing a specific treatment mechanism.
- Counts across signatures overlap. Their sum is not a unique node-sequence count and not a count of independent pieces of evidence.
- Full qualifier sets can fragment a predicate-level pattern into many context-specific signatures. Qualified catalogs include unqualified-parent IDs for comparison.
- Endpoint survival is not a guarantee of connectivity. Missing endpoints remain in the full-training denominator.
- Partial enumeration biases observed frequency downward, especially for expensive pairs. The completion and audit states must accompany any ranking.
- Both chemical views are derived from the same traversal. For a capped pair, chemical exclusion filters its observed prefix; it is not an independently exhausted restricted search.
- No inference about prediction accuracy or generalization is made from these training-only frequencies. A separate candidate-retrieval evaluation is needed for that.

## Verification

Run verification passed: **True**. Checks: `{'pair_checkpoints': 15372, 'directed_witness_edges': 1864, 'witnesses': 703, 'top_pattern_accounting': 160}`.

Every checkpoint: signature projection and state accounting. Selected witnesses: categories, endpoints, no self-loops, directed predicates, and exact qualifiers checked against read-only graph indexes. Top patterns: support diversity and hub accounting.

The independent fixture tests also check both endpoint orientations against brute-force enumeration, source-duplicate collapse, qualifier separation, self-loop exclusion, missing endpoints, and capped-search status.

[Verification record](runs/training-001/verification.json)

## Pair-coverage versus path-frequency rankings

[Separate ranking tables for all eight conditions](dual-ranking-tables.md) show the leading patterns ordered by distinct pair support and, separately, by supporting node-sequence count. Each table reports both metrics and paths per supported pair. These are re-sorted saved counts, not a new graph traversal.
