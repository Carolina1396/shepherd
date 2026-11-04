# 03 — Screen DailyMed labels for shared approved pairs

Date: November 2, 2026. Graph: Translator Tier 0 1.0.4.

## Question

After the [suspicious-label check](../02-suspicious-pairs/README.md), we asked whether condition mentions in warnings necessarily undermine approved treatment claims. We selected the 1,408 exact normalized pairs shared by DrugCentral and Multiomics for a broader screen. Source overlap defines this candidate subset; it is not a validation guarantee.

**The overlap does not eliminate warning mentions.** The screen found condition-name matches in explicit warning sections for **338 of the 1,408 pairs**. Across the broader safety category, **735 pairs** had matches in both indications and safety sections, and **2** had safety matches without an indication-name match. Safety mentions are not inherently evidence against an indication.

This is a completed automated section-location screen of every shared pair using selected cited labels, with seven focused manual case reviews. It is **not** a completed clinical validation of all pairs or an exhaustive audit of all cited labels.

## Scope and coverage

| Measure | Count |
|---|---:|
| Pairs marked `treats` and `approved_for_condition` by both DrugCentral and Multiomics | 1,408 |
| Unique drugs | 729 |
| Unique conditions | 421 |
| Distinct DailyMed set IDs cited across these pairs | 28,869 |
| Selected label documents successfully retrieved | 935 |
| Pairs with at least one cited label screened | 1,408 |
| Pairs for which all cited set IDs were screened | 365 |
| Pairs with only a subset of cited set IDs screened | 1,043 |
| Manually reviewed pairs | 7 |

Initial set-cover selection used 814 labels to cover all pairs. For 118 initially unresolved pairs, selection was expanded toward three cited labels per pair where available, adding 121 distinct labels. Selected labels can cover multiple pairs. The saved set-ID lists preserve the actual selections; this is not a random or representative sample of all DailyMed labels.

The API's XML route returned 404 for 36 initial labels; the official label ZIP endpoint recovered all 36. Final retrieval coverage is 935/935. Labels are stored compressed in `labels/`, with individual metadata and SHA-256 checksums; the cache is gitignored. [label-manifest.csv](label-manifest.csv) preserves a trackable inventory.

## Automated findings

| Condition name or accepted alias found in selected labels | Pairs |
|---|---:|
| Indications and safety sections | 735 |
| Indications, without a safety-section match | 576 |
| Safety sections, without an indication-section match | 2 |
| Other sections only | 5 |
| No condition-name match | 90 |
| **Total** | **1,408** |

“Safety” includes warnings, precautions, contraindications and adverse reactions, including relevant OTC sections. The **338 warning-section pairs** are a narrower subset of the safety matches, not an additional category. A condition mentioned as a trial population in adverse reactions is also a safety-section text match; it does not imply the drug causes that condition.

The 1,311 pairs with indication-section matches are **not automatically validated positives**. Matching may occur in limitations of use, adverse-effect discussion, references to other treatments, or an overly broad condition mapping. Conversely, no match can result from terminology differences, missing synonyms, wording or incomplete label coverage; it is not evidence that a pair is unapproved.

## Manually checked examples

| Pair | Label context | Interpretation |
|---|---|---|
| Carvedilol–heart failure | Section 1.1 indicates treatment of specified chronic heart failure; section 5.4 warns of worsening heart failure/fluid retention during dose up-titration. | A legitimate indication and a warning can coexist for the same condition. |
| Diltiazem–atrial fibrillation | Injection label indicates temporary ventricular-rate control, but contraindicates use with an accessory bypass tract, such as WPW. | Formulation, purpose and patient restrictions matter. |
| Voriconazole–esophageal candidiasis | Explicit indication with age restrictions; also mentioned in adverse-reaction trial-population discussion. | A safety-section mention does not contradict an indication. |
| Ciprofloxacin–arthropathy | The matching passage within section 1.11 describes arthropathy in juvenile animals as an adverse effect. | A verified misleading indication-section match, despite both graph sources marking the pair approved. Generic arthropathy versus separately indicated bone/joint infections also needs mapping review. |
| Liothyronine–congenital hypothyroidism | Broad indication for hypothyroidism, with exceptions; a specific congenital-hypothyroidism dosing subsection. | The precise name does not match the indications wording. This is not a demonstrated invalid indication. |
| Selpercatinib–medullary thyroid gland carcinoma | Section 1.2 explicitly indicates specified RET-mutant medullary thyroid **cancer**; the alias set matched **carcinoma** only in warnings. | Terminology false negative; mutation, stage and age restrictions remain important. |
| Aflibercept–retinopathy of prematurity | Condition is an indication subsection heading and has specific dosing. | Retaining title-only sections resolved an initial parser false negative. |

The two final automated safety-without-indication-name cases are **liothyronine–congenital hypothyroidism** and **selpercatinib–medullary thyroid gland carcinoma**. Both have relevant indication support on contextual review, as described above. They must not be counted as two confirmed errors.

Ciprofloxacin–arthropathy is a different kind of concern: three inspected labels contain adverse-effect text inside indications sections. One was reviewed in detail. Both graph edges assert approval, but that passage does not support a generic arthropathy treatment claim. The drug also has bone/joint infection indications, so this finding does not by itself adjudicate every possible use or all 261 cited labels.

