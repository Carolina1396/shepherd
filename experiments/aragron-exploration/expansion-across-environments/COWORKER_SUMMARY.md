# ARAGORN treatment-rule investigation

We investigated why several of **ARAGORN’s 18 treatment-inference rules** return no matches. We submitted the same **10 disease/phenotype queries to Dev, CI, Test, and Production**, then inspected the expanded query graphs and retrieval logs.

**All 18 rules were expanded.** Seven (6, 10, 11, 14, 15, 17, and 18) returned matches for at least one target. The remaining eleven fell into three groups: predicate validation rejection, missing supported relationship patterns, and empty traversals.
## What we investigated for each unsuccessful rule

Rules sharing the same failing relationship are grouped below. These follow-ups used isolated queries sent directly to Retriever so that we could change individual constraints and inspect raw results independently of ARAGORN’s answer merging.

| Rule(s) and required relationship | What we investigated | What we found |
|---|---|---|
| **1 — affects_response_to** | Tested the full rule and isolated relationship in Production, retaining or removing endpoint categories. Checked the official Biolink 4.3.2 model and local inventory for the predicate and inspected related predicates. | All five query variants returned **HTTP 422 / invalid predicate**. The predicate exists in the inspected model, but no records were found for the inspected family locally. Removing categories did not fix validation. The deployed validation/model discrepancy remains unresolved. |
| **2 — ChemicalEntity → similar_to → ChemicalEntity** | Tested the full rule and isolated relationship, removing one or both categories. Because the initial pinned chemical pair was not a known positive example, scanned the full local similarity predicate family and joined actual endpoint categories. Selected real Gene/Protein examples for hosted verification. | Retaining either ChemicalEntity restriction produced **missing MetaEdges**; removing both allowed a search but returned zero for that pair. The broader scan found **76,519 records, all orthologous_to**, with no chemical-typed endpoints. **16/16 hosted queries** returned expected edges across Dev, CI, Test, and Production for Gene→Gene, Gene→Protein, Protein→Gene, and Protein→Protein. Requests used similar_to; stored orthologous_to edges matched through predicate expansion. This does not satisfy the rule’s chemical categories. |
| **3, 4, 5, 7, 8 — Gene → genetic_association → DiseaseOrPhenotypicFeature** | Inspected metadata and local records to distinguish predicate absence from a category mismatch. Queried a known BiologicalProcess example with its actual category, with Gene, with the broader BiologicalEntity category, and with the subject category omitted. Then tested nine actual category combinations across environments. | The local graph contained **415,530 genetic_association records**. Metadata contained 79 category combinations but no Gene endpoint. The known example returned with BiologicalProcess, BiologicalEntity, or omitted subject category; requiring Gene produced **missing MetaEdges**. **36/36 cross-environment queries** returned expected edges for BiologicalProcess, Pathway, MolecularActivity, or CellularComponent → Disease or PhenotypicFeature, plus BiologicalProcess → Procedure. The predicate exists; the rules’ Gene-to-condition pattern was unavailable. Metadata also contained gene_associated_with_condition relationships, but we have not validated that predicate as a replacement. |
| **9 — BiologicalProcess → has_output → ChemicalEntity** | Tested the full rule and isolated relationship, removing one or both endpoint categories. Checked the model, hosted metadata, and local inventory for has_output and its inverse is_output_of. | All five variants reported **missing MetaEdges**, including the query with both categories omitted. has_output is valid in the inspected model, but neither predicate appeared in the checked metadata or local inventory. No positive alternative node-type combination was established. |
| **12 — decreased metabolic processing on both affects edges** | Compared the full qualified pattern against qualifier-removal variants; scanned the local graph for explicit aspect/direction values and endpoint types; tested a real qualified edge across environments. | **126 records** carried both exact qualifiers, but all affected objects were Gene/Protein rather than ChemicalEntity. **Pregnenolone → GHRL** (SmallMolecule → Gene) returned its expected edge in Dev, Test, and Production, but not CI. |
| **13 — decreased transport on both affects edges** | Applied the same controls, explicitly distinguishing exact transport annotations from Biolink descendants; tested both an exact-transport example and a secretion example requested as transport. | **69 exact transport records; 1,990 including descendants**, all with Gene/Protein objects. **Potassium atom → SCT** verified exact transport; **Ethinylestradiol → TNF** verified transport matching stored secretion. Both examples returned in Dev, Test, and Production, but not CI. |
| **16 — increased secretion on both affects edges** | Applied the same qualifier-removal controls, local inventory, endpoint-category checks, and hosted positive-example tests. | **4,880 records** carried both exact qualifiers, all with Gene/Protein objects. **Astemizole → HEXB** returned its expected edge in Dev, Test, and Production, but not CI. No matching local record had the ChemicalEntity object required by the rule. |

