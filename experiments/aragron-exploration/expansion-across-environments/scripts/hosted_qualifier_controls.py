"""Controlled hosted Retriever probes; no submissions without --submit.

Preserves requests, responses and submission markers. Never repeats an attempted
POST automatically, including attempts with uncertain transport outcomes.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import time

from analyze import expected_graphs, parse_callbacks, RULE_KEY, binding_ids, graph_key
from run import now, save

ROOT = Path(__file__).resolve().parent.parent
ENDPOINTS = {
    'ci_staging': 'https://retriever.ci.transltr.io/query',
    'test': 'https://retriever.test.transltr.io/query',
    'production': 'https://retriever.transltr.io/query',
}
RULES = (12, 13, 16)


def saved_graphs(environment, query):
    folder = ROOT / 'output/run_002' / environment
    request = json.loads((folder / query / 'request.json').read_text())
    response = json.loads((folder / query / 'response.json').read_text())
    rules = json.loads((folder / 'release-rules.json').read_text())[RULE_KEY]
    callbacks, errors = parse_callbacks(response['logs'], expected_graphs(request, rules))
    if errors:
        raise ValueError(errors)
    return {row['rule']: row['query_graph'] for row in callbacks if row.get('rule') is not None}


def strip_qualifiers(graph, edge_ids=('edge_1', 'edge_2')):
    result = copy.deepcopy(graph)
    for edge_id in edge_ids:
        edge = result['edges'][edge_id]
        edge.pop('qualifier_constraints', None)
    return result


def request_for(graph):
    return dict(message={'query_graph': graph}, log_level='DEBUG', bypass_cache=True,
                parameters=dict(tier=0, tiers=[0], tier_fallback=False, timeout=120,
                                dehydrated=False),
                submitter='aragorn-controlled-qualifier-inspection-2026-10-20')


def control_variants(environment, query, output):
    """Pin a real qualified edge from this environment's unqualified result."""
    folder = output / environment / query
    response = json.loads((folder / 'unqualified/response.json').read_text())
    summary = json.loads((folder / 'unqualified/summary.json').read_text())
    if summary['outcome'] != 'returned':
        raise ValueError('A completed positive unqualified search is required')
    kg = response['message']['knowledge_graph']
    aspect = 'biolink:object_aspect_qualifier'
    direction = 'biolink:object_direction_qualifier'
    for eid in summary['bound_edge_ids']['edge_2']:
        edge = kg['edges'][eid]
        values = {q['qualifier_type_id']: q['qualifier_value'] for q in edge.get('qualifiers', [])}
        if (values.get(aspect) == 'activity_or_abundance'
                and values.get(direction) == 'increased'
                and edge['subject'] != edge['object']
                and not any(a.get('attribute_type_id') == 'biolink:support_graphs'
                            for a in edge.get('attributes', []))):
            break
    else:
        raise ValueError('No suitable real qualified edge found')
    graph = dict(nodes={
        'i': dict(ids=[edge['subject']], categories=['biolink:BiologicalEntity']),
        'e': dict(ids=[edge['object']], categories=['biolink:ChemicalEntity']),
    }, edges={'edge_2': dict(subject='i', object='e', predicates=[edge['predicate']])})
    selection = dict(edge_id=eid, edge=edge,
                     nodes={nid: kg['nodes'][nid] for nid in (edge['subject'], edge['object'])},
                     source='unqualified/response.json')
    selected_path = folder / 'control-selection.json'
    if selected_path.exists() and json.loads(selected_path.read_text()) != selection:
        raise ValueError('Control selection changed')
    save(selected_path, selection)
    variants = [('control_unqualified', copy.deepcopy(graph))]
    for name, wanted_aspect, wanted_direction in [
            ('control_matching', values[aspect], values[direction]),
            ('control_opposite_direction', values[aspect], 'decreased'),
            ('control_rule12_effect', 'metabolic_processing', 'decreased'),
            ('control_rule13_effect', 'transport', 'decreased'),
            ('control_rule16_effect', 'secretion', 'increased')]:
        qualified = copy.deepcopy(graph)
        qualified['edges']['edge_2']['qualifier_constraints'] = [{'qualifier_set': [
            dict(qualifier_type_id=aspect, qualifier_value=wanted_aspect),
            dict(qualifier_type_id=direction, qualifier_value=wanted_direction),
        ]}]
        variants.append((name, qualified))
    return variants


