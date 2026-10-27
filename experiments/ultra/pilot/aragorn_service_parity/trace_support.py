"""Reconstruct compatible ARAGORN templates from saved service evidence graphs.

Compatibility is evidence-based attribution, not a service-reported rule ID.
An auxiliary graph may merge multiple bindings/evidence records: full coverage
requires every evidence edge to participate in at least one complete rule match.
"""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
from importlib.metadata import version as package_version
import json
from pathlib import Path
import shutil
import urllib.request

from common import binding_ids, extract_answers

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def support_ids(edge):
    return sorted({graph for attr in edge.get('attributes') or []
                   if attr.get('attribute_type_id') == 'biolink:support_graphs'
                   for graph in attr['value']})


def qualifier_match(edge, constraints):
    values = defaultdict(set)
    for qualifier in edge.get('qualifiers') or []:
        values[qualifier['qualifier_type_id']].add(qualifier['qualifier_value'])
    return not constraints or any(all(values[k].intersection(v if isinstance(v, list) else [v])
                                     for k, v in group.items()) for group in constraints)


def compile_rule(query, predicate_expander, qualifier_expander):
    graph = query['message']['query_graph']
    edges = {}
    for key, edge in graph['edges'].items():
        constraints = edge.get('constraints') or {}
        assert set(constraints) <= {'qualifiers'}, 'Unsupported constraint requires explicit matching'
        forward, inverse = predicate_expander.expand_predicates(edge.get('predicates') or [])
        edges[key] = {'subject': edge['subject'], 'object': edge['object'],
                      'forward': sorted(forward), 'inverse': None if inverse is None else sorted(inverse),
                      'qualifiers': [{k: sorted(v) if isinstance(v, list) else v for k, v in group.items()}
                                     for group in qualifier_expander.expand_qualifier_constraints(
                                         constraints.get('qualifiers') or [])]}
    return {'nodes': graph['nodes'], 'edges': edges}


def match_rule(rule, nodes, edges, answer, disease, ignore_qualifiers=False):
    """Enumerate consistent node/edge bindings, preserving direction and qualifiers.

    Category matching uses literal membership in the ancestor-inclusive returned
    categories, as the local lookup does. Different variables may bind one node;
    evidence edges can be reused if all query constraints permit that binding.
    """
    def node_ok(qnode, curie):
        spec = rule['nodes'][qnode]
        return (curie in nodes and (not spec.get('ids') or curie in spec['ids'])
                and (not spec.get('categories') or
                     bool(set(spec['categories']).intersection(nodes[curie].get('categories') or []))))

    pinned = {'drug': answer, 'disease': disease}
    if not all(node_ok(q, node) for q, node in pinned.items()):
        return None
    candidates = {}
    for key, spec in rule['edges'].items():
        candidates[key] = []
        for edge_id, edge in edges.items():
            if not ignore_qualifiers and not qualifier_match(edge, spec['qualifiers']):
                continue
            orientations = []
            if not spec['forward'] or edge['predicate'] in spec['forward']:
                orientations.append((edge['subject'], edge['object'], False))
            if spec['inverse'] is not None and (not spec['inverse'] or edge['predicate'] in spec['inverse']):
                orientations.append((edge['object'], edge['subject'], True))
            for subject, obj, reverse in orientations:
                if spec['subject'] == spec['object'] and subject != obj:
                    continue
                bindings = {spec['subject']: subject, spec['object']: obj}
                if all(node_ok(q, node) and (q not in pinned or pinned[q] == node)
                       for q, node in bindings.items()):
                    candidates[key].append((edge_id, bindings, reverse))
        if not candidates[key]:
            return None
    order = sorted(candidates, key=lambda key: len(candidates[key]))
    covered, count, witness = set(), 0, None

    def visit(position, bindings, edge_bindings):
        nonlocal count, witness
        if position == len(order):
            count += 1
            covered.update(v['edge_id'] for v in edge_bindings.values())
            if witness is None:
                witness = {'nodes': dict(bindings), 'edges': dict(edge_bindings)}
            return
        key = order[position]
        for edge_id, new, reverse in candidates[key]:
            if any(q in bindings and bindings[q] != node for q, node in new.items()):
                continue
            visit(position + 1, {**bindings, **new},
                  {**edge_bindings, key: {'edge_id': edge_id, 'reversed': reverse}})

    visit(0, pinned, {})
    if not count:
        return None
    return {'binding_count': count, 'covers_entire_support_graph': covered == set(edges),
            'covered_edge_ids': sorted(covered), 'unexplained_edge_ids': sorted(set(edges) - covered),
            'witness': witness}


