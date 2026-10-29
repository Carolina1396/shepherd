"""Submit one prepared query once, cache the response, and audit TRAPI references."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def save(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def binding_ids(value):
    """Support legacy binding lists and deployed TRAPI bindings with an ids field."""
    if isinstance(value, dict):
        return value['ids']
    return [binding['id'] for binding in value]


def inspect(response, request):
    message = response.get('message') or {}
    kg = message.get('knowledge_graph') or {}
    nodes, edges = kg.get('nodes') or {}, kg.get('edges') or {}
    auxiliary = message.get('auxiliary_graphs') or {}
    results = message.get('results') or []
    answer_node, = [k for k, v in request['message']['query_graph']['nodes'].items() if not v.get('ids')]
    candidates, bindings, issues, inferred = set(), set(), [], set()
    references = []
    for eid, edge in edges.items():
        for role in ('subject', 'object'):
            if edge.get(role) not in nodes:
                issues.append(f'edge {eid}: missing {role} node {edge.get(role)}')
        for attr in edge.get('attributes') or []:
            if attr.get('attribute_type_id') == 'biolink:support_graphs':
                inferred.add(eid)
                value = attr.get('value') or []
                references.extend((f'edge {eid}', g) for g in ([value] if isinstance(value, str) else value))
    for i, result in enumerate(results):
        for qnode, values in result.get('node_bindings', {}).items():
            for nid in binding_ids(values):
                if nid not in nodes:
                    issues.append(f'result {i}: missing bound node {nid}')
                if qnode == answer_node:
                    candidates.add(nid)
        for analysis in result.get('analyses') or []:
            references.extend((f'result {i}', g) for g in analysis.get('support_graphs') or [])
            for values in analysis.get('edge_bindings', {}).values():
                for eid in binding_ids(values):
                    bindings.add(eid)
                    if eid not in edges:
                        issues.append(f'result {i}: missing bound edge {eid}')
    for gid, graph in auxiliary.items():
        for eid in graph.get('edges') or []:
            if eid not in edges:
                issues.append(f'auxiliary {gid}: missing edge {eid}')
    for origin, gid in references:
        if gid not in auxiliary:
            issues.append(f'{origin}: missing support graph {gid}')
    logs = response.get('logs') or []
    problem_logs = [x for x in logs if str(x.get('level', '')).upper() in ('ERROR', 'WARNING', 'CRITICAL')]
    if 'message' not in response or 'results' not in message:
        issues.append('Response lacks message.results')
    return dict(status=response.get('status'), description=response.get('description'),
        results=len(results), candidates=len(candidates), candidate_ids=sorted(candidates),
        nodes=len(nodes), edges=len(edges), auxiliary_graphs=len(auxiliary),
        support_graph_references=len(references), edges_with_support_graphs=len(inferred),
        bound_edges_with_support_graphs=len(bindings & inferred),
        bound_edges_without_support_graphs=len(bindings-inferred),
        predicates=dict(Counter(e.get('predicate') for e in edges.values())),
        reference_issues=sorted(set(issues)), problem_logs=problem_logs,
        exposed_metadata={k: response[k] for k in ('schema_version', 'biolink_version', 'parameters', 'workflow') if k in response},
        note='Structural audit only; successful HTTP and complete references do not prove all internal rule lookups succeeded.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qid', type=int, default=0)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--endpoint', help='Override retrieval deployment')
    parser.add_argument('--send', action='store_true', help='Submit if no previous attempt exists')
    args = parser.parse_args()
    prepared = ROOT / 'prepared/queries.json'
    data = json.loads(prepared.read_text())
    endpoint = args.endpoint or data['endpoint']
    query, = [q for q in data['queries'] if q['qid'] == args.qid]
    request = query['request']
    assert request['workflow'] == [{'id': 'aragorn.lookup'}]
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    path = out / 'request.json'
    if path.exists():
        assert json.loads(path.read_text()) == request, 'Cached query differs'
    else:
        save(path, request)
    response_path = out / 'response.json'
    if not response_path.exists():
        if not args.send:
            parser.error('No cached response; use --send to submit')
        if (out / 'attempt.json').exists():
            parser.error('Prior attempt exists; inspect it and choose a new output directory for an explicit retry')
        attempt = dict(qid=args.qid, endpoint=endpoint,
            started_at=datetime.now(timezone.utc).isoformat(), timeout_seconds=args.timeout,
            prepared_sha256=digest(prepared), request_sha256=digest(path),
            script_sha256=digest(Path(__file__)), automatic_retries=0)
        save(out / 'attempt.json', attempt)
        start = time.monotonic()
        req = urllib.request.Request(endpoint, data=path.read_bytes(),
            headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as response:
                raw = response.read()
                attempt.update(http_status=response.status, response_headers=dict(response.headers))
            response_path.write_bytes(raw)
            attempt['response_sha256'] = digest(response_path)
        except urllib.error.HTTPError as error:
            (out / 'http_error_body.txt').write_bytes(error.read())
            attempt.update(http_status=error.code, error=str(error))
        except Exception as error:
            attempt['error'] = repr(error)
        finally:
            attempt.update(elapsed_seconds=time.monotonic()-start,
                           finished_at=datetime.now(timezone.utc).isoformat())
            save(out / 'attempt.json', attempt)
        if not response_path.exists():
            print(json.dumps(attempt, indent=2))
            raise SystemExit(1)
    attempt = json.loads((out / 'attempt.json').read_text())
    assert attempt['endpoint'] == endpoint, 'Cached endpoint differs'
    assert attempt['response_sha256'] == digest(response_path)
    audit = inspect(json.loads(response_path.read_text()), request)
    audit.update(qid=args.qid, response_sha256=digest(response_path), inspection_script_sha256=digest(Path(__file__)))
    save(out / 'inspection.json', audit)
    print(json.dumps({k: v for k, v in audit.items() if k not in ('candidate_ids', 'problem_logs')}, indent=2))
    print(f'Warning/error log entries: {len(audit["problem_logs"])}')


if __name__ == '__main__':
    main()
