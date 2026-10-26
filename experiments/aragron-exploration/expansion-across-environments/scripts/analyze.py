"""Offline evidence audit for real ARAGORN expansion, callbacks and final answers."""
import ast
import copy
import csv
import hashlib
import itertools
import json
from pathlib import Path
import re
from string import Template

RULE_KEY = '{"predicate": "biolink:treats"}'


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def extract_query_ids(logs):
    return sorted({m.group(1) for log in logs for m in
                   re.finditer(r"['\"]query_id['\"]:\s*['\"]([a-f0-9]+)['\"]", log.get('message', ''))})


def graph_key(graph):
    """Normalize only known TRAPI qualifier syntax and optional lookup defaults.

    Preserve directions, variables, categories, IDs, predicates and constraints.
    This is template identity, not equivalence under Biolink expansion.
    """
    graph = copy.deepcopy(graph)
    for node in graph['nodes'].values():
        for key in list(node):
            if node[key] is None:
                del node[key]
        for key in ('ids', 'categories'):
            if key in node:
                node[key] = sorted(node[key])
    for edge in graph['edges'].values():
        for key in list(edge):
            if edge[key] is None:
                del edge[key]
        if edge.get('knowledge_type') == 'lookup':
            del edge['knowledge_type']
        if 'qualifier_constraints' in edge:
            converted = [{q['qualifier_type_id']: q['qualifier_value'] for q in group['qualifier_set']}
                         for group in edge.pop('qualifier_constraints')]
            if converted:
                constraints = edge.setdefault('constraints', {})
                if 'qualifiers' in constraints:
                    raise ValueError('Both TRAPI qualifier encodings present')
                constraints['qualifiers'] = converted
        constraints = edge.get('constraints', {})
        if isinstance(constraints, dict) and 'qualifiers' in constraints:
            constraints['qualifiers'] = sorted(constraints['qualifiers'], key=lambda x: json.dumps(x, sort_keys=True))
        if not constraints:
            edge.pop('constraints', None)
        if 'predicates' in edge:
            edge['predicates'] = sorted(edge['predicates'])
    return json.dumps(graph, sort_keys=True)


def expected_graphs(request, rules):
    direct = copy.deepcopy(request['message']['query_graph'])
    direct['edges']['e'].pop('knowledge_type', None)
    target = direct['nodes']['disease']['ids'][0]
    graphs = {0: direct}
    for number, rule in enumerate(rules, 1):
        graph = json.loads(Template(json.dumps(rule['template'])).substitute(
            source='drug', target='disease', source_id='', target_id=target))['query_graph']
        graph['nodes']['drug'].pop('ids', None)
        graphs[number] = graph
    return graphs


def binding_ids(binding):
    if isinstance(binding, dict):
        return binding.get('ids', [])
    return [item['id'] for item in (binding or [])]


def callback_outcome(row):
    text = ' '.join(row['warnings_errors']).lower()
    if row.get('result_count', 0) > 0:
        return 'paths_returned_with_errors' if row.get('has_error') else 'paths_returned'
    if 'invalid predicates' in text:
        return 'invalid_predicate'
    if 'metaedges could not be found' in text or 'unsupportedconstraint' in text:
        return 'unsupported_pattern'
    if any(s in text for s in ('timeout', 'timed out', 'deadline', 'truncat', 'limit reached')):
        return 'incomplete_or_timeout'
    if row.get('has_error'):
        return 'backend_error'
    if row.get('callback_received'):
        return 'empty_callback_no_error_logged'
    return 'unknown_no_callback'