def classify(rules, nodes, edges, answer, disease, ignore_qualifiers=False):
    full, partial = {}, {}
    for rule_id, rule in rules.items():
        match = match_rule(rule, nodes, edges, answer, disease, ignore_qualifiers)
        if match:
            (full if match['covers_entire_support_graph'] else partial)[rule_id] = match
    return {'full_matches': full, 'partial_matches': partial}


def short_edge(edge):
    return {k: edge[k] for k in ('subject', 'predicate', 'object', 'qualifiers', 'sources') if k in edge}


def toolkit(version, out):
    from bmt.toolkit import Toolkit
    destination = out / 'biolink' / version
    destination.mkdir(parents=True, exist_ok=True)
    for name in ('biolink-model.yaml', 'attributes.yaml', 'predicate_mapping.yaml'):
        path = destination / name
        if not path.exists():
            url = f'https://raw.githubusercontent.com/biolink/biolink-model/refs/tags/v{version}/{name}'
            with urllib.request.urlopen(url, timeout=30) as response:
                path.write_bytes(response.read())
    bmt = Toolkit(schema=str(destination / 'biolink-model.yaml'),
                  predicate_map=str(destination / 'predicate_mapping.yaml'))
    assert str(bmt.get_model_version()) == version
    # Expansion helpers deliberately swallow toolkit errors. Force imported
    # schema loading here so missing imports cannot silently disable expansion.
    bmt.view.all_schema()
    assert bmt.get_element('biolink:treats') is not None
    assert 'biolink:treats' in bmt.get_descendants('biolink:treats_or_applied_or_studied_to_treat', formatted=True)
    from gandalf.search.expanders import QualifierExpander
    assert {'activity', 'abundance'} <= set(QualifierExpander(bmt).get_value_descendants('activity_or_abundance'))
    return bmt


