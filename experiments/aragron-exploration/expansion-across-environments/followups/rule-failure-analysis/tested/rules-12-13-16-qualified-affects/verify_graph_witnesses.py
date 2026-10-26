"""Verify four qualified affects witnesses across public Retriever environments across public Retrievers.

Default: summarize saved evidence offline. --prepare selects witnesses locally.
--submit makes sequential requests with permanent attempt markers; no automatic retry.
"""
import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
PREDICATE = 'biolink:affects'
ENDPOINTS = {
    'development': 'https://dev.retriever.biothings.io',
    'ci_staging': 'https://retriever.ci.transltr.io',
    'test': 'https://retriever.test.transltr.io',
    'production': 'https://retriever.transltr.io',
}
PATTERNS = [('Gene', 'Gene'), ('Gene', 'Protein'), ('Protein', 'Gene'), ('Protein', 'Protein')]


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(path)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(raw, output):
    path = output / 'witnesses.json'
    if path.exists():
        print('Using frozen witnesses', flush=True)
        return
    source = ROOT / 'output/qualifier-graph-audit/run_001'
    prior = read(source / 'witnesses.json')
    chosen = [dict(w) for w in prior]
    exact = None
    for line in (source / 'aspect-bearing-edges.jsonl').open():
        edge = json.loads(line)
        if edge.get('predicate') == PREDICATE and edge.get('object_aspect_qualifier') == 'transport' and edge.get('object_direction_qualifier') == 'decreased':
            exact = edge
            break
    if exact is None:
        raise RuntimeError('No exact transport witness')
    wanted={exact['subject'],exact['object']};nodes={}
    with (raw / 'nodes.jsonl').open() as stream:
        for line in stream:
            node=json.loads(line)
            if node['id'] in wanted:nodes[node['id']]=node
    chosen.insert(1,dict(rule=13,raw_edge=exact,subject=nodes[exact['subject']],object=nodes[exact['object']],required_aspect='transport',required_direction='decreased'))
    witnesses=[]
    for index,w in enumerate(chosen,1):
        def category(node):
            cats=node.get('category',[])
            for cat in ('biolink:SmallMolecule','biolink:ChemicalEntity','biolink:Gene','biolink:Protein'):
                if cat in cats:return cat
            raise RuntimeError('Unrecognized witness type')
        witnesses.append(dict(id=f'p{index:02d}',rule=w['rule'],subject_category=category(w['subject']),object_category=category(w['object']),
            subject=dict(id=w['subject']['id'],name=w['subject'].get('name'),categories=w['subject']['category']),
            object=dict(id=w['object']['id'],name=w['object'].get('name'),categories=w['object']['category']),
            raw_edge=w['raw_edge'],required_aspect=w['required_aspect'],required_direction=w['required_direction']))
    save(path,dict(created_utc=now(),source_hashes={n:sha(source/n) for n in ('findings.json','witnesses.json','aspect-bearing-edges.jsonl')},
        selection='Three original effect witnesses plus an exact transport witness; actual stored endpoint categories, not original rule endpoint types.',witnesses=witnesses))
    print('Four qualified affects witnesses frozen',flush=True)


def request(w, modern=False):
    edge=dict(subject='s',object='o',predicates=[PREDICATE],knowledge_type='lookup')
    quals={'biolink:object_aspect_qualifier':w['required_aspect'],'biolink:object_direction_qualifier':w['required_direction']}
    if modern:
        edge['constraints']={'qualifiers':[quals]}
    else:
        edge['qualifier_constraints']=[{'qualifier_set':[dict(qualifier_type_id=k,qualifier_value=v) for k,v in quals.items()]}]
    return dict(message={'query_graph':{'nodes':{
        's':{'ids':[w['subject']['id']],'categories':[w['subject_category']]},
        'o':{'ids':[w['object']['id']],'categories':[w['object_category']]}},'edges':{'e':edge}}},
        parameters=dict(tier=0,tiers=[0],tier_fallback=False,timeout=60,dehydrated=False,log_level='DEBUG'),
        log_level='DEBUG',bypass_cache=True,submitter='aragorn-qualifier-graph-witnesses-2026-10-22')


