"""Render a local Markdown report from the completed frequency run artifacts."""
import argparse
from collections import Counter
import csv
import gzip
import json
from pathlib import Path
import statistics


def short_category(categories):
    names = {c.removeprefix('biolink:') for c in categories}
    if {'Gene', 'Protein'} <= names:
        return 'Gene/Protein'
    for name in ('ChemicalEntity', 'Gene', 'Protein', 'Procedure', 'OrganismTaxon',
                 'Disease', 'PhenotypicFeature', 'BiologicalProcess', 'Pathway',
                 'AnatomicalEntity', 'Cell', 'MolecularActivity', 'MolecularEntity'):
        if name in names:
            return name
    return '/'.join(sorted(names - {'NamedThing'})) or 'NamedThing'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    run, out = args.run, args.out
    m = json.loads((run / 'manifest.json').read_text())
    summaries = {h: json.loads((run / f'{h}hop/summary.json').read_text()) for h in (2, 3)}
    statuses = {h: json.loads((run / f'{h}hop/pair_status.json').read_text()) for h in (2, 3)}
    uncertain_pairs = {h: {r['pair_index'] for r in statuses[h]
                           if r['state'] not in ('complete', 'missing_endpoint')} for h in (2, 3)}
    relative = Path(__import__('os').path.relpath(run, out.parent))
    lines = ['# Training drug–disease meta-path frequency', '',
             f'Run: `{run.name}`. Analysis date: 2026-11-12.', '',
             'This is a descriptive study of candidate rule structures on known training pairs. '
             'It is not a candidate-retrieval, precision, or held-out prediction evaluation.', '',
             '## Inputs and traversal', '',
             f'- All **{m["training_pairs"]:,}** DrugCentral training pairs were scheduled; '
             f'**{m["present_pairs"]:,}** have both endpoints in the filtered graph and '
             f'**{m["missing_pairs"]:,}** have a missing endpoint.',
             '- Graph: `artifacts/gandalf_no_drug_disease/` (1,685,344 nodes; 27,435,282 edges). '
             'Every chemical–disease/phenotype edge has been removed, regardless of direction, source, or predicate.',
             '- Read-only Gandalf mmap/LMDB indexes; custom traversal, not the Gandalf HTTP service. '
             'No validation or test labels, entity normalization, predicate hierarchy expansion, or inference.',
             '- Both edge directions are traversed, with original assertion arrows retained. No self-loops. '
             'Repeated nonadjacent nodes are allowed, but cannot add 2/3-hop walks here without a direct endpoint edge.',
             '- Signatures preserve complete stored category sets. Source duplicates are collapsed. '
             'Qualified signatures preserve the full qualifier set; unqualified signatures omit qualifiers.',
             '- Chemical exclusion matches any stored Drug, ChemicalEntity, SmallMolecule, MolecularMixture, '
             'ChemicalMixture, or ComplexMolecularMixture category on intermediate nodes only. '
             'This includes metabolites and broad chemical classes.',
             f'- [Frozen manifest]({relative}/manifest.json), [method and commands](README.txt), '
             '[analysis script](analyze.py), [fixture checks](test_analysis.py).', '',
             '## Completion and coverage', '',
             '| Hops | Complete surviving pairs | Missing endpoints | Incomplete/unprocessed pairs |',
             '|---|---:|---:|---:|']
    overall = ['## Overall summary: connected in 2 or 3 hops', '',
               'Count each training pair once if it has a two-hop OR a three-hop path under the '
               'same conditions. Show both all-training and surviving-endpoint denominators.', '',
               '| Chemical intermediates | Qualifier handling | 2 hops | 3 hops | Overall: 2 or 3 hops / all training pairs | Overall / searchable pairs |',
               '|---|---|---:|---:|---:|---:|']
    overlap_notes = []
    for view, field in [('Allowed', 'node_sequences'), ('Excluded', 'no_chemical_node_sequences')]:
        connected = {h: {r['pair_index'] for r in statuses[h] if r.get(field, 0) > 0} for h in (2, 3)}
        two, three = connected[2], connected[3]
        union = two | three
        for qualifiers in ['Ignored', 'Retained in signatures']:
            overall.append(f'| {view} | {qualifiers} | {len(two):,} | {len(three):,} | '
                           f'**{len(union):,} / {m["training_pairs"]:,} = {100*len(union)/m["training_pairs"]:.2f}%** | '
                           f'**{len(union):,} / {m["present_pairs"]:,} = {100*len(union)/m["present_pairs"]:.2f}%** |')
        overlap_notes.append(f'Chemicals {view.lower()}: {len(two & three):,} pairs connect at both hop '
                             f'lengths; {len(three-two):,} additional pairs connect at three hops; '
                             f'{len(two-three):,} connect only at two hops.')
    overall += ['', *overlap_notes, '',
                'Qualifier handling changes how signatures are distinguished, not which paths are retained. '
                'All qualifier variants, including empty qualifier sets, remain available; no qualifier '
                'constraints are imposed. These are connectivity totals, not prediction accuracy. '
                'See completion details below for exactness and bounds.', '']
    where = lines.index('## Inputs and traversal')
    lines[where:where] = overall
    endpoint_audit = run / 'endpoint_audit.json'
    if endpoint_audit.exists():
        audit = json.loads(endpoint_audit.read_text())
        counts = audit['pair_counts']
        endpoint_lines = ['## Important: endpoint availability after filtering', '',
                          'Graph filtering removed chemical–disease/phenotype edges and then removed '
                          'nodes with no remaining edges. Missing endpoints here mean nodes absent from '
                          'the filtered graph, not missing benchmark CSV fields or a traversal failure.', '',
                          '| Endpoint status in the filtered graph | Training pairs |', '|---|---:|']
        for label, key in [('Both endpoints present (searchable)', 'both_present'),
                           ('Disease only missing', 'disease_only_missing'),
                           ('Drug only missing', 'drug_only_missing'), ('Both missing', 'both_missing')]:
            endpoint_lines.append(f'| {label} | {counts.get(key, 0):,} |')
        endpoint_lines += [f'| Total with at least one missing endpoint | {m["missing_pairs"]:,} |',
                           f'| Total training pairs | {m["training_pairs"]:,} |', '',
                           f'These affected pairs involve {audit["unique_missing_drugs"]:,} distinct missing '
                           f'drug nodes and {audit["unique_missing_diseases"]:,} distinct missing disease nodes. '
                           f'Pairs with an absent endpoint in the original graph: '
                           f'**{audit["pairs_with_missing_endpoint_in_original"]:,}**. '
                           'A missing node can affect multiple pairs. Searchable means both endpoints '
                           'survive, not that a connecting path is guaranteed. Keeping isolated nodes '
                           'would not restore connectivity because they have no retained edges.', '',
                           f'[Read-only endpoint audit]({relative}/endpoint_audit.json)', '']
        where = lines.index('## Overall summary: connected in 2 or 3 hops')
        lines[where:where] = endpoint_lines
    for h, s in summaries.items():
        st = s['states']
        partial = sum(v for k, v in st.items() if k not in ('complete', 'missing_endpoint'))
        lines.append(f'| {h} | {st.get("complete", 0):,} | {st.get("missing_endpoint", 0):,} | {partial:,} |')
    lines += ['', 'Bounds: 2-hop searches allow 30 s, 20 million scanned edges, 1 million node sequences, '
              'and 500,000 signatures per qualifier form per pair. Three-hop searches allow 5 s, '
              '5 million edges, 100,000 node sequences, and 100,000 signatures. Checks occur between '
              'operations; these are not hard process timeouts. Partial pairs are preserved as lower bounds.', '',
              '| Hops | Chemical intermediates | Qualifiers | Observed signatures | Connected training pairs | All training coverage | Surviving-endpoint coverage |',
              '|---|---|---|---:|---:|---:|---:|']
    for h, s in summaries.items():
        for v in s['views']:
            lines.append(f'| {h} | {v["view"].removeprefix("chemical_")} | '
                         f'{"with" if v["qualified"] else "without"} | {v["signatures_observed"]:,} | '
                         f'{v["pairs_connected_observed"]:,} | {100*v["coverage_all_training_lower_bound"]:.2f}% | '
                         f'{100*v["coverage_present_lower_bound"]:.2f}% |')
    lines += ['', 'Signature counts and individual-pattern support are exact when all surviving pairs '
              'completed; otherwise they are observed lower bounds. The full TSVs distinguish support from complete pairs from support '
              'observed across all processed pairs. Rankings may change if incomplete searches are completed.', '',
              'Two-hop chemical exclusion makes no difference: a chemical intermediate would require '
              'an edge to the disease endpoint, which graph cleaning removed.', '', '## Three-hop cost pilot', '']
    partial = len(uncertain_pairs[3])
    views3 = summaries[3]['views']
    if all(v['pairs_connected_observed']-v['pairs_connected_complete'] == partial for v in views3):
        allowed, excluded = [v['pairs_connected_observed'] for v in views3 if not v['qualified']]
        paragraph = (f'All {partial:,} incomplete three-hop pairs already have a connection in both '
                     f'chemical views, and every other surviving pair was exhaustively searched. '
                     f'Therefore pair-level existence totals ({allowed:,} allowed; {excluded:,} excluded) '
                     f'are exact despite incomplete signature enumeration. The difference is '
                     f'{allowed-excluded:,} pairs whose three-hop connectivity requires a chemical '
                     f'intermediate under these semantics.')
        where = lines.index('## Three-hop cost pilot')
        lines[where:where] = [paragraph, '']
    pilot = json.loads((run / '3hop/pilot.json').read_text())
    times = [r['seconds'] for r in pilot['records']]
    lines += [f'The 32-pair pilot sampled eight pairs from each quartile of endpoint degree product '
              f'(seed 42). States: `{dict(Counter(r["state"] for r in pilot["records"]))}`. '
              f'Pair enumeration median: {statistics.median(times):.4f} s; maximum: {max(times):.4f} s. '
              'This is a stratified cost probe, not a random performance sample. Its checkpoints were '
              'reused in the full pass.', '', '## Leading patterns', '',
              'Rank: distinct observed training-pair support, then observed node-sequence count, then '
              'exact signature. The tables show five patterns per condition; artifacts contain the top 20 '
              'with witnesses and the full ranked catalog. Category labels below are shortened for display '
              'only; distinct complete category sets remain distinct signatures.', '',
              'For a partial run, the pair-support interval is [observed support, observed support plus '
              'every unfinished pair not already observed supporting that signature]. It is a conservative '
              'uncertainty bound, not a statistical confidence interval.', '',
              '`T` = `biolink:treats_or_applied_or_studied_to_treat`. `Q1`, `Q2`, etc. identify '
              'exact qualifier sets defined at the end of this section. An edge without a Q label in '
              'a qualified table has no stored qualifiers.', '']
    qlabels = {}
    def pattern(r):
        text = short_category(r['categories'][0])
        for e, c in zip(r['edges'], r['categories'][1:]):
            pred = e['predicate'].removeprefix('biolink:')
            if pred == 'treats_or_applied_or_studied_to_treat':
                pred = 'T'
            qualifiers = e.get('qualifiers', {})
            if qualifiers:
                key = json.dumps(qualifiers, sort_keys=True)
                if key not in qlabels:
                    qlabels[key] = 'Q' + str(len(qlabels)+1)
                pred += '[' + qlabels[key] + ']'
            text += (f' —{pred}→ ' if e['direction'] == '>' else f' ←{pred}— ') + short_category(c)
        return text
    for h in (2, 3):
        for q in ('unqualified', 'qualified'):
            for view in ('chemical_allowed', 'chemical_excluded'):
                stem = f'{q}-{view}'
                rows = json.loads((run / f'{h}hop/{stem}-top20.json').read_text())
                lines += [f'### {h} hops; {q}; {view.replace("_", " ")}', '',
                          '| Rank | Pattern | Pair support (lower–upper) | Drugs observed | Diseases observed | Node sequences observed |',
                          '|---|---|---:|---:|---:|---:|']
                for r in rows[:5]:
                    upper = len(set(r['supporting_pair_indices']) | uncertain_pairs[h])
                    interval = str(r['pair_support_observed']) if upper == r['pair_support_observed'] else f'{r["pair_support_observed"]}–{upper}'
                    lines.append(f'| {r["rank"]} | `{pattern(r)}` | {interval} | '
                                 f'{r["distinct_drugs"]:,} | {r["distinct_diseases"]:,} | '
                                 f'{r["node_sequences_observed"]:,} |')
                lines += ['', f'[Top 20, support IDs, and witnesses]({relative}/{h}hop/{stem}-top20.json) · '
                          f'[Full ranked TSV, gzip]({relative}/{h}hop/{stem}.tsv.gz)', '']
    lines += ['### Qualifier key', '']
    for qs, label in qlabels.items():
        lines.append(f'- **{label}**: `' + qs + '`.')
    lines += ['', '## Hub participation and position-specific exclusion', '',
              'For each selected pattern, the audit re-enumerates its supporting pairs. Only fully '
              'completed audits enter hub denominators. “Pairs using hub” means at least one witness '
              'uses it; “pairs lost” means there is no alternative node at that position. '
              'This is position-specific exclusion, not global deletion of the node.', '',
              '| Hops | Pattern rank (unqualified, chemicals allowed) | Position | Hub | Pairs using hub / audited support | Pairs lost | Pairs remaining |',
              '|---|---:|---:|---|---:|---:|---:|']
    for h in (2, 3):
        rows = json.loads((run / f'{h}hop/unqualified-chemical_allowed-top20.json').read_text())
        for r in rows[:5]:
            for hub in r.get('hubs_by_position', []):
                lines.append(f'| {h} | {r["rank"]} | {hub["position"]} | '
                             f'{hub["node"]["name"]} (`{hub["node"]["id"]}`) | '
                             f'{hub["pairs_using_hub"]:,} / {r["hub_audit_complete_pairs"]:,} | '
                             f'{hub["pairs_lost_if_hub_excluded_at_position"]:,} | '
                             f'{hub["pairs_remaining_if_hub_excluded_at_position"]:,} |')
        audit_path = run / f'{h}hop/hub_audit.json'
        if audit_path.exists():
            audit = json.loads(audit_path.read_text())
            lines += ['', f'{h}-hop hub audit states: `{audit["pair_states"]}`. '
                      f'Selected distinct signatures: {audit["selected_signatures"]}.', '']
            # Restart the table after prose so Markdown remains valid.
            if h == 2:
                lines += ['| Hops | Pattern rank (unqualified, chemicals allowed) | Position | Hub | Pairs using hub / audited support | Pairs lost | Pairs remaining |',
                          '|---|---:|---:|---|---:|---:|---:|']
    lines += ['', '## Relation to BTE and ARAGORN', '',
              'The leading frequent paths are observations of connectivity, not automatically BTE or '
              'ARAGORN treatment rules. BTE’s gene templates require specific variant-form and '
              'qualified-predicate constraints or a `has_phenotype` edge. Generic `related_to` or '
              'ancestor paths do not establish those conditions. ARAGORN’s ten stored treatment '
              'patterns all require a chemical–disease/phenotype edge somewhere in the rule body, '
              'so the filtered graph blocks them structurally. Several are conjunctive patterns '
              'rather than simple paths. No service-level matching or recovery result is inferred here.', '',
              'See the [local rule comparison](../../bte-aragorn-drug-disease-recovery/rule-comparison-report.md) '
              'for exact templates, qualifiers, directions, and source links.', '',
              '## Limitations and interpretation', '',
              '- Broad disease ancestors, procedures, chemical classes, and other hubs can create '
              'high pair coverage without providing a specific treatment mechanism.',
              '- Counts across signatures overlap. Their sum is not a unique node-sequence count '
              'and not a count of independent pieces of evidence.',
              '- Full qualifier sets can fragment a predicate-level pattern into many context-specific '
              'signatures. Qualified catalogs include unqualified-parent IDs for comparison.',
              '- Endpoint survival is not a guarantee of connectivity. Missing endpoints remain in '
              'the full-training denominator.',
              '- Partial enumeration biases observed frequency downward, especially for expensive pairs. '
              'The completion and audit states must accompany any ranking.',
              '- Both chemical views are derived from the same traversal. For a capped pair, '
              'chemical exclusion filters its observed prefix; it is not an independently exhausted '
              'restricted search.',
              '- No inference about prediction accuracy or generalization is made from these training-only '
              'frequencies. A separate candidate-retrieval evaluation is needed for that.', '']
    verification = run / 'verification.json'
    if verification.exists():
        v = json.loads(verification.read_text())
        lines += ['## Verification', '',
                  f'Run verification passed: **{v["passed"]}**. Checks: `{v["checks"]}`.', '',
                  v['checks_scope'], '',
                  'The independent fixture tests also check both endpoint orientations against brute-force '
                  'enumeration, source-duplicate collapse, qualifier separation, self-loop exclusion, '
                  'missing endpoints, and capped-search status.', '',
                  f'[Verification record]({relative}/verification.json)', '']
    dual_tables = out.parent / 'dual-ranking-tables.md'
    if dual_tables.exists():
        lines += ['## Pair-coverage versus path-frequency rankings', '',
                  '[Separate ranking tables for all eight conditions](dual-ranking-tables.md) '
                  'show the leading patterns ordered by distinct pair support and, separately, '
                  'by supporting node-sequence count. Each table reports both metrics and paths '
                  'per supported pair. These are re-sorted saved counts, not a new graph traversal.', '']
    out.write_text('\n'.join(lines))
    print(out)


if __name__ == '__main__':
    main()
