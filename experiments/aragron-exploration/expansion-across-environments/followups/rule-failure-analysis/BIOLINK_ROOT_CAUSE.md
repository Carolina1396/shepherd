# Biolink root cause of the failing treatment rules

Checked 26 October 2026. This note asks whether each of the eleven treatment rules with no paths fails because of a Biolink model change, or because the graph lacks the data. It builds on the per-rule controls in [`tested/`](tested/) and the published-metadata counts in [`upstream_audit.json`](../../../upstream_audit.json).

## Summary

**Six rules (1, 3, 4, 5, 7, 8) fail because of Biolink 4.x changes the rule file never adopted. Five rules (2, 9, 12, 13, 16) fail because Tier 0 lacks the data.** In those five cases the Biolink terms are still valid.

| Rules | Failing edge | Cause | Kind |
|---|---|---|---|
| 1, 3, 4, 5, 7, 8 | `Gene → genetic_association → DiseaseOrPhenotypicFeature` | `genetic_association` is deprecated in Biolink 4.x. Gene–condition links use `gene_associated_with_condition`. | Model change |
| 1 (second edge) | `Gene → affects_response_to → ChemicalEntity` | Renamed `affects_sensitivity_to` in v4.3.3 and moved out from under `affects`. | Model change plus a Retriever version mismatch |
| 2 | `ChemicalEntity → similar_to → ChemicalEntity` | No chemical-similarity edges in Tier 0. | Graph coverage |
| 9 | `BiologicalProcess → has_output → ChemicalEntity` | No `has_output` edges in either direction. | Graph coverage |
| 12, 13, 16 | qualified `affects` on a ChemicalEntity object | No records with the required aspect on a chemical object. | Graph coverage |

Rule 1 has both problems, so fixing one edge will not recover it.

## Model changes

Compared `biolink-model.yaml` at v3.1.2, v4.3.2 and v4.4.6. Changes were located with `git log -S`, and PR numbers came from the GitHub API.

### `genetic_association` deprecated (rules 1, 3, 4, 5, 7, 8)

- **v3.1.2:** canonical predicate, `is_a: related to at instance level`, symmetric.
- **v4.0.0 onward:** `deprecated: true`, `is_a: associated with`. The change landed in [biolink/biolink-model#1418](https://github.com/biolink/biolink-model/pull/1418), "initial documentation and repo hierarchy refactoring", merged 2023-12-04.
- **The 4.x Gene→condition predicate:** `gene_associated_with_condition` (`is_a: genetically associated with`, domain `gene`, range `disease or phenotypic feature`). In v3.1.2 its domain and range were reversed (disease → gene).

Tier 0 published metadata ([`upstream_audit.json`](../../../upstream_audit.json), checked 2026-10-17):

| Predicate | Records | Records with a Gene endpoint |
|---|---:|---:|
| `biolink:genetic_association` | 336,904 | 0 |
| `biolink:gene_associated_with_condition` | 183,456 | 183,456 |

This agrees with the [genetic-association controls](tested/rules-03-04-05-07-08-genetic-association/README.md): the predicate exists, but never with a Gene subject.

### `affects_response_to` renamed (rule 1)

[biolink/biolink-model#1625](https://github.com/biolink/biolink-model/pull/1625), merged 2025-10-31, first released in **v4.3.3**:

- `affects_response_to` → `affects_sensitivity_to`, `response_affected_by` → `sensitivity_affected_by`, and the same for the `increases_`/`decreases_` children.
- The parent changed from `affects` to `related_to_at_instance_level`. The PR explains: "if X affects the sensitivity of Y to Z, X is not actually affecting Z". The new term is not a semantic drop-in.

v4.3.2 still defines `affects_response_to` (see [rule 1](tested/rule-01-affects-response-to/README.md)). The rejection is explained by Retriever's own setup:

- `BioPack-team/retriever` `src/retriever/config/openapi.py` advertises `biolink_version: "4.3.2"`, which is what every response logs.
- Its `uv.lock` pins the `biolink-model` package at **4.4.6**. That was 4.4.3 from "Migrate to TOM 2.0" (2026-08-21), and moved to 4.4.6 in the 2026-10-21 lockfile update.

Retriever validates against a model in which the predicate no longer exists. The exact code path that loads the model for validation has not been traced.

### No model change (rules 2, 9, 12, 13, 16)

- **`similar_to` / `chemically_similar_to`:** unchanged across v3.1.2, v4.3.2 and v4.4.6. In Tier 0 all 76,519 similarity-family records are gene orthology ([rule 2](tested/rule-02-similar-to/README.md)).
- **`has_output`:** only the range widened (`occurrent` → `named thing`). Tier 0 has neither `has_output` nor `is_output_of` ([rule 9](tested/rule-09-has-output/README.md)).
- **`metabolic_processing`, `transport`, `secretion`:** present in the aspect enum in all three versions. 4.x added `gene affects chemical association`, which supports the rules' `BiologicalEntity → affects → ChemicalEntity` direction. The qualified records in Tier 0 have Gene/Protein objects only ([rules 12/13/16](tested/rules-12-13-16-qualified-affects/GRAPH_QUALIFIER_AUDIT.md)).

## Why the rule file is behind

- The rules were mined from ROBOKOP under Biolink 3. In `ranking-agent/aragorn`, `src/rules/AMIE_rules/` files are named `robokop_biolink3_*`, and `src/rules/rules.json` was last changed on 2023-01-27.
- Shepherd's copy, `workers/aragorn_lookup/rules_with_types_cleaned_finalized.json`, has only had rules removed since 2025-05 (Max Wang, Chris Bizon). Predicates were updated by hand only where needed, for example `treats` → `treats_or_applied_or_studied_to_treat`, which did not exist in v3.1.2. The 4.x deprecations were never applied.

## Existing upstream tracking

- [BioPack-team/shepherd#157](https://github.com/BioPack-team/shepherd/issues/157), "Remove invalid predicate from Aragorn rules": open since 2026-09-11, no comments. It covers `affects_response_to` only. Nothing tracks `genetic_association`.

## Proposed next steps (nothing submitted)

1. **Test the predicate swap.** Replace `biolink:genetic_association` with `biolink:gene_associated_with_condition` in rules 3, 4, 5, 7 and 8, then run them against Tier 0 for the ten study targets. If they return paths, propose the change to the Shepherd rules file.
2. **Rule 1.** Comment on #157 with the rename and the change of parent, and ask whether to drop or adapt the rule. Check Tier 0 for `affects_sensitivity_to` records first.
3. **Retriever.** Raise the mismatch between the advertised `biolink_version` and the loaded model.
4. **Rules 2, 9, 12, 13, 16.** These are coverage questions for the graph team, not rule fixes.

## Sources

- `biolink/biolink-model` at tags v3.1.2, v4.3.2 and v4.4.6 (`biolink-model.yaml`), and its git history.
- `ranking-agent/aragorn` at `39f3135`: `src/rules/Notes`, history of `src/rules/rules.json`.
- `BioPack-team/retriever`: `src/retriever/config/openapi.py`, history of `uv.lock`.
- This repository: `workers/aragorn_lookup/rules_with_types_cleaned_finalized.json`, [`upstream_audit.json`](../../../upstream_audit.json).