def snapshot(client, base, folder, phase):
    name = 'openapi' if phase == 'openapi' else 'metadata-' + phase
    route = '/openapi.json' if phase == 'openapi' else '/metadata/tier_0'
    marker = folder / (name + '-transport.json')
    path = folder / (name + '.json')
    if marker.exists():
        return path.exists()
    state = dict(url=base + route, started_utc=now())
    try:
        response = client.get(base + route, timeout=45)
        state['http_status'] = response.status_code
        response.raise_for_status()
        save(path, response.json())
        state['sha256'] = sha(path)
    except Exception as error:
        state['error'] = str(error)
    state['finished_utc'] = now()
    save(marker, state)
    return path.exists()


def ids(binding):
    return binding.get('ids', []) if isinstance(binding, dict) else [b['id'] for b in binding or []]


def classify(w, data, state):
    if not isinstance(data, dict):
        data = {}
    message = data.get('message') or {}
    results = message.get('results')
    logs = data.get('logs') or []
    text = ' '.join(str(l.get('message', '')) for l in logs).lower()
    count = len(results) if isinstance(results, list) else None
    errors = [l for l in logs if l.get('level', '').upper() in ('ERROR', 'CRITICAL')]
    bound = {eid for result in results or [] for analysis in result.get('analyses') or []
             for b in analysis.get('edge_bindings', {}).values() for eid in ids(b)}
    edges = (message.get('knowledge_graph') or {}).get('edges') or {}
    expected = (w['subject']['id'], w['raw_edge']['predicate'], w['object']['id'])
    forward = [eid for eid in sorted(bound) if (edges.get(eid, {}).get('subject'),
                edges.get(eid, {}).get('predicate'), edges.get(eid, {}).get('object')) == expected]
    reverse = [eid for eid in sorted(bound) if (edges.get(eid, {}).get('object'),
                edges.get(eid, {}).get('predicate'), edges.get(eid, {}).get('subject')) == expected]
    if state.get('state') != 'response_received':
        outcome = 'transport_uncertain'
    elif 'invalid predicates' in text:
        outcome = 'invalid_predicate'
    elif 'metaedges could not be found' in text:
        outcome = 'missing_metaedge'
    elif any(s in text for s in ('timed out', 'timeout reached', 'deadline exceeded', 'truncat')):
        outcome = 'incomplete'
    elif state.get('http_status') != 200 or errors:
        outcome = 'error'
    elif data.get('status') not in ('Success', 'Completed', 'OK') or count is None:
        outcome = 'unconfirmed_status'
    elif forward:
        outcome = 'verified_forward_witness'
    elif reverse:
        outcome = 'returned_reverse_only'
    elif count:
        outcome = 'returned_other_edges'
    else:
        outcome = 'empty'
    return dict(outcome=outcome, raw_results=count, http_status=state.get('http_status'),
                response_status=data.get('status'), forward_bound_edge_ids=forward,
                reverse_bound_edge_ids=reverse, original_edge_id_returned=w['raw_edge'].get('id') in forward,
                requested_predicate=PREDICATE, expected_stored_predicate=w['raw_edge']['predicate'], required_aspect=w['required_aspect'],required_direction=w['required_direction'],returned_witness_qualifiers={eid:edges[eid].get('qualifiers',[]) for eid in forward},
                query_graph_matches=message.get('query_graph') == request(w, state.get('modern',False))['message']['query_graph'],
                reported_releases=data.get('data_release_versions'), biolink_version=data.get('biolink_version'),
                trapi_version=data.get('schema_version'),
                tier_logs=[l.get('message') for l in logs if 'Begin processing tier' in l.get('message', '')],
                warnings_errors=[l for l in logs if l.get('level', '').upper() in ('WARNING', 'ERROR', 'CRITICAL')])


