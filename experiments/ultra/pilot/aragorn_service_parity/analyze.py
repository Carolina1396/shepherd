"""Verify saved responses and compare observed answers separately from rule errors."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

from common import compare_answers, extract_answers, response_issues


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def verified_answers(path, record):
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['response_sha256'], path
    with gzip.open(path, 'rt') as stream:
        response = json.load(stream)
    answers = extract_answers(response)
    assert answers == set(record['answers']), path
    assert response_issues(response) == record['issues'], path
    return answers


def analyze(out):
    cfg = read(out / 'settings.json')
    rows = []
    for i, disease in enumerate(cfg['cohort']):
        directory = out / f'{i:02d}'
        if not all((directory / f'{side}.json').exists() for side in ('local', 'service')):
            continue
        local, service = (read(directory / f'{side}.json') for side in ('local', 'service'))
        assert local['disease'] == service['disease'] == disease
        rule_answers = {}
        for j, record in enumerate(local['rules']):
            assert record == read(directory / 'local' / f'rule_{j:02d}.json')
            if 'response_sha256' in record:
                rule_answers[record['rule_id']] = verified_answers(
                    directory / 'local' / f'rule_{j:02d}.response.json.gz', record)
        local_answers = set().union(*rule_answers.values())
        assert local_answers == set(local['answers'])
        assert local['complete'] == all(r['complete'] for r in local['rules'])
        row = {'disease': disease, 'local_rules_complete': local['complete'],
               'service_rules_complete': service['complete'],
               'service_issues': service.get('issues', []),
               'valid_response_pair': len(rule_answers) == 19 and service.get('http_status') == 200
                                      and 'response_sha256' in service}
        if row['valid_response_pair']:
            remote_answers = verified_answers(directory / 'service.response.json.gz', service)
            row.update(compare_answers(local_answers, remote_answers))
            row['local_only_answer_rule_ids'] = {
                answer: [rule for rule, answers in rule_answers.items() if answer in answers]
                for answer in row['only_local']}
            row['local_rule_counts'] = {rule: len(answers) for rule, answers in rule_answers.items()}
            reference = read(directory / 'baseline_reference.json')
            row['original_masked_capped_comparison'] = compare_answers(set(reference['answers']), remote_answers)
        else:
            row.update(exact_answer_set_match=None, error=service.get('error', 'Missing valid rule responses'))
        save(directory / 'observed_comparison.json', row)
        rows.append(row)
    summary = {
        'analysis_finished': len(rows) == len(cfg['cohort']),
        'requested_queries': len(cfg['cohort']), 'finished_queries': len(rows),
        'verified_response_pairs': sum(r['valid_response_pair'] for r in rows),
        'observed_exact_matches': sum(r['exact_answer_set_match'] is True for r in rows),
        'nonempty_exact_matches': sum(r['exact_answer_set_match'] is True and not r['both_empty'] for r in rows),
        'error_free_exact_matches': sum(r['exact_answer_set_match'] is True and r['local_rules_complete']
                                       and r['service_rules_complete'] for r in rows),
        'all_rule_searches_complete': len(rows) == len(cfg['cohort']) and all(
            r['local_rules_complete'] and r['service_rules_complete'] for r in rows),
        'endpoint': cfg['endpoint'], 'local_graph': read(out / 'local_graph.json'),
        'remote_biolink_versions': sorted({read(out / f'{i:02d}' / 'service.json').get('biolink_version', 'unknown')
                                         for i in range(len(cfg['cohort'])) if (out / f'{i:02d}' / 'service.json').exists()}),
        'interpretation': 'Exact returned chemical CURIE sets, ignoring order and duplicate bindings. '
                          'Service rule failures remain visible; observed equality does not imply every rule ran. '
                          'Remote graph identity and backend controls are unverified. No synonym normalization.',
        'rows': rows}
    save(out / 'observed_comparison.json', summary)
    fields = ['disease', 'local_answers', 'service_answers', 'intersection', 'exact_answer_set_match',
              'local_rules_complete', 'service_rules_complete', 'valid_response_pair']
    with (out / 'per_query.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent / 'results/run_001')
    result = analyze(parser.parse_args().output)
    print(json.dumps({key: value for key, value in result.items() if key not in ('rows', 'local_graph')}, indent=2))
