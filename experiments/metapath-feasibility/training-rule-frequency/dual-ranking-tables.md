# Meta-path rankings: pair coverage versus path frequency

Run `training-001`; 7,686 training pairs. This re-sorts saved counts; no graph traversal was rerun.

- Pair coverage ranking: distinct training pairs, then node sequences.
- Path-frequency ranking: distinct supporting node sequences, then training pairs.
- Paths/pair is the average across the pairs supporting that signature, not across all training pairs.
- Source duplicates are collapsed. Counts across signatures overlap and should not be summed as unique paths.
- Two-hop counts are exact. Three-hop counts are observed lower bounds because 92 searches were capped; ranks can change.
- Qualifiers distinguish signatures and do not filter paths. No self-loops; exact predicates and full stored category sets.
- Category labels are shortened for display only. Full categories and signature IDs are in the machine-readable tables.

`T` means `treats_or_applied_or_studied_to_treat`. Qualifier codes are defined below. An unlabeled edge in a qualified table has an empty qualifier set.

[Top 20 for all 16 rankings (TSV)](runs/training-001/dual_rankings/top20.tsv) · [Full signature details (JSON)](runs/training-001/dual_rankings/top20.json)

## 2 hops; unqualified; chemical intermediates allowed

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1,588 | 2,292 | 1.44 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease` | 1,415 | 11,491 | 8.12 |
| 4 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1,340 | 12,441 | 9.28 |
| 5 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1,226 | 3,199 | 2.61 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —associated_with→ BiologicalProcess ←genetic_association— Disease` | 304 | 12,929 | 42.53 |
| 2 | `ChemicalEntity —associated_with→ BiologicalProcess —genetic_association→ Disease` | 304 | 12,929 | 42.53 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1,340 | 12,441 | 9.28 |
| 4 | `ChemicalEntity —affects→ Gene/Protein ←condition_associated_with_gene— Disease` | 482 | 11,700 | 24.27 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —gene_associated_with_condition→ Disease` | 482 | 11,700 | 24.27 |

## 2 hops; unqualified; chemical intermediates excluded

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1,588 | 2,292 | 1.44 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease` | 1,415 | 11,491 | 8.12 |
| 4 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1,340 | 12,441 | 9.28 |
| 5 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1,226 | 3,199 | 2.61 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —associated_with→ BiologicalProcess ←genetic_association— Disease` | 304 | 12,929 | 42.53 |
| 2 | `ChemicalEntity —associated_with→ BiologicalProcess —genetic_association→ Disease` | 304 | 12,929 | 42.53 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —associated_with→ Disease` | 1,340 | 12,441 | 9.28 |
| 4 | `ChemicalEntity —affects→ Gene/Protein ←condition_associated_with_gene— Disease` | 482 | 11,700 | 24.27 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —gene_associated_with_condition→ Disease` | 482 | 11,700 | 24.27 |

## 2 hops; qualified; chemical intermediates allowed

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1,588 | 2,292 | 1.44 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1,233 | 8,241 | 6.68 |
| 4 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1,226 | 3,199 | 2.61 |
| 5 | `ChemicalEntity ←has_input— Procedure —in_clinical_trials_for→ Disease` | 1,019 | 2,053 | 2.01 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —associated_with→ BiologicalProcess ←genetic_association— Disease` | 304 | 12,929 | 42.53 |
| 2 | `ChemicalEntity —associated_with→ BiologicalProcess —genetic_association→ Disease` | 304 | 12,929 | 42.53 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1,233 | 8,241 | 6.68 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein ←condition_associated_with_gene— Disease` | 424 | 5,491 | 12.95 |

## 2 hops; qualified; chemical intermediates excluded

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease` | 1,588 | 2,292 | 1.44 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1,233 | 8,241 | 6.68 |
| 4 | `ChemicalEntity —located_in→ AnatomicalEntity ←located_in— Disease` | 1,226 | 3,199 | 2.61 |
| 5 | `ChemicalEntity ←has_input— Procedure —in_clinical_trials_for→ Disease` | 1,019 | 2,053 | 2.01 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —associated_with→ BiologicalProcess ←genetic_association— Disease` | 304 | 12,929 | 42.53 |
| 2 | `ChemicalEntity —associated_with→ BiologicalProcess —genetic_association→ Disease` | 304 | 12,929 | 42.53 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease` | 1,233 | 8,241 | 6.68 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease` | 2,335 | 5,972 | 2.56 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein ←condition_associated_with_gene— Disease` | 424 | 5,491 | 12.95 |

## 3 hops; unqualified; chemical intermediates allowed

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 4,073 | 477,284 | 117.18 |
| 2 | `ChemicalEntity —affects→ Gene/Protein —causes→ Disease ←subclass_of— Disease` | 3,770 | 78,487 | 20.82 |
| 3 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3,750 | 45,574 | 12.15 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3,731 | 58,467 | 15.67 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —affects→ Disease ←subclass_of— Disease` | 3,727 | 87,188 | 23.39 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,689 | 4,021,917 | 1495.69 |
| 2 | `ChemicalEntity —subclass_of→ ChemicalEntity ←subclass_of— Gene/Protein ←condition_associated_with_gene— Disease` | 595 | 3,288,734 | 5527.28 |
| 3 | `ChemicalEntity —subclass_of→ ChemicalEntity ←subclass_of— Gene/Protein —gene_associated_with_condition→ Disease` | 595 | 3,288,734 | 5527.28 |
| 4 | `ChemicalEntity —affects→ Gene/Protein ←affects— Protein —T→ Disease` | 3,019 | 3,043,237 | 1008.03 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —affects→ Gene/Protein —related_to→ Disease` | 1,810 | 1,454,131 | 803.39 |

