"""Extract source benchmark labels without guessing normalized identifiers."""
import collections
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'labels/sprint_6_tests.json'
    cases = json.loads(source.read_text())['test_cases']
    queries = json.loads((ROOT / 'queries/hyi_all.json').read_text())['queries']
    records, mismatches = [], []
    assert len(queries) == len(cases)
    for query, (case_id, case) in zip(queries, cases.items()):
        graph = query['trapi_query']['message']['query_graph']
        edge, = graph['edges'].values()
        pinned, = [n['ids'][0] for n in graph['nodes'].values() if n.get('ids')]
        assert edge['predicates'] == [case['test_case_predicate_id']], case_id
        assert sorted((n['categories'][0] for n in graph['nodes'].values()), key=str) == sorted(
            [case['input_category'], case['output_category']], key=str), case_id
        expected_qualifiers = sorted(
            (q['parameter'].replace('biolink_', 'biolink:'), q['value'])
            for q in case.get('qualifiers', []) if q['value']
        ) if case['test_case_predicate_id'] == 'biolink:affects' else []
        actual_qualifiers = sorted(
            (q['qualifier_type_id'], q['qualifier_value'])
            for group in edge.get('qualifier_constraints', []) for q in group['qualifier_set'])
        assert actual_qualifiers == expected_qualifiers, case_id
        match = pinned == case['test_case_input_id']
        if not match:
            mismatches.append({'qid': query['qid'], 'source_input': case['test_case_input_id'],
                               'query_input': pinned, 'status': 'identifier equivalence not verified'})
        for asset in case['test_assets']:
            records.append(dict(qid=query['qid'], test_case_id=case_id, asset_id=asset['id'],
                query_input_id=pinned, source_input_id=case['test_case_input_id'],
                input_name=asset['input_name'], predicate=case['test_case_predicate_id'],
                output_id=asset['output_id'], output_name=asset['output_name'],
                output_category=asset['output_category'], expected_output=asset['expected_output'],
                input_id_matches=match))
    counts = lambda rows: dict(collections.Counter(r['expected_output'] for r in rows))
    treats = [r for r in records if r['predicate'] == 'biolink:treats']
    provenance = dict(repository='https://github.com/TranslatorSRI/Tests',
        commit='90d4c7b497427850665971d9fad62d3fdbdc178f',
        path='test_suites/sprint_6_tests.json', sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        note='Source suite matches query order, predicates, categories and qualifiers. Exact historical suite version used by hyi is unconfirmed. Output IDs are original source IDs, not node-normalized. Records are test assets, not necessarily unique answers. Unlabeled candidates are unknown, not negative.')
    for name, rows in [('all', records), ('treats', treats)]:
        with (ROOT / f'labels/expected_answers_{name}.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(rows)
    report = dict(source=provenance, queries=len(queries), asset_records=len(records),
        labels=counts(records), treats_asset_records=len(treats), treats_labels=counts(treats),
        input_id_mismatches=mismatches,
        treats_queries_with_topanswer=len({r['qid'] for r in treats if r['expected_output']=='TopAnswer'}))
    (ROOT / 'labels/provenance.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
