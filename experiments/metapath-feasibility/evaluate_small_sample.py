import csv,json,pickle,random,time,itertools,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from functools import lru_cache
import numpy as np,lmdb,msgpack
ROOT=Path(__file__).resolve().parents[2]; G=ROOT/'artifacts/gandalf_no_drug_disease'
meta=pickle.load(open(G/'metadata.pkl','rb')); preds={v:k for k,v in meta['predicate_to_idx'].items()}
a={n:np.load(G/(n+'.npy'),mmap_mode='r') for n in ['fwd_offsets','fwd_targets','fwd_predicates','rev_offsets','rev_sources','rev_to_fwd','edge_quals_idx']}
pools=pickle.load(open(G/'edge_property_pools.pkl','rb')); quals=[tuple(sorted((q['qualifier_type_id'],q['qualifier_value']) for q in qs)) for qs in pools['quals_pool']];del pools
E=lmdb.open(str(G/'node_store.lmdb'),readonly=True,lock=False,max_dbs=3,readahead=False); ids=E.open_db(b'id_to_idx');props=E.open_db(b'properties');names=E.open_db(b'idx_to_id');tx=E.begin()
def idx(c):
 v=tx.get(c.encode(),db=ids);return int.from_bytes(v,'big') if v else None
@lru_cache(None)
def node(i):
 k=int(i).to_bytes(4,'big');p=msgpack.unpackb(tx.get(k,db=props),raw=False);return {'id':tx.get(k,db=names).decode(),'name':p.get('name'),'categories':p.get('categories',[])}
def cats(i):
 c=node(i)['categories'];return tuple(sorted(c if isinstance(c,list) else [c]))
def arrays(i):
 lo,hi=map(int,a['fwd_offsets'][i:i+2]);rl,rh=map(int,a['rev_offsets'][i:i+2]);return [(a['fwd_targets'][lo:hi],np.arange(lo,hi),'>'),(a['rev_sources'][rl:rh],a['rev_to_fwd'][rl:rh],'<')]
def adjacency(i):
 d=defaultdict(set)
 for ns,es,di in arrays(i):
  for n,e in zip(ns,es):
   if int(n)!=i:d[int(n)].add((di,preds[int(a['fwd_predicates'][e])],quals[int(a['edge_quals_idx'][e])]))
 return d
def inv(edges):return {(('<' if d=='>' else '>'),p,q) for d,p,q in edges}

import argparse,sys
sys.path.insert(0,str(ROOT/'data_split'))
from analyze_graph import DRUG_CATEGORIES
ap=argparse.ArgumentParser(description='Read-only 10-pair meta-path coverage and hub-dependence pilot.')
ap.add_argument('--out',type=Path,required=True)
args=ap.parse_args();OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
if (OUT/'summary.json').exists():raise RuntimeError('Completed output already exists; choose a new directory')
rows=list(csv.DictReader(open(ROOT/'data_split/nonisolated/train.csv')))
sample=random.Random(42).sample(rows,10)

def walks(d,z,h):
 A,B=adjacency(d),adjacency(z);assert z not in A
 if h==2:
  for m in sorted(A.keys() & B.keys()):yield (d,m,z),(A[m],inv(B[m]))
 else:
  def volume(ns):return sum(int(a['fwd_offsets'][n+1]-a['fwd_offsets'][n]+a['rev_offsets'][n+1]-a['rev_offsets'][n]) for n in ns)
  reverse=volume(B)<volume(A);left,right=(B,A) if reverse else (A,B);right_nodes=list(right)
  for u in sorted(left):
   links=defaultdict(set)
   for ns,es,di in arrays(u):
    for j in np.flatnonzero(np.isin(ns,right_nodes)):
     v=int(ns[j]);e=int(es[j])
     if v==u:continue
     links[v].add((di,preds[int(a['fwd_predicates'][e])],quals[int(a['edge_quals_idx'][e])]))
   for v,mid in links.items():
    if reverse:yield (d,v,u,z),(A[v],inv(mid),inv(B[u]))
    else:yield (d,u,v,z),(A[u],mid,inv(B[v]))

def signatures(ns,edges,qualified):
 c=tuple(cats(n) for n in ns)
 es=edges if qualified else [{(di,p) for di,p,q in ee} for ee in edges]
 for e in itertools.product(*es):yield c,e

def chemical(k):return any(DRUG_CATEGORIES.intersection(c) for c in k[0][1:-1])
def views(k):return ['all','chemical_only' if chemical(k) else 'no_chemical']
def describe(k):
 c,es=k
 return {'categories':c,'edges':[{'direction':e[0],'predicate':e[1],**({'qualifiers':dict(e[2])} if len(e)==3 else {})} for e in es]}

