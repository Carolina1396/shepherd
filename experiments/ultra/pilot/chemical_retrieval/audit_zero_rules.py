"""Audit zero-result ARAGORN rule components against native graph matching semantics."""
from collections import Counter
import json
from pathlib import Path
import sys

import numpy as np
from gandalf import CSRGraph
from gandalf.biolink import make_toolkit
from gandalf.search.expanders import PredicateExpander, QualifierExpander
from gandalf.search.qualifiers import edge_matches_qualifier_constraints

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'pilot/retrieval'))
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, save
from masking import mask_graph


def read(path):
    return json.loads(path.read_text())


def main():
    out = ROOT / 'pilot/results/chemical_retrieval_001'
    cfg = read(out / 'settings.json')
    rules = read(out / 'aragorn_rules.json')['{"predicate": "biolink:treats"}']
    assert digest(out / 'aragorn_rules.json') == cfg['rules_sha256']
    raw_counts, retained_counts, before_counts = Counter(), Counter(), Counter()
    for path in (out / 'treats_only/diseases').glob('*/rules.json'):
        report = read(path.with_name('report.json'))
        assert digest(path) == report['artifact_sha256']['rules.json']
        for r in read(path):
            raw_counts[r['rule_id']] += r.get('raw_results', 0)
            retained_counts[r['rule_id']] += r['retained_matches']
            before_counts[r['rule_id']] += r['bounded_matches_before_union']
    zero_ids = [i for i in range(18) if retained_counts[str(i)] == 0]
    source = CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
    assert digest(ROOT / 'output/gandalf/full-store/metadata.pkl') == cfg['source_graph_metadata_sha256']
    labels_path = Path(cfg['dataset']) / 'data/labels.json'
    assert digest(labels_path) == cfg['dataset_sha256']['labels.json']
    labels = read(labels_path)
    hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
    graph = mask_graph(source, hidden, 'treats_only')
    bmt = make_toolkit()
    assert str(bmt.get_model_version()) == read(out / 'biolink.json')['version']
    pe, qe = PredicateExpander(bmt), QualifierExpander(bmt)
    categories = {c for i in zero_ids for node in rules[i]['template']['query_graph']['nodes'].values()
                  for c in node['categories']}
    masks = {cat: np.zeros(graph.num_nodes, dtype=bool) for cat in categories}
    for index, props in graph.node_store.iter_properties():
        for category in set(props.get('categories', [])) & categories:
            masks[category][index] = True
    target_mask = np.zeros(graph.num_nodes, dtype=bool)
    cohort = set(cfg['cohort'])
    for row in labels:
        if row['disease'] in cohort:
            target_mask[row['disease_index']] = True
    print('Graph and category masks ready', flush=True)
    predicate_positions = {p: np.flatnonzero(graph.fwd_predicates == p) for p in range(len(graph.predicate_to_idx))}
    cache = {}

    def audit_edge(edge, nodes):
        spec = {'predicates': edge['predicates'], 'constraints': edge.get('constraints', {}),
                'subject_categories': nodes[edge['subject']]['categories'],
                'object_categories': nodes[edge['object']]['categories'],
                'subject_is_target': edge['subject'] == '$target',
                'object_is_target': edge['object'] == '$target'}
        key = json.dumps(spec, sort_keys=True)
        if key in cache:
            return cache[key]
        forward, reverse = pe.expand_predicates(edge['predicates'])
        quals = qe.expand_qualifier_constraints(edge.get('constraints', {}).get('qualifiers', []))
        allowed_quals = np.array([edge_matches_qualifier_constraints(q, quals)
                                 for q in graph.edge_properties._quals_pool])
        subject_mask = target_mask if spec['subject_is_target'] else np.logical_or.reduce([masks[c] for c in spec['subject_categories']])
        object_mask = target_mask if spec['object_is_target'] else np.logical_or.reduce([masks[c] for c in spec['object_categories']])
        stages = Counter()
        matched_predicates = Counter()
        for backwards, predicates in [(False, forward), (True, reverse or [])]:
            for name in predicates:
                if name not in graph.predicate_to_idx:
                    continue
                positions = predicate_positions[graph.predicate_to_idx[name]]
                if not len(positions):
                    continue
                heads = np.searchsorted(graph.fwd_offsets, positions, side='right')-1
                tails = graph.fwd_targets[positions]
                h, t = (tails, heads) if backwards else (heads, tails)
                typed = subject_mask[h] & object_mask[t]
                qualified = allowed_quals[graph.edge_properties._quals_idx[positions]]
                stages.update(predicate_records=len(positions),
                              predicate_and_category_records=int(typed.sum()),
                              predicate_and_qualifier_records=int(qualified.sum()),
                              fully_matching_records=int((typed & qualified).sum()))
                matched_predicates[name] += int((typed & qualified).sum())
        result = {**spec, 'expanded_forward_predicates': forward, 'expanded_reverse_predicates': reverse,
                  'expanded_qualifiers': quals, 'counts': {k: stages[k] for k in (
                      'predicate_records', 'predicate_and_category_records',
                      'predicate_and_qualifier_records', 'fully_matching_records')},
                  'fully_matching_by_stored_predicate': dict(matched_predicates)}
        cache[key] = result
        return result

    results = {}
    for i in zero_ids:
        query = rules[i]['template']['query_graph']
        result = {'rule': rules[i]['Rule'], 'raw_results': raw_counts[str(i)],
                  'before_union_matches': before_counts[str(i)], 'retained_matches': retained_counts[str(i)],
                  'edges': {name: audit_edge(edge, query['nodes']) for name, edge in query['edges'].items()}}
        results[str(i)] = result
        print(json.dumps({'rule_id': i, 'raw_results': result['raw_results'],
                          'edge_counts': {name: r['counts'] for name, r in result['edges'].items()}}), flush=True)
    report = {'policy': 'treats_only', 'cohort_diseases': len(cohort), 'zero_rule_ids': zero_ids,
              'categories_node_counts': {cat: int(mask.sum()) for cat, mask in masks.items()},
              'rules': results, 'source_settings_sha256': digest(out / 'settings.json'),
              'scope': 'Individual-edge availability, not a new full-rule search. Counts are evidence records/orientations, not unique triples. Target endpoints restricted to the evaluated diseases; other categories use native literal membership. Predicate and qualifier expansion use the pinned native toolkit.'}
    save(out / 'zero_rule_audit.json', report)


if __name__ == '__main__':
    main()
