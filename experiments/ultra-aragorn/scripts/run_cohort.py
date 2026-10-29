"""Resume the 48-query matched comparison; every query keeps an explicit outcome."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from retrieve import digest, save

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'scripts'
PYTHON=sys.executable
ENDPOINT='https://shepherd.ci.transltr.io/aragorn/query'
NORMALIZER='https://nodenormalization-sri.renci.org/get_normalized_nodes'


def run(script, argv, log, model=False, timeout=900):
    with log.open('w') as stream:
        process=subprocess.run([str(PYTHON) if model else sys.executable,'-B','-u',str(SCRIPTS/script),
            *map(str,argv)],stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
    if process.returncode:
        raise RuntimeError(f'{script} exited {process.returncode}; {log}')


def normalization(qid,candidates,out):
    labels=[a for a in json.loads((ROOT/'prepared/expected_answers.json').read_text())['answers'] if a['qid']==qid]
    ids=sorted(set(candidates)|{c for a in labels for c in a['source_ids']})
    payload=dict(curies=ids,conflate=True,drug_chemical_conflate=True)
    if (out/'normalization_response.json').exists():
        assert json.loads((out/'normalization_request.json').read_text())==payload
        record=json.loads((out/'normalization_metadata.json').read_text())
        assert digest(out/'normalization_response.json')==record['sha256']
        return out/'normalization_response.json'
    save(out/'normalization_request.json',payload)
    errors=[]
    for attempt in range(2):
        try:
            request=urllib.request.Request(NORMALIZER,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=120) as response:
                raw=response.read()
            data=json.loads(raw)
            assert set(data)==set(ids),'Missing normalization results'
            (out/'normalization_response.json').write_bytes(raw)
            save(out/'normalization_metadata.json',dict(endpoint=NORMALIZER,sha256=digest(out/'normalization_response.json'),
                retrieved_at=datetime.now(timezone.utc).isoformat(),prior_errors=errors))
            return out/'normalization_response.json'
        except Exception as error:
            errors.append(repr(error))
    save(out/'normalization_errors.json',errors)
    raise RuntimeError('Normalization failed twice')


def process(qid,root,reuse_query0=False):
    out=root/f'query_{qid:03d}'
    out.mkdir(exist_ok=True)
    status_path=out/'status.json'
    if status_path.exists():
        old=json.loads(status_path.read_text())
        if old['status'] in ('complete','empty_retrieval'):
            return old
    stage='retrieval'
    started=time.perf_counter()
    try:
        if qid==0 and reuse_query0:
            retrieval=ROOT/'results/smoke_002'
            ultra=retrieval/'ultra_scores'
            aragorn=retrieval/'aragorn_ci_legacy_001'
        else:
            retrieval=None
            for n in (1,2):
                trial=out/f'retrieval_{n:02d}'
                # Never resubmit an accepted-but-failed request automatically in place.
                if (trial/'inspection.json').exists():
                    retrieval=trial;break
                if (trial/'attempt.json').exists():continue
                try:
                    run('retrieve.py',['--qid',qid,'--output',trial,'--endpoint',ENDPOINT,'--send'],out/f'retrieval_{n}.log')
                    retrieval=trial;break
                except Exception:
                    if n==2:raise
            if retrieval is None:raise RuntimeError('No successful retrieval after two recorded attempts')
            ultra=retrieval/'ultra_scores'
            aragorn=None
        audit=json.loads((retrieval/'inspection.json').read_text())
        if audit['reference_issues']:raise RuntimeError('Retrieval has missing references')
        if not audit['candidates']:
            result=dict(qid=qid,status='empty_retrieval',retrieval=str(retrieval),candidates=0,
                service_problem_logs=len(audit['problem_logs']),note='No model scores; report separately from matched ranking metrics')
            save(status_path,result);return result
        stage='conversion'
        converted=retrieval/'ultra_input'
        if not (converted/'conversion.json').exists():
            run('convert_graph.py',['--retrieval',retrieval,'--output',converted],out/'conversion.log')
        stage='ultra_scoring'
        if not (ultra/'summary.json').exists():
            run('score_ultra.py',['--dataset',converted,'--output',ultra,'--device','cpu'],out/'ultra.log',model=True)
        stage='aragorn_scoring'
        if aragorn is None:
            for n in (1,2):
                trial=out/f'aragorn_{n:02d}'
                if (trial/'inspection.json').exists():
                    report=json.loads((trial/'inspection.json').read_text())
                    if report.get('scoring_complete') and report['matched_candidate_ids'] and not report['reference_issues']:
                        aragorn=trial;break
                if (trial/'attempt.json').exists():continue
                try:
                    run('score_aragorn.py',['--retrieval',retrieval,'--output',trial,'--endpoint',ENDPOINT,
                        '--legacy-bindings','--send'],out/f'aragorn_{n}.log')
                    aragorn=trial;break
                except Exception:
                    if n==2:raise
            if aragorn is None:raise RuntimeError('No complete scoring response after two attempts')
        stage='normalization'
        norm=normalization(qid,audit['candidate_ids'],out)
        stage='comparison'
        comparison=out/'comparison'
        if not (comparison/'summary.json').exists():
            run('compare_rankers.py',['--retrieval',retrieval,'--ultra',ultra,'--aragorn',aragorn,
                '--normalization',norm,'--output',comparison],out/'comparison.log')
        summary=json.loads((comparison/'summary.json').read_text())
        assert summary['status']=='matched_scores_available'
        result=dict(qid=qid,status='complete',retrieval=str(retrieval),ultra=str(ultra),aragorn=str(aragorn),
            comparison=str(comparison),candidates=audit['candidates'],identities=summary['identity_candidates'],
            service_problem_logs=len(audit['problem_logs']),elapsed_seconds=time.perf_counter()-started,
            reused_query0=qid==0 and reuse_query0)
    except Exception as error:
        result=dict(qid=qid,status='failed',stage=stage,error=repr(error),elapsed_seconds=time.perf_counter()-started)
    save(status_path,result)
    return result


def aggregate(root,ids):
    states=[];labels=[];rank_rows=[]
    for qid in ids:
        path=root/f'query_{qid:03d}/status.json'
        state=json.loads(path.read_text()) if path.exists() else dict(qid=qid,status='pending')
        states.append(state)
        if state['status']=='complete':
            comparison=Path(state['comparison'])
            labels.extend(json.loads((comparison/'label_matches.json').read_text()))
            with (comparison/'comparison.csv').open() as stream:
                rank_rows.extend(dict(qid=qid,**r) for r in csv.DictReader(stream))
    metrics={}
    positives=[r for r in labels if r['evaluation_status']=='eligible' and r['expected_output']=='TopAnswer']
    negatives=[r for r in labels if r['evaluation_status']=='eligible' and r['expected_output']=='NeverShow']
    for ranker in ['ultra','aragorn']:
        ranks=[r['ranks'][ranker] for r in positives]
        recovered=[r for r in ranks if r is not None]
        by_query={q:[r['ranks'][ranker] for r in positives if r['qid']==q] for q in {r['qid'] for r in positives}}
        metrics[ranker]=dict(eligible_positive_answers=len(ranks),eligible_positive_queries=len(by_query),
            answer_mrr=sum(1/r if r else 0 for r in ranks)/len(ranks) if ranks else None,
            conditional_answer_mrr=sum(1/r for r in recovered)/len(recovered) if recovered else None,
            query_macro_answer_mrr=sum(sum(1/r if r else 0 for r in rr)/len(rr) for rr in by_query.values())/len(by_query) if by_query else None,
            positive_retrieval_coverage=len(recovered)/len(ranks) if ranks else None,
            cutoffs={str(k):dict(topanswer_hits=sum(r is not None and r<=k for r in ranks),
                topanswer_recall=sum(r is not None and r<=k for r in ranks)/len(ranks) if ranks else None,
                nevershow_hits=sum(r['ranks'][ranker] is not None and r['ranks'][ranker]<=k for r in negatives)) for k in [1,5,10,20]})
    report=dict(requested_queries=len(ids),status_counts=dict(Counter(s['status'] for s in states)),
        all_queries_processed=all(s['status']!='pending' for s in states),queries=states,metrics=metrics,
        labels_in_matched_queries=len(labels),flagged_labels=sum(r['evaluation_status']!='eligible' for r in labels),
        matched_queries_with_service_warnings=sum(s['status']=='complete' and s.get('service_problem_logs',0)>0 for s in states),
        scope='Metrics apply only to successfully matched queries and eligible labels. Failed/empty queries remain listed, not silently included as ranking successes.',
        missing_positive_policy='For each matched query, eligible TopAnswer labels not retrieved receive reciprocal rank zero.',
        checkpoint='Pretrained ULTRA 4g, CPU, no training',retrieval_endpoint=ENDPOINT,
        query0_exception='Reuses development retrieval and CI scores from prior verified run' if any(s.get('reused_query0') for s in states) else None,
        label_policy='Keep conflicts/unresolved IDs/name-identity ambiguities flagged; no manual name matching',
        flags_by_reason=dict(Counter(r['evaluation_status'] for r in labels)),updated_at=datetime.now(timezone.utc).isoformat())
    save(root/'summary.json',report)
    save(root/'label_matches.json',labels)
    if rank_rows:
        with (root/'comparison.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rank_rows[0]));writer.writeheader();writer.writerows(rank_rows)
    return report


def main():
    global PYTHON
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'results/cohort_001')
    parser.add_argument('--max-new',type=int)
    parser.add_argument('--summarize-only',action='store_true')
    parser.add_argument('--model-python',type=Path,default=Path(sys.executable),help='Python interpreter with ULTRA dependencies (default: current interpreter)')
    parser.add_argument('--reuse-query0',action='store_true',help='Reuse historical local results/smoke_002 artifacts; otherwise retrieve query 0 normally')
    args=parser.parse_args()
    PYTHON=args.model_python.resolve()
    args.output.mkdir(parents=True,exist_ok=True)
    ids=[q['qid'] for q in json.loads((ROOT/'prepared/queries.json').read_text())['queries']]
    settings=dict(qids=ids,endpoint=ENDPOINT,normalizer=NORMALIZER,source_queries_sha256=digest(ROOT/'prepared/queries.json'),
        labels_sha256=digest(ROOT/'prepared/expected_answers.json'),concurrency=1,retries_per_stage=1,
        model_python=str(PYTHON),reuse_query0=args.reuse_query0,
        code_sha256={p.name:digest(p) for p in [Path(__file__),SCRIPTS/'retrieve.py',SCRIPTS/'convert_graph.py',SCRIPTS/'score_ultra.py',SCRIPTS/'score_aragorn.py',SCRIPTS/'compare_rankers.py']})
    if (args.output/'settings.json').exists():
        assert json.loads((args.output/'settings.json').read_text())==settings,'Settings or implementation changed; use a new output'
    else:save(args.output/'settings.json',settings)
    processed=0
    for qid in ids:
        if args.summarize_only:break
        status=args.output/f'query_{qid:03d}/status.json'
        if status.exists() and json.loads(status.read_text())['status'] in ['complete','empty_retrieval']:continue
        print(f'START qid={qid}',flush=True)
        result=process(qid,args.output,reuse_query0=args.reuse_query0)
        summary=aggregate(args.output,ids)
        print(f"DONE qid={qid} {result['status']} {summary['status_counts']}",flush=True)
        processed+=1
        if args.max_new is not None and processed>=args.max_new:break
    report=aggregate(args.output,ids)
    print(json.dumps({'status_counts':report['status_counts'],'metrics':report['metrics']},indent=2),flush=True)


if __name__=='__main__':main()
