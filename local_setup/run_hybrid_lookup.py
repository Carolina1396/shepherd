"""Local Aragorn lookup/scoring with development-server Omnicorp enrichment.

The development server receives the local lookup message (nodes, edges, results).
Each stage is saved separately. This does not change the default Aragorn workflow.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def validate_query(qgraph):
    edges = list(qgraph['edges'].values())
    inferred = [e for e in edges if e.get('knowledge_type', 'lookup') == 'inferred']
    if any(e.get('knowledge_type', 'lookup') not in ('lookup', 'inferred') for e in edges):
        raise ValueError('Only lookup and inferred knowledge types are supported.')
    if inferred:
        if len(edges) != 1:
            raise ValueError('AMIE inference requires a single query edge.')
        edge = inferred[0]
        nodes = [qgraph['nodes'][edge[k]] for k in ('subject', 'object')]
        pinned = [node for node in nodes if node.get('ids')]
        if len(pinned) != 1 or len(pinned[0]['ids']) != 1:
            raise ValueError('AMIE inference requires exactly one endpoint pinned to one ID.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--query', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--local-url', default='http://127.0.0.1:55440/aragorn/query')
    parser.add_argument('--omnicorp-url', default='https://shepherd.renci.org/aragorn/query')
    parser.add_argument('--timeout', type=int, default=180)
    parser.add_argument('--max-results', type=int, default=500)
    args = parser.parse_args()
    query = json.loads(args.query.read_text())
    qgraph = query['message']['query_graph']
    try:
        validate_query(qgraph)
    except ValueError as error:
        parser.error(str(error))
    if args.timeout <= 0 or args.max_results <= 0:
        parser.error('timeout and max-results must be positive')
    args.out.mkdir(parents=True, exist_ok=False)
    message = {'query_graph': qgraph}
    stages = [
        ('1_local_lookup', args.local_url, [{'id': 'aragorn.lookup'}]),
        ('2_dev_omnicorp', args.omnicorp_url, [{'id': 'aragorn.omnicorp'}]),
        ('3_local_scored', args.local_url, [
            {'id': 'aragorn.score'}, {'id': 'sort_results_score'},
            {'id': 'filter_results_top_n', 'parameters': {'max_results': args.max_results}},
            {'id': 'filter_kgraph_orphans'},
        ]),
    ]
    summary = []
    for name, url, workflow in stages:
        payload = {'message': message, 'workflow': workflow,
                   'parameters': {**query.get('parameters', {}), 'timeout': args.timeout}}
        data = json.dumps(payload).encode()
        (args.out / f'{name}.request.json').write_bytes(data)
        request = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=args.timeout + 30) as response:
                status, raw = response.status, response.read()
        except urllib.error.HTTPError as error:
            (args.out / f'{name}.response.json').write_bytes(error.read())
            raise SystemExit(f'{name}: HTTP {error.code}; response saved in {args.out}')
        (args.out / f'{name}.response.json').write_bytes(raw)
        result = json.loads(raw)
        if result.get('status') not in (None, 'Success', 'OK'):
            raise SystemExit(f'{name}: status {result.get("status")}; inspect saved response')
        message = result.get('message', {})
        if not message.get('results'):
            raise SystemExit(f'{name}: no results; stopped before subsequent stages')
        kg = message.get('knowledge_graph', {})
        record = {'stage': name, 'url': url, 'http_status': status,
                  'seconds': round(time.monotonic()-started, 3),
                  'results': len(message['results']),
                  'nodes': len(kg.get('nodes', {})), 'edges': len(kg.get('edges', {})),
                  'scored_analyses': sum('score' in a for r in message['results'] for a in r.get('analyses', []))}
        summary.append(record)
        (args.out / 'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
