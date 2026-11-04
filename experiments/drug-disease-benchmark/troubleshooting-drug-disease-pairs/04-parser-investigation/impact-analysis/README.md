# Extend the parser investigation to all Multiomics approved treatment pairs

This analysis belongs to stage 04: it extends the two-label reproduction to the full set of Multiomics `biolink:treats` edges with `clinical_approval_status = approved_for_condition` in Tier 0 1.0.4.

**Current status: both runs are stopped.** The original-parser comparison finished its requested 20% cap; the separate XML-only census was paused by the user. The saved results are partial and must not be described as a complete analysis of all pairs.

| Run | Inspected labels | Finding | State |
|---|---:|---|---|
| Original-parser comparison | 8,286 / 41,430 | 9 pairs lost a match in at least one label; 6 retained no matches across their cited labels | Finished at the requested 20% cap |
| XML-only structure census | 11,492 / 41,430 at the last saved checkpoint | 2 labels with nested warnings; 5 with any nested safety section; 8 failed labels | Paused; checkpoint counts, not final census totals |

The XML-only scan found an additional nested-warning example, **Premjact Male Genital Desensitizer Spray**, after the 20% parser comparison stopped. It has not undergone the larger pair-impact comparison. The five matching original compressed XML documents and checksums are preserved in [structure-examples](structure-examples/manifest.json), so those findings can be inspected offline even without the ignored download cache. The complete cache is not committed, so a fresh checkout cannot reproduce the entire partial census offline.

## Inventory

From the repository root:

```bash
python experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/04-parser-investigation/impact-analysis/extract_candidates.py /path/to/tier0-1.0.4/raw
```

`pairs.json` retains all source edges per normalized pair and their cited DailyMed set IDs. `nodes.json` preserves relevant node metadata. `inventory.json` records coverage of the existing stage 03 label cache. Raw graph files and the cache are external to this subdirectory.

## Comparison method

1. Run the unchanged pinned upstream extraction entry point on each inspected label.
2. Record condition-name/alias matches in its indication output and in nested safety sections.
3. Create a temporary comparison XML that removes nested safety sections from indications while retaining legitimate indication subsections. Run the same unchanged parser on that comparison input. Preserve the original XML and its checksum.
4. Report whether the condition match disappears. Save the relevant label, section codes and text evidence, and distinguish warning text from other safety text.
5. Aggregate by normalized drug–condition pair: whether any other inspected label retains a match, the total cited labels, inspected labels, retrieval failures and completeness of coverage.

The original parser remains unchanged. The altered XML is an experimental comparison, not a replacement of the source evidence or a validated upstream fix. A broad indication can describe a condition using different terminology; absence of a lexical match does not establish absence of an indication.

## Interpretation

- **Exposed to leakage:** matching condition text in a nested safety section enters the original indication output.
- **Observed match depends on nested safety text:** the matching text disappears after removing those sections.
- **Alternative inspected-label match retained:** another inspected cited label still has a match outside the removed text.
- **Incomplete or unresolved evidence:** missing labels, no usable name matches, or incomplete citation coverage prevent a complete label-level conclusion.

These categories measure the extraction mechanism's observed reach. They do not prove clinical nonapproval, historical pipeline causality, or the overall error rate of Tier 0. Warning mentions alone are not errors. Exhaustive cited-label coverage and selected-label coverage must be reported separately.

## Initial cached-label pass (not the exhaustive result)

On November 3, 2026, the initial pass inspected the 935 previously cached labels plus the original naproxen fixture: **936 labels**, covering **3,219 pairs**, with all cited labels inspected for **858 pairs**. One inspected label had coded safety sections nested under indications: the original naproxen label. Seven pairs had matches in that nested safety text; six lost their indication-name matches after removing it, with no alternative match in their inspected citations.

The six pairs were naproxen with **wheezing, chest pain, asthma, stroke disorder, heart failure, and allergy**. Each cites only that label, so the cited-label coverage for these six is complete. They are suspected extraction-dependent claims, not six independent clinical adjudications. The original 935 labels alone had no coded nested safety sections under indications under this detection rule.

The exhaustive download/parse run was started after this initial pass. Use `summary.json` for the most recent saved aggregate; it updates periodically and at completion. `run-status.json` and `run.log` are local runtime files and are not committed. A status file alone does not prove a process is still alive; check the recorded PID when monitoring. The process is resumable, and the `--download` command can be run again after an interruption.