def parse_callbacks(logs, expected):
    by_graph = {graph_key(graph): n for n, graph in expected.items()}
    callbacks, parse_errors = {}, []
    for log in logs:
        match = re.match(r'^\[([a-zA-Z0-9_-]+)\] (.*)$', log.get('message', ''), re.DOTALL)
        if not match:
            continue
        cid, message = match.groups()
        row = callbacks.setdefault(cid, {'callback_id': cid, 'warnings_errors': []})
        if message.startswith('Sending lookup query to '):
            row['retrieval_url'] = message.removeprefix('Sending lookup query to ')
        found = re.match(r'Got back (\d+) results(?:, (\d+) nodes and (\d+) edges)?\.', message)
        if found:
            row.update(result_count=int(found[1]), callback_received=True)
        if message.startswith('for query graph: '):
            try:
                raw = message.removeprefix('for query graph: ')
                try:
                    graph = json.loads(raw)
                except ValueError:
                    graph = ast.literal_eval(raw)
                row.update(query_graph=graph, rule=by_graph.get(graph_key(graph)))
            except (ValueError, SyntaxError, KeyError, TypeError) as error:
                parse_errors.append(f'{cid}: {error}')
        if log.get('level', '').upper() in ('WARNING', 'ERROR', 'CRITICAL'):
            row['warnings_errors'].append(message)
            if log.get('level', '').upper() in ('ERROR', 'CRITICAL'):
                row['has_error'] = True
        if re.search(r'Begin processing tier[- ]0 job', message, re.I):
            row['tier0_execution_logged'] = True
        if 'subclass expansion' in message.lower():
            row['subclass_expansion_logged'] = True
    rows = [r for r in callbacks.values() if any(k in r for k in ('retrieval_url', 'query_graph', 'callback_received'))]
    for row in rows:
        row['outcome'] = callback_outcome(row)
    return rows, parse_errors


def audit_results(response):
    message = response.get('message') or {}
    results = message.get('results')
    if not isinstance(results, list):
        return {'final_result_count': None, 'unique_chemical_count': None, 'answers': [],
                'integrity_errors': [], 'final_results_present': False}
    kg = message.get('knowledge_graph') or {}
    nodes, edges = kg.get('nodes') or {}, kg.get('edges') or {}
    aux = message.get('auxiliary_graphs') or {}
    errors, answers = [], {}
    for eid, edge in edges.items():
        for endpoint in ('subject', 'object'):
            if edge.get(endpoint) not in nodes:
                errors.append(f'Edge {eid} missing {endpoint} node')
        for attr in edge.get('attributes') or []:
            if attr.get('attribute_type_id') == 'biolink:support_graphs':
                for gid in attr.get('value') or []:
                    if gid not in aux:
                        errors.append(f'Edge {eid} missing support graph {gid}')
    for gid, graph in aux.items():
        for eid in graph.get('edges') or []:
            if eid not in edges:
                errors.append(f'Support graph {gid} missing edge {eid}')
    for index, result in enumerate(results):
        for binding in result.get('node_bindings', {}).values():
            for nid in binding_ids(binding):
                if nid not in nodes:
                    errors.append(f'Result {index} missing node {nid}')
        bound = {eid for analysis in result.get('analyses') or []
                 for binding in analysis.get('edge_bindings', {}).values() for eid in binding_ids(binding)}
        for eid in bound - edges.keys():
            errors.append(f'Result {index} missing bound edge {eid}')
        inferred = {eid for eid in bound if any(s.get('resource_id') == 'infores:shepherd-aragorn' and
                    s.get('resource_role') == 'primary_knowledge_source' for s in edges.get(eid, {}).get('sources') or [])}
        for curie in binding_ids(result.get('node_bindings', {}).get('drug')):
            row = answers.setdefault(curie, {'id': curie, 'name': nodes.get(curie, {}).get('name'),
                                             'has_inferred_support': False, 'has_direct_support': False})
            row['has_inferred_support'] |= bool(inferred)
            row['has_direct_support'] |= bool((bound & edges.keys()) - inferred)
    return {'final_result_count': len(results), 'unique_chemical_count': len(answers),
            'answers': sorted(answers.values(), key=lambda r: r['id']),
            'knowledge_graph_nodes': len(nodes), 'knowledge_graph_edges': len(edges),
            'auxiliary_graphs': len(aux), 'integrity_errors': errors, 'final_results_present': True,
            'direct_only': sum(a['has_direct_support'] and not a['has_inferred_support'] for a in answers.values()),
            'inferred_only': sum(a['has_inferred_support'] and not a['has_direct_support'] for a in answers.values()),
            'both': sum(a['has_direct_support'] and a['has_inferred_support'] for a in answers.values())}


