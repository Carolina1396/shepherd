"""Small actual Shepherd ARAGORN HTTP versus local Gandalf comparison."""
import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import csv
import gzip
import json
import multiprocessing as mp
from pathlib import Path
import random
import resource
import sys
import time
import urllib.error
import urllib.request

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'pilot/retrieval'))
from full_graph_common import digest, save
from run import queries_for_disease
from common import compare_answers, extract_answers, make_query, response_issues, worker_expansion

CONTEXT = {}


def read(path):
    return json.loads(path.read_text())


def prepare(out, endpoint, timeout):
    baseline = ROOT / 'pilot/results/chemical_retrieval_001'
    old = read(baseline / 'settings.json')
    labels_path = Path(old['dataset']) / 'data/labels.json'
    assert digest(labels_path) == old['dataset_sha256']['labels.json']
    labels = read(labels_path)
    diseases = sorted(random.Random(7317).sample(sorted({r['disease'] for r in labels if r['split'] == 'validation'}), 10))
    worker = REPO / 'workers/aragorn_lookup/worker.py'
    rule_path = REPO / 'workers/aragorn_lookup/rules_with_types_cleaned_finalized.json'
    rules = read(rule_path)['{"predicate": "biolink:treats"}']
    assert len(rules) == 18 and digest(rule_path) == old['rules_sha256']
    cfg = {'endpoint': endpoint, 'timeout_seconds': timeout, 'cohort': diseases, 'seed': 7317,
           'selection': 'Ten diseases sampled from all Experiment 11 validation diseases; no answer-based selection',
           'worker_sha256': digest(worker), 'rules_sha256': digest(rule_path),
           'local_graph_metadata_sha256': digest(ROOT / 'output/gandalf/full-store/metadata.pkl'),
           'labels_sha256': digest(labels_path), 'source_sha256': {p.name: digest(p) for p in (Path(__file__), HERE / 'common.py')},
           'primary_local': 'Unmasked full local graph; subclass=False; no experiment edge cap; all 19 query answer sets unioned',
           'service': 'Actual HTTP /aragorn/query with workflow aragorn.lookup; requested tier 0, gandalf=True, subclass=False',
           'baseline_reference': str(baseline), 'comparison': 'Exact answer CURIE sets, not ranking or full response bytes',
           'remote_graph_identity': 'Unverified; the service may use a different graph snapshot or ignore requested backend controls'}
    if (out / 'settings.json').exists():
        assert read(out / 'settings.json') == cfg, 'Configuration changed; choose a new output directory'
        return cfg
    out.mkdir(parents=True)
    save(out / 'settings.json', cfg)
    for n, disease in enumerate(diseases):
        directory = out / f'{n:02d}'
        directory.mkdir()
        request = make_query(disease, timeout)
        save(directory / 'request.json', request)
        actual = worker_expansion(request, worker)
        local = queries_for_disease(disease, rules)
        local[0]['query']['query_graph']['nodes']['drug']['categories'] = request['message']['query_graph']['nodes']['drug']['categories']
        assert [r['message']['query_graph'] for r in actual] == [r['query']['query_graph'] for r in local]
        save(directory / 'expanded_queries.json', actual)
        old_number = old['cohort'].index(disease)
        old_dir = baseline / 'treats_only/diseases' / f'{old_number:04d}'
        report = read(old_dir / 'report.json')
        graph = read(old_dir / 'graph.json')
        assert digest(old_dir / 'graph.json') == report['artifact_sha256']['graph.json']
        save(directory / 'baseline_reference.json', {'disease': disease, 'graph_path': str(old_dir / 'graph.json'),
             'answer_indices': graph['rule_answer_nodes'], 'nodes': next(iter(report['splits'].values()))['nodes'],
             'edges': len(graph['edges']), 'expansion_equal_to_checkout_worker': True})
    save(out / 'expansion_parity.json', {'complete': True, 'queries': 10, 'expansions_per_query': 19,
         'all_query_graphs_identical': True, 'worker_sha256': cfg['worker_sha256'],
         'scope': 'Checkout worker helper compared with local experiment builder; deployed worker version is separate'})
    return cfg


