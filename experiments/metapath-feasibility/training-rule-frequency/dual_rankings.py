"""Compare pair-support and node-sequence rankings without traversing the graph.

Stream each chemical-allowed catalog once. Its chemical-excluded subset has
identical per-signature counts, so both views can be selected in the same pass.
"""
import argparse
import csv
import gzip
import hashlib
import heapq
import json
from pathlib import Path
import time

from report import short_category


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--top', type=int, default=20)
    args = ap.parse_args()
    run = args.run
    manifest = json.loads((run / 'manifest.json').read_text())
    chemical = set(manifest['chemical_categories'])
    results = []
    for hops in (2, 3):
        summary = json.loads((run / f'{hops}hop/summary.json').read_text())
        for form in ('unqualified', 'qualified'):
            heaps = {view: [] for view in ('allowed', 'excluded')}
            path = run / f'{hops}hop/{form}-chemical_allowed.tsv.gz'
            start = time.monotonic()
            with gzip.open(path, 'rt') as stream:
                for n, row in enumerate(csv.DictReader(stream, delimiter='\t'), 1):
                    # Earlier original rank breaks ties after sequence and pair
                    # counts, preserving the original deterministic signature tie.
                    score = (int(row['node_sequences_observed']),
                             int(row['pair_support_observed']), -int(row['rank']))
                    eligible = [v for v, h in heaps.items() if len(h) < args.top or score > h[0][0]]
                    if eligible:
                        decoded = json.loads(row['signature_json'])
                        has_chemical = any(chemical.intersection(c) for c in decoded['categories'][1:-1])
                        for view in eligible:
                            if view == 'excluded' and has_chemical:
                                continue
                            entry = (score, row['signature_id'], row)
                            if len(heaps[view]) < args.top:
                                heapq.heappush(heaps[view], entry)
                            else:
                                heapq.heapreplace(heaps[view], entry)
                    if n % 500_000 == 0:
                        print(hops, form, n, 'rows', round(time.monotonic()-start, 1), 'seconds', flush=True)
            expected = next(v['signatures_observed'] for v in summary['views']
                            if v['qualified'] == (form == 'qualified') and v['view'] == 'chemical_allowed')
            assert n == expected
            for view in ('allowed', 'excluded'):
                pair_rows = json.loads((run / f'{hops}hop/{form}-chemical_{view}-top20.json').read_text())[:args.top]
                def metrics(row):
                    pairs = int(row['pair_support_observed'])
                    sequences = int(row['node_sequences_observed'])
                    return {'signature_id': row['signature_id'], 'categories': row['categories'],
                            'edges': row['edges'], 'pairs': pairs, 'node_sequences': sequences,
                            'paths_per_supported_pair': sequences / pairs,
                            'coverage_all_training': pairs / manifest['training_pairs'],
                            'distinct_drugs': int(row['distinct_drugs']),
                            'distinct_diseases': int(row['distinct_diseases'])}
                pair_top = [dict(metrics(r), rank=i) for i, r in enumerate(pair_rows, 1)]
                path_top = []
                for rank, (_, sid, row) in enumerate(sorted(heaps[view], reverse=True), 1):
                    decoded = json.loads(row['signature_json'])
                    path_top.append(dict(metrics(dict(row, **decoded)), rank=rank))
                assert all(path_top[j]['node_sequences'] >= path_top[j+1]['node_sequences']
                           for j in range(len(path_top)-1))
                if view == 'excluded':
                    assert all(not any(chemical.intersection(c) for c in r['categories'][1:-1])
                               for r in path_top)
                results.append({'hops': hops, 'qualifiers': form, 'chemical_intermediates': view,
                                'ranked_by_pair_coverage': pair_top, 'ranked_by_path_frequency': path_top})
            print('FINISHED', hops, form, n, 'rows', round(time.monotonic()-start, 1), 'seconds', flush=True)
    output = run / 'dual_rankings'
    output.mkdir(exist_ok=True)
    payload = {'training_pairs': manifest['training_pairs'], 'top_n': args.top,
               'pair_ranking': 'Distinct observed pair support, then observed node sequences, then original signature order.',
               'path_ranking': 'Observed node sequences, then distinct observed pair support, then original signature order.',
               'three_hop_limits': '92 capped pairs; three-hop observed frequencies and rankings may change on completion.',
               'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'conditions': results}
    (output / 'top20.json').write_text(json.dumps(payload, indent=2)+'\n')
    with (output / 'top20.tsv').open('w') as stream:
        w = csv.writer(stream, delimiter='\t')
        w.writerow(['hops', 'qualifiers', 'chemical_intermediates', 'ranking', 'rank', 'signature_id',
                    'pairs', 'node_sequences', 'paths_per_supported_pair', 'distinct_drugs',
                    'distinct_diseases', 'categories', 'edges'])
        for condition in results:
            for ranking in ('ranked_by_pair_coverage', 'ranked_by_path_frequency'):
                for r in condition[ranking]:
                    w.writerow([condition['hops'], condition['qualifiers'], condition['chemical_intermediates'],
                                ranking, r['rank'], r['signature_id'], r['pairs'], r['node_sequences'],
                                r['paths_per_supported_pair'], r['distinct_drugs'], r['distinct_diseases'],
                                json.dumps(r['categories']), json.dumps(r['edges'])])
    qlabels = {}
    def pattern(r):
        text = short_category(r['categories'][0])
        for edge, cats in zip(r['edges'], r['categories'][1:]):
            pred = edge['predicate'].removeprefix('biolink:')
            if pred == 'treats_or_applied_or_studied_to_treat':
                pred = 'T'
            q = edge.get('qualifiers', {})
            if q:
                key = json.dumps(q, sort_keys=True)
                if key not in qlabels:
                    qlabels[key] = 'Q' + str(len(qlabels)+1)
                pred += '['+qlabels[key]+']'
            text += (f' —{pred}→ ' if edge['direction'] == '>' else f' ←{pred}— ')+short_category(cats)
        return text
    relative = Path(__import__('os').path.relpath(output, args.out.parent))
    lines = ['# Meta-path rankings: pair coverage versus path frequency', '',
             f'Run `{run.name}`; {manifest["training_pairs"]:,} training pairs. '
             'This re-sorts saved counts; no graph traversal was rerun.', '',
             '- Pair coverage ranking: distinct training pairs, then node sequences.',
             '- Path-frequency ranking: distinct supporting node sequences, then training pairs.',
             '- Paths/pair is the average across the pairs supporting that signature, not across all training pairs.',
             '- Source duplicates are collapsed. Counts across signatures overlap and should not be summed as unique paths.',
             '- Two-hop counts are exact. Three-hop counts are observed lower bounds because 92 searches were capped; ranks can change.',
             '- Qualifiers distinguish signatures and do not filter paths. No self-loops; exact predicates and full stored category sets.',
             '- Category labels are shortened for display only. Full categories and signature IDs are in the machine-readable tables.', '',
             '`T` means `treats_or_applied_or_studied_to_treat`. Qualifier codes are defined below. '
             'An unlabeled edge in a qualified table has an empty qualifier set.', '',
             f'[Top 20 for all 16 rankings (TSV)]({relative}/top20.tsv) · '
             f'[Full signature details (JSON)]({relative}/top20.json)', '']
    for c in results:
        lines += [f'## {c["hops"]} hops; {c["qualifiers"]}; chemical intermediates {c["chemical_intermediates"]}', '']
        for key, title in [('ranked_by_pair_coverage', 'Ranked by pair coverage'),
                           ('ranked_by_path_frequency', 'Ranked by path frequency')]:
            lines += [f'### {title}', '', '| Rank | Meta-path | Pairs | Node sequences | Paths/pair |',
                      '|---|---|---:|---:|---:|']
            for r in c[key][:5]:
                lines.append(f'| {r["rank"]} | `{pattern(r)}` | {r["pairs"]:,} | '
                             f'{r["node_sequences"]:,} | {r["paths_per_supported_pair"]:.2f} |')
            lines.append('')
    lines += ['## Exact qualifier sets', '']
    for qs, label in qlabels.items():
        lines.append(f'- **{label}**: `{qs}`.')
    args.out.write_text('\n'.join(lines)+'\n')
    print('WROTE', args.out, output, flush=True)


if __name__ == '__main__':
    main()
