"""Prepare treatment requests and benchmark identities using cached Node Normalizer data."""
import argparse
from collections import Counter, defaultdict
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = 'https://nodenormalization-sri.renci.org/get_normalized_nodes'
LABELS = {'TopAnswer', 'Acceptable', 'BadButForgivable', 'NeverShow'}


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def group_labels(rows, response):
    groups = defaultdict(list)
    for row in rows:
        node = response[row['output_id']]
        preferred = node['id']['identifier'] if node else row['output_id']
        malformed = ':' not in row['output_id'] or not row['output_id'].split(':', 1)[1].strip()
        discriminator = row['asset_id'] if malformed else ''
        groups[(int(row['qid']), preferred, discriminator)].append(row)
    answers = []
    for (qid, preferred, discriminator), assets in sorted(groups.items()):
        labels = sorted({a['expected_output'] for a in assets})
        resolved = all(response[a['output_id']] is not None for a in assets)
        answers.append(dict(qid=qid, preferred_id=preferred,
            normalization_status='resolved' if resolved else 'unresolved',
            malformed_id=bool(discriminator),
            expected_output=labels[0] if len(labels) == 1 else None,
            labels=labels, conflict=len(labels) > 1,
            source_asset_ids=sorted({a['asset_id'] for a in assets}),
            source_ids=sorted({a['output_id'] for a in assets}),
            source_names=sorted({a['output_name'] for a in assets}),
            source_record_count=len(assets)))
    return answers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fetch', action='store_true', help='Fetch and freeze normalization if cache absent')
    args = parser.parse_args()
    out = ROOT / 'prepared'
    out.mkdir(exist_ok=True)
    query_path = ROOT / 'queries/hyi_treats.json'
    label_path = ROOT / 'labels/expected_answers_treats.csv'
    queries = json.loads(query_path.read_text())['queries']
    with label_path.open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(queries) == 48 and len({q['qid'] for q in queries}) == 48
    requests, corrections = [], []
    for query in queries:
        payload = copy.deepcopy(query['trapi_query'])
        graph = payload['message']['query_graph']
        edge, = graph['edges'].values()
        assert len(graph['nodes']) == 2
        assert edge['predicates'] == ['biolink:treats'] and edge['knowledge_type'] == 'inferred'
        answer, disease = graph['nodes'][edge['subject']], graph['nodes'][edge['object']]
        assert disease['categories'] == ['biolink:Disease'] and len(disease['ids']) == 1
        assert not answer.get('ids')
        if answer['categories'] == [None]:
            assert query['qid'] == 25
            answer['categories'] = ['biolink:ChemicalEntity']
            corrections.append(dict(qid=25, field=f"message.query_graph.nodes.{edge['subject']}.categories",
                                    original=[None], submitted=answer['categories']))
        assert answer['categories'] == ['biolink:ChemicalEntity']
        assert payload['parameters']['gandalf'] is True
        payload['workflow'] = [{'id': 'aragorn.lookup'}]
        requests.append(dict(qid=query['qid'], request=payload))
        local = [r for r in rows if int(r['qid']) == query['qid']]
        assert local and all(r['query_input_id'] == disease['ids'][0] for r in local)
    assert len(corrections) == 1
    assert all(r['expected_output'] in LABELS for r in rows)
    assert {int(r['qid']) for r in rows} == {q['qid'] for q in queries}
    ids = sorted({r['output_id'] for r in rows} | {r['query_input_id'] for r in rows})
    normalization_request = dict(curies=ids, conflate=True, drug_chemical_conflate=True)
    cache_path = out / 'normalization_cache.json'
    if not cache_path.exists():
        if not args.fetch:
            parser.error('Normalization cache absent; run with --fetch')
        request = urllib.request.Request(ENDPOINT, data=json.dumps(normalization_request).encode(),
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read()
            headers = dict(response.headers)
        data = json.loads(raw)
        assert set(data) == set(ids), 'Normalizer omitted or added requested IDs'
        (out / 'normalization_response.json').write_bytes(raw)
        save(cache_path, dict(endpoint=ENDPOINT, retrieved_at=datetime.now(timezone.utc).isoformat(),
            request=normalization_request, response_headers=headers,
            response_sha256=digest(out / 'normalization_response.json')))
    cache = json.loads(cache_path.read_text())
    assert cache['endpoint'] == ENDPOINT and cache['request'] == normalization_request
    assert cache['response_sha256'] == digest(out / 'normalization_response.json')
    data = json.loads((out / 'normalization_response.json').read_text())
    assert set(data) == set(ids)
    identities = []
    for curie in ids:
        node = data[curie]
        if node:
            assert node['id']['identifier']
        identities.append(dict(source_id=curie,
            preferred_id=node['id']['identifier'] if node else None,
            equivalent_ids=sorted({n['identifier'] for n in node['equivalent_identifiers']}) if node else [],
            status='resolved' if node else 'unresolved'))
    answers = group_labels(rows, data)
    conflicts = [a for a in answers if a['conflict']]
    unresolved = [a for a in answers if a['normalization_status'] == 'unresolved']
    # Do not collapse contradictory judgments into a positive or negative label.
    save(out / 'queries.json', dict(endpoint='https://shepherd.renci.org/aragorn/query', queries=requests))
    save(out / 'identities.json', identities)
    save(out / 'expected_answers.json', dict(answers=answers,
        policy='Unresolved IDs retain exact source identity. Conflicts have no selected label. Unknown candidates are not negatives.'))
    save(out / 'conflicts.json', conflicts)
    save(out / 'unresolved_answers.json', unresolved)
    report = dict(status='prepared_with_review_items' if conflicts or unresolved else 'prepared',
        queries=len(requests), corrections=corrections, source_label_records=len(rows),
        exact_duplicate_records=len(rows)-len({(r['qid'],r['output_id'],r['expected_output']) for r in rows}),
        prepared_answer_groups=len(answers), collapsed_records=len(rows)-len(answers),
        normalized_ids=len(ids), unresolved_ids=[i['source_id'] for i in identities if i['status']=='unresolved'],
        conflicting_query_answers=len(conflicts), unresolved_query_answers=len(unresolved),
        labels_without_conflicts=dict(Counter(a['expected_output'] for a in answers if not a['conflict'])),
        queries_with_unconflicted_topanswer=len({a['qid'] for a in answers if a['expected_output']=='TopAnswer'}),
        retrieval_submissions=0,
        limitations=['Source suite historical equivalence with hyi is unconfirmed.',
                    'Conflicting labels require review before aggregate evaluation.',
                    'Unresolved IDs must not be silently scored as retrieval misses.',
                    'Use this normalization configuration for returned candidates and preserve alias matches.'],
        sha256={str(p.relative_to(ROOT)):digest(p) for p in
            [query_path,label_path,Path(__file__),cache_path,out/'normalization_response.json',
             out/'queries.json',out/'identities.json',out/'expected_answers.json',
             out/'conflicts.json',out/'unresolved_answers.json']})
    save(out / 'report.json', report)
    print(json.dumps({k:v for k,v in report.items() if k!='sha256'}, indent=2))


if __name__ == '__main__':
    main()
