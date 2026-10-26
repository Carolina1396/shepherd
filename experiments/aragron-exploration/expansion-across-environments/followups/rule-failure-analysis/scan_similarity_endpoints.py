"""Offline raw-edge scan for the model's similarity family and endpoint typing."""
import argparse,collections,hashlib,json,subprocess
from pathlib import Path
from datetime import datetime,timezone
import yaml
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--raw',type=Path,default=Path('/home/agonzalez/shepherd/experiments/ultra/data/tier0-20260621/raw'));p.add_argument('--output',type=Path,default=ROOT/'output/similarity-endpoint-audit');args=p.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 model_path=ROOT/'output/predicate-model-audit/source/biolink-model.yaml';model=yaml.safe_load(model_path.read_text())
 def descendants(definitions,name):
  found={name}
  while True:
   more={k for k,v in definitions.items() if v.get('is_a') in found or set(v.get('mixins',[]))&found}
   if more<=found:return found
   found|=more
 terms={'biolink:'+n.replace(' ','_') for n in descendants(model['slots'],'similar to')}
 chemical={'biolink:'+''.join(w[0].upper()+w[1:] for w in n.split()) for n in descendants(model['classes'],'chemical entity')}
 paths=[args.raw/'edges.jsonl',args.raw/'nodes.jsonl'];before={str(p):{'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in paths}
 cmd=['rg','--text','--no-line-number','--no-heading','-F']
 for term in sorted(terms):cmd+=['-e','"'+term+'"']
 cmd += [str(paths[0])]
 edges=[];counts=collections.Counter();ids=set()
 print('Scanning raw edge file for entire similarity predicate family...',flush=True)
 proc=subprocess.Popen(cmd,stdout=subprocess.PIPE)
 with (args.output/'matching-edges.jsonl').open('w') as out:
  for line in proc.stdout:
   e=json.loads(line)
   if e.get('predicate') not in terms:continue
   edges.append((e['subject'],e['object'],e['predicate']));ids.update((e['subject'],e['object']));counts[e['predicate']]+=1;out.write(line.decode())
 if proc.wait() not in (0,1):raise RuntimeError('Edge scan failed')
 print('Matching records:',len(edges),'; reading endpoint categories...',flush=True)
 nodes={};total=0
 with paths[1].open() as handle, (args.output/'endpoint-nodes.jsonl').open('w') as out:
  for line in handle:
   n=json.loads(line);total+=1
   if n['id'] in ids:nodes[n['id']]=n;out.write(line)
 def cats(n):
  c=n.get('category',n.get('categories',[]));return [c] if isinstance(c,str) else c
 missing=sorted(ids-nodes.keys());assert not missing,missing[:5]
 chemical_ids={i for i,n in nodes.items() if set(cats(n))&chemical}
 prefixes=('CHEBI:','PUBCHEM.COMPOUND:','CHEMBL.COMPOUND:','DRUGBANK:','UNII:')
 suspicious={i for i,n in nodes.items() if i.startswith(prefixes) or any(x.startswith(prefixes) for x in n.get('equivalent_identifiers',[]))}
 pairs=collections.Counter((tuple(sorted(cats(nodes[s]))),tuple(sorted(cats(nodes[o]))),pred) for s,o,pred in edges)
 report=dict(created_utc=datetime.now(timezone.utc).isoformat(),model_version='4.3.2',model_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),inputs=before,total_nodes_scanned=total,predicate_counts={t:counts[t] for t in sorted(terms)},unique_endpoints=len(ids),chemical_typed_endpoint_count=len(chemical_ids),chemical_to_chemical_records=sum(s in chemical_ids and o in chemical_ids for s,o,_ in edges),records_with_either_chemical_endpoint=sum(s in chemical_ids or o in chemical_ids for s,o,_ in edges),chemical_identifier_candidates=sorted(suspicious),chemical_identifier_details=[dict(id=i,name=nodes[i].get('name'),categories=cats(nodes[i]),chemical_aliases=[x for x in nodes[i].get('equivalent_identifiers',[]) if x.startswith(prefixes)]) for i in sorted(suspicious)],records_between_two_chemical_identifier_candidates=sum(s in suspicious and o in suspicious for s,o,_ in edges),chemical_category_set=sorted(chemical),category_pairs=[dict(subject_categories=s,object_categories=o,predicate=pred,records=c) for (s,o,pred),c in pairs.items()],limitations=['Full scan of downloaded release, not independently scanned hosted graph.','Node labels and identifiers may themselves be erroneous; arbitrary mislabeling without chemical identifiers is not ruled out.','Scope is the pinned model similarity hierarchy, not every possible chemically relevant relationship.'])
 assert before=={str(p):{'size':p.stat().st_size,'mtime_ns':p.stat().st_mtime_ns} for p in paths},'Inputs changed during scan'
 (args.output/'findings.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ('category_pairs','chemical_category_set')},indent=2))
if __name__=='__main__':main()
