"""Forty real ARAGORN lookup queries. Offline analysis by default; --submit opts in.

A saved submission marker is never retried automatically, including ambiguous
network failures. --submit resumes only pairs that have never been submitted.
"""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent
RULE_KEY = '{"predicate": "biolink:treats"}'
SOURCES = {'release-rules.json': 'workers/aragorn_lookup/rules_with_types_cleaned_finalized.json',
           'release-lookup-worker.py': 'workers/aragorn_lookup/worker.py',
           'release-merge-worker.py': 'workers/merge_message/worker.py'}


def save(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_request(config, target, trapi_version="2.0.0"):
    request = {'message': {'query_graph': {'nodes': {
        'drug': {'categories': ['biolink:ChemicalEntity']},
        'disease': {'categories': ['biolink:DiseaseOrPhenotypicFeature'], 'ids': [target['id']]}},
        'edges': {'e': {'subject': 'drug', 'object': 'disease',
                        'predicates': ['biolink:treats'], 'knowledge_type': 'inferred'}}}},
        'workflow': copy.deepcopy(config['workflow']),
        'parameters': copy.deepcopy(config['parameters']),
        'submitter': config.get('submitter', 'aragorn-ten-target-environment-comparison')}
    if not trapi_version.startswith('2.'):
        # Verified in v1.3.0/v1.1.7 base_routes.run_query. This changes logging only.
        request['log_level'] = config['parameters']['log_level']
    return request


def snapshot(client, env, path):
    path.mkdir(parents=True, exist_ok=True)
    if not (path / 'openapi.json').exists():
        response = client.get(env['base_url'] + '/openapi.json', timeout=45)
        response.raise_for_status()
        save(path / 'openapi.json', response.json())
    api = json.loads((path / 'openapi.json').read_text())
    sources = []
    for name, relative in SOURCES.items():
        url = f"https://raw.githubusercontent.com/BioPack-team/shepherd/v{api['info']['version']}/{relative}"
        entry = {'file': name, 'url': url}
        if not (path / name).exists():
            response = client.get(url, timeout=45)
            entry['status'] = response.status_code
            if response.status_code == 200:
                (path / name).write_bytes(response.content)
        if (path / name).exists():
            entry.update(status=200, sha256=digest(path / name))
        sources.append(entry)
    save(path / 'sources.json', sources)
    # No substitute rule file if this environment's declared release is missing.
    if not (path / 'release-rules.json').exists():
        raise RuntimeError('Cannot identify release rules; preflight failed before submission')
    return api


def submit_one(client, env, target, config, directory):
    from analyze import extract_query_ids
    directory.mkdir(parents=True, exist_ok=True)
    api = json.loads((directory.parent / 'openapi.json').read_text())
    query = make_request(config, target, api['info']['x-trapi']['version'])
    if (directory / 'submission.json').exists():
        if json.loads((directory / 'request.json').read_text()) != query:
            raise ValueError('Existing request differs; use a new run directory')
        print(f"SKIP existing attempt {env['name']} {target['id']}", flush=True)
        return
    save(directory / 'request.json', query)
    state = {'environment': env['name'], 'target': target['id'],
             'endpoint': env['base_url'] + '/query', 'started_utc': now(), 'state': 'submitting'}
    save(directory / 'submission.json', state)
    started = time.monotonic()
    try:
        response = client.post(state['endpoint'], json=query)
        (directory / 'response.body').write_bytes(response.content)
        state.update(state='response_received', http_status=response.status_code)
        try:
            data = response.json()
            save(directory / 'response.json', data)
        except ValueError:
            data = {}
            state['response_not_json'] = True
        ids = extract_query_ids(data.get('logs') or []) if isinstance(data, dict) else []
        state['query_ids'] = ids
        if len(ids) == 1:
            try:
                status = client.get(env['base_url'] + '/asyncquery_status/' + ids[0], timeout=30)
                save(directory / 'status-transport.json', {'http_status': status.status_code})
                if status.status_code == 200:
                    save(directory / 'status.json', status.json())
            except Exception as error:
                state['status_check_error'] = f'{type(error).__name__}: {error}'
    except Exception as error:
        state.update(state='submission_outcome_uncertain', error=f'{type(error).__name__}: {error}')
    finally:
        state.update(seconds=round(time.monotonic() - started, 3), finished_utc=now())
        save(directory / 'submission.json', state)
    print(json.dumps(state), flush=True)


def main():
    import httpx
    from analyze import analyze_run
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'config.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'output/run_002')
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--limit', type=int, help='Restrict to first N targets, for a pilot; full manifest remains frozen')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if len(config['targets']) != 10 or len({t['id'] for t in config['targets']}) != 10:
        raise ValueError('Expected ten distinct targets')
    if args.submit:
        args.output.mkdir(parents=True, exist_ok=True)
        frozen = args.output / 'config.json'
        if frozen.exists() and json.loads(frozen.read_text()) != config:
            raise ValueError('Run configuration differs; use a new output directory')
        save(frozen, config)
        if not (args.output / 'manifest.json').exists():
            save(args.output / 'manifest.json', {'created_utc': now(), 'runner_sha256': digest(Path(__file__)),
                 'planned_queries': 40, 'config_sha256': digest(args.config),
                 'scope': 'Real hosted lookup-only expansion/retrieval/merge; no scoring or holdout.',
                 'graph_release': 'Unknown for internal retrievers; tier 0 is requested, execution is checked in logs.'})
        with httpx.Client(timeout=config['timeout_seconds'] + 90) as client:
            ready = []
            for env in config['environments']:
                try:
                    snapshot(client, env, args.output / env['name'])
                    ready.append(env)
                except Exception as error:
                    save(args.output / env['name'] / 'preflight-error.json', {'error': str(error), 'at': now()})
                    print(f"PREFLIGHT FAILED {env['name']}: {error}", flush=True)
            for index, target in enumerate(config['targets'][:args.limit], 1):
                for env in ready:
                    submit_one(client, env, target, config, args.output / env['name'] / f'q{index:02d}')
                    analyze_run(args.output)
    report = analyze_run(args.output)
    print(json.dumps(report['overview'], indent=2))


if __name__ == '__main__':
    main()