def local_child(connection, query, destination, timeout):
    try:
        from gandalf import lookup
        from gandalf.trapi import Deadline
        ceiling = psutil.Process().memory_info().vms + 4*1024**3
        resource.setrlimit(resource.RLIMIT_AS, (ceiling, ceiling))
        tick = time.perf_counter()
        result = lookup(CONTEXT['graph'], query, bmt=CONTEXT['bmt'], subclass=False,
                        dehydrated=True, deadline=Deadline(timeout), log_level='ERROR')
        with gzip.open(destination, 'wt') as stream:
            json.dump(result, stream)
        answers = extract_answers(result)
        issues = response_issues(result)
        kg = result['message'].get('knowledge_graph') or {}
        connection.send({'complete': not issues, 'issues': issues, 'answers': sorted(answers),
                         'status': result.get('status'), 'results': len(result['message']['results']),
                         'kg_nodes': len(kg.get('nodes') or {}), 'kg_edges': len(kg.get('edges') or {}),
                         'seconds': time.perf_counter()-tick, 'response_sha256': digest(destination)})
    except BaseException as error:
        connection.send({'complete': False, 'error': repr(error), 'answers': []})
    finally:
        connection.close()


def local_query(task):
    number, disease, out, timeout = task
    directory = out / f'{number:02d}' / 'local'
    directory.mkdir(exist_ok=True)
    queries = read(directory.parent / 'expanded_queries.json')
    records, union = [], set()
    for i, query in enumerate(queries):
        path = directory / f'rule_{i:02d}.json'
        raw = directory / f'rule_{i:02d}.response.json.gz'
        if path.exists():
            record = read(path)
            if record.get('response_sha256'):
                assert digest(raw) == record['response_sha256']
        else:
            ctx = mp.get_context('fork')
            parent, child = ctx.Pipe(duplex=False)
            process = ctx.Process(target=local_child, args=(child, query, raw, timeout))
            process.start()
            child.close()
            if parent.poll(timeout+15):
                try:
                    record = parent.recv()
                except EOFError:
                    record = {'complete': False, 'error': 'worker exited', 'answers': []}
            else:
                record = {'complete': False, 'error': 'hard timeout', 'answers': []}
            process.join(timeout=2)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join()
            parent.close()
            record['rule_id'] = 'direct' if i == 0 else str(i-1)
            save(path, record)
        records.append(record)
        union.update(record['answers'])
    result = {'disease': disease, 'complete': all(r['complete'] for r in records),
              'answers': sorted(union), 'rules': records}
    save(directory.parent / 'local.json', result)
    baseline = read(directory.parent / 'baseline_reference.json')
    baseline['answers'] = sorted(CONTEXT['graph'].get_node_id(i) for i in baseline['answer_indices'])
    save(directory.parent / 'baseline_reference.json', baseline)
    return number, disease, len(union), result['complete']


