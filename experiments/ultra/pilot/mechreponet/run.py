"""Evaluate pretrained 4g on masked MechRepoNet, using Experiment 3's ranking rules."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
import torch
from torch_geometric.data import Data

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'pilot'))
sys.path.insert(0,str(ROOT/'vendor/ULTRA'))
from full_graph_common import digest, hidden_pair_mask, save
from finetune.run import evaluate
from ultra import tasks
from ultra.models import Ultra


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--max-queries',type=int,help='Partial smoke check per split; resume without limit for final metrics')
    args=parser.parse_args()
    if args.max_queries is not None and args.max_queries<1:parser.error('max-queries must be positive')
    prepared=args.dataset.resolve();out=prepared/'evaluation'
    if out.exists() and not args.resume:parser.error('Evaluation exists; use --resume')
    read=lambda p:json.loads(p.read_text())
    cfg,manifest=read(prepared/'config.json'),read(prepared/'preparation.json')
    assert manifest['complete'] and cfg['training_epochs']==0
    assert digest(prepared/'config.json')==manifest['config_sha256']
    for name,expected in manifest['dataset_sha256'].items():assert digest(prepared/'data'/name)==expected,name
    checkpoint=ROOT/cfg['checkpoint'];assert digest(checkpoint)==cfg['checkpoint_sha256']
    original=read(ROOT/'output/full-graph-ultra/run_001/config.json')
    assert cfg['checkpoint_sha256']==original['checkpoint_sha256']
    upstream=ROOT/'vendor/ULTRA'
    assert subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()==cfg['ultra_commit']
    subprocess.run(['git','-C',str(upstream),'diff','--quiet','HEAD','--','ultra'],check=True)
    assert torch.cuda.is_available(),'Use scripts/gpu_python.sh'
    torch.set_num_threads(8);torch.manual_seed(1024)
    code=[Path(__file__),ROOT/'pilot/finetune/run.py',ROOT/'scripts/full_graph_common.py']
    settings={'experiment':8,'protocol_reference':'Experiment 3','checkpoint_sha256':cfg['checkpoint_sha256'],
              'preparation_sha256':digest(prepared/'preparation.json'),'training_epochs':0,'seed':1024,
              'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in code},'ultra_commit':cfg['ultra_commit'],
              'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
              'ranking':cfg['ranking'],'batch_size':1,'splits':['validation','test'],
              'selection':'Fixed pretrained checkpoint; validation does not select a model or change settings'}
    if args.resume:assert read(out/'settings.json')==settings,'Settings changed'
    else:
        out.mkdir();save(out/'settings.json',settings)
        for path in code:
            dest=out/'source'/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    labels=read(prepared/'data/labels.json');candidates=read(prepared/'data/candidates.json')
    predicates=read(prepared/'data/predicates.json')
    hidden={(r['drug_index'],r['disease_index']) for r in labels if r['split']!='visible'}
    tick=time.perf_counter();triples=np.load(prepared/'data/triples.npy')
    assert not hidden_pair_mask(triples[:,0],triples[:,2],hidden,cfg['num_nodes']).any()
    edges=torch.from_numpy(triples[:,[0,2]].T.copy());types=torch.from_numpy(triples[:,1].copy());p=len(predicates)
    graph=Data(edge_index=torch.cat([edges,edges.flip(0)],1),edge_type=torch.cat([types,types+p]),num_nodes=cfg['num_nodes'],num_relations=2*p)
    del triples,edges,types
    cache=prepared/'relation_graph.pt';metadata=prepared/'relation_graph.json'
    if metadata.exists():
        details=read(metadata)
        assert digest(cache)==details['sha256'] and details['triples_sha256']==manifest['dataset_sha256']['triples.npy']
        graph.relation_graph=torch.load(cache,map_location='cpu')
    else:
        print('Building relation graph from masked MechRepoNet context...',flush=True)
        start=time.perf_counter();graph=tasks.build_relation_graph(graph)
        torch.save(graph.relation_graph,cache.with_suffix('.tmp'));cache.with_suffix('.tmp').replace(cache)
        details={'sha256':digest(cache),'triples_sha256':manifest['dataset_sha256']['triples.npy'],
                 'seconds':time.perf_counter()-start,'edges':graph.relation_graph.num_edges}
        save(metadata,details)
    graph=graph.cuda()
    common={'input_dim':64,'hidden_dims':[64]*6,'message_func':'distmult','aggregate_func':'sum','short_cut':True,'layer_norm':True}
    model=Ultra(rel_model_cfg={'class':'RelNBFNet',**common},entity_model_cfg={'class':'EntityNBFNet',**common}).cuda()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu')['model'],strict=True);model.eval()
    print(f'Ready: {graph.num_nodes} nodes, {graph.num_edges} directed/inverse edges, {len(candidates)} candidates; setup {time.perf_counter()-tick:.1f}s',flush=True)
    reports={}
    for split in ['validation','test']:
        torch.cuda.reset_peak_memory_stats()
        reports[split]=evaluate(model,graph,labels,candidates,predicates.index(cfg['target_predicate']),out/split,split,limit=args.max_queries)
        record={'checkpoint_sha256':cfg['checkpoint_sha256'],'settings_sha256':digest(out/'settings.json'),
                'peak_gpu_allocated_bytes':torch.cuda.max_memory_allocated(),'peak_gpu_reserved_bytes':torch.cuda.max_memory_reserved(),
                'relation_graph_sha256':details['sha256'],'complete':reports[split]['complete']}
        save(out/split/'provenance.json',record)
        save(out/'progress.json',{'complete':False,'completed_split':split,'scored_queries':{s:r['scored_queries'] for s,r in reports.items()}})
        print(json.dumps({split:{k:v for k,v in reports[split].items() if k!='score_files_sha256'}}),flush=True)
    complete=all(r['complete'] for r in reports.values())
    if complete:
        assert all(r['evaluated_pairs']==cfg['pair_splits'][s] for s,r in reports.items())
        save(out/'comparison.json',{'complete':True,'experiment':8,'graph':'MechRepoNet','pretrained_checkpoint':'4g',
             'candidate_compounds':len(candidates),'preparation':manifest,'settings_sha256':digest(out/'settings.json'),
             'results':{s:{k:v for k,v in r.items() if k!='score_files_sha256'} for s,r in reports.items()},
             'tier0_experiment3':{s:read(ROOT/f'output/full-graph-ultra/run_001/{s}/metrics.json')['ultra'] for s in reports},
             'limitations':['Different KG, evaluation pairs and candidate category/count; protocol comparison, not a controlled graph-only effect.','Previously inspected graphs and historical test labels; exploratory evaluation.']})
    save(out/'progress.json',{'complete':complete,'scored_queries':{s:r['scored_queries'] for s,r in reports.items()}})
    print('Complete' if complete else 'Partial smoke run; resume without --max-queries.',flush=True)


if __name__=='__main__':main()
