# 02 — Check suspicious treatment claims

Started 2026-11-02. First case: naproxen (`CHEBI:7476`) → `biolink:treats` → heart failure (`MONDO:0005252`). Initial focus is DailyMed; FAERS inputs and the upstream Multiomics generation process remain unverified.

## Question and method

Do individual source-asserted approved treatment claims agree with their cited evidence? Following the [Tier 0 analysis](../01-tier0-pair-analysis/README.md), we inspected exact graph records, downloaded the cited DailyMed label, and compared direct section text with the treatment claim. The naproxen–heart failure case is the primary example; saved naproxen–stroke and verapamil–heart failure records are supporting cases, not estimates of error frequency.

## Evidence collected

- [Later parser investigation](../04-parser-investigation/README.md): pinned source, fixtures and executable comparison explain a mechanism consistent with this discrepancy.

- [DailyMed audit of the 1,408 shared approved pairs](../03-dailymed-screening/README.md): all-pair automated screening, label coverage, evidence CSVs and focused manual reviews.

- `evidence/tier0-naproxen-heart-failure.json`: exact edge extracted from Tier 0 1.0.4, edge ID `4fb89be6-3968-36d4-9524-f3b4b40facf0`.
- `dailymed/raw/naproxen-label.zip`: individual-label ZIP downloaded from DailyMed; contains SPL XML and a label image.
- [Original XML fixture](../04-parser-investigation/fixtures/naproxen.xml): the unmodified XML member from that ZIP. The additional local copy under `dailymed/raw/` is ignored by Git; reproduction uses this committed fixture.
- `dailymed/raw/naproxen-history.json`: DailyMed version history.
- `dailymed/raw/bulk-downloads.html`: snapshot of the official bulk download catalog.
- `dailymed/raw/*.headers`: HTTP response headers for each download.
- `dailymed/download-manifest.json`: download URLs, retrieval timestamp and SHA-256 checksums.
- `dailymed/label-sections.json`: section-aware extraction produced by `dailymed/inspect_label.py`.

The raw graph was read from `/home/agonzalez/shepherd/experiments/ultra/data/tier0-1.0.4/raw/edges.jsonl`.

## DailyMed download options

Official references:

- [SPL download resources](https://dailymed.nlm.nih.gov/dailymed/spl-resources.cfm)
- [All drug labels: full releases and periodic ZIP updates](https://dailymed.nlm.nih.gov/dailymed/spl-resources-all-drug-labels.cfm)
- [Web services, individual ZIPs and historical versions](https://dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm)
- [The label cited by the graph edge](https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=1b63177f-17e5-4b5a-8924-7023efe016aa)

Full human prescription and OTC releases are split across multiple ZIP parts; the former single-file RX/OTC releases are no longer provided. Daily, weekly and monthly update ZIPs are also available. The catalog snapshot preserves the available links. Bulk archives have not been downloaded for this initial single-label investigation.

For one label, download the latest ZIP:

```text
https://dailymed.nlm.nih.gov/dailymed/downloadzipfile.cfm?setId=1b63177f-17e5-4b5a-8924-7023efe016aa
```

Get version history:

```text
https://dailymed.nlm.nih.gov/dailymed/services/v2/spls/1b63177f-17e5-4b5a-8924-7023efe016aa/history.json
```

Download a specific version (replace VERSION):

```text
https://dailymed.nlm.nih.gov/dailymed/getFile.cfm?type=zip&setid=1b63177f-17e5-4b5a-8924-7023efe016aa&version=VERSION
```

## Confirmed in the downloaded XML

The downloaded label has set ID `1b63177f-17e5-4b5a-8924-7023efe016aa`, version 8, document ID `e89898f3-afe1-4077-bf15-2621f32ace12`, and effective date `20251009`. DailyMed history reports publication on November 17, 2025. Effective date and publication date are different metadata fields.

| Item | Observation |
|---|---|
| Direct Uses text | Section code `34067-9`, `INDICATIONS & USAGE SECTION`: its direct `<text>` contains toothache but not heart failure. Nested warning sections are excluded from this observation. |
| Warnings | Section code `34071-1`, `WARNINGS SECTION`: contains heart failure in a risk warning. |
| Application number in XML | `ANDA074661` |
| Application number on Tier 0 edge | `NDA017581` |
| Graph approval status | `approved_for_condition` |
| Graph primary source | `infores:multiomics-drugapprovals` |
| Graph supporting sources | `infores:dailymed`, `infores:faers` |

These observations show a discrepancy between the graph assertion and its cited label. They do not establish how the incorrect assertion was generated. Application numbers may have been aggregated across products, but that has not been verified. This downloaded version also has not been established as the version used to generate the Multiomics release.

Reproduce the section extraction from the repository root:

```bash
python experiments/drug-disease-benchmark/troubleshooting-drug-disease-pairs/02-suspicious-pairs/dailymed/inspect_label.py
```

## Open investigation steps

1. Identify the exact Multiomics release and the label version used for this edge.
2. Retrieve relevant historical label versions and compare section text and application numbers.
3. Trace how the upstream process selected `NDA017581` and linked it to this SPL set ID.
4. Inspect the underlying FAERS drug–indication records separately; their existence and interpretation have not yet been verified.
5. The current DAKP parser's nested warning leakage is now reproduced in [stage 04](../04-parser-investigation/README.md). Establish whether the historical pipeline used the same logic; the complete historical edge-generation path remains unverified.

Do not use this case to conclude that all Multiomics pairs are wrong or that every edge carrying an application number is a validated approved indication.

## What question came next?

A discrepancy in one label does not mean every warning mention invalidates a treatment pair. [Stage 03](../03-dailymed-screening/README.md) screens the 1,408 pairs shared by DrugCentral and Multiomics to examine where condition names appear and which cases need contextual review.

The inspection script reads the committed original XML fixture in stage 04, so the command above works offline without the external graph or an ignored XML cache. Historical download manifests retain their original paths and timestamps as provenance; current file locations are documented here.
