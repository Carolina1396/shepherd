"""Count available broader treatment evidence for validation answers, without ranking."""
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np
from gandalf import CSRGraph
from gandalf.biolink import make_toolkit
from gandalf.search.expanders import PredicateExpander

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, save


def main():
    out = ROOT / 'pilot/results/chemical_retrieval_001'
    settings = json.loads((out / 'settings.json').read_text())
    dataset = Path(settings['dataset'])
    labels_path = dataset / 'data/labels.json'
    assert digest(labels_path) == settings['dataset_sha256']['labels.json']
    graph = CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
    assert digest(ROOT / 'output/gandalf/full-store/metadata.pkl') == settings['source_graph_metadata_sha256']
    toolkit = make_toolkit()
    assert str(toolkit.get_model_version()) == json.loads((out / 'biolink.json').read_text())['version']
    expander = PredicateExpander(toolkit)
    forward, reverse = expander.expand_predicates(['biolink:treats_or_applied_or_studied_to_treat'])
    target = graph.predicate_to_idx['biolink:treats']
    forward_ids = {graph.predicate_to_idx[p] for p in forward if p in graph.predicate_to_idx} - {target}
    reverse_ids = {graph.predicate_to_idx[p] for p in (reverse or []) if p in graph.predicate_to_idx} - {target}
    covered = set()
    for path in (out / 'treats_only/diseases').glob('*/report.json'):
        report = json.loads(path.read_text())
        for a in report['splits'].get('validation', {}).get('recovered_answer_indices', []):
            covered.add((a, report['disease']))
    records, pred_counts = [], Counter()
    all_direct = 0
    labels = [r for r in json.loads(labels_path.read_text()) if r['split'] == 'validation']
    for row in labels:
        h, t = row['drug_index'], row['disease_index']
        a, b = graph.fwd_offsets[h:h+2]
        outgoing = set(map(int, graph.fwd_predicates[a:b][graph.fwd_targets[a:b] == t])) - {target}
        a, b = graph.fwd_offsets[t:t+2]
        incoming = set(map(int, graph.fwd_predicates[a:b][graph.fwd_targets[a:b] == h])) - {target}
        all_direct += bool(outgoing or incoming)
        matches = (outgoing & forward_ids) | (incoming & reverse_ids)
        if matches:
            predicates = sorted(graph.id_to_predicate[p] for p in matches)
            pred_counts.update(predicates)
            records.append({'drug': row['drug'], 'disease': row['disease'], 'predicates': predicates,
                            'already_recovered': (h, row['disease']) in covered})
    potential = {(next(r['drug_index'] for r in labels if r['drug'] == x['drug'] and r['disease'] == x['disease']), x['disease'])
                 for x in records}
    report = {'policy': 'treats_only', 'split': 'validation', 'pairs': len(labels),
              'current_recovered': len(covered), 'pairs_with_any_remaining_direct_evidence': all_direct,
              'pairs_with_broader_treatment_evidence': len(records),
              'broader_treatment_evidence_coverage': len(records)/len(labels),
              'additional_pairs_available': len(potential-covered),
              'union_with_current_retrieval': len(potential | covered),
              'union_coverage': len(potential | covered)/len(labels),
              'matched_predicates_pair_counts': dict(pred_counts),
              'forward_predicate_family': forward, 'reverse_predicate_family': reverse,
              'interpretation': 'Evidence availability, not a completed retrieval experiment. Adding a direct broader-treatment lookup may retrieve these pairs; shared budgets can truncate matches.'}
    save(out / 'validation_evidence_audit.json', report)
    save(out / 'validation_broader_treatment_pairs.json', records)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
