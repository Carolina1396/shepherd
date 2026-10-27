"""Run rows 2–8 serially on the A6000 and publish each independently verified result."""
import argparse
from pathlib import Path
import re
import subprocess
import time
from common import ROOT, CONDITIONS, read,save,digest,policy

HERE=Path(__file__).resolve().parent


def write_results(suite_path):
    suite=read(suite_path/'suite.json')
    status=read(suite_path/'status.json') if (suite_path/'status.json').exists() else {}
    rows=[]
    for number in CONDITIONS:
        result={'condition':number,'policy':policy(number),'status':'pending'}
        if number==1:
            result.update(status='verified_existing_baseline',test=suite['baseline_test'],
                          source='full_graph_chemical_disease_4g_results.json',
                          removed_connections=11133,remaining_connections=27916156)
        else:
            directory=suite_path/f'row_{number:02d}'
            if (directory/'preparation.json').exists():
                result['preparation']=read(directory/'preparation.json')
            verification=directory/'evaluation/verification.json'
            if verification.exists():
                verified=read(verification)
                metrics_path=directory/'evaluation/test/metrics.json'
                assert verified['complete'] and verified['metrics_sha256']==digest(metrics_path)
                assert verified['dataset_sha256']==result['preparation']['dataset_sha256']
                metrics=read(metrics_path)
                result.update(status='verified',test=metrics['ultra'],
                    metrics={k:v for k,v in metrics.items() if k!='score_files_sha256'},
                    verification=verified,preparation_verification=read(directory/'preparation_verification.json'),
                    settings=read(directory/'evaluation/settings.json'),
                    provenance=read(directory/'evaluation/test/provenance.json'),
                    relation_graph=read(directory/'relation_graph.json'))
            elif status.get('condition')==number:
                result['status']=status['phase']
        rows.append(result)
    complete=all(r['status'].startswith('verified') for r in rows)
    record={'name':'Tier 0 full-graph pretrained 4g labeled-pair masking matrix',
            'complete':complete,'completed_conditions':sum(r['status'].startswith('verified') for r in rows),
            'suite_path':str(suite_path),'suite_sha256':digest(suite_path/'suite.json'),
            'protocol':suite,'conditions':rows,
            'baseline_parity':read(suite_path/'parity/parity.json') if (suite_path/'parity/parity.json').exists() else None,
            'interpretation':'Only labeled-pair direct context changes. Single existing split; exploratory, no model selection.'}
    save(suite_path/'results.json',record)
    save(ROOT/'pilot/studies'/f'{suite_path.name}_results.json',record)
    lines=['# Tier 0 masking matrix: test results','',
           f'**Status: {record["completed_conditions"]}/8 conditions verified.**','',
           'Fixed chemical/drug dataset: 22,918 labels (18,334 visible / 2,291 validation / 2,293 test),',
           '1,117,832 candidates, pretrained ULTRA 4g, no training, A6000 GPU. Held-out means validation and test.',
           'Only direct edges between labeled endpoints are changed, in both directions; unlabeled pairs remain unchanged.',
           'Every new row rebuilds its relation graph and retains all nodes and candidates, including isolated nodes.','',
           '| Row | Visible treats | Visible other | Held-out treats | Held-out other | Test MRR | Test Hits@10 | Top-10 answers | Status |',
           '|---|---|---|---|---|---:|---:|---:|---|']
    for r in rows:
        p=r['policy']; m=r.get('test')
        flags=['Keep' if p[k] else 'Remove' for k in ['visible_treats','visible_other','heldout_treats','heldout_other']]
        values=[f'{m["mrr"]:.4f}',f'{m["hits_at_10"]:.2%}',f'{m["top_10_answers"]} / 2,293'] if m else ['—']*3
        lines.append('| '+' | '.join([str(r['condition']),*flags,*values,r['status']])+' |')
    lines+=['','[Protocol and commands](README.md) · [Exact results and provenance](../studies/'+suite_path.name+'_results.json).',
            '', 'Row 1 reuses the verified original baseline. New scores are listed only after all test score hashes and ranks pass independent verification.',
            'Validation is masked but not rescored in this suite. Results are not comparable to older Drug-only or global edge-removal runs without accounting for their different scope.','']
    table=HERE/'RESULTS.md'
    tmp=table.with_suffix('.tmp')
    tmp.write_text('\n'.join(lines))
    tmp.replace(table)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite',type=Path,required=True)
    args=parser.parse_args()
    suite_path=args.suite.resolve()
    suite=read(suite_path/'suite.json')
    assert suite['complete']
    code=[HERE/name for name in ['common.py','run.py','verify.py','run_suite.py']]
    code += [ROOT/'pilot/finetune/run.py',ROOT/'scripts/full_graph_common.py',ROOT/'scripts/gpu_python.sh']
    settings={'suite_sha256':digest(suite_path/'suite.json'),
              'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in code},
              'order':list(range(2,9)),'gpu':'NVIDIA RTX A6000','test_only':True}
    if (suite_path/'runner_settings.json').exists():
        assert read(suite_path/'runner_settings.json')==settings,'Suite code changed; do not silently reuse scores'
    else:
        save(suite_path/'runner_settings.json',settings)
        for path in code:
            destination=suite_path/'runner_source'/path.relative_to(ROOT)
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(path.read_bytes())
    status={'complete':False,'phase':'starting','condition':None,'started_unix':time.time()}
    save(suite_path/'status.json',status)
    write_results(suite_path)
    gpu=['bash',str(ROOT/'scripts/gpu_python.sh'),'-B','-u',str(HERE/'run.py')]
    python=str(ROOT/'.venv-model-gpu/bin/python')

    def execute(command,logfile,phase,condition):
        status.update(phase=phase,condition=condition,updated_unix=time.time(),scored_queries=0)
        save(suite_path/'status.json',status)
        write_results(suite_path)
        with logfile.open('a') as log:
            process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
            status['child_pid']=process.pid
            save(suite_path/'status.json',status)
            for line in process.stdout:
                log.write(line);log.flush()
                print(line,end='',flush=True)
                match=re.search(r'test: (\d+)/(\d+) queries',line)
                if match:
                    status.update(scored_queries=int(match[1]),total_queries=int(match[2]),updated_unix=time.time())
                    save(suite_path/'status.json',status)
            code=process.wait()
            if code:
                raise RuntimeError(f'{phase} failed for row {condition}, exit={code}; see {logfile}')

    try:
        parity=suite_path/'parity'
        if not (parity/'parity.json').exists():
            command=gpu+['--dataset',suite['baseline'],'--output',str(parity),'--parity']
            if parity.exists():command+=['--resume']
            execute(command,suite_path/'parity.log','baseline_parity',1)
        assert read(parity/'parity.json')['complete']
        for row in range(2,9):
            dataset=suite_path/f'row_{row:02d}'
            if (dataset/'evaluation/verification.json').exists():
                write_results(suite_path)
                continue
            print(f'ROW_START {row}: {policy(row)}',flush=True)
            command=gpu+['--dataset',str(dataset)]
            if (dataset/'evaluation').exists():command+=['--resume']
            execute(command,dataset/'run.log','scoring',row)
            execute([python,'-B','-u',str(HERE/'verify.py'),'--dataset',str(dataset)],
                    dataset/'verification.log','verifying',row)
            result=write_results(suite_path)['conditions'][row-1]
            m=result['test']
            print(f'VERIFIED_RESULT row={row} test_MRR={m["mrr"]:.8f} test_Hits@10={m["hits_at_10"]:.8f} top10={m["top_10_answers"]}/2293',flush=True)
        final=write_results(suite_path)
        assert final['complete']
        status.update(complete=True,phase='complete',finished_unix=time.time())
        save(suite_path/'status.json',status)
        print('ALL EIGHT CONDITIONS VERIFIED',flush=True)
    except BaseException as error:
        status.update(complete=False,phase='failed',error=repr(error),updated_unix=time.time())
        save(suite_path/'status.json',status)
        write_results(suite_path)
        raise


if __name__=='__main__':
    main()
