"""Check run accounting and an independent read-only sample of stored witnesses."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random

import analyze as a


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run', type=Path, required=True)
    args = ap.parse_args()
    run = args.run
    g = a.Graph()
    m = a.freeze(run, g)
    checks = Counter()
    selected = set(random.Random(37).sample(m['present_indices'], 80))
    for hops in (2, 3):
        expected_states = Counter()
        for i in range(m['training_pairs']):
            file = a.pair_file(run, hops, i)
            if not file.exists():
                expected_states['not_processed'] += 1
                continue
            rec = a.read_pair(file)
            assert rec['pair_index'] == i
            expected_states[rec['state']] += 1
            assert rec['no_chemical_node_sequences'] <= rec['node_sequences']
            if hops == 2:
                assert rec['no_chemical_node_sequences'] == rec['node_sequences']
            # Every observed bare signature must be exactly the projection of a
            # qualified signature, including for searches interrupted by bounds.
            bare = {(tuple(c), tuple(tuple(e) for e in es)) for c, es, count, ns in rec['tables'][0]}
            projected = {(tuple(c), tuple((d, p, -1) for d, p, q in es))
                         for c, es, count, ns in rec['tables'][1]}
            assert bare == projected
            checks['pair_checkpoints'] += 1
            if i % 500 == 0:
                a.log('Verify checkpoints', hops, i, '/', m['training_pairs'])
            if i not in selected:
                continue
            for q in (False, True):
                entries = rec['tables'][q]
                # Stable spread across each pair's records, including its last.
                chosen = sorted({0, len(entries)//2, len(entries)-1}) if entries else []
                for j in chosen:
                    c, es, count, ns = entries[j]
                    assert 0 < count <= rec['node_sequences']
                    assert tuple(c) == tuple(int(g.node_class[n]) for n in ns)
                    assert ns[0] == g.idx(m['pairs'][i]['drug_id'])
                    assert ns[-1] == g.idx(m['pairs'][i]['disease_id'])
                    for u, v, e in zip(ns, ns[1:], es):
                        assert u != v
                        available = g.adjacency(u).get(v, set())
                        if not q:
                            available = {(d, p, -1) for d, p, qual in available}
                        assert tuple(e) in available
                        checks['directed_witness_edges'] += 1
                    checks['witnesses'] += 1
        summary = json.loads((run / f'{hops}hop/summary.json').read_text())
        assert dict(expected_states) == summary['states']
        assert sum(expected_states.values()) == m['training_pairs']
        assert expected_states['missing_endpoint'] == m['missing_pairs']
        for q in (False, True):
            allowed, excluded = [v for v in summary['views'] if v['qualified'] == q]
            assert excluded['signatures_observed'] <= allowed['signatures_observed']
            assert excluded['pairs_connected_observed'] <= allowed['pairs_connected_observed']
        for file in (run / f'{hops}hop').glob('*-top20.json'):
            for r in json.loads(file.read_text()):
                ps = r['supporting_pair_indices']
                assert len(set(ps)) == r['pair_support_observed']
                assert len({m['pairs'][i]['drug_id'] for i in ps}) == r['distinct_drugs']
                assert len({m['pairs'][i]['disease_id'] for i in ps}) == r['distinct_diseases']
                for h in r.get('hubs_by_position', []):
                    total = r['hub_audit_complete_pairs']
                    assert 0 <= h['pairs_lost_if_hub_excluded_at_position'] <= h['pairs_using_hub'] <= total
                    assert h['pairs_remaining_if_hub_excluded_at_position'] + h['pairs_lost_if_hub_excluded_at_position'] == total
                checks['top_pattern_accounting'] += 1
        a.log('Verified', hops, 'hop', dict(checks))
    a.save(run / 'verification.json', {'passed': True, 'checks': checks,
           'witness_sample': 'Seed 37; 80 surviving training pairs; up to three witnesses per pair/hop/qualifier form',
           'checks_scope': 'Every checkpoint: signature projection and state accounting. Selected witnesses: categories, endpoints, no self-loops, directed predicates, and exact qualifiers checked against read-only graph indexes. Top patterns: support diversity and hub accounting.'})


if __name__ == '__main__':
    main()