def analyze_query(directory, compiled_by_version):
    service = read(directory / 'service.json')
    raw_path = directory / 'service.response.json.gz'
    assert digest(raw_path) == service['response_sha256']
    with gzip.open(raw_path, 'rt') as stream:
        response = json.load(stream)
    assert extract_answers(response) == set(service['answers'])
    message = response['message']
    nodes, edges = (message['knowledge_graph'][key] for key in ('nodes', 'edges'))
    auxiliary = message.get('auxiliary_graphs') or {}
    rows, paths = {}, {}
    local = {r['rule_id']: set(r['answers']) for r in read(directory / 'local.json')['rules']}
    for result in message['results']:
        answers = binding_ids(result['node_bindings']['drug'])
        diseases = binding_ids(result['node_bindings']['disease'])
        assert diseases == {service['disease']}, 'Unexpected normalized disease binding'
        for answer in sorted(answers):
            row = rows.setdefault(answer, {'answer': answer, 'name': nodes[answer].get('name'),
                                          'direct_edge_ids': [], 'support_graph_ids': [],
                                          'unsupported_prediction_edge_ids': []})
            for analysis in result.get('analyses') or []:
                assert not analysis.get('support_graphs'), 'Analysis-level support needs explicit tracing'
                for binding in (analysis.get('edge_bindings') or {}).values():
                    for edge_id in sorted(binding_ids(binding)):
                        edge = edges[edge_id]
                        if {edge['subject'], edge['object']} != {answer, service['disease']}:
                            raise ValueError('Bound edge endpoints do not match answer and disease')
                        supports = support_ids(edge)
                        if not supports:
                            key = ('unsupported_prediction_edge_ids' if edge.get('knowledge_level') == 'prediction'
                                   else 'direct_edge_ids')
                            row[key].append(edge_id)
                        for graph_id in supports:
                            row['support_graph_ids'].append(graph_id)
                            cache_key = (answer, graph_id)
                            if cache_key in paths:
                                continue
                            evidence = {key: edges[key] for key in auxiliary[graph_id]['edges']}
                            assert evidence and not any(support_ids(e) for e in evidence.values()), 'Nested support needs recursion'
                            path_nodes = {key: nodes[key] for e in evidence.values() for key in (e['subject'], e['object'])}
                            matches = {}
                            for version, rules in compiled_by_version.items():
                                strict = classify(rules, path_nodes, evidence, answer, service['disease'])
                                relaxed = classify(rules, path_nodes, evidence, answer, service['disease'], True)
                                matches[version] = {
                                    'qualified': strict, 'without_qualifiers': relaxed,
                                    'classification': ('unique' if len(strict['full_matches']) == 1 else
                                                       'ambiguous' if strict['full_matches'] else 'unmatched')}
                            paths[cache_key] = {'answer': answer, 'support_graph_id': graph_id,
                                'nodes': {key: {'name': node.get('name'), 'categories': node.get('categories', [])}
                                          for key, node in path_nodes.items()},
                                'edges': {key: short_edge(e) for key, e in evidence.items()}, 'matches': matches}
    for answer, row in rows.items():
        for key in ('direct_edge_ids', 'support_graph_ids', 'unsupported_prediction_edge_ids'):
            row[key] = sorted(set(row[key]))
        row['compatible_rules_by_version'] = {
            version: sorted({rule for graph in row['support_graph_ids']
                             for rule in paths[(answer, graph)]['matches'][version]['qualified']['full_matches']}, key=int)
            for version in compiled_by_version}
        row['compatible_rules_missing_local_answer'] = {
            version: [rule for rule in rules if answer not in local[rule]]
            for version, rules in row['compatible_rules_by_version'].items()}
    assert set(rows) == set(service['answers'])
    return {'disease': service['disease'], 'disease_name': nodes[service['disease']].get('name'),
            'response_sha256': service['response_sha256'], 'answers': list(rows.values()),
            'support_paths': list(paths.values()), 'service_issues': service.get('issues', []),
            'unreferenced_auxiliary_graph_ids': sorted(set(auxiliary) - {key[1] for key in paths})}


