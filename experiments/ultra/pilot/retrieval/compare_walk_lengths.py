"""Experiment 7: compare native three- and six-hop walk coverage on all validation diseases."""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path
import random
import resource
import shutil
import subprocess
import time

import numpy as np
from run import ROOT, GANDALF, CSRGraph, GraphSampler, coverage, digest, mask_pairs, save, union_units


def sample(sampler, anchor, length, attempts, cap, seed):
    sampler.rng = random.Random(seed)
    tick = time.perf_counter()
    units = []
    for _ in range(attempts):
        walk = sampler.walk(anchor, length)
        if walk is None:
            continue
        nodes, edges = walk
        units.append({'edges': [(nodes[h], p, nodes[t]) for h, p, t in edges]})
    edges, _ = union_units([units], cap, seed)
    return edges, len(units), time.perf_counter() - tick


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, default=ROOT/'pilot/results/retrieval_validation_001')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    baseline, out = args.baseline.resolve(), args.output.resolve()
    if out.exists() and not args.resume: parser.error('Output exists; choose a new directory or --resume')
    read = lambda path: json.loads(path.read_text())
    original = read(baseline/'settings.json')
    cohort = read(baseline/'cohort.json')['diseases']
    summary = read(baseline/'summary.json')
    assert summary['complete'] and len(cohort)==986 and summary['cohort_validation_pairs']==1807
    assert original['walk_length']==3 and original['attempts']==1000 and original['edge_cap']==3000
    assert summary['settings_sha256']==digest(baseline/'settings.json')
    source = ROOT/'output/full-graph-ultra/run_001/data'
    assert digest(source/'labels.json')==original['source_labels_sha256']
    assert digest(source/'candidates.json')==original['candidate_sha256']
    assert digest(ROOT/'output/gandalf/full-store/metadata.pkl')==original['source_graph_metadata_sha256']
    assert digest(GANDALF/'scripts/benchmarks/generate_queries.py')==original['native_sampler_sha256']
    assert subprocess.check_output(['git','-C',str(GANDALF),'rev-parse','HEAD'], text=True).strip()==original['gandalf_commit']
    subprocess.run(['git','-C',str(GANDALF),'diff','--quiet','HEAD','--','gandalf','scripts/benchmarks/generate_queries.py'],check=True)
    for name, expected in original['source_sha256'].items():
        assert digest(Path(__file__).with_name(name))==expected, 'Baseline retrieval code changed'
    sources = [Path(__file__), Path(__file__).with_name('run.py'), Path(__file__).with_name('masked_graph.py'), ROOT/'scripts/full_graph_common.py']
    settings = {'experiment':'7 walk-length coverage comparison', 'split':'validation', 'walk_lengths':[3,6],
                'diseases':986, 'pairs':1807, 'attempts':1000, 'edge_cap':3000, 'candidate_drugs':5326,
                'seed':original['seed'], 'baseline_settings_sha256':digest(baseline/'settings.json'),
                'baseline_cohort_sha256':digest(baseline/'cohort.json'), 'baseline_summary_sha256':digest(baseline/'summary.json'),
                'source_sha256':{p.name:digest(p) for p in sources}, 'gandalf_commit':original['gandalf_commit'],
                'sampling':'Unchanged native Gandalf walk; same seed per disease for each length; whole-walk cap; no label-guided selection',
                'mask':original['mask'], 'model_evaluation':False, 'test_evaluation':False}
    if args.resume:
        assert read(out/'settings.json')==settings, 'Settings changed'
    else:
        out.mkdir(parents=True)
        save(out/'settings.json',settings)
        shutil.copyfile(baseline/'cohort.json',out/'cohort.json')
        (out/'source').mkdir()
        for p in sources: shutil.copyfile(p,out/'source'/p.name)
    start = time.perf_counter()
    labels = read(source/'labels.json')
    drugs = {r['index'] for r in read(source/'candidates.json')}
    answers = defaultdict(set)
    for row in labels:
        if row['split']=='validation': answers[row['disease_index']].add(row['drug_index'])
    assert len(drugs)==5326 and {r['index'] for r in cohort}==set(answers)
    hidden = {(r['drug_index'],r['disease_index']) for r in labels if r['split']!='visible'}
    print('Loading source graph and masking every held-out pair before sampling...',flush=True)
    graph = CSRGraph.load_mmap(ROOT/'output/gandalf/full-store',mmap_mode='r')
    masked, removed = mask_pairs(graph,hidden)
    for h,t in hidden:
        for a,b in [(h,t),(t,h)]:
            lo,hi=masked.fwd_offsets[a:a+2]
            assert not np.any(masked.fwd_targets[lo:hi]==b)
    assert removed==read(baseline/'mask_verification.json')['removed_records']
    save(out/'mask_verification.json',{'all_heldout_pairs_absent':True,'hidden_pairs':len(hidden),
         'removed_evidence_records':removed,'load_mask_seconds':time.perf_counter()-start})
    sampler = GraphSampler(masked,random.Random(original['seed']))
    (out/'diseases').mkdir(exist_ok=True)
    records = []
    for number,item in enumerate(cohort):
        directory=out/'diseases'/f'{number:03d}'
        directory.mkdir(exist_ok=True)
        anchor=item['index']; seed=original['seed']+number
        reference_dir=baseline/'diseases'/f'{number:03d}'
        reference=read(reference_dir/'report.json')
        reference_path=reference_dir/'gandalf_walks.json'
        assert reference['disease']==item['disease']
        assert digest(reference_path)==reference['artifact_sha256']['gandalf_walks.json']
        if (directory/'report.json').exists():
            record=read(directory/'report.json')
            for name,expected in record['artifact_sha256'].items(): assert digest(directory/name)==expected
            records.append(record)
            continue
        reports={}; reached={}
        for length in [3,6]:
            edges,completed,seconds=sample(sampler,anchor,length,1000,3000,seed)
            assert len(edges)<=3000
            for h,p,t in edges:
                assert (h,t) not in hidden and (t,h) not in hidden
                assert masked._find_edge_index(h,t,p) is not None
            if length==3:
                assert sorted(edges)==[tuple(e) for e in read(reference_path)['edges']], 'Three-hop reproduction failed'
                assert completed==reference['completed_walks']
            nodes={anchor}|{x for h,p,t in edges for x in (h,t)}
            reached[length]=answers[anchor]&nodes
            reports[str(length)]={**coverage(edges,anchor,drugs,answers[anchor]),
                                  'completed_walks':completed,'retrieval_seconds':seconds}
            save(directory/f'walks_{length}.json',{'anchor':anchor,'edges':sorted(edges)})
        record={'disease':item['disease'],'index':anchor,'lengths':reports,
                'answers_reached_both':len(reached[3]&reached[6]),
                'answers_gained_at_6':len(reached[6]-reached[3]), 'answers_lost_at_6':len(reached[3]-reached[6]),
                'three_hop_exact_reproduction':True,
                'artifact_sha256':{f'walks_{length}.json':digest(directory/f'walks_{length}.json') for length in [3,6]}}
        save(directory/'report.json',record); records.append(record)
        if (number+1)%50==0 or number+1==len(cohort):
            print(f'{number+1}/986 diseases compared',flush=True)
            save(out/'progress.json',{'complete':False,'diseases':number+1,'total':986})
    result={'complete':True,'diseases':986,'validation_pairs':1807,'lengths':{},
            'answers_reached_both':sum(r['answers_reached_both'] for r in records),
            'answers_gained_at_6':sum(r['answers_gained_at_6'] for r in records),
            'answers_lost_at_6':sum(r['answers_lost_at_6'] for r in records),
            'three_hop_exact_reproduction_diseases':sum(r['three_hop_exact_reproduction'] for r in records),
            'settings_sha256':digest(out/'settings.json'),'elapsed_seconds_this_invocation':time.perf_counter()-start,
            'parent_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'model_evaluation':False,'test_evaluation':False}
    for length in [3,6]:
        rows=[r['lengths'][str(length)] for r in records]
        pairs=sum(r['validation_pairs'] for r in rows); reached=sum(r['answers_reached'] for r in rows)
        assert pairs==1807
        result['lengths'][str(length)]={'answers_reached':reached,'answer_coverage':reached/pairs,
            'mean_disease_answer_coverage':float(np.mean([r['answer_coverage'] for r in rows])),
            'mean_nodes':float(np.mean([r['nodes'] for r in rows])), 'mean_edges':float(np.mean([r['edges'] for r in rows])),
            'mean_drug_nodes':float(np.mean([r['drug_nodes'] for r in rows])),
            'graphs_at_cap':sum(r['edges']==3000 for r in rows), 'completed_walks':sum(r['completed_walks'] for r in rows),
            'attempted_walks':986000,'retrieval_seconds':sum(r['retrieval_seconds'] for r in rows)}
    assert result['lengths']['3']['answers_reached']==summary['strategies']['gandalf_walks']['answers_reached']
    save(out/'comparison.json',result)
    save(out/'progress.json',{'complete':True,'diseases':986,'total':986})
    with (out/'per_disease.csv').open('w',newline='') as stream:
        rows=[{'disease':r['disease'],'hops':length,**r['lengths'][str(length)]} for r in records for length in [3,6]]
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
