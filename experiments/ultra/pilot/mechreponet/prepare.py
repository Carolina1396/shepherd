"""Prepare MechRepoNet indications using the pair split and masking of Experiment 3."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from full_graph_common import digest, hidden_pair_mask, save, split_pairs


def eligible_pair(h, predicate, t, categories):
    return predicate=='indication' and categories[h]=='ChemicalSubstance' and categories[t]=='Disease'


def triples(path):
    with path.open() as stream:
        for number,line in enumerate(stream,1):
            fields=line.rstrip('\n').split('\t')
            if len(fields)!=3: raise ValueError(f'Malformed source row {number}')
            yield fields


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,default=Path('/home/agonzalez/git/ULTRA/kg-datasets/MechRepoNet/raw/graph.txt.backup'))
    parser.add_argument('--nodes',type=Path,default=Path('/home/agonzalez/data_KG/MIND_nodes/nodes.csv'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve()
    if out.exists():parser.error('Refusing to overwrite existing preparation')
    start=time.perf_counter()
    props={}
    with args.nodes.open() as stream:
        for row in csv.DictReader(stream):
            assert row['id'] not in props
            props[row['id']]={'name':row['name'],'category':row['label']}
    categories={k:v['category'] for k,v in props.items()}
    connected=set();relations=set();pairs=set();excluded=Counter();raw_count=0
    print('Inventorying original MechRepoNet triples and node categories...',flush=True)
    for h,p,t in triples(args.graph):
        assert h in categories and t in categories, 'Missing source category'
        connected.update((h,t));relations.add(p);raw_count+=1
        if eligible_pair(h,p,t,categories):pairs.add((h,t))
        elif p=='indication':excluded[f'{categories[h]} -> {categories[t]}']+=1
    nodes=sorted(connected);indices={v:i for i,v in enumerate(nodes)}
    predicates=sorted(relations);relation_indices={v:i for i,v in enumerate(predicates)}
    n,p=len(nodes),len(predicates)
    assert n*n*p<np.iinfo(np.int64).max
    labels=[{'drug':h,'disease':t,'drug_index':indices[h],'disease_index':indices[t],'split':s}
            for h,t,s in split_pairs(pairs,731)]
    counts=dict(Counter(r['split'] for r in labels))
    assert all(counts.get(s,0)>0 for s in ['visible','validation','test'])
    hidden={(r['drug_index'],r['disease_index']) for r in labels if r['split']!='visible'}
    candidates=[{'index':i,'id':v,'name':props[v]['name']} for i,v in enumerate(nodes) if categories[v]=='ChemicalSubstance']
    drugs={r['index'] for r in candidates};diseases={i for i,v in enumerate(nodes) if categories[v]=='Disease'}
    print(f'{len(pairs)} eligible indication pairs, splits {counts}, {len(candidates)} ChemicalSubstance candidates',flush=True)
    encoded=np.fromiter(((indices[h]*p+relation_indices[r])*n+indices[t] for h,r,t in triples(args.graph)),dtype=np.int64,count=raw_count)
    unique=np.unique(encoded);del encoded
    heads,types,tails=unique//(n*p),(unique//n)%p,unique%n
    original_unique=len(unique);del unique
    remove=hidden_pair_mask(heads,tails,hidden,n)
    removed_predicates=dict(Counter(predicates[int(r)] for r in types[remove]))
    masked=np.column_stack((heads[~remove],types[~remove],tails[~remove]))
    assert not hidden_pair_mask(masked[:,0],masked[:,2],hidden,n).any()
    target=relation_indices['indication']
    actual={(int(h),int(t)) for h,r,t in masked[masked[:,1]==target] if int(h) in drugs and int(t) in diseases}
    assert actual=={(r['drug_index'],r['disease_index']) for r in labels if r['split']=='visible'}
    active=np.zeros(n,dtype=bool);active[masked[:,0]]=True;active[masked[:,2]]=True
    visible_diseases={r['disease'] for r in labels if r['split']=='visible'}
    for row in labels:
        row.update(disease_has_visible_treatment=row['disease'] in visible_diseases,
                   drug_isolated=not bool(active[row['drug_index']]),disease_isolated=not bool(active[row['disease_index']]))
    data=out/'data';data.mkdir(parents=True)
    np.save(data/'triples.npy',masked)
    save(data/'nodes.json',[{'id':v,'category':categories[v]} for v in nodes])
    save(data/'labels.json',labels);save(data/'candidates.json',candidates);save(data/'predicates.json',predicates)
    tier= json.loads((ROOT/'output/full-graph-ultra/run_001/config.json').read_text())
    assert digest(ROOT/tier['checkpoint'])==tier['checkpoint_sha256']
    cfg={'experiment':'8','graph':'MechRepoNet original graph.txt.backup','protocol_reference':'Experiment 3',
         'num_nodes':n,'num_relations':p,'target_predicate':'indication','candidate_category':'ChemicalSubstance',
         'disease_category':'Disease','split_seed':731,'pair_splits':counts,'training_epochs':0,
         'checkpoint':tier['checkpoint'],'checkpoint_sha256':tier['checkpoint_sha256'],'ultra_commit':tier['ultra_commit'],
         'ranking':'Given disease, rank all connected ChemicalSubstance nodes; all-known filtering and pessimistic ties',
         'mask':'Every direct connection of every validation/test pair, all predicates and both directions; original nodes retained',
         'difference_from_tier0':'Source has no Drug category: chemical candidates instead of Tier 0 Drug-only candidates; different labels and candidate count'}
    save(out/'config.json',cfg)
    sources=[Path(__file__),ROOT/'scripts/full_graph_common.py']
    for path in sources:shutil.copyfile(path,out/path.name)
    report={'complete':True,'nodes':n,'candidate_compounds':len(candidates),'disease_nodes':len(diseases),
            'eligible_pairs':len(pairs),'pair_splits':counts,
            'queries_by_split':{s:len({r['disease'] for r in labels if r['split']==s}) for s in counts},
            'original_edge_records':raw_count,'original_unique_connections':original_unique,
            'removed_connections':int(remove.sum()),'removed_by_predicate':removed_predicates,
            'remaining_connections':len(masked),'edges_with_inverses':2*len(masked),
            'non_target_indication_records_by_categories':dict(excluded),
            'isolated_candidate_compounds':sum(not bool(active[i]) for i in drugs),
            'all_heldout_direct_connections_absent':True,'all_visible_indication_pairs_retained':True,
            'source_files':{str(path.resolve()):digest(path) for path in [args.graph,args.nodes]},
            'source_code_sha256':{path.name:digest(path) for path in sources},
            'config_sha256':digest(out/'config.json'),'dataset_sha256':{path.name:digest(path) for path in sorted(data.iterdir())},
            'preparation_seconds':time.perf_counter()-start}
    save(out/'preparation.json',report);print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