def service_query(task):
    number, disease, out, cfg = task
    directory = out / f'{number:02d}'
    path = directory / 'service.json'
    if path.exists():
        return read(path)
    request = read(directory / 'request.json')
    body = json.dumps(request).encode()
    req = urllib.request.Request(cfg['endpoint'], data=body, headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
    tick = time.perf_counter()
    result = {'disease': disease, 'complete': False, 'endpoint': cfg['endpoint']}
    try:
        with urllib.request.urlopen(req, timeout=cfg['timeout_seconds']+90) as response:
            payload = response.read()
            result['http_status'] = response.status
            result['headers'] = {k: v for k, v in response.headers.items() if k.lower() in ('content-type', 'date', 'server', 'x-query-id')}
        with gzip.open(directory / 'service.response.json.gz', 'wb') as stream:
            stream.write(payload)
        response = json.loads(payload)
        answers = extract_answers(response)
        issues = response_issues(response)
        kg = response['message'].get('knowledge_graph') or {}
        result.update(complete=not issues, issues=issues, answers=sorted(answers),
                      status=response.get('status'), schema_version=response.get('schema_version'),
                      biolink_version=response.get('biolink_version'), parameters=response.get('parameters'),
                      results=len(response['message']['results']), kg_nodes=len(kg.get('nodes') or {}),
                      kg_edges=len(kg.get('edges') or {}),
                      response_sha256=digest(directory / 'service.response.json.gz'))
        save(directory / 'service.logs.json', response.get('logs') or [])
    except urllib.error.HTTPError as error:
        payload = error.read()
        with gzip.open(directory / 'service.response.json.gz', 'wb') as stream:
            stream.write(payload)
        result.update(http_status=error.code, error=f'HTTP {error.code}', body_preview=payload.decode(errors='replace')[:1500])
    except Exception as error:
        result['error'] = repr(error)
    result['seconds'] = time.perf_counter()-tick
    save(path, result)
    return result


def summarize(out, cfg):
    rows = []
    for i, disease in enumerate(cfg['cohort']):
        directory = out / f'{i:02d}'
        if not (directory / 'local.json').exists() or not (directory / 'service.json').exists():
            continue
        local, remote = read(directory / 'local.json'), read(directory / 'service.json')
        row = {'disease': disease, 'local_complete': local['complete'], 'service_complete': remote['complete'],
               'comparable_completed_responses': local['complete'] and remote['complete']}
        if row['comparable_completed_responses']:
            row.update(compare_answers(set(local['answers']), set(remote['answers'])))
            reference = read(directory / 'baseline_reference.json')
            row['original_masked_capped_comparison'] = compare_answers(set(reference['answers']), set(remote['answers']))
        else:
            row.update(exact_answer_set_match=None, error=remote.get('error') or remote.get('issues') or 'Local query incomplete')
        save(directory / 'comparison.json', row)
        rows.append(row)
    result = {'finished_queries': len(rows), 'requested_queries': len(cfg['cohort']),
              'complete': len(rows) == len(cfg['cohort']) and all(r['comparable_completed_responses'] for r in rows),
              'exact_matches': sum(r['exact_answer_set_match'] is True for r in rows),
              'nonempty_exact_matches': sum(r['exact_answer_set_match'] is True and not r['both_empty'] for r in rows),
              'endpoint': cfg['endpoint'], 'rows': rows,
              'interpretation': 'Observed exact answer-ID agreement. Unknown remote graph snapshot, backend settings, model versions, normalization, or truncation may explain differences; this is not proof of implementation equivalence.'}
    save(out / 'comparison.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'results/run_001')
    parser.add_argument('--endpoint', default='https://shepherd.renci.org/aragorn/query')
    parser.add_argument('--phase', choices=('prepare', 'local', 'service', 'compare', 'all'), default='all')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10 or args.timeout < 1:
        parser.error('Use 1–10 queries and a positive timeout')
    out = args.output.resolve()
    cfg = prepare(out, args.endpoint, args.timeout)
    if args.phase == 'prepare':
        print(json.dumps({'output': str(out), 'cohort': cfg['cohort'], 'expansion_parity': True}), flush=True)
        return
    status = {'phase': args.phase, 'started_unix': time.time(), 'complete': False}
    save(out / 'status.json', status)
    try:
        if args.phase in ('local', 'all'):
            from gandalf import CSRGraph
            from gandalf.biolink import make_toolkit
            graph = CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
            bmt = make_toolkit()
            CONTEXT.update(graph=graph, bmt=bmt)
            save(out / 'local_graph.json', {'nodes': graph.num_nodes, 'evidence_records': len(graph.fwd_targets),
                 'biolink_version': str(bmt.get_model_version()), 'mask': 'none', 'edge_cap': None,
                 'metadata_sha256': cfg['local_graph_metadata_sha256']})
            with ProcessPoolExecutor(max_workers=2, mp_context=mp.get_context('fork')) as pool:
                tasks = [(i, d, out, args.timeout) for i, d in enumerate(cfg['cohort'][:args.limit]) if not (out / f'{i:02d}' / 'local.json').exists()]
                for future in as_completed([pool.submit(local_query, t) for t in tasks]):
                    print('local ' + json.dumps(future.result()), flush=True)
        if args.phase in ('service', 'all'):
            url = args.endpoint.rsplit('/', 1)[0] + '/openapi.json'
            with urllib.request.urlopen(url, timeout=20) as response:
                api = json.load(response)
            save(out / 'service_openapi.json', api)
            save(out / 'service_info.json', api.get('info', {}))
            with ThreadPoolExecutor(max_workers=2) as pool:
                tasks = [(i, d, out, cfg) for i, d in enumerate(cfg['cohort'][:args.limit])]
                for future in as_completed([pool.submit(service_query, t) for t in tasks]):
                    r = future.result()
                    print('service ' + json.dumps({k: r.get(k) for k in ('disease', 'complete', 'http_status', 'results', 'error')}), flush=True)
        result = summarize(out, cfg)
        status.update(complete=result['complete'], finished_unix=time.time(), phase='complete' if result['complete'] else 'partial')
        save(out / 'status.json', status)
        print(json.dumps({'complete': result['complete'], 'finished_queries': result['finished_queries'], 'exact_matches': result['exact_matches']}), flush=True)
    except BaseException as error:
        status.update(phase='failed', error=repr(error), finished_unix=time.time())
        save(out / 'status.json', status)
        raise


if __name__ == '__main__':
    main()
