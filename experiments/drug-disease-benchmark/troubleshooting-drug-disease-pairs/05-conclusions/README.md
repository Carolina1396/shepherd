# 05 — Conclusions and remaining work

## What did the investigation establish?

| Evidence | Conclusion | Limit |
|---|---|---|
| [Tier 0 summaries](../01-tier0-pair-analysis/README.md) | Approval fields and source overlap define candidate training pairs. | They do not independently validate condition-specific approval. |
| [Naproxen edge and cited label](../02-suspicious-pairs/README.md) | The examined label does not support treating heart failure; it describes risk. | The historical label version and complete upstream evidence remain unverified. |
| [Shared-pair screening](../03-dailymed-screening/README.md) | Warning mentions occur alongside valid indications. | The 338 warning matches are not 338 errors; this is lexical screening of selected labels. |
| [Pinned parser reproduction](../04-parser-investigation/README.md) | Nested warning text enters the extracted naproxen indication text. Donepezil's separate warning stays out. | The direct test runs the original extraction entry point; the earlier negation-filter check, downstream approval logic and historical graph generation are outside its scope. |

## Implications for the benchmark

The [expanded stage 04 analysis](../04-parser-investigation/impact-analysis/README.md) stopped at 8,286 parsed labels (20% of citations). Nine pairs lost a name match in at least one label; six naproxen pairs retained no matches across their complete cited-label sets. A separate XML-only scan was paused at a checkpoint of 11,492 labels, with two nested-warning documents and five nested-safety documents. The two runs have different scopes and denominators. Neither constitutes an exhaustive error count or a representative estimate of error prevalence.

Do not reject every pair mentioned in a warning. Do not accept a pair solely because it has `approved_for_condition`, an FDA application number, source agreement, or an indication-section name match. Preserve those fields as provenance and distinguish source-asserted approval from independently checked label support. Unresolved or excluded positives should not automatically become negative training examples.

## Proposed correction and open work

1. Exclude nested safety sections when collecting indication text, while retaining legitimate indication subsections. Donepezil demonstrates why removing every nested section would lose valid content.
2. Test an upstream correction on the bundled cases and a broader set of SPL layouts. No upstream fix is included here.
3. Identify the exact code and input versions used for the historical Multiomics edge; replay the full path if those inputs can be recovered.
4. Resolve the application discrepancy: the examined XML carries `ANDA074661`, whereas the Tier 0 edge carries `NDA017581`.
5. Inspect the relevant FAERS candidate and determine how it was linked to the application and label.
6. Measure the effect of corrected extraction before deciding which benchmark pairs to remove or retain.

## Review or reproduce the evidence

Follow the [main investigation index](../README.md) for the full sequence, or run the [offline parser comparison](../04-parser-investigation/README.md). Its checksums, fixtures and direct behavioral assertions make the confirmed finding independently reviewable. The case does not establish an overall error rate for Multiomics or Tier 0.
