# Investigating Tier 0 drug–disease treatment claims

We began by examining drug–disease pairs for a treatment benchmark. Approval metadata looked useful for selecting positives, but checking an example exposed a discrepancy: Tier 0 says naproxen treats heart failure, while its cited DailyMed label describes heart failure as a risk. We followed that evidence through a broader label screen and a reproducible investigation of the DAKP parser.

## Read in investigation order

| Stage | Question | Evidence and finding |
|---|---|---|
| [01 — Tier 0 pair analysis](01-tier0-pair-analysis/README.md) | Which pairs could supply approved treatment examples? | Predicate, source, approval and overlap tables define the candidate pool. |
| [02 — Suspicious pairs](02-suspicious-pairs/README.md) | Do the claimed approvals agree with the cited evidence? | Naproxen–heart failure is marked approved, but its cited label describes risk rather than treatment. |
| [03 — DailyMed screening](03-dailymed-screening/README.md) | Does a warning mention always invalidate a treatment pair? | Screening 1,408 shared pairs found 338 with warning mentions; valid indications can also have warnings. |
| [04 — Parser investigation](04-parser-investigation/README.md) | How can warning text enter indication evidence? | Naproxen's nested warning leaks into the extracted indication text; donepezil's separate warning does not. |
| [05 — Conclusions](05-conclusions/README.md) | What can we conclude for the benchmark? | Confirmed parser behavior, remaining historical uncertainties, and proposed next steps. |

These stages organize the evidence logically. They do not imply that every current artifact or control test existed at the beginning of the investigation.

## Reproduction scope

- **Stage 01:** published summary CSVs are included. Regenerating them requires the external Tier 0 1.0.4 raw graph and the existing benchmark scripts.
- **Stage 02:** the saved edge and original XML support an offline label inspection.
- **Stage 03:** saved pair-level results are included. Full re-screening requires the ignored 935-label cache or downloading the selected labels again; later downloads may differ from the saved versions.
- **Stage 04:** a direct test imports the unchanged pinned upstream parser and reads its extracted tables. It requires Python 3.12+ and the documented parser dependencies; extraction runs offline after setup.

Stage 04 also contains a [partial impact analysis and XML-only structure census](04-parser-investigation/impact-analysis/README.md). The parser comparison completed its requested 20% cap; the broader structural census is paused. Its saved checkpoint is explicitly marked partial, with matching example XMLs included for review.

Follow the [stage 04 setup and test instructions](04-parser-investigation/README.md) to run the direct parser test. On the pinned version, donepezil passes and naproxen fails the warning-exclusion assertion, reproducing the bug.

The parser bug is reproduced on the saved label. The complete historical pipeline that generated the Tier 0 edge has not been reproduced. No graph edges or training labels have been corrected by this investigation.