def analyze_case(env, target, directory, rules, index):
    state = read(directory / 'submission.json', {})
    row = {'environment': env['name'], 'query': f'q{index:02d}', 'target': target['id'],
           'target_name': target['name'], 'endpoint': env['base_url'] + '/query',
           'submission_state': state.get('state', 'not_submitted'), 'http_status': state.get('http_status'),
           'seconds': state.get('seconds')}
    response = read(directory / 'response.json', {})
    if not isinstance(response, dict):
        response = {}
    row.update(audit_results(response))
    request = read(directory / 'request.json')
    expected = expected_graphs(request, rules) if request is not None else {}
    logs = response.get('logs') or []
    callbacks, parse_errors = parse_callbacks(logs, expected)
    row.update(callbacks=callbacks, log_parse_errors=parse_errors,
               query_ids=extract_query_ids(logs),
               query_status=read(directory / 'status.json', {}).get('status'),
               response_status=response.get('status'),
               sent_requests=sum('retrieval_url' in r for r in callbacks),
               received_callbacks=sum(bool(r.get('callback_received')) for r in callbacks),
               observed_retrieval_urls=sorted({r['retrieval_url'] for r in callbacks if 'retrieval_url' in r}),
               all_lookups_returned_logged=any('Got all lookups back' in l.get('message', '') for l in logs),
               warnings_errors=[l for l in logs if l.get('level', '').upper() in ('WARNING','ERROR','CRITICAL')],
               graph_release=None)
    row['rule_results'] = []
    for number in range(len(rules) + 1):
        matches = [r for r in callbacks if r.get('rule') == number]
        row['rule_results'].append({'rule': number, 'expanded_graph_observed': bool(matches),
            'callback_count': sum(bool(r.get('callback_received')) for r in matches),
            'raw_result_count': sum(r.get('result_count', 0) for r in matches) if any(r.get('callback_received') for r in matches) else None,
            'outcomes': sorted({r['outcome'] for r in matches}) or ['not_observed'],
            'callback_ids': [r['callback_id'] for r in matches]})
    row['observed_rule_count'] = sum(r['expanded_graph_observed'] for r in row['rule_results'] if r['rule'])
    row['positive_rules'] = [r['rule'] for r in row['rule_results'] if r['rule'] and (r['raw_result_count'] or 0) > 0]
    row['complete_callback_observation'] = (bool(expected) and len(callbacks) == len(expected) and
        all(r['expanded_graph_observed'] and r['callback_count'] == 1 for r in row['rule_results']))
    row['tier0_execution_logged'] = any(c.get('tier0_execution_logged') for c in callbacks)
    returned_graph = (response.get('message') or {}).get('query_graph')
    try:
        row['response_query_matches_request'] = bool(request and returned_graph) and graph_key(returned_graph) == graph_key(request['message']['query_graph'])
    except (KeyError, TypeError, ValueError):
        row['response_query_matches_request'] = False
    row['complete_for_answer_comparison'] = (row['query_status'] == 'Completed' and
        row['response_status'] in (None, 'OK', 'Success', 'Completed') and row['response_query_matches_request'] and
        row['http_status'] == 200 and row['final_results_present'] and row['complete_callback_observation'] and
        not row['integrity_errors'] and not row['log_parse_errors'] and row['all_lookups_returned_logged'])
    row['artifact_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in (directory / 'request.json', directory / 'response.json') if p.exists()}
    return row


def write_csv(path, rows):
    if not rows:
        return
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})


