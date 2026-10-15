"""Independently verify Experiment 10 labels, candidate types, split and masking."""
import argparse,json,sys,random
from pathlib import Path
from collections import Counter
import numpy as np
from gandalf import CSRGraph
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'scripts'))
from full_graph_common import digest,save
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--dataset',type=Path,required=True)
out=parser.parse_args().dataset.resolve()
manifest=json.loads((out/'preparation.json').read_text())
for name,value in manifest['dataset_sha256'].items(): assert digest(out/'data'/name)==value
G=CSRGraph.load_mmap(root/'output/gandalf/full-store',mmap_mode='r');n=G.num_nodes
pos=np.flatnonzero(G.fwd_predicates==G.predicate_to_idx['biolink:treats'])
heads=np.searchsorted(G.fwd_offsets,pos,side='right')-1
expected=set();diseases=set()
for i,props in G.node_store.iter_properties():
 categories=set(props.get('categories',[]))
 if categories & {'biolink:Drug','biolink:SmallMolecule','biolink:ChemicalEntity'}: expected.add(i)
 if 'biolink:Disease' in categories:diseases.add(i)
pairs={(int(h),int(t)) for h,t in zip(heads,G.fwd_targets[pos]) if int(h) in expected and int(t) in diseases}
labels=json.loads((out/'data/labels.json').read_text())
assert {(r['drug_index'],r['disease_index']) for r in labels}==pairs
ordered=sorted((G.get_node_id(h),G.get_node_id(t)) for h,t in pairs);random.Random(731).shuffle(ordered)
a,b=int(.8*len(ordered)),int(.1*len(ordered))
for s,rows in [('visible',ordered[:a]),('validation',ordered[a:a+b]),('test',ordered[a+b:])]:
 assert set(rows)=={(r['drug'],r['disease']) for r in labels if r['split']==s}
candidates=json.loads((out/'data/candidates.json').read_text())
assert expected=={r['index'] for r in candidates}
assert {h for h,t in pairs}<=expected
hidden={(r['drug_index'],r['disease_index']) for r in labels if r['split']!='visible'}
for h,t in list(hidden): hidden.add((t,h))
hidden_keys=np.array(sorted(h*n+t for h,t in hidden),dtype=np.int64)
triples=np.load(out/'data/triples.npy',mmap_mode='r')
for i in range(0,len(triples),1000000):
 block=triples[i:i+1000000]
 assert not np.isin(block[:,0]*n+block[:,2],hidden_keys).any()
assert len(pairs)==22918 and len(candidates)==1117832
report={'complete':True,'raw_treats_records':len(pos),'deduplicated_pairs':len(pairs),'pair_splits':dict(Counter(r['split'] for r in labels)), 'candidates':len(candidates),'all_eligible_treats_pairs_in_split':True,'all_targets_have_Disease_category':True,'exact_seed731_split':True,'all_eligible_category_nodes_are_candidates':True,'all_target_subjects_in_candidate_pool':True,'no_heldout_direct_pair_in_either_direction':True,'prepared_file_hashes_verified':True}
save(out/'independent_verification.json',report);print(json.dumps(report,indent=2),flush=True)