def summarize(output):
    witnesses = read(output / 'witnesses.json')['witnesses']
    rows, snapshots = [], {}
    for env, base in ENDPOINTS.items():
        folder = output / env
        values = {}
        for phase in ('before', 'after'):
            path = folder / ('metadata-' + phase + '.json')
            if path.exists():
                data = read(path)
                values[phase] = dict(version=data.get('version'), sha256=hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest())
        snapshots[env] = dict(snapshots=values, unchanged=(values['before']['sha256'] == values['after']['sha256']) if len(values) == 2 else None)
        for w in witnesses:
            case = folder / w['id']
            if not (case / 'submission.json').exists():
                result = dict(outcome='not_submitted')
            else:
                data = read(case / 'response.json') if (case / 'response.json').exists() else {}
                result = classify(w, data, read(case / 'submission.json'))
                save(case / 'summary.json', result)
            rows.append(dict(environment=env, endpoint=base + '/query', pattern=w['id'],
                             subject_category=w['subject_category'], object_category=w['object_category'],
                             subject_id=w['subject']['id'], subject_name=w['subject']['name'],
                             object_id=w['object']['id'], object_name=w['object']['name'], **result))
    report = dict(created_utc=now(), scope='Four real qualified affects witnesses across public Retrievers, with version-appropriate qualifier encodings and actual stored endpoint types.',
                  witnesses_sha256=sha(output / 'witnesses.json'), rows=rows, metadata=snapshots,
                  limitations=['One example per pattern; not representative coverage or biological validation.',
                               'Public Development Retriever identity relative to ARAGORN internal Retriever remains unverified.',
                               'Only forward patterns selected; separate reverse-direction controls not performed.',
                               'Confirms qualified edge retrieval for actual witness types, not original rule BiologicalEntity-to-ChemicalEntity patterns or full paths.',
                               'Graph edge identifiers can differ between releases.'])
    save(output / 'summary.json', report)
    columns=['environment','pattern','subject_category','object_category','subject_id','subject_name','object_id','object_name','outcome','http_status','raw_results','original_edge_id_returned']
    with (output / 'summary.csv').open('w', newline='') as stream:
        writer=csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    for env in ENDPOINTS:
        subset=[r for r in rows if r['environment']==env]
        print(env, {s:sum(r['outcome']==s for r in subset) for s in sorted({r['outcome'] for r in subset})}, flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--raw', type=Path, default=Path('/home/agonzalez/shepherd/experiments/ultra/data/tier0-20260621/raw'))
    parser.add_argument('--output', type=Path, default=ROOT/'output/qualifier-graph-audit/hosted-witnesses_001')
    args=parser.parse_args()
    if args.prepare:
        prepare(args.raw, args.output)
    witnesses=read(args.output/'witnesses.json')['witnesses']
    if args.submit:
        import httpx
        with httpx.Client(timeout=90, follow_redirects=False) as client:
            ready=[]
            for env,base in ENDPOINTS.items():
                folder=args.output/env
                schema_ok=snapshot(client,base,folder,'openapi')
                metadata_ok=snapshot(client,base,folder,'before')
                if schema_ok and metadata_ok:
                    ready.append(env)
                else:
                    print('Preflight failed:',env,flush=True)
            for w in witnesses:
                for env in ready:
                    case=args.output/env/w['id']; modern=read(args.output/env/'openapi.json')['info']['x-trapi']['version'].startswith('2.'); q=request(w,modern)
                    if (case/'submission.json').exists():
                        if read(case/'request.json')!=q:
                            raise ValueError('Saved request differs; use a new directory')
                        continue
                    save(case/'request.json',q)
                    state=dict(modern=modern,endpoint=ENDPOINTS[env]+'/query',started_utc=now(),state='submitting',request_sha256=sha(case/'request.json'),runner_sha256=sha(Path(__file__)))
                    save(case/'submission.json',state)
                    try:
                        response=client.post(state['endpoint'],json=q)
                        (case/'response.body').write_bytes(response.content)
                        state.update(http_status=response.status_code,state='response_received')
                        save(case/'response.json',response.json())
                    except Exception as error:
                        state.update(state='uncertain_or_unparsed',error=str(error))
                    finally:
                        state['finished_utc']=now();save(case/'submission.json',state)
                    data=read(case/'response.json') if (case/'response.json').exists() else {}
                    result=classify(w,data,state);save(case/'summary.json',result)
                    print(env,w['id'],result['outcome'],result['raw_results'],flush=True)
                    time.sleep(2)
            for env in ready:
                snapshot(client,ENDPOINTS[env],args.output/env,'after')
    summarize(args.output)

if __name__=='__main__':
    main()
