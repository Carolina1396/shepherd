"""Offline graph-wide inventory of qualifier conditions in rules 12/13/16."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import orjson
import yaml

ROOT=Path(__file__).resolve().parents[4]
RULES={12:('metabolic_processing','decreased'),13:('transport','decreased'),16:('secretion','increased')}

def save(p,d):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2)+'\n')

def descendants(items,name):
 found={name}
 while True:
  more={k for k,v in items.items() if v and (v.get('is_a') in found or set(v.get('mixins',[]))&found)}
  if more<=found:return found
  found|=more

def values(v):
 return v if isinstance(v,list) else [v]

def qualifiers(edge):
 pairs=[]
 for key,value in edge.items():
  bare=key.removeprefix('biolink:')
  if bare.endswith('_qualifier') or bare in ('object_aspect','subject_aspect','object_direction','subject_direction'):
   for v in values(value):
    if isinstance(v,str):pairs.append((bare,v,'top_level'))
 for q in edge.get('qualifiers') or []:
  if isinstance(q,dict):
   for v in values(q.get('qualifier_value')):
    if isinstance(v,str):pairs.append((q.get('qualifier_type_id','').removeprefix('biolink:'),v,'qualifiers'))
 for q in edge.get('attributes') or []:
  if isinstance(q,dict):
   key=q.get('attribute_type_id','').removeprefix('biolink:')
   if 'qualifier' in key or key in ('object_aspect','subject_aspect','object_direction','subject_direction'):
    for v in values(q.get('value')):
     if isinstance(v,str):pairs.append((key,v,'attributes'))
 return pairs

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--raw',type=Path,default=Path('/home/agonzalez/shepherd/experiments/ultra/data/tier0-20260621/raw'))
 parser.add_argument('--output',type=Path,default=ROOT/'output/qualifier-graph-audit/run_001')
 args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 modelpath=ROOT/'output/predicate-model-audit/source/biolink-model.yaml';model=yaml.safe_load(modelpath.read_text())
 enums={k:v for e in model['enums'].values() for k,v in e.get('permissible_values',{}).items()}
 aspects={n:descendants(enums,a) for n,(a,d) in RULES.items()};directions={n:descendants(enums,d) for n,(a,d) in RULES.items()}
 affect_preds={'biolink:'+s.replace(' ','_') for s in descendants(model['slots'],'affects')}
 needed=set().union(*aspects.values())
 before={str(args.raw/n):{'size':(args.raw/n).stat().st_size,'mtime_ns':(args.raw/n).stat().st_mtime_ns} for n in ('edges.jsonl','nodes.jsonl')}
 cmd=['rg','--text','--no-heading','--no-line-number','-F']
 for v in sorted(needed):cmd+=['-e',json.dumps(v)]
 cmd += [str(args.raw/'edges.jsonl')]
 print('Scanning all raw edges for required aspect values and descendants:',sorted(needed),flush=True)
 proc=subprocess.Popen(cmd,stdout=subprocess.PIPE)
 target_rows=[];endpoint_ids=set();field_counts=Counter();aspect_counts=Counter();candidate_lines=0
 with (args.output/'aspect-bearing-edges.jsonl').open('wb') as handle:
  for line in proc.stdout:
   candidate_lines+=1;e=orjson.loads(line);pairs=qualifiers(e)
   if not any(v in needed for _,v,_ in pairs):continue
   handle.write(line);target_rows.append(e);endpoint_ids.update((e['subject'],e['object']))
   for k,v,source in set(pairs):
    field_counts[(k,v,source)]+=1
    if v in needed:aspect_counts[(e['predicate'],k,v)]+=1
 if proc.wait() not in (0,1):raise RuntimeError('Raw edge scan failed')
 print('Aspect-bearing records:',len(target_rows),'; reading endpoint nodes...',flush=True)
 nodes={}
 with (args.raw/'nodes.jsonl').open('rb') as handle:
  for line in handle:
   n=orjson.loads(line)
   if n['id'] in endpoint_ids:nodes[n['id']]=n
 assert endpoint_ids<=nodes.keys(),'Missing endpoint nodes'
 def cats(n):
  return set(values(n.get('category',n.get('categories',[]))))
 chemical={'biolink:'+''.join(w[0].upper()+w[1:] for w in n.split()) for n in descendants(model['classes'],'chemical entity')}
 biological={'biolink:'+''.join(w[0].upper()+w[1:] for w in n.split()) for n in descendants(model['classes'],'biological entity')}
 results={};witnesses=[]
 for rule,(aspect,direction) in RULES.items():
  counts=Counter();types=Counter();examples={}
  for e in target_rows:
   q={}
   for k,v,source in qualifiers(e):q.setdefault(k,set()).add(v)
   family=e['predicate'] in affect_preds
   typed=bool(cats(nodes[e['subject']])&biological) and bool(cats(nodes[e['object']])&chemical)
   for side in ('object','subject'):
    aspect_match=bool(q.get(side+'_aspect_qualifier',set())&aspects[rule]);direction_match=bool(q.get(side+'_direction_qualifier',set())&directions[rule])
    if aspect_match:
     counts[side+'_aspect_any_direction']+=1
     if not direction_match:counts[side+'_aspect_wrong_or_missing_direction']+=1
    if not (aspect_match and direction_match):continue
    bucket=side+('_affects_family' if family else '_other_predicate')
    counts[bucket]+=1
    exact=aspect in q.get(side+'_aspect_qualifier',set()) and direction in q.get(side+'_direction_qualifier',set())
    if exact:counts[bucket+'_exact_values']+=1
    if family and typed:counts[bucket+'_rule_endpoint_types']+=1
    if family and not typed:counts[bucket+'_other_endpoint_types']+=1
    sc=tuple(sorted(cats(nodes[e['subject']])));oc=tuple(sorted(cats(nodes[e['object']])))
    types[(side,e['predicate'],sc,oc)]+=1
    key=bucket+('_typed' if typed else '_other_types')
    if key not in examples:examples[key]=dict(rule=rule,case=key,raw_edge=e,subject=nodes[e['subject']],object=nodes[e['object']],observed_qualifiers=qualifiers(e),required_aspect=aspect,required_direction=direction)
  for key in ('object_affects_family','object_affects_family_rule_endpoint_types','subject_affects_family','object_other_predicate'):counts.setdefault(key,0)
  results[str(rule)]=dict(required_aspect=aspect,required_direction=direction,accepted_aspect_values=sorted(aspects[rule]),accepted_direction_values=sorted(directions[rule]),counts=dict(counts),category_patterns=[dict(side=side,predicate=pred,subject_categories=list(sc),object_categories=list(oc),records=c) for (side,pred,sc,oc),c in types.items()])
  witnesses.extend(examples.values())
 for filename,v in before.items():
  st=Path(filename).stat();assert v==dict(size=st.st_size,mtime_ns=st.st_mtime_ns),'Raw file changed'
 report=dict(created_utc=datetime.now(timezone.utc).isoformat(),model_version='4.3.2',model_sha256=hashlib.sha256(modelpath.read_bytes()).hexdigest(),inputs=before,raw_text_candidate_lines=candidate_lines,aspect_bearing_records=len(target_rows),affects_predicate_family=sorted(affect_preds),rule_results=results,qualifier_field_value_counts=[dict(field=k,value=v,representation=s,records=c) for (k,v,s),c in field_counts.most_common()],aspect_predicate_counts=[dict(predicate=p,field=k,value=v,records=c) for (p,k,v),c in aspect_counts.most_common()],limitations=['Local downloaded release only, not an independent hosted graph scan.','Counts are raw records; multi-valued annotations are inventoried as sets, not proof of deployed matching semantics.','Alternative fields and subject qualifiers are inventoried, not substituted into original rules.','Only explicit qualifier fields and qualifier-typed attributes are interpreted; free text is not a qualifier.'])
 save(args.output/'findings.json',report);save(args.output/'witnesses.json',witnesses)
 print(json.dumps({n:v['counts'] for n,v in results.items()},indent=2),flush=True)
 print('Saved witness cases:',len(witnesses),flush=True)
if __name__=='__main__':main()
