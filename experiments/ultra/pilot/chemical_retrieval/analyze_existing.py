"""Training recovery on existing queries and retrieval bottlenecks; no new lookups."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, save


def analyze():
    out = ROOT / 'pilot/results/chemical_retrieval_001'
    settings = json.loads((out / 'settings.json').read_text())
    labels_path = Path(settings['dataset']) / 'data/labels.json'
    assert digest(labels_path) == settings['dataset_sha256']['labels.json']
    labels = json.loads(labels_path.read_text())
    answers = {s: defaultdict(set) for s in ('visible', 'validation', 'test')}
    for r in labels:
        answers[r['split']][r['disease']].add(r['drug_index'])
    totals = {s: Counter() for s in answers}
    rules_total, statuses = Counter(), Counter()
    missing_by_split = {s: [] for s in answers}
    capped_diseases, bounded_diseases, cutoff_loss = [], [], {s: [] for s in ('validation', 'test')}
    seen = set()
    for directory in sorted((out / 'treats_only/diseases').iterdir()):
        report = json.loads((directory / 'report.json').read_text())
        for name, sha in report['artifact_sha256'].items():
            assert digest(directory / name) == sha
        g = json.loads((directory / 'graph.json').read_text())
        rules = json.loads((directory / 'rules.json').read_text())
        d = report['disease']
        seen.add(d)
        nodes = {g['anchor']} | {x for h, p, t in g['edges'] for x in (h, t)}
        bound = set(g['rule_answer_nodes'])
        if len(g['edges']) == settings['edge_cap']:
            capped_diseases.append(d)
        if any(r.get('bounded_results') for r in rules):
            bounded_diseases.append(d)
        for r in rules:
            rules_total[r['rule_id']] += r['retained_matches']
            statuses[r['status']] += 1
        for split in answers:
            truth = answers[split][d]
            if not truth:
                continue
            reached, returned = truth & nodes, truth & bound
            totals[split].update(diseases=1, pairs=len(truth), reached=len(reached), bound=len(returned))
            missing_by_split[split].extend([[a, d] for a in sorted(truth-nodes)])
            if split != 'visible':
                before = set().union(*(set(r['coverage']['before_union_cap'][split]['recovered_answer_indices']) for r in rules))
                before_bound = set().union(*(set(r['coverage']['before_union_cap'][split]['bound_answer_indices']) for r in rules))
                totals[split].update(before_union_reached=len(before), before_union_bound=len(before_bound))
                cutoff_loss[split].extend([[a, d] for a in sorted(before-reached)])
                assert reached == set(report['splits'][split]['recovered_answer_indices'])
    result = {'policy': 'treats_only', 'source_settings_sha256': digest(out / 'settings.json'),
              'queries_available': len(seen),
              'coverage': {s: {**dict(v), 'recovery': v['reached']/v['pairs'],
                               'bound_recovery': v['bound']/v['pairs'],
                               'all_split_pairs': sum(map(len, answers[s].values())),
                               'unqueried_diseases': len(set(answers[s])-seen),
                               'unqueried_pairs': sum(len(a) for d, a in answers[s].items() if d not in seen)}
                           for s, v in totals.items()},
              'rule_retained_matches': dict(rules_total), 'statuses': dict(statuses),
              'graphs_at_cap': len(capped_diseases), 'diseases_with_bounded_rule_results': len(bounded_diseases),
              'union_cap_answer_losses': {s: len(a) for s, a in cutoff_loss.items()},
              'limitations': 'Before-union metrics still include per-rule truncation. Training is only measured on already queried diseases; visible treats edges are present.'}
    save(out / 'treats_only_diagnostics.json', result)
    save(out / 'treats_only_missing_answers.json', missing_by_split)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    analyze()
