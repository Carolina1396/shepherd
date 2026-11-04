# 04 — Trace and reproduce the parser behavior

## GitHub repository and exact version investigated

The upstream code investigated here is **[glusman-team/dakp on GitHub](https://github.com/glusman-team/dakp)**. This repository contains the DAKP pipeline's DailyMed XML extraction and approved-treatment assertion logic.

Our reproduction uses **[commit d0456b3db7468ef3e9c17a7beab01c506249225d](https://github.com/glusman-team/dakp/tree/d0456b3db7468ef3e9c17a7beab01c506249225d)**. The links below point to that fixed version, so later changes to `main` do not change the code being discussed.

| Upstream file at the pinned commit | Role in this investigation |
|---|---|
| [Python DailyMed parser: `spl_xml.py`](https://github.com/glusman-team/dakp/blob/d0456b3db7468ef3e9c17a7beab01c506249225d/src/dakp_pipeline/extract/spl_xml.py) | Classifies sections and collects their text. The direct test calls its extraction entry point. |
| [Section indexing: `evidence.py`](https://github.com/glusman-team/dakp/blob/d0456b3db7468ef3e9c17a7beab01c506249225d/src/dakp_pipeline/assertions/evidence.py) | Shows how indication-section text enters the evidence index; inspected in source. |
| [Treatment assertions: `approved_treats.py`](https://github.com/glusman-team/dakp/blob/d0456b3db7468ef3e9c17a7beab01c506249225d/src/dakp_pipeline/assertions/approved_treats.py) | Contains the condition-support checks. Inspected for context; the direct parser test does not execute this assertion stage. |
| [Go DailyMed parser: `dailymed.go`](https://github.com/glusman-team/dakp/blob/d0456b3db7468ef3e9c17a7beab01c506249225d/go/internal/dailymed/dailymed.go) | Shows the corresponding descendant-text collection; inspected but not executed. |

The complete unmodified repository snapshot is bundled under `upstream/`, with their original [license](upstream/LICENSE). The [manifest](manifest.json) records source URLs and checksums. Our [test_upstream_parser.py](test_upstream_parser.py) calls the upstream extraction entry point directly. This test is our code; the parser and its supporting modules remain unchanged.

Earlier investigation examined [multiomicsKP/drug_approvals_kp](https://github.com/multiomicsKP/drug_approvals_kp). The parser behavior reproduced in this stage comes specifically from **glusman-team/dakp**. We have not established that this pinned version generated the historical Tier 0 edge.

## Question

The [broader label screen](../03-dailymed-screening/README.md) showed that warnings can coexist with valid indications. Why might a warning become indication evidence in one label but stay separate in another? We compared original naproxen and donepezil XML and inspected pinned DAKP extraction code.

## Finding

The pinned DAKP parser classifies SPL sections by LOINC code but collects all descendant text for each section. In the saved naproxen label, a warning is nested under Uses: its text is emitted both in the warning record and in the indication record. In the saved donepezil label, warnings are separate from indications, so the same leakage does not occur.

```text
Naproxen                         Donepezil
Document                         Document
└── Uses [34067-9]               ├── Indications [34067-9]
    ├── Pain relief / fever      │   └── Alzheimer-type dementia
    └── Warnings [34071-1]       └── Warnings [43685-7]
        └── Heart failure risk       └── Seizure risk
```

The [Tier 0 edge](../02-suspicious-pairs/evidence/tier0-naproxen-heart-failure.json) asserts naproxen (`CHEBI:7476`) `biolink:treats` heart failure (`MONDO:0005252`), with `approved_for_condition`. Its primary source is Multiomics Drug Approvals, supporting sources are DailyMed and FAERS, and its cited DailyMed set ID matches the naproxen fixture. Heart failure is a risk in this label, not a stated use.

## Preferred test: run the upstream parser unchanged

`upstream/` contains all 285 original files from the pinned GitHub archive, including the parser, supporting modules, upstream tests, dependency declarations and license. [upstream-snapshot.json](upstream-snapshot.json) records the archive URL and SHA-256 hashes of every file. No upstream file has been patched. The original archive is also included as `dakp-source.tar.gz`: upstream’s own ignore rules hide two planning documents from Git, so extract the archive as shown below to restore the entire snapshot in a fresh checkout. Its archive checksum is in the snapshot manifest.

Our [test_upstream_parser.py](test_upstream_parser.py) is beside the repository snapshot. It imports `dakp_pipeline.extract.spl_xml` normally from `upstream/src`, constructs the real upstream `TaskContext`, and calls **`spl_xml.extract(...)`**, the entry point backed by `SPLXMLExtractor.extract`. It reads the resulting `spl_sections.parquet` with real Polars. There is no AST extraction, mocking, or substitution of upstream record classes in this test.

On Linux with Python **3.12+**, from this directory:

```bash
tar -xzf dakp-source.tar.gz --strip-components=1 -C upstream
python3.12 -m venv .venv-parser
.venv-parser/bin/python -m pip install -r parser-requirements.txt
.venv-parser/bin/python test_upstream_parser.py
```

The four direct import dependencies are pinned from upstream `uv.lock`. This installs the parser's dependencies, not the full Airflow/NER/graph runtime. Environment setup needs package-index access; extraction then runs offline on the two included labels. Full pipeline installation instructions remain in the original [upstream README](upstream/README.md).

| Test | Required correct behavior | Expected result on the pinned parser |
|---|---|---|
| Naproxen | Retain pain/fever uses and the separate warning record, but exclude heart failure from indication text | **FAIL**: nested warning text leaks into indications |
| Donepezil | Retain the Alzheimer indication and separate seizure warning; exclude seizure/convulsion text from indications | **PASS** |

A failure of the naproxen assertion is the bug demonstration. Missing imports or extraction errors are setup/runtime errors and do not demonstrate the bug. The suite intentionally does not mark the naproxen test as an expected failure: a future corrected parser should satisfy both behavior assertions. The snapshot integrity check must be deliberately updated if testing a different upstream revision.

**Verified result:** the direct test was executed on November 3, 2026 with Python 3.12 and the pinned parser dependencies. Donepezil passed. Naproxen failed the intended behavioral assertion:

```text
naproxen: 'heart failure' leaked into LOINC 34067-9 indication output
Ran 2 tests
FAILED (failures=1)
```

This nonzero exit status is the expected bug demonstration, not an import or runtime error. Both tests use the actual upstream extraction output. They check that legitimate indication text and separate warning records are retained. Donepezil's indication occurs in a nested unclassified subsection (`42229-5`), illustrating why removing all nested sections would lose valid content.

## What is bundled

- `fixtures/naproxen.xml`: unmodified XML from the previously downloaded label ZIP, set ID `1b63177f-17e5-4b5a-8924-7023efe016aa`, version 8. The original ZIP and download manifest remain under `../02-suspicious-pairs/dailymed/`.
- `fixtures/donepezil.xml`: unmodified XML decompressed from the audit cache, set ID `03e26183-3e07-45e8-a414-a8bad32483e2`. The fixture is deliberately included outside the ignored cache so a fresh checkout can run the test.
- `upstream/`: the complete unmodified DAKP source snapshot from commit **d0456b3db7468ef3e9c17a7beab01c506249225d**, including its Apache 2.0 license. The direct test imports this snapshot; it does not modify it.
- `manifest.json`: source URLs, pinned upstream commit, packaging timestamp, and SHA-256 hashes. Packaging time is not the original label retrieval time.
- `test_upstream_parser.py`: our direct behavioral test of the original extraction entry point.
- `parser-requirements.txt`: parser dependency versions from upstream `uv.lock`.

## Code path

1. `upstream/src/dakp_pipeline/extract/spl_xml.py`: `_collect_sections` labels the parent with `34067-9` and calls `_all_text(sec)`. `_all_text` uses `itertext()`, including nested warnings.
2. `upstream/src/dakp_pipeline/assertions/evidence.py`: the index places text from `34067-9` records into `indication_docs`.
3. `upstream/src/dakp_pipeline/assertions/approved_treats.py`: `_positive_context_text` removes selected negation phrases, such as “not indicated.” It does not remove the heart-failure risk wording. `_section_mentions_condition` can use a word-bounded condition mention as support.
4. The upstream Go parser also uses all descendant section text (`sec.allText()`); its behavior is inspected in source, not executed by this Python harness.

The test uses the original upstream modules and record classes. It does not execute downstream NER, condition matching, application reconciliation, or graph generation. No AST extraction or dependency mocking is used.

## Scope and remaining questions

**Confirmed by the direct test:** warning-text leakage in the pinned parser on this naproxen XML and absence of that leakage in the donepezil control. The earlier investigation also checked the negation filter; that downstream filter is outside this focused test.

**Not established:** that this exact code/version and label version generated the historical Tier 0 edge. The full historical pipeline has not been reproduced. The label's application is `ANDA074661`, whereas the edge carries `NDA017581`; this discrepancy and the underlying FAERS candidate remain unresolved. Do not interpret this reproduction as proof that all Multiomics treatment assertions are incorrect.

Proposed correction: preserve legitimate indication subsections while excluding nested safety sections from indication text. This package documents the bug; it does not modify upstream DAKP or training labels.

The broader [1,408-pair screening audit](../03-dailymed-screening/README.md) is a separate analysis. Its large label cache is gitignored and is not needed for this reproduction.

## What follows?

The [impact analysis](impact-analysis/README.md) extends this investigation to all 5,095 Multiomics approved treatment pairs. It contains the inventory and a resumable comparison using the same original parser. Its summary reports inspected-label coverage; incomplete runs are not an exhaustive impact count. The two-label test above remains the small verified reproduction.

[Stage 05](../05-conclusions/README.md) separates confirmed findings from historical uncertainties and records implications for benchmark construction.