The user subsequently capped this run at **8,286 successfully parsed labels (20% of 41,430)**. Resume with `analyze.py --download --max-labels 8286` to preserve that cap. Cached successful labels count toward the limit; failed retrievals do not. The script saves its final summary before exiting at the limit. This is a partial, nonrandom inspection, not an estimate of the full graph's error rate. Do not use the uncapped download command below unless intentionally extending the run.

## Run the original parser across labels

### Separate XML-only census of nested warnings

After stopping the parser comparison at 20%, a separate structural census was requested for **all 41,430 cited labels**. It does not run DAKP, match disease names or change the stopped parser comparison's outputs. It reuses the downloaded XML and retrieves missing labels with six workers, a shared maximum of four request starts per second, and up to three attempts per missing label.

```bash
python -m unittest test_structure.py
python scan_structure.py --download
```

This uses only Python's standard library. Without `--download`, it scans cached labels and reports missing documents. XML inspection is fast, but completing the census still requires the missing downloads. The scope is the labels cited by our 5,095 pairs, not every product in DailyMed.

`structure-summary.json` reports inspected, failed, pending and missing labels separately. `structure-matches.json` lists matching documents and exact nested section paths. `structure-inventory.json` is written at completion or a graceful pause and includes inspected XML hashes; the first run was terminated before this inventory was written. `structure-failures.json` records failed documents. The original labels are cached for resumption. Updated shutdown handling cancels queued requests on SIGINT/SIGTERM; requests already in flight may take up to their timeout to return. Resumption rechecks cached XML without downloading it again.

The parent must have indication code **34067-9**. A nested section is a coded warning if it has **34066-1**, **34071-1** or **43685-7**. A separate count also accepts a nested section whose title contains “warning” or “warnings.” Broader nested safety counts include precautions and other safety codes; these must not be described as warning-only counts. Words in ordinary body text do not count as structural warning sections, and uncoded parent indication headings are outside this definition.

### Parser comparison (still capped at 20%)

Use the Python 3.12+ environment prepared in the [stage 04 instructions](../README.md). The same four parser dependencies are sufficient. From this directory:

```bash
../.venv-parser/bin/python -m unittest test_comparison.py
../.venv-parser/bin/python analyze.py
../.venv-parser/bin/python analyze.py --download
```

The first analysis command processes available cached labels. The second resumes and retrieves every missing cited label; this can take hours. Original downloads are never replaced by altered comparison XML. The temporary comparison inputs are deleted after parsing. Successfully parsed labels are cached by XML checksum and analysis version, so interrupted runs can resume. Re-run the download command to retry failed retrievals. Downloads use a 0.25-second delay per request and process labels sequentially, including a ZIP fallback for XML API 404s.

`parsed/` and `labels/` are ignored caches. The included original source snapshot is hash-checked before running. Every inspected label goes through the unchanged `spl_xml.extract` entry point. If no nested safety section exists, the unchanged input needs parsing only once. The comparison test checks both labels and verifies that the original XML trees remain intact.

Outputs:

- `summary.json`: current coverage and aggregate counts; timestamps identify partial snapshots.
- `pair-impact.csv`: all 5,095 pairs, inspected/cited label counts, retained and lost condition matches, and coverage completeness.
- `label-evidence.csv`: condition-specific nested-safety matches with normalized excerpts, section codes, and DailyMed links.
- `condition-terms.json`: exact terms used for every condition.
- `failures.json`: unresolved download or parsing failures from the last run.

Name matching uses canonical Tier 0 names, available node synonyms, and the saved equivalent-identifier labels from stage 03 where available. Alias coverage is uneven across the 963 conditions. No new synonym-service request or LLM interpretation is performed. A remaining match is not proof of a valid indication; a missing match is not proof of nonapproval.

Safety removal uses explicit LOINC codes for warnings, contraindications, precautions, adverse reactions, and relevant OTC safety sections. Uncoded safety headings are not removed by this experiment, so its measured scope is conservative with respect to uncoded sections. The broader `nested_safety` count must not be described as a warnings-only count. A label can lose a match while the pair retains a match in another cited label.

The input inventory contains 5,095 pairs, 41,430 distinct cited labels, and three pairs without usable DailyMed citations. The previously downloaded 935 labels cover 3,201 pairs at least once and all citations for 842 pairs. These inventory counts describe starting availability, not completed parser coverage.