Direct label references:

- [Carvedilol](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=010290af-81f4-0037-e063-6394a90a4638)
- [Diltiazem](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=3f2942d7-f4d0-2d77-e063-6294a90a74ad)
- [Voriconazole](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=08d08721-1f4c-478a-8abf-d9c402d50553)
- [Ciprofloxacin](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=043e4beb-5dc0-2fdb-e063-6294a90afded)
- [Liothyronine](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=4a8f7bf4-fa8f-4cde-9be2-11d5a4e6f07f)
- [Selpercatinib](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=7fa848ba-a59c-4144-9f52-64d090f4d828)
- [Aflibercept](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=f96cfd69-da34-41ee-90a9-610a4655cd1c)

## Method and limits

1. Extract exact shared subject/object IDs from raw edges, requiring `biolink:treats`, `approved_for_condition` and the relevant primary source on both sides. Save both complete edges for every pair in [pairs.json](pairs.json).
2. Select cited DailyMed set IDs to cover every pair, then expand unresolved cases. Download current/last-served SPL XML from the [official DailyMed API](https://dailymed.nlm.nih.gov/dailymed/webservices-help/v2/spls_setid_api.cfm), with an [official ZIP fallback](https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm). Requests are rate-limited and cached.
3. Search canonical condition names and equivalent-identifier labels from Translator Node Normalization. Only identifiers already in the Tier 0 node's equivalence list are accepted. The request, response and [alias provenance](alias-provenance.json) are saved. Current labels for those identifiers can still differ from historical terminology.
4. Normalize case, punctuation, accents and possessive disease names; match whole phrases of at least four normalized characters. No fuzzy matching, ontology-ancestor expansion or automatic negation adjudication is performed.
5. Preserve XML section codes, headings and inherited parent-section context, including headings without a text body. Match headings plus body text and retain the matching passage and label URL.
6. Record manual reviews separately from automated categories. A manual disposition is limited to the specified label(s), not all evidence for the pair.

The audit uses documents served now, not a reconstruction of the exact Multiomics input release. **12 downloaded labels have effective dates later than the Tier 0 release date of October 18, 2026.** Historical versions, routes, formulations, combination products, populations and label restrictions need review before constructing a regulatory gold standard. No graph edges or training labels were changed.

## Files to use for decisions

- [pair-screen.csv](pair-screen.csv): one row per pair, category, coverage, condition aliases, graph IDs, FDA numbers and manual-review notes.
- [mention-evidence.csv](mention-evidence.csv): matching section headings, codes, normalized excerpts and DailyMed links. It records one representative match per matching section, not all occurrences.
- [review-queue.csv](review-queue.csv): 98 rows—97 without an indication-name match plus ciprofloxacin–arthropathy. Two of the 97 already have contextual-review explanations; do not count every queue entry as an error. Other indication matches can still need review.
- [manual-review.json](manual-review.json): seven reviewed cases and scope-qualified conclusions.
- [reviewed-case-evidence.json](reviewed-case-evidence.json): full graph pairs and indication sections for the reviewed labels.
- [summary.json](summary.json): machine-readable counts.
- [label-manifest.csv](label-manifest.csv): source URLs, versions, dates and checksums.

For a training decision, the useful next step is context review of indications, starting with the flagged example and unresolved wording cases. Excluding every pair that appears in a warning would discard valid indications; accepting every indication-section string match would admit misleading passages.

## Reproduction

From the repository root, using the saved inputs and cached labels:

```bash
python experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/03-dailymed-screening/audit.py screen
python experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/03-dailymed-screening/audit.py export
python -m unittest discover -s experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/03-dailymed-screening -p test_audit.py
```

`audit.py extract` recreates shared pairs from the raw graph; `fetch` retrieves the saved selected-label list, skipping cached successes. `select` and `expand` allow a new selection experiment and will overwrite selection files; retain the supplied lists to reproduce this run. Re-fetching later can return changed label versions, so compare checksums. Tests cover nested sections, warnings versus indications, title-only sections, possessive names and the original naproxen control case.

## Reproduction prerequisites and next question

`audit.py` requires Python 3.10+ and `requests` (`python -m pip install requests`). The saved result CSVs and JSONs can be read without running code. Tests use the committed naproxen fixture in stage 04 and do not need the label cache.

The `screen` and `export` commands above require `labels/`, an ignored cache of 935 XML documents and metadata. On a fresh checkout, `python experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/03-dailymed-screening/audit.py fetch` retrieves the saved selection over the network. Compare downloaded hashes with the committed label manifest before interpreting a new run as a historical reproduction; server versions can change. Only `extract` needs the external raw graph (`--raw /path/to/raw`).

The screen showed why warning mentions alone cannot identify extraction errors. [Stage 04](../04-parser-investigation/README.md) then compares the naproxen and donepezil XML hierarchies and reproduces the current parser's treatment of nested text. Our screening parser and the upstream DAKP parser are different implementations; this screen does not estimate how many graph edges were caused by the upstream bug.