## What the logs actually say

**Rule 1 — validation rejection:**

```text
Validation Error: Edge edge_0 has invalid predicates: ['biolink:affects_response_to']
```

**Rules 2, 3, 4, 5, 7, 8, and 9 — unsupported relationship pattern:**

```text
MetaEdges could not be found for the following QEdge
```

This means Retriever could not select the required **subject category–predicate–object category combination** from its metadata. It does not necessarily mean the predicate is globally absent. The tested missing-MetaEdge responses used HTTP 200, so HTTP success alone does not establish a successful traversal.

**Rules 12, 13, and 16 — empty traversal:**

```text
Found no edge matches, returning 0 results.
Found 0 complete paths
```

In the inspected Development q01 callbacks, supporting chemical–disease relationships were found, but the qualified BiologicalEntity → affects → supporting chemical step returned zero matches. The other affects edge was not reached. These are empty-search messages, not validation errors.

## What we learned about the qualifiers

Rules 12, 13, and 16 require the same biological entity to affect both a candidate chemical and a supporting chemical connected to the disease. **Both affects edges** require the rule’s object-aspect and object-direction qualifiers.

| Rule | Required object aspect and direction | Matching local edge records |
|---|---|---:|
| **12** | `metabolic_processing` + `decreased` | **126** |
| **13** | `transport` + `decreased` | **69 exact; 1,990 including descendants** |
| **16** | `secretion` + `increased` | **4,880** |

These counts require both qualifiers on the same edge. Rule 13’s total includes 69 transport, 1,813 secretion, and 108 uptake records, all decreased. **None had the ChemicalEntity objects required by the rules.** These are edge-record counts, not complete rule paths or distinct treatments.

We verified real **SmallMolecule → affects → Gene** examples: Pregnenolone → GHRL (decreased metabolic processing), potassium atom → SCT (decreased transport), Ethinylestradiol → TNF (decreased secretion, matching a transport request), and Astemizole → HEXB (increased secretion). All four returned their expected edges in **Dev, Test, and Production**. CI returned zero for all four examples even after removing qualifiers in four additional controls. In one control, logs showed four intermediate affects matches eliminated at an object-subclass join: `No valid paths found after joining edge 'o_subclass_edge'`. This identifies where paths were lost, but not the underlying cause or whether the expected edge was among those intermediate matches.

For **pheochromocytoma**, removing qualifiers from the full isolated patterns changed retrieval from **zero to 27,984 raw result records per environment** in CI, Test, and Production. Across 48 requests, we also retained qualifiers on only one affects edge at a time; each such pattern still returned zero. Separate positive/negative controls on a known SRPK2 → affects → Doxorubicin edge demonstrated qualifier enforcement for that tested edge. Development’s original constraint-format warnings require separate interpretation; empty-path logs alone do not prove qualifier enforcement.

## Complete rule graphs and the relationships that failed

The following reference includes **every edge in each saved template**, including treatment edges already required by some rules. Each row is a complete graph: all listed edges must hold together, and repeated node labels refer to the same query node. Arrows preserve the template direction; they do not indicate search order.

**Labels:** C = candidate ChemicalEntity; D = query DiseaseOrPhenotypicFeature; S = supporting ChemicalEntity; G = Gene; B = BiologicalEntity; P = BiologicalProcess; X = additional Disease. `T` abbreviates `treats_or_applied_or_studied_to_treat`; plain `treats` remains distinct. Qualifier brackets give object aspect and, where requested, object direction. The `biolink:` prefix is omitted for readability.

**Bold edges** mark the specific rejected or locally unavailable pattern. Other edges are not automatically confirmed present: rejection or early stopping can prevent their evaluation. For rules 12/13/16, highlighting both affects edges reflects the later local inventory; the original q01 traversal stopped at the supporting-chemical edge without reaching the candidate edge.

