"""Experiment 7b: score per-disease retrieval graphs with both frozen 4g checkpoints."""
import argparse
from collections import defaultdict
from contextlib import contextmanager
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import numpy as np
import torch
from torch_geometric.data import Data

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'vendor/ULTRA'))
from full_graph_common import digest, filtered_rank, save, summarize
from ultra import tasks
from ultra.models import Ultra


def local_graph(edges, anchor, candidates, num_relations):
    """Keep every candidate, including missing answers, without adding any context edges."""
    triples = np.asarray(edges, dtype=np.int64).reshape(-1, 3)
    nodes = np.unique(np.concatenate(([anchor], candidates, triples[:, 0], triples[:, 2])))
    endpoints = torch.from_numpy(np.searchsorted(nodes, triples[:, [0, 2]]).T.copy())
    types = torch.from_numpy(triples[:, 1].copy())
    graph = Data(edge_index=torch.cat([endpoints, endpoints.flip(0)], dim=1),
                 edge_type=torch.cat([types, types + num_relations]),
                 num_nodes=len(nodes), num_relations=2 * num_relations)
    graph = tasks.build_relation_graph(graph)
    return graph, int(np.searchsorted(nodes, anchor)), np.searchsorted(nodes, candidates)


@contextmanager
def empty_safe_aggregation(enabled):
    """The sum of messages from zero edges is zero; retain native boundary/update."""
    if not enabled:
        yield
        return
    from ultra import rspmm
    original=rspmm.generalized_rspmm
    def guarded(edge_index, edge_type, edge_weight, relation, input, sum='add', mul='mul'):
        if edge_index.numel()==0:
            assert sum=='add', 'Only sum aggregation is used by these checkpoints'
            return torch.zeros_like(input)
        return original(edge_index,edge_type,edge_weight,relation,input,sum=sum,mul=mul)
    rspmm.generalized_rspmm=guarded
    try:
        yield
    finally:
        rspmm.generalized_rspmm=original


def make_model():
    common = dict(input_dim=64, hidden_dims=[64]*6, message_func='distmult',
                  aggregate_func='sum', short_cut=True, layer_norm=True)
    return Ultra(rel_model_cfg={'class':'RelNBFNet', **common},
                 entity_model_cfg={'class':'EntityNBFNet', **common})


def score(model, graph, anchor, candidates, relation):
    batch = torch.zeros((1, len(candidates), 3), dtype=torch.long, device='cuda')
    batch[0, :, 0] = torch.as_tensor(candidates, device='cuda')
    batch[0, :, 1] = anchor
    batch[0, :, 2] = relation
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()
    start = time.perf_counter()
    with torch.no_grad(), empty_safe_aggregation(graph.num_edges==0):
        scores = model(graph, batch).squeeze(0).cpu().numpy()
    torch.cuda.synchronize()
    return scores, {'inference_seconds':time.perf_counter()-start,
                    'peak_gpu_allocated_bytes':torch.cuda.max_memory_allocated(),
                    'peak_gpu_reserved_bytes':torch.cuda.max_memory_reserved()}