tables={(h,q):{} for h in (2,3) for q in (False,True)};pair_walks=[]
for i,r in enumerate(sample):
 d,z=idx(r['drug_id']),idx(r['disease_id']);assert d is not None and z is not None
 for h in (2,3):
  counts=Counter()
  for ns,edges in walks(d,z,h):
   assert all(ns[j]!=ns[j+1] for j in range(h))
   has_chem=any(DRUG_CATEGORIES.intersection(cats(n)) for n in ns[1:-1]);counts['all']+=1;counts['chemical_only' if has_chem else 'no_chemical']+=1
   for q in (False,True):
    tab=tables[h,q]
    for k in signatures(ns,edges,q):
     if k not in tab:tab[k]={'pairs':set(),'node_sequences':0,'witness':ns}
     tab[k]['pairs'].add(i);tab[k]['node_sequences']+=1
  pair_walks.append({'pair_index':i,'hops':h,'node_sequences':dict(counts)})
 print('Enumerated',i+1,r['drug_name'],flush=True)

rankings={};tracked={key:set() for key in tables}
for key,tab in tables.items():
 for view in ['all','no_chemical','chemical_only']:
  ordered=sorted((k for k in tab if view in views(k)),key=lambda k:(-len(tab[k]['pairs']),-tab[k]['node_sequences'],repr(k)))
  rankings[*key,view]=ordered
  tracked[key].update(ordered[:20])
hubs={key:{k:[defaultdict(set) for _ in range(key[0]-1)] for k in ks} for key,ks in tracked.items()}
for i,r in enumerate(sample):
 for h in (2,3):
  for ns,edges in walks(idx(r['drug_id']),idx(r['disease_id']),h):
   for q in (False,True):
    for k in signatures(ns,edges,q):
     if k in tracked[h,q]:
      for pos,n in enumerate(ns[1:-1]):hubs[h,q][k][pos][n].add(i)
 print('Audited hubs',i+1,flush=True)

summary=[]
for (h,q,view),ordered in rankings.items():
 tab=tables[h,q];name=f'{h}hop-{"qualified" if q else "unqualified"}-{view}'
 top=[]
 with open(OUT/(name+'.tsv'),'w') as stream:
  w=csv.writer(stream,delimiter='\t');w.writerow(['rank','pair_count','pair_coverage','distinct_drugs','distinct_diseases','node_sequences','categories','edges'])
  for rank,k in enumerate(ordered,1):
   r=tab[k];ps=r['pairs'];nd=len({sample[i]['drug_id'] for i in ps});nz=len({sample[i]['disease_id'] for i in ps})
   row={'rank':rank,**describe(k),'pair_count':len(ps),'pair_coverage':len(ps)/len(sample),'distinct_drugs':nd,'distinct_diseases':nz,'node_sequences':r['node_sequences']}
   w.writerow([rank,len(ps),row['pair_coverage'],nd,nz,r['node_sequences'],json.dumps(k[0]),json.dumps(row['edges'])])
   if rank<=20:
    hh=[]
    for pos,buckets in enumerate(hubs[h,q][k],1):
     n,pairs_for_node=min(buckets.items(),key=lambda item:(-len(item[1]),node(item[0])['id']))
     assert pairs_for_node<=ps
     hh.append({'intermediate_position':pos,'node':node(n),'supporting_pair_count':len(pairs_for_node),'fraction_of_signature_pairs':len(pairs_for_node)/len(ps),'distinct_intermediate_nodes':len(buckets)})
    top.append({**row,'supporting_pairs':[sample[i] for i in sorted(ps)],'example_path':[node(n) for n in r['witness']],'top_hubs_by_position':hh})
 json.dump(top,open(OUT/(name+'-top20.json'),'w'),indent=2)
 connected=set().union(*(tab[k]['pairs'] for k in ordered)) if ordered else set()
 summary.append({'hops':h,'qualified':q,'view':view,'signatures':len(ordered),'connected_pairs':len(connected),'pair_coverage':len(connected)/len(sample)})
# Verify the view partition preserves every signature and supporting sequence count.
for key,tab in tables.items():
 allset=set(rankings[*key,'all']);no=set(rankings[*key,'no_chemical']);yes=set(rankings[*key,'chemical_only'])
 assert not no&yes and no|yes==allset
for r in pair_walks:
 c=r['node_sequences'];assert c.get('all',0)==c.get('chemical_only',0)+c.get('no_chemical',0)
json.dump({'summary':summary,'pair_node_sequences':pair_walks},open(OUT/'summary.json','w'),indent=2)
json.dump({'seed':42,'sample':sample,'denominator_pairs':len(sample),'sample_source':'data_split/nonisolated/train.csv','sample_source_sha256':hashlib.sha256((ROOT/'data_split/nonisolated/train.csv').read_bytes()).hexdigest(),'graph':str(G),'graph_report_sha256':hashlib.sha256((G/'filtering_report.json').read_bytes()).hexdigest(),'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'chemical_categories':sorted(DRUG_CATEGORIES),'semantics':'Exact predicates/full category sets, both directions, no self-loops; repeated nodes otherwise allowed. Source duplicates collapsed. All paths fully enumerated for these 10 pairs.','ranking':'pair count descending, node sequences descending, lexical tie break','hub_metric':'Distinct supporting pairs containing node at this intermediate position / pairs supporting signature. Report one lexically selected node when tied.','interpretation':'Descriptive training-pair connectivity; not precision, candidate retrieval, or held-out prediction.'},open(OUT/'manifest.json','w'),indent=2)
print('DONE',json.dumps(summary),flush=True)