| Rule | Complete required graph (all edges) | What failed or was found |
|---|---|---|
| **1** | **G → affects_response_to → C**<br>C → T → D<br>G → genetic_association → D | Invalid-predicate rejection on affects_response_to. The graph also requires Gene → genetic_association → D, the unsupported pattern investigated in rules 3/4/5/7/8; this does not mean rule 1 progressed to that check. |
| **2** | C → T → D<br>S → T → D<br>**C → similar_to → S** | Missing MetaEdge for chemical similarity; successful alternatives connected Gene/Protein nodes. |
| **3** | C → T → D<br>**G → genetic_association → D**<br>C → interacts_with → G | Missing MetaEdge for Gene → genetic_association → D; positive examples used other subject categories. |
| **4** | G → affects [activity_or_abundance] → C<br>C → T → D<br>**G → genetic_association → D** | Missing MetaEdge for Gene → genetic_association → D; positive examples used other subject categories. |
| **5** | C → T → D<br>**G → genetic_association → D**<br>C → affects [secretion, increased] → G | Missing MetaEdge for Gene → genetic_association → D; positive examples used other subject categories. |
| **6** | C → T → D<br>C → T → X<br>X → has_phenotype → D | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **7** | C → T → D<br>**G → genetic_association → D**<br>C → affects [transport, decreased] → G | Missing MetaEdge for Gene → genetic_association → D; positive examples used other subject categories. |
| **8** | C → T → D<br>**G → genetic_association → D**<br>C → affects [molecular_interaction, decreased] → G | Missing MetaEdge for Gene → genetic_association → D; positive examples used other subject categories. |
| **9** | S → T → D<br>**P → has_output → C**<br>**P → has_output → S** | Missing MetaEdge for BiologicalProcess → has_output → ChemicalEntity; both branches require that pattern. |
| **10** | C → T → X<br>X → has_phenotype → D<br>D → has_phenotype → X | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **11** | S → treats → D<br>B → affects [activity_or_abundance, decreased] → C<br>B → affects [activity_or_abundance, decreased] → S | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **12** | S → T → D<br>**B → affects [metabolic_processing, decreased] → C**<br>**B → affects [metabolic_processing, decreased] → S** | Empty traversal. Later local inventory found no edges with this qualifier pair and ChemicalEntity object; positive examples affected Gene/Protein objects. |
| **13** | S → T → D<br>**B → affects [transport, decreased] → C**<br>**B → affects [transport, decreased] → S** | Empty traversal. Later local inventory found no edges with this qualifier pair and ChemicalEntity object; positive examples affected Gene/Protein objects. |
| **14** | X → positively_correlated_with → D<br>C → treats → X | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **15** | S → T → D<br>B → affects [abundance, increased] → S<br>B → affects [activity_or_abundance, increased] → C | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **16** | S → T → D<br>**B → affects [secretion, increased] → C**<br>**B → affects [secretion, increased] → S** | Empty traversal. Later local inventory found no edges with this qualifier pair and ChemicalEntity object; positive examples affected Gene/Protein objects. |
| **17** | S → treats → D<br>B → affects [activity, increased] → C<br>B → affects [activity_or_abundance, increased] → S | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |
| **18** | S → T → D<br>B → affects [abundance, increased] → C<br>B → affects [activity_or_abundance, increased] → S | Complete matches returned for at least one of the ten targets; no universally failing edge identified. |

Source: [saved ARAGORN rule templates](../../../workers/aragorn_lookup/rules_with_types_cleaned_finalized.json), numbered in their stored treats-rule order. This is the template topology, not a claim that every possible target or deployed version produces the same result.

## Interpretation and limits

ARAGORN is expanding the rules, but several requirements do not align with the available graph relationships or validation behavior. The required qualifiers are **not globally missing**; they occur on different object types in the downloaded graph.

The local inventory examined Tier 0 release `2026_06_21`; hosted follow-ups reported the same release label. This does not prove identical backend contents. Successful alternative examples establish retrieval of individual stored edges, not full ARAGORN rule recovery or biologically valid replacements. We have not established when the mismatches arose, whether the rules worked on older releases, or whether changing their requirements would preserve their intended meaning.

Full methods, saved evidence, and remaining questions: [detailed report](REPORT.md) and [systematic follow-up investigations](followups/rule-failure-analysis/README.md).
