"""Fixed screening/ranked evaluation. No autonomous edits or test-set access."""
import argparse,csv,fcntl,gzip,hashlib,json,math,os,statistics,time,urllib.request,urllib.error
from pathlib import Path
from prepare import HERE,ROOT,digest
from template_format import validate_collection,template_hash
from service_execute import ServiceExecutor,check_metadata
from build_candidates import build_service
from runtime import capture

def save(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(obj,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def hash_object(o):return hashlib.sha256(json.dumps(o,sort_keys=True).encode()).hexdigest()
def metrics(rows):
    grouped={}
    for r in rows:grouped.setdefault(r['disease'],[]).append(r)
    return {'pairs':len(rows),'pair_recovery':sum(r['recovered'] for r in rows)/len(rows),
            'pair_mrr_at_500':sum(r['rr'] for r in rows)/len(rows),
            'macro_hits_at_10':statistics.mean(sum(r['rank'] is not None and r['rank']<=10 for r in rs)/len(rs) for rs in grouped.values()),
            'macro_recovery':statistics.mean(sum(r['recovered'] for r in rs)/len(rs) for rs in grouped.values())}
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mode',choices=['screen','ranked'],required=True)
    ap.add_argument('--batch',choices=['debug','train_a','train_b','validation'],required=True)
    ap.add_argument('--templates',type=Path,default=HERE/'templates.json')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--disease',help='Training-only manual rehearsal; never eligible for selection')
    a=ap.parse_args();c=json.load(open(HERE/'config.json'));b=json.load(open(HERE/'batches.json'))
    if b['config_sha256']!=digest(HERE/'config.json'):raise ValueError('Protocol changed since preparation')
    for key in ('train','validation'):
        if b[key+'_sha256']!=digest(ROOT/c[key]):raise ValueError('Labels changed')
    if b['graph_report_sha256']!=digest(ROOT/c['graph']/'filtering_report.json'):raise ValueError('Graph changed')
    templates=validate_collection(json.load(a.templates.open()))
    if not templates['templates']:raise ValueError('Use at least one template')
    if a.batch=='validation' and a.disease:raise ValueError('Validation cannot be cherry-picked')
    with (ROOT/c['validation' if a.batch=='validation' else 'train']).open() as f:labels=list(csv.DictReader(f))
    diseases=sorted({r['disease_id'] for r in labels}) if a.batch=='validation' else b['batches'][a.batch]
    if a.disease:
        if a.disease not in {r['disease_id'] for r in labels}:raise ValueError('Rehearsal disease must be a training disease')
        diseases=[a.disease]
    labels=[r for r in labels if r['disease_id'] in diseases]
    a.out.mkdir(parents=True,exist_ok=False)
    lock=(HERE/'runs/runner.lock');lock.parent.mkdir(exist_ok=True)
    with lock.open('w') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:os.nice(15)
        except OSError:pass
        source={str(p.relative_to(ROOT)):digest(p) for p in sorted(HERE.glob('*.py'))}
        manifest={'config':c,'inputs':b,'code':source,'mode':a.mode,'batch':a.batch,'diseases':diseases,'templates':templates,
                  'note':'Explicit lookup through Shepherd/Retriever/filtered Gandalf; local enrichment/ranking. No AMIE expansion.'}
        manifest['runtime']=capture(ROOT)
        manifest['retrieval_metadata']=check_metadata(c,ROOT)
        save(a.out/'manifest.json',manifest);save(a.out/'templates.json',templates)
        for p in HERE.glob('*.py'):(a.out/p.name).write_bytes(p.read_bytes())
        print('Using local service retrieval',flush=True);executor=ServiceExecutor(c);rows=[];reports=[]
        identity={'backend':c['retrieval_backend'],'protocol':c,'runtime':manifest['runtime'],
                  'metadata':manifest['retrieval_metadata'],'code':source}
        for disease in diseases:
            directory=a.out/'queries'/hash_object(disease)[:24];records=[];began=time.monotonic()
            for t in templates['templates']:
                key=hash_object({'identity':identity,'template':template_hash(t),'disease':disease})
                cp=HERE/'cache'/(key+'.json')
                if cp.exists():rec=json.load(cp.open())
                else:
                    rec=executor.lookup(t,disease,directory/'lookups'/template_hash(t))
                    if rec['state']=='complete':save(cp,rec)
                records.append(rec)
            save(directory/'lookup.json',records)
            candidates={p[0] for r in records for p in r['paths']}
            complete=all(r['state'] in ('complete','missing_endpoint') for r in records)
            ranks={};errors=[];scorelist=[]
            if a.mode=='ranked' and candidates:
                message=build_service(disease,records)
                workflows=[('enriched',[{'id':'aragorn.omnicorp'}]),('ranked',[{'id':'aragorn.score'},{'id':'sort_results_score'},
                  {'id':'filter_results_top_n','parameters':{'max_results':c['result_cap']}},{'id':'filter_kgraph_orphans'}])]
                try:
                    for stage,workflow in workflows:
                        payload={'message':message,'workflow':workflow,'parameters':{'tiers':[0],'timeout':c['timeout']}}
                        with gzip.open(directory/(stage+'.request.json.gz'),'wt') as f:json.dump(payload,f)
                        req=urllib.request.Request(c['local_url'],data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
                        try:
                            with urllib.request.urlopen(req,timeout=c['timeout']+60) as response:raw=response.read()
                        except urllib.error.HTTPError as e:
                            raw=e.read();(directory/(stage+'.error.txt')).write_bytes(raw);raise
                        with gzip.open(directory/(stage+'.response.json.gz'),'wb') as f:f.write(raw)
                        data=json.loads(raw)
                        warnings=[x for x in data.get('logs',[]) if x.get('level','').upper() in ('ERROR','WARNING')]
                        if data.get('status') not in (None,'Success','OK','NoResults') or warnings:
                            raise ValueError('Non-success or warnings: '+str(warnings)[:1000])
                        message=data['message']
                    scored={}
                    for r in message.get('results',[]):
                        ids=r['node_bindings']['drug']['ids']
                        scores=[z.get('score') for z in r.get('analyses',[])]
                        scores=[v for v in scores if isinstance(v,(int,float)) and math.isfinite(v)]
                        if not scores:raise ValueError('Missing finite score')
                        for drug in ids:scored[drug]=max(scored.get(drug,-math.inf),max(scores))
                    if not scored:raise ValueError('Scoring dropped all nonempty input candidates')
                    ranked=sorted(scored,key=lambda x:(-scored[x],x));ranks={drug:i+1 for i,drug in enumerate(ranked)}
                    scorelist=[{'drug':d,'rank':ranks[d],'score':scored[d]} for d in ranked]
                except (OSError,ValueError,KeyError) as e:complete=False;errors=[str(e)]
            for r in labels:
                if r['disease_id']!=disease:continue
                rank=ranks.get(r['drug_id'])
                rows.append({'drug':r['drug_id'],'disease':disease,'recovered':r['drug_id'] in candidates if a.mode=='screen' else rank is not None,
                             'rank':rank,'rr':1/rank if rank else 0,'complete':complete})
            report={'disease':disease,'complete':complete,'lookup_states':[r['state'] for r in records],'candidate_count':len(candidates),
                    'seconds':round(time.monotonic()-began,3),'errors':errors,'ranked':scorelist}
            save(directory/'record.json',report);reports.append(report);print(json.dumps({k:v for k,v in report.items() if k!='ranked'}),flush=True)
        measured=metrics(rows)
        if a.mode=='screen':
            measured.pop('pair_mrr_at_500');measured.pop('macro_hits_at_10')
        runtime_unchanged=capture(ROOT)==manifest['runtime'] and check_metadata(c,ROOT)==manifest['retrieval_metadata']
        all_complete=all(r['complete'] for r in reports) and runtime_unchanged
        result={'mode':a.mode,'batch':a.batch,'complete':all_complete,'metrics':measured,
          'runtime_unchanged':runtime_unchanged,
          'eligible_for_selection':a.mode=='ranked' and a.batch=='validation' and not a.disease and all_complete,
          'candidate_mean':statistics.mean(r['candidate_count'] for r in reports),
          'candidate_max':max(r['candidate_count'] for r in reports),'query_seconds':sum(r['seconds'] for r in reports),
          'incomplete_diseases':[r['disease'] for r in reports if not r['complete']],
          'interpretation':'Observed metrics include incomplete runs; never select from incomplete evaluation.',
          'treatment_or_procedure_templates':[t['id'] for t in templates['templates'] if 'Procedure' in t['intermediate_category'] or any(any(x in e['predicate'] for x in ('treat','clinical_trial')) for e in t['edges'].values())]}
        save(a.out/'pairs.json',rows);save(a.out/'summary.json',result)
        with (HERE/'runs/results.jsonl').open('a') as f:f.write(json.dumps({'out':str(a.out),'candidate_hash':hash_object(templates),**result})+'\n')
        print(json.dumps(result),flush=True)
if __name__=='__main__':main()