## 3 hops; unqualified; chemical intermediates excluded

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 4,073 | 477,284 | 117.18 |
| 2 | `ChemicalEntity —affects→ Gene/Protein —causes→ Disease ←subclass_of— Disease` | 3,770 | 78,487 | 20.82 |
| 3 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3,750 | 45,574 | 12.15 |
| 4 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3,731 | 58,467 | 15.67 |
| 5 | `ChemicalEntity —affects→ Gene/Protein —affects→ Disease ←subclass_of— Disease` | 3,727 | 87,188 | 23.39 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,689 | 4,021,917 | 1495.69 |
| 2 | `ChemicalEntity —affects→ Gene/Protein ←affects— Protein —T→ Disease` | 3,019 | 3,043,237 | 1008.03 |
| 3 | `ChemicalEntity —affects→ Gene/Protein —affects→ Gene/Protein —related_to→ Disease` | 1,810 | 1,454,131 | 803.39 |
| 4 | `ChemicalEntity —affects→ Gene/Protein ←affects— Gene/Protein —related_to→ Disease` | 1,837 | 1,366,968 | 744.13 |
| 5 | `ChemicalEntity —affects→ Gene/Protein ←affects— Gene/Protein ←condition_associated_with_gene— Disease` | 592 | 1,188,547 | 2007.68 |

## 3 hops; qualified; chemical intermediates allowed

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 3,809 | 297,178 | 78.02 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3,750 | 45,574 | 12.15 |
| 3 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3,731 | 58,467 | 15.67 |
| 4 | `ChemicalEntity ←has_input— Procedure —causes→ Disease ←subclass_of— Disease` | 3,668 | 32,847 | 8.96 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein —causes[Q2]→ Disease ←subclass_of— Disease` | 3,548 | 50,717 | 14.29 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —subclass_of→ ChemicalEntity ←subclass_of— Gene/Protein ←condition_associated_with_gene— Disease` | 595 | 3,288,734 | 5527.28 |
| 2 | `ChemicalEntity —subclass_of→ ChemicalEntity ←subclass_of— Gene/Protein —gene_associated_with_condition→ Disease` | 595 | 3,288,734 | 5527.28 |
| 3 | `ChemicalEntity —affects[Q1]→ Gene/Protein ←affects[Q1]— Protein —T→ Disease` | 2,732 | 1,476,205 | 540.34 |
| 4 | `ChemicalEntity —affects[Q1]→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,430 | 1,331,445 | 547.92 |
| 5 | `ChemicalEntity —affects[Q3]→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,272 | 1,153,561 | 507.73 |

## 3 hops; qualified; chemical intermediates excluded

### Ranked by pair coverage

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects[Q1]→ Gene/Protein —related_to→ Disease ←subclass_of— Disease` | 3,809 | 297,178 | 78.02 |
| 2 | `ChemicalEntity ←has_input— Procedure —affects→ Disease ←subclass_of— Disease` | 3,750 | 45,574 | 12.15 |
| 3 | `ChemicalEntity ←has_input— Procedure —T→ Disease ←subclass_of— Disease` | 3,731 | 58,467 | 15.67 |
| 4 | `ChemicalEntity ←has_input— Procedure —causes→ Disease ←subclass_of— Disease` | 3,668 | 32,847 | 8.96 |
| 5 | `ChemicalEntity —affects[Q1]→ Gene/Protein —causes[Q2]→ Disease ←subclass_of— Disease` | 3,548 | 50,717 | 14.29 |

### Ranked by path frequency

| Rank | Meta-path | Pairs | Node sequences | Paths/pair |
|---|---|---:|---:|---:|
| 1 | `ChemicalEntity —affects[Q1]→ Gene/Protein ←affects[Q1]— Protein —T→ Disease` | 2,732 | 1,476,205 | 540.34 |
| 2 | `ChemicalEntity —affects[Q1]→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,430 | 1,331,445 | 547.92 |
| 3 | `ChemicalEntity —affects[Q3]→ Gene/Protein —expressed_in→ AnatomicalEntity ←located_in— Disease` | 2,272 | 1,153,561 | 507.73 |
| 4 | `ChemicalEntity —affects[Q1]→ Gene/Protein ←affects[Q3]— Protein —T→ Disease` | 2,700 | 1,065,509 | 394.63 |
| 5 | `ChemicalEntity —associated_with→ BiologicalProcess ←associated_with— Protein —T→ Disease` | 1,582 | 902,190 | 570.28 |

## Exact qualifier sets

- **Q1**: `{"biolink:object_aspect_qualifier": "activity_or_abundance", "biolink:object_direction_qualifier": "decreased", "biolink:qualified_predicate": "biolink:causes"}`.
- **Q2**: `{"biolink:subject_form_or_variant_qualifier": "genetic_variant_form"}`.
- **Q3**: `{"biolink:object_aspect_qualifier": "activity_or_abundance", "biolink:object_direction_qualifier": "increased", "biolink:qualified_predicate": "biolink:causes"}`.
