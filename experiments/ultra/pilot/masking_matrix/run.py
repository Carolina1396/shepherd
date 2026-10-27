"""Evaluate one fixed masking condition on test; optional baseline parity check."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time
import numpy as np
import torch
from torch_geometric.data import Data
from common import ROOT, read, save, digest

sys.path.insert(0,str(ROOT/'pilot'))
sys.path.insert(0,str(ROOT/'vendor/ULTRA'))
from finetune.run import evaluate
from ultra import tasks
from ultra.models import Ultra


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--parity',action='store_true',help='Two baseline test queries; compare every score and answer rank')
    args=parser.parse_args()
    prepared=args.dataset.resolve()
    out=args.output.resolve() if args.output else prepared/'evaluation'
    if out.exists() and not args.resume:
        parser.error('Output exists; use --resume')
    cfg,manifest=read(prepared/'config.json'),read(prepared/'preparation.json')
    assert manifest['complete'] and cfg['training_epochs']==0
    assert cfg['target_scope']=='chemical-disease' and cfg['candidate_scope']=='chemical'
    assert digest(prepared/'config.json')==manifest['config_sha256']
    for name,expected in manifest['dataset_sha256'].items():
        assert digest(prepared/'data'/name)==expected,name
    if args.parity:
        reference=read(ROOT/'pilot/studies/full_graph_chemical_disease_4g_results.json')
        assert manifest['dataset_sha256']==reference['comparison']['preparation']['dataset_sha256']
    else:
        verified=read(prepared/'preparation_verification.json')
        assert verified['complete'] and verified['dataset_sha256']==manifest['dataset_sha256']
        suite=read(Path(cfg['suite'])/'suite.json')
        assert suite['complete'] and cfg['policy']==suite['conditions'][str(cfg['condition'])]
    checkpoint=ROOT/cfg['checkpoint']
    assert digest(checkpoint)==cfg['checkpoint_sha256']
    upstream=ROOT/'vendor/ULTRA'
    assert subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'],text=True).strip()==cfg['ultra_commit']
    subprocess.run(['git','-C',str(upstream),'diff','--quiet','HEAD','--','ultra'],check=True)
    assert torch.cuda.is_available()
    assert torch.cuda.get_device_name(0)=='NVIDIA RTX A6000','Keep hardware matched to baseline'
    torch.set_num_threads(8)
    torch.manual_seed(1024)
    code=[Path(__file__),Path(__file__).with_name('common.py'),ROOT/'pilot/finetune/run.py',ROOT/'scripts/full_graph_common.py']
    settings={'experiment':'Tier 0 masking matrix','condition':cfg.get('condition',1),
              'parity_check':args.parity,'policy':cfg.get('policy'),
              'preparation_sha256':digest(prepared/'preparation.json'),
              'checkpoint_sha256':digest(checkpoint),'ultra_commit':cfg['ultra_commit'],
              'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in code},
              'torch':torch.__version__,'cuda':torch.version.cuda,'gpu':torch.cuda.get_device_name(0),
              'seed':1024,'training_epochs':0,'batch_size':1,'splits':['test'],
              'ranking':cfg['ranking'],'selection':'Fixed pretrained checkpoint; no model selection'}
    if args.resume:
        assert read(out/'settings.json')==settings,'Inputs or code changed'
    else:
        out.mkdir(parents=True)
        save(out/'settings.json',settings)
        for path in code:
            dest=out/'source'/path.relative_to(ROOT)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest)
    labels=read(prepared/'data/labels.json')
    candidates=read(prepared/'data/candidates.json')
    predicates=read(prepared/'data/predicates.json')
    assert len(candidates)==1117832 and sum(r['split']=='test' for r in labels)==2293
    start=time.perf_counter()
    triples=np.load(prepared/'data/triples.npy')
    edges=torch.from_numpy(triples[:,[0,2]].T.copy())
    types=torch.from_numpy(triples[:,1].copy())
    p=len(predicates)
    graph=Data(edge_index=torch.cat([edges,edges.flip(0)],1),edge_type=torch.cat([types,types+p]),
               num_nodes=cfg['num_nodes'],num_relations=2*p)
    del triples,edges,types
    cache,metadata=prepared/'relation_graph.pt',prepared/'relation_graph.json'
    if metadata.exists():
        details=read(metadata)
        assert digest(cache)==details['sha256'] and details['triples_sha256']==manifest['dataset_sha256']['triples.npy']
        graph.relation_graph=torch.load(cache,map_location='cpu')
    else:
        assert not args.parity,'Baseline relation cache must already exist'
        print(f'ROW {cfg["condition"]}: rebuilding relation graph from this condition only...',flush=True)
        tick=time.perf_counter()
        graph=tasks.build_relation_graph(graph)
        torch.save(graph.relation_graph,cache.with_suffix('.tmp'))
        cache.with_suffix('.tmp').replace(cache)
        details={'sha256':digest(cache),'triples_sha256':manifest['dataset_sha256']['triples.npy'],
                 'seconds':time.perf_counter()-tick,'edges':graph.relation_graph.num_edges}
        save(metadata,details)
    graph=graph.cuda()
    architecture={'input_dim':64,'hidden_dims':[64]*6,'message_func':'distmult','aggregate_func':'sum',
                  'short_cut':True,'layer_norm':True}
    model=Ultra(rel_model_cfg={'class':'RelNBFNet',**architecture},
                entity_model_cfg={'class':'EntityNBFNet',**architecture}).cuda()
    model.load_state_dict(torch.load(checkpoint,map_location='cpu')['model'],strict=True)
    model.eval()
    print(f'READY row={settings["condition"]} nodes={graph.num_nodes} edges_with_inverses={graph.num_edges} candidates={len(candidates)} setup_seconds={time.perf_counter()-start:.1f}',flush=True)
    torch.cuda.reset_peak_memory_stats()
    report=evaluate(model,graph,labels,candidates,predicates.index('biolink:treats'),out/'test','test',
                    limit=2 if args.parity else None)
    if args.parity:
        original=read(prepared/'evaluation/test/metrics.json')
        differences=[]
        for filename in report['score_files_sha256']:
            old=prepared/'evaluation/test/scores'/filename
            assert digest(old)==original['score_files_sha256'][filename]
            with np.load(old,allow_pickle=False) as a,np.load(out/'test/scores'/filename,allow_pickle=False) as b:
                assert np.allclose(a['scores'],b['scores'],atol=1e-5,rtol=1e-5)
                differences.append(float(np.max(np.abs(a['scores']-b['scores']))))
        import csv
        with (prepared/'evaluation/test/answer_ranks.csv').open() as f:
            old_ranks={(r['drug'],r['disease']):int(r['rank']) for r in csv.DictReader(f)}
        with (out/'test/answer_ranks.csv').open() as f:
            new_ranks=list(csv.DictReader(f))
        assert all(int(r['rank'])==old_ranks[r['drug'],r['disease']] for r in new_ranks)
        save(out/'parity.json',{'complete':True,'queries':2,'max_absolute_score_difference':max(differences),
                              'all_answer_ranks_match':True,'settings_sha256':digest(out/'settings.json')})
        print('BASELINE PARITY PASSED',flush=True)
    else:
        assert report['complete'] and report['evaluated_pairs']==2293
        save(out/'test/provenance.json',{'checkpoint_sha256':digest(checkpoint),
             'settings_sha256':digest(out/'settings.json'),'relation_graph_sha256':details['sha256'],
             'peak_gpu_allocated_bytes':torch.cuda.max_memory_allocated(),
             'peak_gpu_reserved_bytes':torch.cuda.max_memory_reserved(),'complete':True})
        print(f'SCORED row={cfg["condition"]} mrr={report["ultra"]["mrr"]:.8f} hits10={report["ultra"]["hits_at_10"]:.8f}; awaiting independent verification',flush=True)


if __name__=='__main__':
    main()
