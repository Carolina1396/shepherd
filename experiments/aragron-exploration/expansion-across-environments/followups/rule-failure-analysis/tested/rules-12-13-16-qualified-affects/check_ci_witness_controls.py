"""Four CI unqualified controls for saved qualified witnesses; offline by default."""
import argparse,copy,json,time
from pathlib import Path
import verify_graph_witnesses as shared
ROOT=shared.ROOT

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--submit',action='store_true');args=p.parse_args()
 run=ROOT/'output/qualifier-graph-audit/hosted-witnesses_001';out=ROOT/'output/qualifier-graph-audit/ci-unqualified_001'
 witnesses=shared.read(run/'witnesses.json')['witnesses'];rows=[]
 client=None
 if args.submit:
  import httpx
  client=httpx.Client(timeout=90,follow_redirects=False)
 for w in witnesses:
  case=out/w['id'];q=shared.read(run/'ci_staging'/w['id']/'request.json');q['message']['query_graph']['edges']['e'].pop('qualifier_constraints')
  if args.submit and not (case/'submission.json').exists():
   shared.save(case/'request.json',q);state=dict(endpoint=shared.ENDPOINTS['ci_staging']+'/query',state='submitting',started_utc=shared.now(),runner_sha256=shared.sha(Path(__file__)))
   shared.save(case/'submission.json',state)
   try:
    r=client.post(state['endpoint'],json=q);(case/'response.body').write_bytes(r.content);state.update(state='response_received',http_status=r.status_code);shared.save(case/'response.json',r.json())
   except Exception as e:state.update(state='uncertain_or_unparsed',error=str(e))
   finally:state['finished_utc']=shared.now();shared.save(case/'submission.json',state)
   time.sleep(2)
  if not (case/'submission.json').exists():continue
  d=shared.read(case/'response.json') if (case/'response.json').exists() else {}
  s=shared.classify(w,d,shared.read(case/'submission.json'));s['query_graph_matches']=(d.get('message') or {}).get('query_graph')==q['message']['query_graph'];s['control']='unqualified';s['pattern']=w['id'];s['warnings_errors']=[l for l in d.get('logs',[]) if l.get('level') in ['WARNING','ERROR']]
  shared.save(case/'summary.json',s);rows.append(s);print(w['id'],s['outcome'],s['raw_results'],s['returned_witness_qualifiers'],flush=True)
 if client:client.close()
 shared.save(out/'summary.json',dict(scope='Same four CI requests with only qualifier_constraints removed.',rows=rows))
if __name__=='__main__':main()