def analyze_run(output):
    config = read(output / 'config.json')
    if config is None:
        raise ValueError('Run has no frozen config.json; first use --submit')
    cases, versions = [], []
    baseline = None
    for env in config['environments']:
        directory = output / env['name']
        api = read(directory / 'openapi.json', {})
        rules = read(directory / 'release-rules.json', {}).get(RULE_KEY, [])
        fingerprints = [hashlib.sha256(graph_key(r['template']['query_graph']).encode()).hexdigest() for r in rules]
        if env['name'] == 'development':
            baseline = fingerprints
        versions.append({'environment': env['name'], 'base_url': env['base_url'],
            'application_version': api.get('info', {}).get('version'),
            'trapi_version': api.get('info', {}).get('x-trapi', {}).get('version'),
            'biolink_version': api.get('info', {}).get('x-translator', {}).get('biolink-version'),
            'servers': api.get('servers'), 'release_rule_count': len(rules),
            'rule_fingerprints': fingerprints,
            'same_ordered_semantic_templates_as_development': bool(rules) and fingerprints == baseline,
            'sources': read(directory / 'sources.json', []), 'backend_graph_release': None})
        for index, target in enumerate(config['targets'], 1):
            cases.append(analyze_case(env, target, directory / f'q{index:02d}', rules, index))
    comparisons = []
    for target in config['targets']:
        for a, b in itertools.combinations([c for c in cases if c['target'] == target['id']], 2):
            valid = a['complete_for_answer_comparison'] and b['complete_for_answer_comparison']
            aset, bset = {x['id'] for x in a['answers']}, {x['id'] for x in b['answers']}
            comparisons.append({'target': target['id'], 'target_name': target['name'],
                'environment_a': a['environment'], 'environment_b': b['environment'],
                'complete_for_comparison': valid, 'intersection': len(aset & bset) if valid else None,
                'only_a': sorted(aset - bset) if valid else None, 'only_b': sorted(bset - aset) if valid else None,
                'jaccard': (len(aset & bset) / len(aset | bset) if aset | bset else 1.0) if valid else None,
                'identical_answer_ids': aset == bset if valid else None})
    rule_comparisons = []
    for target in config['targets']:
        target_cases = [c for c in cases if c['target'] == target['id']]
        for number in range(19):
            observed = {c['environment']: next((r for r in c['rule_results'] if r['rule'] == number), None)
                        for c in target_cases}
            complete = len(observed) == 4 and all(r and r['expanded_graph_observed'] and
                       r['callback_count'] == 1 for r in observed.values())
            counts = {e: r['raw_result_count'] if r else None for e, r in observed.items()}
            outcomes = {e: r['outcomes'] if r else ['not_observed'] for e, r in observed.items()}
            rule_comparisons.append({'target': target['id'], 'target_name': target['name'], 'rule': number,
                'complete_observation': complete, 'raw_counts': counts, 'outcomes': outcomes,
                'identical_raw_counts': len(set(counts.values())) == 1 if complete else None,
                'identical_outcomes': len({tuple(v) for v in outcomes.values()}) == 1 if complete else None})
    report = {'versions': versions, 'cases': cases, 'answer_comparisons': comparisons,
              'rule_comparisons': rule_comparisons,
              'overview': {'planned_queries': len(cases),
                'attempted': sum(c['submission_state'] != 'not_submitted' for c in cases),
                'http_200': sum(c['http_status'] == 200 for c in cases),
                'status_completed': sum(c['query_status'] == 'Completed' for c in cases),
                'all_expected_callbacks_observed': sum(c['complete_callback_observation'] for c in cases),
                'complete_for_answer_comparison': sum(c['complete_for_answer_comparison'] for c in cases)},
              'limitations': [
                  'Convenience cohort: seven previous rule probes plus three distinct seeded holdout targets; not representative coverage.',
                  'Lookup-only workflow; no scoring/ranking, graph masking or evaluation of clinical efficacy.',
                  'Raw rule callback counts precede merge filters and cannot be attributed directly to final answers.',
                  'A matched logged query graph proves that expansion was observed; release source alone does not.',
                  'Empty callbacks and missing observations do not establish graph-wide absence.',
                  'Tier 0 requested, but internal backend graph release and deployed image digest are not verified.',
                  'Release snapshots are reference source; runtime parameters and server maturity environment variables are not directly readable.',
                  'Answer overlap uses exact returned CURIEs; no cross-environment synonym normalization.',
                  'Qualifier-encoding normalization is for offline comparison only; submitted queries are not locally expanded.',
                  'Requests ask to bypass cache; actual cache policy remains service-controlled.'
              ]}
    save(output / 'report.json', report)
    scalar_fields = ['environment', 'query', 'target', 'target_name', 'submission_state', 'http_status',
                     'query_status', 'seconds', 'sent_requests', 'received_callbacks', 'observed_rule_count',
                     'positive_rules', 'final_result_count', 'unique_chemical_count', 'tier0_execution_logged',
                     'complete_for_answer_comparison', 'observed_retrieval_urls']
    write_csv(output / 'results.csv', [{k: c[k] for k in scalar_fields} for c in cases])
    write_csv(output / 'rules.csv', [dict(environment=c['environment'], query=c['query'], target=c['target'], **r)
                                    for c in cases for r in c['rule_results']])
    write_csv(output / 'answer_overlap.csv', comparisons)
    write_csv(output / 'rule_comparisons.csv', rule_comparisons)
    return report