def main():
    from gandalf.search.expanders import PredicateExpander, QualifierExpander
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=HERE / 'results/run_001')
    args = parser.parse_args()
    out = args.run / 'support_trace'
    out.mkdir(exist_ok=True)
    versions = ['4.4.2', '4.4.4']
    expanders = {v: (PredicateExpander(bmt), QualifierExpander(bmt))
                 for v in versions for bmt in [toolkit(v, out)]}
    cfg = read(args.run / 'settings.json')
    reports = []
    input_hashes = {}
    for index, disease in enumerate(cfg['cohort']):
        directory = args.run / f'{index:02d}'
        queries = read(directory / 'expanded_queries.json')
        assert len(queries) == 19
        compiled = {v: {str(i): compile_rule(query, *expanders[v]) for i, query in enumerate(queries[1:])}
                    for v in versions}
        report = analyze_query(directory, compiled)
        assert report['disease'] == disease
        save(out / f'{index:02d}.json', report)
        save(out / f'{index:02d}.compiled_rules.json', compiled)
        reports.append(report)
        input_hashes[f'{index:02d}'] = {name: digest(directory / name) for name in
                                      ('service.response.json.gz', 'expanded_queries.json', 'service.json', 'local.json')}
        print(disease, len(report['answers']), 'answers;', len(report['support_paths']), 'support paths', flush=True)
    summary = {'queries': len(reports), 'answer_pairs': sum(len(r['answers']) for r in reports),
               'support_paths': sum(len(r['support_paths']) for r in reports),
               'direct_only_answers': sum(bool(a['direct_edge_ids']) and not a['support_graph_ids'] for r in reports for a in r['answers']),
               'inferred_only_answers': sum(bool(a['support_graph_ids']) and not a['direct_edge_ids'] for r in reports for a in r['answers']),
               'direct_and_inferred_answers': sum(bool(a['support_graph_ids']) and bool(a['direct_edge_ids']) for r in reports for a in r['answers']),
               'unsupported_prediction_edges': sum(len(a['unsupported_prediction_edge_ids']) for r in reports for a in r['answers']),
               'unreferenced_auxiliary_graphs': sum(len(r['unreferenced_auxiliary_graph_ids']) for r in reports),
               'by_version': {}, 'input_sha256': input_hashes,
               'method': 'Compare saved support against all 18 checkout templates. Pin answer and disease; check stored categories, '
                         'directed predicates with native descendant/inverse/symmetric expansion, and qualifier constraints. '
                         'Full match means every support edge participates in a complete rule binding; subgraph-only matches are separate. '
                         'Qualifier-free matches are diagnostic only. Matches are compatible templates, not original rule provenance.'}
    for version in versions:
        statuses, full, partial, relaxed = Counter(), Counter(), Counter(), Counter()
        answer_pairs = defaultdict(set)
        for report in reports:
            for path in report['support_paths']:
                match = path['matches'][version]
                statuses[match['classification']] += 1
                full.update(match['qualified']['full_matches'].keys())
                partial.update(match['qualified']['partial_matches'].keys())
                relaxed.update(match['without_qualifiers']['full_matches'].keys())
                for rule in match['qualified']['full_matches']:
                    answer_pairs[rule].add((report['disease'], path['answer']))
        summary['by_version'][version] = {'path_classification': dict(statuses),
            'rules': {str(i): {'full_match_paths': full[str(i)], 'compatible_answer_pairs': len(answer_pairs[str(i)]),
                              'partial_match_paths': partial[str(i)], 'qualifier_free_full_match_paths': relaxed[str(i)]}
                      for i in range(18)}}
    summary['paths_with_version_dependent_full_rule_ids'] = sum(
        set(path['matches'][versions[0]]['qualified']['full_matches']) != set(path['matches'][versions[1]]['qualified']['full_matches'])
        for report in reports for path in report['support_paths'])
    summary['compatible_rule_answer_pairs_missing_locally'] = {
        v: sum(len(a['compatible_rules_missing_local_answer'][v]) for r in reports for a in r['answers']) for v in versions}
    # Human-readable answer index and one concrete witness per matched rule.
    with (out / 'answer_rules.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['disease', 'disease_name', 'answer', 'name',
                                                  'direct_edges', 'support_graphs', 'compatible_rule_ids'])
        writer.writeheader()
        for report in reports:
            for answer in report['answers']:
                writer.writerow({'disease': report['disease'], 'disease_name': report['disease_name'],
                                 'answer': answer['answer'], 'name': answer['name'],
                                 'direct_edges': len(answer['direct_edge_ids']),
                                 'support_graphs': len(answer['support_graph_ids']),
                                 'compatible_rule_ids': ','.join(answer['compatible_rules_by_version'][versions[-1]])})
    examples = {}
    for report in reports:
        for path in report['support_paths']:
            for rule in path['matches'][versions[-1]]['qualified']['full_matches']:
                examples.setdefault(rule, {'disease': report['disease'], 'disease_name': report['disease_name'], **path})
    save(out / 'examples.json', examples)
    source_files = [Path(__file__), HERE / 'common.py', HERE / 'test_trace_support.py']
    for file in source_files:
        shutil.copy2(file, out / file.name)
    summary['source_sha256'] = {file.name: digest(file) for file in source_files}
    from gandalf.search import expanders, qualifiers
    summary['native_helper_sha256'] = {module.__file__: digest(Path(module.__file__)) for module in (expanders, qualifiers)}
    summary['package_versions'] = {name: package_version(name) for name in ('bmt', 'linkml-runtime')}
    summary['schema_sha256'] = {str(path.relative_to(out)): digest(path) for path in sorted((out / 'biolink').rglob('*.yaml'))}
    save(out / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k not in ('input_sha256', 'source_sha256', 'schema_sha256')}, indent=2))


if __name__ == '__main__':
    main()
