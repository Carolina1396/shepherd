"""Score frozen retrieval evidence through Shepherd; do not run retrieval again."""
import argparse
import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
import urllib.error
import urllib.request

from retrieve import binding_ids, digest, inspect, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--endpoint', help='Scoring deployment override; retrieval stays frozen')
    parser.add_argument('--legacy-bindings', action='store_true', help='Use TRAPI 1.x binding lists, omit version metadata, and request debug logs')
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    source = args.retrieval
    attempt = json.loads((source/'attempt.json').read_text())
    endpoint = args.endpoint or attempt['endpoint']
    assert digest(source/'response.json') == attempt['response_sha256']
    raw = json.loads((source/'response.json').read_text())
    payload = {'message': copy.deepcopy(raw['message']),
               'workflow': [{'id':'aragorn.omnicorp'}, {'id':'aragorn.score'}]}
    # Preserve the deployed response schema so TRAPI bindings are interpreted correctly.
    for key in ('schema_version', 'biolink_version'):
        if key in raw:
            payload[key] = raw[key]
    if args.legacy_bindings:
        for result in payload['message'].get('results') or []:
            for key, value in result['node_bindings'].items():
                result['node_bindings'][key] = [{'id':i} for i in binding_ids(value)]
            for analysis in result.get('analyses') or []:
                for key, value in analysis.get('edge_bindings',{}).items():
                    analysis['edge_bindings'][key] = [{'id':i} for i in binding_ids(value)]
        payload.pop('schema_version',None)
        payload.pop('biolink_version',None)
        payload['parameters'] = {'log_level':'DEBUG'}
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    path = out/'request.json'
    if path.exists():
        assert json.loads(path.read_text()) == payload
    else:
        save(path,payload)
    response_path = out/'response.json'
    if not response_path.exists():
        if not args.send:
            parser.error('No cached scoring response; use --send')
        if (out/'attempt.json').exists():
            parser.error('Prior attempt exists; choose fresh output for an explicit retry')
        record = dict(endpoint=endpoint, retrieval_endpoint=attempt['endpoint'], qid=attempt['qid'],
            request_sha256=digest(path), source_response_sha256=attempt['response_sha256'],
            started_at=datetime.now(timezone.utc).isoformat(), timeout_seconds=600,
            workflow=payload['workflow'], automatic_retries=0)
        save(out/'attempt.json',record)
        start=time.perf_counter()
        try:
            req=urllib.request.Request(record['endpoint'],data=path.read_bytes(),
                headers={'Content-Type':'application/json','Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=600) as response:
                content=response.read()
                record.update(http_status=response.status,response_headers=dict(response.headers))
            response_path.write_bytes(content)
            record['response_sha256']=digest(response_path)
        except urllib.error.HTTPError as error:
            (out/'http_error_body.txt').write_bytes(error.read())
            record.update(http_status=error.code,error=str(error))
        except Exception as error:
            record['error']=repr(error)
        finally:
            record.update(elapsed_seconds=time.perf_counter()-start,
                finished_at=datetime.now(timezone.utc).isoformat())
            save(out/'attempt.json',record)
        if not response_path.exists():
            print(json.dumps(record,indent=2))
            raise SystemExit(1)
    record=json.loads((out/'attempt.json').read_text())
    assert record['endpoint']==endpoint, 'Cached scoring deployment differs'
    assert digest(response_path)==record['response_sha256']
    scored=json.loads(response_path.read_text())
    request=json.loads((source/'request.json').read_text())
    before,after=inspect(raw,request),inspect(scored,request)
    matched=before['candidate_ids']==after['candidate_ids']
    results=scored.get('message',{}).get('results') or []
    scored_results=sum(any(isinstance(a.get('score'),(int,float)) and math.isfinite(a['score'])
                          for a in r.get('analyses') or []) for r in results)
    report=dict(qid=attempt['qid'],endpoint=endpoint,matched_candidate_ids=matched,
        source_candidates=before['candidates'],scored_candidates=after['candidates'],
        source_response_sha256=attempt['response_sha256'],response_sha256=record['response_sha256'],
        source_nodes=before['nodes'],scored_nodes=after['nodes'],source_edges=before['edges'],
        scored_edges=after['edges'],reference_issues=after['reference_issues'],
        results_with_finite_scores=scored_results,total_results=len(results),
        scoring_complete=bool(results) and scored_results==len(results),
        problem_logs=after['problem_logs'],
        evidence_note='Same retrieval input. Standard ARAGORN workflow adds OmniCorp literature evidence; comparison is of complete scorers, not identical feature representations.')
    save(out/'inspection.json',report)
    print(json.dumps(report,indent=2))
    if not matched or after['reference_issues']:
        raise SystemExit('Scoring response failed matched-cohort/reference checks')
    if not results or scored_results!=len(results):
        raise SystemExit('Response is missing finite analysis scores; HTTP success is not scoring success')


if __name__=='__main__':
    main()
