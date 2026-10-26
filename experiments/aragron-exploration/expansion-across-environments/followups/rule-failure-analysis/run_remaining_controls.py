"""Bounded Production rules 1, 2, and 9 pilot. Offline unless --submit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = 'https://retriever.transltr.io'

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)

def now():
    return datetime.now(timezone.utc).isoformat()

def variants():
    audit=json.loads((ROOT/'output/run_002/report.json').read_text())
    case=next(c for c in audit['cases'] if c['environment']=='production' and c['query']=='q01')
    specs={1:('edge_0','NCBIGene:6733','CHEBI:28748'),2:('edge_2','CHEBI:28748','CHEBI:28748'),9:('edge_1','GO:0045721','CHEBI:28748')}
    result=[]
    for rule,(edge_id,subject_id,object_id) in specs.items():
        graph=copy.deepcopy(next(c['query_graph'] for c in case['callbacks'] if c.get('rule')==rule))
        def request(g):
            return dict(message={'query_graph':g},parameters=dict(tier=0,tiers=[0],tier_fallback=False,timeout=60,dehydrated=False),log_level='DEBUG',bypass_cache=True,submitter='aragorn-rules-1-2-9-controlled-pilot-2026-10-22')
        result.append((f'rule_{rule:02d}_full',request(graph)))
        edge=graph['edges'][edge_id]
        isolated={'nodes':{k:copy.deepcopy(graph['nodes'][k]) for k in (edge['subject'],edge['object'])},'edges':{edge_id:copy.deepcopy(edge)}}
        isolated['nodes'][edge['subject']]['ids']=[subject_id]
        isolated['nodes'][edge['object']]['ids']=[object_id]
        for label,omit in [('typed',()),('omit_subject',(edge['subject'],)),('omit_object',(edge['object'],)),('omit_both',(edge['subject'],edge['object']))]:
            g=copy.deepcopy(isolated)
            for node in omit:g['nodes'][node].pop('categories',None)
            result.append((f'rule_{rule:02d}_{label}',request(g)))
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
        rows.append(dict(control=name, endpoint=ENDPOINT+'/query', http_status=state.get('http_status'), status=response.get('status'), outcome=outcome, raw_results=count, bound_edge_ids=sorted(bound), releases=response.get('data_release_versions'), tier_logs=[m for m in messages if 'Begin processing tier' in m], warnings_errors=issues, query_graph_matches=message.get('query_graph') == request['message']['query_graph']))
    snapshots = {}
    for phase in ('before','after'):
        path = folder / f'metadata-{phase}.json'
        if path.exists():
            snapshots[phase] = hashlib.sha256(json.dumps(json.loads(path.read_text()), sort_keys=True).encode()).hexdigest()
    report = dict(scope='15 sequential Production Tier 0 requests: full rule plus four isolated category controls for each of rules 1, 2, 9.', controls=rows, metadata_hashes=snapshots, metadata_unchanged=(snapshots['before']==snapshots['after']) if len(snapshots)==2 else None, limitations=['Public Retriever identity relative to internal ARAGORN deployment unverified.', 'Pinned nodes are diagnostic probes, not known positive witnesses for these predicates; rule 2 uses a same-node pair.', 'Category controls differ only in requested categories; empty pinned searches cannot establish global absence.', 'No semantic substitution or other environment tested; predicate descendants and replacements remain unreviewed.'])
    if (folder/'metadata-before.json').exists():
        metadata=json.loads((folder/'metadata-before.json').read_text())
        report['predicate_inventory']={p:[e for e in metadata.get('schema',{}).get('edges',[]) if e.get('predicate')==p] for p in ('biolink:affects_response_to','biolink:similar_to','biolink:has_output')}
    save(folder/'summary.json', report)
    print(json.dumps(report, indent=2))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--output', type=Path, default=ROOT/'output/rules-01-02-09-controls/run_001')
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