def summarize(response, http_status, graph):
    logs = response.get('logs') or []
    issues = [log.get('message', '') for log in logs
              if log.get('level', '').upper() in ('WARNING', 'ERROR', 'CRITICAL')]
    error = any(log.get('level', '').upper() in ('ERROR', 'CRITICAL') for log in logs)
    incomplete = any(re.search(r'timeout|timed out|truncat|deadline|limit reached', x, re.I) for x in issues)
    message = response.get('message') or {}
    results = message.get('results')
    count = len(results) if isinstance(results, list) else None
    status = response.get('status')
    if http_status != 200 or error or status not in ('Success', 'Completed', 'OK'):
        outcome = 'error_or_unconfirmed_status'
    elif incomplete:
        outcome = 'incomplete'
    elif count is None:
        outcome = 'unknown_missing_results'
    else:
        outcome = 'returned' if count else 'empty'
    chemicals = {curie for result in (results or [])
                 for curie in binding_ids(result.get('node_bindings', {}).get('drug'))}
    kg = message.get('knowledge_graph') or {}
    edges = kg.get('edges') or {}
    qualifiers = {}
    bound_ids = {}
    for result in results or []:
        for analysis in result.get('analyses') or []:
            for qedge_id, binding in analysis.get('edge_bindings', {}).items():
                bound_ids.setdefault(qedge_id, set()).update(binding_ids(binding))
    for qedge_id, ids in bound_ids.items():
        distributions = {}
        for eid in ids:
            quals = edges.get(eid, {}).get('qualifiers', [])
            signature = json.dumps(quals, sort_keys=True)
            distributions[signature] = distributions.get(signature, 0) + 1
        qualifiers[qedge_id] = distributions
    returned_graph = message.get('query_graph')
    return dict(outcome=outcome, status=status, http_status=http_status, raw_result_count=count,
                unique_candidate_chemicals=len(chemicals), knowledge_graph_edges=len(edges),
                warnings_errors=issues,
                tier0_logged=any(re.search(r'Begin processing tier[- ]0 job', l.get('message', '')) for l in logs),
                query_graph_matches=graph_key(returned_graph) == graph_key(graph) if returned_graph else None,
                data_release_versions=response.get('data_release_versions'),
                bound_edge_ids={k: sorted(v) for k, v in bound_ids.items()},
                bound_edge_qualifier_distributions=qualifiers)


def submit(client, environment, query, variant, graph, output):
    directory = output / environment / query / variant
    directory.mkdir(parents=True, exist_ok=True)
    request = request_for(graph)
    marker = directory / 'submission.json'
    if marker.exists():
        if json.loads((directory / 'request.json').read_text()) != request:
            raise ValueError(f'Existing request differs: {directory}')
        print(f'SKIP existing attempt {environment} {query} {variant}', flush=True)
        return
    save(directory / 'request.json', request)
    state = dict(environment=environment, query=query, variant=variant,
                 endpoint=ENDPOINTS[environment], started_utc=now(), state='submitting',
                 request_sha256=hashlib.sha256((directory / 'request.json').read_bytes()).hexdigest())
    save(marker, state)
    started = time.monotonic()
    try:
        response = client.post(state['endpoint'], json=request)
        (directory / 'response.body').write_bytes(response.content)
        state.update(http_status=response.status_code, state='response_received')
        data = response.json()
        save(directory / 'response.json', data)
        summary = summarize(data, response.status_code, graph)
        save(directory / 'summary.json', summary)
        state.update({k: summary[k] for k in ('outcome', 'status', 'raw_result_count', 'tier0_logged')})
    except Exception as exc:
        state.update(state='attempt_failed_no_auto_retry', error=f'{type(exc).__name__}: {exc}')
    finally:
        state.update(seconds=round(time.monotonic() - started, 3), finished_utc=now())
        save(marker, state)
    print(json.dumps(state), flush=True)


def analyze(output):
    rows = []
    for path in sorted(output.glob('*/*/*/submission.json')):
        row = json.loads(path.read_text())
        summary = path.with_name('summary.json')
        if summary.exists():
            row.update(json.loads(summary.read_text()))
        row['artifact_directory'] = str(path.parent.relative_to(output))
        rows.append(row)
    save(output / 'summary.json', dict(analyzed_utc=now(), attempts=len(rows), rows=rows))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--environments', nargs='+', choices=ENDPOINTS, default=list(ENDPOINTS))
    parser.add_argument('--queries', nargs='+', default=[f'q{n:02}' for n in range(1, 11)])
    parser.add_argument('--phase', choices=('baseline', 'single_edge', 'control'), default='baseline')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/hosted-qualifier-controls/run_001')
    args = parser.parse_args()
    if args.submit:
        import httpx
        args.output.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=180, follow_redirects=False) as client:
            for query in args.queries:
                for environment in args.environments:
                    graphs = saved_graphs(environment, query)
                    unqualified = strip_qualifiers(graphs[12])
                    assert all(strip_qualifiers(graphs[n]) == unqualified for n in RULES)
                    if args.phase == 'baseline':
                        variants = [(f'rule_{n}', graphs[n]) for n in RULES]
                        variants.append(('unqualified', unqualified))
                    elif args.phase == 'single_edge':
                        variants = [(f'rule_{n}_only_{kept}', strip_qualifiers(graphs[n], [removed]))
                                    for n in RULES for kept, removed in
                                    [('edge_1', 'edge_2'), ('edge_2', 'edge_1')]]
                    else:
                        variants = control_variants(environment, query, args.output)
                    for variant, graph in variants:
                        submit(client, environment, query, variant, graph, args.output)
                        analyze(args.output)
    rows = analyze(args.output)
    print(json.dumps({'saved_attempts': len(rows), 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