def report_method(directory, rows, diagnostics, total_queries, total_pairs):
    with (directory / 'answer_ranks.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    report = {'complete':len(diagnostics)==total_queries, 'split':'validation',
              'scored_queries':len(diagnostics), 'total_queries':total_queries,
              'evaluated_pairs':len(rows), 'total_pairs':total_pairs,
              'candidates_per_query':5326, 'ultra':summarize(rows, 'rank'),
              'inference_seconds':sum(r['inference_seconds'] for r in diagnostics),
              'graph_preparation_seconds':sum(r['graph_preparation_seconds'] for r in diagnostics),
              'retrieval_seconds':sum(r['retrieval_seconds'] for r in diagnostics),
              'peak_gpu_allocated_bytes':max(r['peak_gpu_allocated_bytes'] for r in diagnostics),
              'peak_gpu_reserved_bytes':max(r['peak_gpu_reserved_bytes'] for r in diagnostics),
              'answers_with_retrieved_context':sum(r['answer_in_graph'] for r in rows),
              'answer_ranks_sha256':digest(directory / 'answer_ranks.csv')}
    if report['complete']: assert len(rows)==total_pairs
    save(directory / ('metrics.json' if report['complete'] else 'partial.json'), report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--follow', action='store_true', help='Wait for retrieval reports as they are produced')
    parser.add_argument('--max-queries', type=int, help='Partial smoke check; never final split metrics')
    parser.add_argument('--idle-timeout', type=float, default=1200)
    args = parser.parse_args()
    if args.max_queries is not None and args.max_queries < 1: parser.error('max-queries must be positive')
    if args.idle_timeout <= 0: parser.error('idle-timeout must be positive')
    out, retrieval = args.output.resolve(), args.retrieval.resolve()
    if out.exists() and not args.resume: parser.error('Output exists; use --resume')
    if args.resume and not (out/'settings.json').exists(): parser.error('No settings to resume')
    assert torch.cuda.is_available(), 'Use scripts/gpu_python.sh'
    torch.set_num_threads(8); torch.manual_seed(1024)
    source = ROOT/'output/full-graph-ultra/run_001'
    trained = ROOT/'pilot/results/finetune_4g_001'
    read = lambda p: json.loads(p.read_text())
    original, preparation = read(source/'config.json'), read(source/'preparation.json')
    for name in ('labels.json','candidates.json','predicates.json'):
        assert digest(source/'data'/name)==preparation['dataset_sha256'][name]
    labels, candidates, predicates = [read(source/'data'/name) for name in ('labels.json','candidates.json','predicates.json')]
    candidate_ids = np.array([r['index'] for r in candidates], dtype=np.int64)
    positions = {int(idx):i for i,idx in enumerate(candidate_ids)}
    assert len(positions)==5326
    rs = read(retrieval/'settings.json'); cohort = read(retrieval/'cohort.json')['diseases']
    assert rs['source_labels_sha256']==digest(source/'data/labels.json')
    assert rs['candidate_sha256']==digest(source/'data/candidates.json')
    assert [r['disease'] for r in cohort]==rs['cohort']
    mask = read(retrieval/'mask_verification.json')
    assert mask['all_heldout_direct_connections_absent'] and mask['hidden_pairs']==3616
    known, queries = defaultdict(set), defaultdict(list)
    hidden = set()
    for row in labels:
        known[row['disease_index']].add(positions[row['drug_index']])
        if row['split']=='validation': queries[row['disease_index']].append(row)
        if row['split']!='visible': hidden.add(frozenset((row['drug_index'],row['disease_index'])))
    assert all(r['index'] in queries and queries[r['index']][0]['disease']==r['disease'] for r in cohort)
    total_pairs = sum(len(queries[r['index']]) for r in cohort)
    completion = read(trained/'completed.json')
    assert read(trained/'settings.json')['dataset_sha256']==preparation['dataset_sha256']
    checkpoints = {'pretrained_4g':ROOT/original['checkpoint'], 'finetuned_4g':trained/'best.pt'}
    hashes = {k:digest(p) for k,p in checkpoints.items()}
    assert hashes['pretrained_4g']==original['checkpoint_sha256']
    assert hashes['finetuned_4g']==completion['checkpoint_sha256'] and completion['best_step']==1000
    upstream = ROOT/'vendor/ULTRA'
    assert subprocess.check_output(['git','-C',str(upstream),'rev-parse','HEAD'], text=True).strip()==original['ultra_commit']
    subprocess.run(['git','-C',str(upstream),'diff','--quiet','HEAD','--','ultra'],check=True)
    code = [Path(__file__), ROOT/'scripts/full_graph_common.py']
    settings = {'experiment':'7b', 'split':'validation', 'diseases':len(cohort), 'pairs':total_pairs,
                'candidates':5326, 'checkpoint_sha256':hashes, 'retrieval_settings_sha256':digest(retrieval/'settings.json'),
                'cohort_sha256':digest(retrieval/'cohort.json'), 'ultra_commit':original['ultra_commit'],
                'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in code},
                'torch':torch.__version__, 'cuda':torch.version.cuda, 'gpu':torch.cuda.get_device_name(0),
                'ranking':'Drug heads; all-known filtered, pessimistic ties; no answers dropped',
                'graph':'Local node remapping; all 5326 candidates retained; absent drugs isolated; relation graph rebuilt per query',
                'training_updates':0, 'seed':1024, 'empty_graphs':'Zero-edge message sum is zero; native boundary and update unchanged; no synthetic edges'}
    if args.resume: assert read(out/'settings.json')==settings, 'Settings changed'
    else:
        out.mkdir(parents=True); save(out/'settings.json',settings)
        for p in code: shutil.copyfile(p,out/p.name)
        shutil.copyfile(retrieval/'settings.json',out/'retrieval_settings.json')
        shutil.copyfile(retrieval/'cohort.json',out/'cohort.json')
    models = {}
    for name,path in checkpoints.items():
        model=make_model().cuda(); model.load_state_dict(torch.load(path,map_location='cpu')['model'],strict=True)
        model.eval(); models[name]=model
    methods = [(strategy,name) for strategy in ('gandalf_walks','aragorn_rules') for name in models]
    rows = {f'{s}/{m}':[] for s,m in methods}; diagnostics={key:[] for key in rows}
    selected = cohort if args.max_queries is None else cohort[:args.max_queries]
    total_start=time.perf_counter(); comparisons={}
    for number,item in enumerate(selected):
        directory=retrieval/'diseases'/f'{number:03d}'; report_path=directory/'report.json'
        waiting=time.monotonic()
        while not report_path.exists():
            if not args.follow: raise FileNotFoundError(report_path)
            if time.monotonic()-waiting > args.idle_timeout: raise TimeoutError(f'No retrieval report for {item["disease"]}; resume later')
            time.sleep(5)
        retrieved=read(report_path); anchor=item['index']
        assert retrieved['disease']==item['disease'] and retrieved['index']==anchor
        for strategy in ('gandalf_walks','aragorn_rules'):
            path=directory/f'{strategy}.json'; expected=retrieved['artifact_sha256'][path.name]
            assert digest(path)==expected
            saved=read(path); edges=saved['edges']; assert saved['anchor']==anchor
            assert len(edges)<=rs['edge_cap'] and len({tuple(e) for e in edges})==len(edges)
            assert all(frozenset((h,t)) not in hidden and 0<=p<len(predicates) for h,p,t in edges)
            reached={anchor}|{x for h,p,t in edges for x in (h,t)}
            assert sum(r['drug_index'] in reached for r in queries[anchor])==retrieved['strategies'][strategy]['answers_reached']
            graph=None; preparation_seconds=0
            for name,model in models.items():
                key=f'{strategy}/{name}'; target=out/key; (target/'scores').mkdir(parents=True,exist_ok=True)
                score_path=target/'scores'/f'{anchor}.npz'; metadata_path=score_path.with_suffix('.json')
                if metadata_path.exists():
                    info=read(metadata_path)
                    assert info['sha256']==digest(score_path) and info['graph_sha256']==expected
                    assert info['settings_sha256']==digest(out/'settings.json')
                    with np.load(score_path,allow_pickle=False) as data:
                        scores=data['scores']; assert int(data['disease_index'])==anchor
                else:
                    if graph is None:
                        tick=time.perf_counter()
                        graph,local_anchor,local_candidates=local_graph(edges,anchor,candidate_ids,len(predicates))
                        graph=graph.to('cuda'); torch.cuda.synchronize()
                        preparation_seconds=time.perf_counter()-tick
                    scores,info=score(model,graph,local_anchor,local_candidates,predicates.index('biolink:treats'))
                    info.update(graph_preparation_seconds=preparation_seconds,
                                retrieval_seconds=retrieved['strategies'][strategy]['retrieval_seconds'],
                                graph_sha256=expected,settings_sha256=digest(out/'settings.json'),
                                graph_nodes_with_candidates=graph.num_nodes,relation_graph_edges=graph.relation_graph.num_edges)
                    temp=score_path.with_suffix('.tmp')
                    with temp.open('wb') as stream: np.savez(stream,scores=scores,disease_index=anchor)
                    temp.replace(score_path); info['sha256']=digest(score_path); save(metadata_path,info)
                assert scores.shape==(5326,) and np.isfinite(scores).all()
                diagnostics[key].append(info)
                for row in queries[anchor]:
                    rows[key].append({**row,'rank':filtered_rank(scores,positions[row['drug_index']],known[anchor]),
                                      'answer_in_graph':row['drug_index'] in reached})
            del graph
        if (number+1)%25==0 or number+1==len(selected):
            for key in rows: comparisons[key]=report_method(out/key,rows[key],diagnostics[key],len(cohort),total_pairs)
            complete=all(r['complete'] for r in comparisons.values())
            save(out/'progress.json',{'complete':complete,'scored_diseases':number+1,'total_diseases':len(cohort),
                                      'elapsed_seconds_this_invocation':time.perf_counter()-total_start})
            print(f'{number+1}/{len(cohort)} diseases scored with both contexts and checkpoints',flush=True)
    if args.max_queries is None and len(cohort)==986:
        assert total_pairs==1807 and all(r['complete'] for r in comparisons.values())
        baseline_paths={'pretrained_4g':source/'validation/metrics.json',
                        'finetuned_4g':trained/'validation_step_001000/metrics.json'}
        baselines={name:read(path) for name,path in baseline_paths.items()}
        assert all(r['complete'] and r['evaluated_pairs']==1807 for r in baselines.values())
        save(out/'comparison.json',{'complete':True,'split':'validation','pairs':1807,'diseases':986,
             'retrieval_contexts':comparisons,'full_graph_reference':{k:r['ultra'] for k,r in baselines.items()},
             'baseline_metrics_sha256':{k:digest(p) for k,p in baseline_paths.items()},
             'settings_sha256':digest(out/'settings.json'),'test_evaluated':False})
        print(json.dumps({k:r['ultra'] for k,r in comparisons.items()},indent=2),flush=True)
    print('Done; test evaluation remains a separate stage.',flush=True)


if __name__=='__main__':main()
