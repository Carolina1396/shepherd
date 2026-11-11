"""Explicit service lookups; no local graph-reader fallback."""
import gzip,json,time,urllib.request,urllib.error
from collections import defaultdict
from copy import deepcopy
from template_format import make_query,matches_qualifiers
from predicate_semantics import SYMMETRIC_PREDICATES

def binding_ids(b):
    return b.get('ids',[]) if isinstance(b,dict) else [v['id'] for v in b or []]

def interpret(data,template,disease,limits):
    message=data.get('message') or {};kg=message.get('knowledge_graph') or {'nodes':{},'edges':{}}
    warnings=[x for x in data.get('logs',[]) if x.get('level','').upper() in ('WARNING','ERROR')]
    state='complete' if data.get('status') in (None,'Success','OK','NoResults') and isinstance(data.get('message'),dict) else 'failed'
    if warnings and state=='complete':state='partial'
    paths=[];seen=set();drugs=set();issues=[]
    try:
        for result in message.get('results',[]):
            bindings={k:set(binding_ids(v)) for k,v in result['node_bindings'].items()}
            for analysis in result.get('analyses',[]):
                matches={}
                for name in ('drug_edge','disease_edge'):
                    qe=template['edges'][name];by_mid=defaultdict(list)
                    for eid in binding_ids(analysis['edge_bindings'][name]):
                        edge=kg['edges'][eid]
                        if not matches_qualifiers(edge.get('qualifiers'),qe):
                            raise ValueError('Service returned a bound edge missing requested exact qualifiers: '+eid)
                        subject, obj = edge['subject'], edge['object']
                        if subject not in bindings[qe['subject']] or obj not in bindings[qe['object']]:
                            if (qe['predicate'] in SYMMETRIC_PREDICATES and edge['predicate'] in SYMMETRIC_PREDICATES
                                    and obj in bindings[qe['subject']] and subject in bindings[qe['object']]):
                                subject, obj = obj, subject
                            else:
                                raise ValueError('Edge endpoints disagree with result bindings')
                        # Align query roles only; retain stored edges and qualifier orientation.
                        m=subject if qe['subject']=='intermediate' else obj
                        endpoint=obj if qe['subject']=='intermediate' else subject
                        by_mid[m].append((endpoint,eid))
                    matches[name]=by_mid
                for mid,left in matches['drug_edge'].items():
                    for drug,e1 in left:
                        for d,e2 in matches['disease_edge'].get(mid,[]):
                            if d!=disease:raise ValueError('Returned disease differs from pinned disease')
                            if len({drug,mid,d})!=3:continue
                            path=(drug,mid,d,e1,e2)
                            if path in seen:continue
                            if len(paths)>=limits['max_paths'] or (drug not in drugs and len(drugs)>=limits['max_candidates']):
                                return {'state':'evidence_limit','paths':paths,'knowledge_graph':kg,'issues':issues,'warnings':warnings}
                            for n in (drug,mid,d):
                                if n not in kg['nodes']:raise ValueError('Missing evidence node')
                            paths.append(list(path));seen.add(path);drugs.add(drug)
    except (KeyError,TypeError,ValueError) as e:
        state='invalid_evidence';issues.append(str(e));paths=[]
    return {'state':state,'paths':paths,'knowledge_graph':kg,'issues':issues,'warnings':warnings}

class ServiceExecutor:
    def __init__(self,config):self.config=config
    def lookup(self,template,disease,directory):
        directory.mkdir(parents=True,exist_ok=True)
        q=make_query(template,disease)
        q['workflow']=[{'id':'aragorn.lookup'}]
        q['parameters']['timeout']=self.config['timeout']
        (directory/'request.json').write_text(json.dumps(q,indent=2)+'\n')
        start=time.monotonic();status=None
        try:
            req=urllib.request.Request(self.config['local_url'],data=json.dumps(q).encode(),headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=self.config['timeout']+60) as r:raw=r.read();status=r.status
            except urllib.error.HTTPError as e:raw=e.read();status=e.code
            with gzip.open(directory/'response.json.gz','wb') as f:f.write(raw)
            data=json.loads(raw)
            record=interpret(data,template,disease,self.config['limits'])
            if status!=200:record['state']='failed';record['paths']=[]
        except (OSError,ValueError) as e:
            record={'state':'failed','paths':[],'knowledge_graph':{'nodes':{},'edges':{}},'issues':[str(e)],'warnings':[]}
        record.update(seconds=round(time.monotonic()-start,6),http_status=status,source_artifacts=str(directory.resolve()))
        return record

def check_metadata(config,root):
    with urllib.request.urlopen(config['retriever_url']+'/metadata/tier_0',timeout=20) as r:remote=json.load(r)
    local=json.loads((root/config['graph']/'graph-metadata.json').read_text())
    if remote!=local:raise ValueError('Live Retriever metadata does not match filtered graph')
    return remote
