"""Bounded Production genetic-association pilot. Offline unless --submit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[4]
ENDPOINT = 'https://retriever.transltr.io'

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)

def now():
    return datetime.now(timezone.utc).isoformat()

def variants():
    original = json.loads((ROOT / 'output/genetic-association-audit/clearer-example_001/request.json').read_text())
    original['submitter'] = 'aragorn-genetic-association-controlled-pilot-2026-10-22'
    result = [('witness_original', original)]
    for name, category in [('subject_gene', 'biolink:Gene'), ('subject_parent', 'biolink:BiologicalEntity'), ('subject_category_omitted', None)]:
        request = copy.deepcopy(original)
        node = request['message']['query_graph']['nodes']['s']
        if category:
            node['categories'] = [category]
        else:
            node.pop('categories')
        result.append((name, request))
    request = copy.deepcopy(original)
    nodes = request['message']['query_graph']['nodes']
    nodes['s'] = {'categories': ['biolink:Gene']}
    nodes['o']['categories'] = ['biolink:DiseaseOrPhenotypicFeature']
    result.append(('exact_rule_edge_disease_pinned', request))
    return result

def summarize(folder):
    rows = []
    for name, request in variants():
        case = folder / name
        if not (case / 'submission.json').exists():
            continue
        state = json.loads((case / 'submission.json').read_text())
        response = json.loads((case / 'response.json').read_text()) if (case / 'response.json').exists() else {}
        logs = response.get('logs') or [] if isinstance(response, dict) else []
        messages = [str(l.get('message', '')) for l in logs]
        issues = [l for l in logs if l.get('level', '').upper() in ('WARNING','ERROR','CRITICAL')]
        message = response.get('message') or {} if isinstance(response, dict) else {}
        results = message.get('results')
        count = len(results) if isinstance(results, list) else None
        text = ' '.join(messages).lower()
        outcome = 'unknown'
        if 'invalid predicates' in text:
            outcome = 'invalid_predicate'
        elif 'metaedges could not be found' in text:
            outcome = 'missing_metaedge'
        elif any(x in text for x in ('timed out', 'timeout reached', 'truncat', 'deadline exceeded')):
            outcome = 'incomplete'
        elif state.get('http_status') != 200 or any(l.get('level','').upper() in ('ERROR','CRITICAL') for l in issues):
            outcome = 'error'
        elif response.get('status') in ('Success','Completed','OK') and count is not None:
            outcome = 'returned' if count else 'empty'
        edges = (message.get('knowledge_graph') or {}).get('edges') or {}
        bound = set()
        for result in results or []:
            for analysis in result.get('analyses') or []:
                for bindings in analysis.get('edge_bindings', {}).values():
                    bound.update(bindings.get('ids', []) if isinstance(bindings, dict) else [b['id'] for b in bindings])
        witnesses = [eid for eid in bound if edges.get(eid, {}).get('subject') == 'GO:0045721' and edges[eid].get('object') == 'MONDO:0005148' and edges[eid].get('predicate') == 'biolink:genetic_association']
        rows.append(dict(control=name, endpoint=ENDPOINT+'/query', http_status=state.get('http_status'), status=response.get('status'), outcome=outcome, raw_results=count, witness_bound_edge_ids=witnesses, releases=response.get('data_release_versions'), tier_logs=[m for m in messages if 'Begin processing tier' in m], warnings_errors=issues, query_graph_matches=message.get('query_graph') == request['message']['query_graph']))
    snapshots = {}
    for phase in ('before','after'):
        path = folder / f'metadata-{phase}.json'
        if path.exists():
            snapshots[phase] = hashlib.sha256(json.dumps(json.loads(path.read_text()), sort_keys=True).encode()).hexdigest()
    report = dict(scope='Five sequential Production Tier 0 controls; one stored BiologicalProcess/disease witness. No adapted predicate or full-rule replay.', controls=rows, metadata_hashes=snapshots, metadata_unchanged=(snapshots['before']==snapshots['after']) if len(snapshots)==2 else None, limitations=['Public Retriever identity relative to internal ARAGORN deployment unverified.', 'Wrong-category witness is a category-handling diagnostic, not evidence for a real Gene association.', 'Exact rule-edge query changes category and pinning; it is a baseline, not a single-variable contrast.', 'No semantic substitution, full rule, or other environment tested.'])
    save(folder/'summary.json', report)
    print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'output/genetic-association-audit/controlled-pilot_001')
    args = parser.parse_args()
    if args.submit:
        import httpx
        args.output.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            for filename, route in [('metadata-before','/metadata/tier_0'), ('openapi','/openapi.json')]:
                path=args.output/(filename+'.json')
                if not path.exists():
                    r=client.get(ENDPOINT+route)
                    r.raise_for_status()
                    save(path,r.json())
                    save(args.output/(filename+'-transport.json'),dict(url=ENDPOINT+route,http_status=r.status_code,time=now()))
            for name, request in variants():
                case=args.output/name
                if (case/'submission.json').exists():
                    if json.loads((case/'request.json').read_text()) != request:
                        raise ValueError('Request changed; use a new output directory')
                    continue
                save(case/'request.json',request)
                state=dict(started=now(),state='submitting',endpoint=ENDPOINT+'/query',runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
                save(case/'submission.json',state)
                try:
                    r=client.post(ENDPOINT+'/query',json=request)
                    state.update(http_status=r.status_code,state='response_received')
                    (case/'response.body').write_bytes(r.content)
                    save(case/'response.json',r.json())
                except Exception as exc:
                    state.update(state='uncertain_or_unparsed',error=str(exc))
                finally:
                    state['finished']=now()
                    save(case/'submission.json',state)
                time.sleep(2)
            if not (args.output/'metadata-after.json').exists():
                r=client.get(ENDPOINT+'/metadata/tier_0')
                r.raise_for_status()
                save(args.output/'metadata-after.json',r.json())
                save(args.output/'metadata-after-transport.json',dict(url=ENDPOINT+'/metadata/tier_0',http_status=r.status_code,time=now()))
    summarize(args.output)

if __name__ == '__main__':
    main()
