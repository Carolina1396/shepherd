"""Experiment 7a: native Gandalf walks versus ARAGORN rule retrieval; no ULTRA inference."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import logging
import multiprocessing as mp
from pathlib import Path
import random
import resource
import shutil
from string import Template
import subprocess
import sys
import time

import numpy as np
import psutil

ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
GANDALF = ROOT/'vendor/gandalf'
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(GANDALF/'scripts/benchmarks'))
from full_graph_common import digest, save
from generate_queries import GraphSampler
from gandalf import CSRGraph, lookup
from gandalf.biolink import make_toolkit
from gandalf.trapi import Deadline
try:
    from .masked_graph import mask_pairs
except ImportError:
    from masked_graph import mask_pairs


def cohort_from_labels(labels, size, seed):
    ids = sorted({r['disease'] for r in labels if r['split']=='validation'})
    if not 0 < size <= len(ids):
        raise ValueError('Invalid cohort size')
    return sorted(random.Random(seed).sample(ids, size))


def queries_for_disease(disease, rules):
    direct = {'query_graph': {'nodes': {'drug': {'categories':['biolink:Drug']},
             'disease': {'ids':[disease], 'categories':['biolink:Disease']}},
             'edges': {'treats': {'subject':'drug','object':'disease','predicates':['biolink:treats']}}}}
    queries = [{'rule_id':'direct', 'requires_direct_pair': True, 'query':direct}]
    for i, rule in enumerate(rules):
        query = json.loads(Template(json.dumps(rule['template'])).substitute(
            source='drug', target='disease', source_id='', target_id=disease))
        del query['query_graph']['nodes']['drug']['ids']
        direct_pair = any({e['subject'],e['object']} == {'drug','disease'} for e in query['query_graph']['edges'].values())
        queries.append({'rule_id':str(i), 'requires_direct_pair':direct_pair, 'query':query})
    return queries


def union_units(groups, edge_cap, seed):
    """Round-robin whole matches; budgets never depend on validation answers."""
    rng = random.Random(seed)
    queues = [list(units) for units in groups]
    for units in queues:
        rng.shuffle(units)
    order = list(range(len(queues)))
    rng.shuffle(order)
    edges, answers = set(), set()
    while any(queues):
        for i in order:
            if not queues[i]:
                continue
            unit = queues[i].pop()
            new = {tuple(e) for e in unit['edges']}
            if len(edges | new) <= edge_cap:
                edges.update(new)
                answers.update(unit.get('answers', []))
    return edges, answers


def coverage(edges, anchor, drugs, answers, rule_answers=None):
    nodes = {anchor} | {x for h, p, t in edges for x in (h,t)}
    reached = nodes & drugs
    return {'nodes':len(nodes), 'edges':len(edges), 'drug_nodes':len(reached),
            'validation_pairs':len(answers), 'answers_reached':len(answers & reached),
            'answer_coverage':len(answers & reached)/len(answers) if answers else None,
            'answers_returned_as_rule_drugs':len(answers & (rule_answers or set()))}


def rule_child(connection, graph, query, bmt, timeout, cap, seed):
    try:
        # Bound extra virtual allocation while preserving large read-only LMDB mappings.
        limit = psutil.Process().memory_info().vms + 4*1024**3
        resource.setrlimit(resource.RLIMIT_AS, (limit,limit))
        tick = time.perf_counter()
        response = lookup(graph, {'message':query, 'parameters':{'timeout':timeout}},
                          bmt=bmt, subclass=False, dehydrated=True, deadline=Deadline(timeout), log_level='ERROR')
        message = response.get('message') or {}
        kg = (message.get('knowledge_graph') or {}).get('edges', {})
        results = message.get('results') or []
        if isinstance(results, bytes):
            raise ValueError('Unexpected serialized results')
        order = list(range(len(results)))
        random.Random(seed).shuffle(order)
        units = []
        graph_edges = set()
        cache = {}
        for i in order:
            result = results[i]
            ids = {eid for analysis in result.get('analyses',[]) for binding in analysis.get('edge_bindings',{}).values() for eid in binding.get('ids',[])}
            edges = set()
            for eid in ids:
                if eid not in cache:
                    e = kg[eid]
                    h,t = graph.get_node_idx(e['subject']), graph.get_node_idx(e['object'])
                    p = graph.predicate_to_idx.get(e['predicate'])
                    if h is None or t is None or p is None or graph._find_edge_index(h,t,p) is None:
                        cache[eid] = None
                    else:
                        cache[eid] = (int(h),int(p),int(t))
                if cache[eid] is not None:
                    edges.add(cache[eid])
            if not edges or len(graph_edges | edges)>cap:
                continue
            answer_ids = result.get('node_bindings',{}).get('drug',{}).get('ids',[])
            answer_nodes = {graph.get_node_idx(x) for x in answer_ids}
            answer_nodes.discard(None)
            nodes = {x for h,p,t in edges for x in (h,t)}
            answer_nodes &= nodes
            units.append({'edges':sorted(edges),'answers':sorted(answer_nodes)})
            graph_edges.update(edges)
            if len(graph_edges)>=cap or len(units)>=cap:
                break
        connection.send({'status':response.get('status','Success'), 'raw_results':len(results),
                         'units':units, 'seconds':time.perf_counter()-tick,
                         'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                         'bounded_results':len(units)<len(results)})
    except BaseException as exc:
        connection.send({'status':'error','error':f'{type(exc).__name__}: {exc}','units':[]})
    finally:
        connection.close()


def bounded_rule(graph, query, bmt, timeout, cap, seed):
    context = mp.get_context('fork')
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=rule_child, args=(child,graph,query,bmt,timeout,cap,seed))
    tick = time.perf_counter()
    process.start()
    child.close()
    if parent.poll(timeout+2):
        try:
            result = parent.recv()
        except EOFError:
            result = {'status':'worker_exit','units':[]}
    else:
        result = {'status':'hard_timeout','units':[]}
    if process.is_alive():
        process.terminate()
    process.join(timeout=2)
    if process.is_alive():
        process.kill();process.join()
    parent.close()
    result['wall_seconds'] = time.perf_counter()-tick
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--diseases',type=int,default=50)
    parser.add_argument('--seed',type=int,default=7317)
    parser.add_argument('--attempts',type=int,default=1000)
    parser.add_argument('--edge-cap',type=int,default=3000)
    parser.add_argument('--rule-timeout',type=float,default=5)
    parser.add_argument('--max-new-diseases',type=int,help='Pause after this many completed diseases')
    args=parser.parse_args()
    if min(args.diseases,args.attempts,args.edge_cap,args.rule_timeout)<=0:
        parser.error('Budgets must be positive')
    if args.max_new_diseases is not None and args.max_new_diseases<1:
        parser.error('max-new-diseases must be positive')
    out=args.output.resolve()
    if out.exists() and not args.resume:parser.error('Output exists; use --resume')
    if args.resume and not (out/'settings.json').exists():parser.error('Missing settings for resume')
    start=time.perf_counter()
    prepared=ROOT/'output/full-graph-ultra/run_001'
    prep=json.loads((prepared/'preparation.json').read_text())
    labels=json.loads((prepared/'data/labels.json').read_text())
    candidates=json.loads((prepared/'data/candidates.json').read_text())
    for name in ['labels.json','candidates.json','predicates.json']:
        assert digest(prepared/'data'/name)==prep['dataset_sha256'][name]
    selected=cohort_from_labels(labels,args.diseases,args.seed)
    rule_file=REPO/'workers/aragorn_lookup/rules_with_types_cleaned_finalized.json'
    rules=json.loads(rule_file.read_text())['{"predicate": "biolink:treats"}']
    assert len(rules)==18
    commit=subprocess.check_output(['git','-C',str(GANDALF),'rev-parse','HEAD'],text=True).strip()
    assert commit=='3fbaded1c922de3d61ff2af17694264d13b221f5'
    subprocess.run(['git','-C',str(GANDALF),'diff','--quiet','HEAD','--','gandalf','scripts/benchmarks/generate_queries.py'],check=True)
    sources=[Path(__file__),Path(__file__).with_name('masked_graph.py')]
    settings={'experiment':'7a','evaluation':'retrieval coverage only; no model scores',
              'diseases':args.diseases,'seed':args.seed,'attempts':args.attempts,'walk_length':3,'edge_cap':args.edge_cap,
              'rule_timeout_seconds':args.rule_timeout,'rule_hard_timeout_grace_seconds':2,'rule_extra_virtual_memory_gb':4,
              'subclass_expansion':False,'rules_sha256':digest(rule_file),'rules_count':len(rules),'includes_direct_lookup':True,
              'candidate_drugs':len(candidates),'gandalf_commit':commit,'native_sampler_sha256':digest(GANDALF/'scripts/benchmarks/generate_queries.py'),
              'source_sha256':{p.name:digest(p) for p in sources},'source_labels_sha256':digest(prepared/'data/labels.json'),
              'candidate_sha256':digest(prepared/'data/candidates.json'),
              'source_graph_metadata_sha256':digest(ROOT/'output/gandalf/full-store/metadata.pkl'),
              'mask':'All 3616 validation/test pairs; all direct predicates and both directions before traversal',
              'edge_count':'Unique directed subject-predicate-object triples; duplicate evidence records retain native sampling weight',
              'cohort':selected}
    if args.resume:
        assert json.loads((out/'settings.json').read_text())==settings,'Settings changed'
    else:
        out.mkdir(parents=True)
        save(out/'settings.json',settings)
        shutil.copyfile(rule_file,out/'aragorn_rules.json')
        for p in sources:shutil.copyfile(p,out/p.name)
    print('Loading Gandalf graph and masking held-out pairs before either retrieval strategy...',flush=True)
    graph=CSRGraph.load_mmap(ROOT/'output/gandalf/full-store',mmap_mode='r')
    drug_nodes={r['index'] for r in candidates}
    for row in candidates:assert graph.get_node_id(row['index'])==row['id']
    hidden={(r['drug_index'],r['disease_index']) for r in labels if r['split']!='visible'}
    assert len(hidden)==3616
    masked,removed=mask_pairs(graph,hidden)
    # Independently check every masked endpoint pair in both directions.
    for h,t in hidden:
        a,b=masked.fwd_offsets[h:h+2]; assert not np.any(masked.fwd_targets[a:b]==t)
        a,b=masked.fwd_offsets[t:t+2]; assert not np.any(masked.fwd_targets[a:b]==h)
    graph_report={'source_records':len(graph.fwd_targets),'removed_records':removed,
                  'remaining_records':len(masked.fwd_targets),'nodes':graph.num_nodes,
                  'hidden_pairs':len(hidden),'source_unmodified':True,'forward_reverse_mapping_verified':True,
                  'all_heldout_direct_connections_absent':True,'load_mask_seconds':time.perf_counter()-start}
    save(out/'mask_verification.json',graph_report)
    print(json.dumps(graph_report),flush=True)
    bmt=make_toolkit()
    save(out/'biolink.json',{'version':str(bmt.get_model_version())})
    sampler=GraphSampler(masked,random.Random(args.seed))
    validation=defaultdict(set)
    indices={}
    for row in labels:
        indices[row['disease']]=row['disease_index']
        if row['split']=='validation':validation[row['disease']].add(row['drug_index'])
    cohort=[{'disease':d,'index':indices[d],'validation_pairs':len(validation[d])} for d in selected]
    save(out/'cohort.json',{'seed':args.seed,'diseases':cohort,'validation_pairs':sum(len(validation[d]) for d in selected)})
    (out/'diseases').mkdir(exist_ok=True)
    completed=0
    for number,disease in enumerate(selected):
        directory=out/'diseases'/f'{number:03d}'
        report_path=directory/'report.json'
        if report_path.exists():
            saved=json.loads(report_path.read_text())
            for name,expected in saved['artifact_sha256'].items():assert digest(directory/name)==expected
            continue
        directory.mkdir(exist_ok=True)
        anchor=indices[disease];seed=args.seed+number
        sampler.rng=random.Random(seed)
        tick=time.perf_counter();units=[];success=0
        for attempt in range(args.attempts):
            walk=sampler.walk(anchor,3)
            if walk is None:continue
            success+=1;nodes,edges=walk
            units.append({'edges':[(nodes[h],p,nodes[t]) for h,p,t in edges]})
        walk_edges,_=union_units([units],args.edge_cap,seed)
        walk_seconds=time.perf_counter()-tick
        rule_groups=[];rule_reports=[]
        tick=time.perf_counter()
        for item in queries_for_disease(disease,rules):
            rule_number=len(rule_reports)
            result=bounded_rule(masked,item['query'],bmt,args.rule_timeout,args.edge_cap,seed*100+rule_number)
            rule_groups.append(result.pop('units'))
            rule_reports.append({'rule_id':item['rule_id'],'requires_direct_pair':item['requires_direct_pair'],**result})
        rule_edges,rule_answers=union_units(rule_groups,args.edge_cap,seed)
        rule_seconds=time.perf_counter()-tick
        statuses=Counter(r['status'] for r in rule_reports)
        # Neither retrieval function receives validation answers; coverage is computed afterward.
        reports={}
        for strategy,edges,seconds in [('gandalf_walks',walk_edges,walk_seconds),('aragorn_rules',rule_edges,rule_seconds)]:
            assert len(edges)<=args.edge_cap
            for h,p,t in edges:
                assert (h,t) not in hidden and (t,h) not in hidden
                assert masked._find_edge_index(h,t,p) is not None
            save(directory/f'{strategy}.json',{'anchor':anchor,'edges':sorted(edges),'rule_answer_nodes':sorted(rule_answers) if strategy=='aragorn_rules' else []})
            reports[strategy]={**coverage(edges,anchor,drug_nodes,validation[disease],rule_answers if strategy=='aragorn_rules' else None),'retrieval_seconds':seconds}
        save(directory/'rules.json',rule_reports)
        record={'disease':disease,'index':anchor,'strategies':reports,'completed_walks':success,'attempted_walks':args.attempts,
                'rule_status_counts':dict(statuses),'artifact_sha256':{name:digest(directory/name) for name in ['gandalf_walks.json','aragorn_rules.json','rules.json']}}
        save(report_path,record)
        completed+=1
        print(f"{number+1}/{len(selected)} {disease}: "+json.dumps(reports)+' rules='+json.dumps(dict(statuses)),flush=True)
        if args.max_new_diseases is not None and completed>=args.max_new_diseases:break
    records=[json.loads(p.read_text()) for p in sorted((out/'diseases').glob('*/report.json'))]
    total_pairs=sum(len(validation[d]) for d in selected)
    summary={'complete':len(records)==len(selected),'cohort_diseases':len(selected),'completed_diseases':len(records),
             'cohort_validation_pairs':total_pairs,'strategies':{},'settings_sha256':digest(out/'settings.json'),
             'rule_status_counts':dict(sum((Counter(r['rule_status_counts']) for r in records),Counter())),
             'scope':'Coverage under fixed budgets; timeouts/errors are reported, not silently treated as exhaustive rule searches. No ULTRA inference or test metrics.',
             'driver_elapsed_seconds':time.perf_counter()-start,'parent_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024}
    for strategy in ['gandalf_walks','aragorn_rules']:
        rows=[r['strategies'][strategy] for r in records]
        pairs=sum(r['validation_pairs'] for r in rows);reached=sum(r['answers_reached'] for r in rows)
        summary['strategies'][strategy]={'evaluated_validation_pairs':pairs,'answers_reached':reached,'answer_coverage':reached/pairs if pairs else None,
             'mean_disease_answer_coverage':float(np.mean([r['answer_coverage'] for r in rows])) if rows else None,
             'mean_nodes':float(np.mean([r['nodes'] for r in rows])) if rows else None,
             'mean_edges':float(np.mean([r['edges'] for r in rows])) if rows else None,
             'mean_drug_nodes':float(np.mean([r['drug_nodes'] for r in rows])) if rows else None,
             'total_retrieval_seconds':sum(r['retrieval_seconds'] for r in rows),
             'answers_returned_as_rule_drugs':sum(r['answers_returned_as_rule_drugs'] for r in rows)}
    save(out/('summary.json' if summary['complete'] else 'partial.json'),summary)
    with (out/'per_disease.csv').open('w',newline='') as f:
        rows=[{'disease':r['disease'],'strategy':strategy,**v} for r in records for strategy,v in r['strategies'].items()]
        if rows:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    logging.basicConfig(level=logging.ERROR)
    main()
