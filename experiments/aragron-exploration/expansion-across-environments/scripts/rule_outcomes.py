"""Offline classification of observed ARAGORN rule expansions and callback outcomes.

Reads the main audit only; does not submit requests. Direct lookup is kept apart
from the 18 inference rules. Empty means a zero callback without a logged error,
not global absence or proof every requested constraint was enforced.
"""
import argparse
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from analyze import write_csv

ROOT = Path(__file__).resolve().parent.parent
CATEGORIES = ('returned', 'rejected', 'empty', 'incomplete', 'error', 'unknown')


def classify(rule, callbacks):
    outcomes = set(rule.get('outcomes') or [])
    count = rule.get('raw_result_count')
    flags = []
    if not rule.get('expanded_graph_observed'):
        return 'unknown', ['expanded query graph not observed']
    if rule.get('callback_count') != 1 or len(callbacks) != 1:
        flags.append('expected one identified callback')
    warnings = ' '.join(m for c in callbacks for m in c.get('warnings_errors', []))
    if any(c.get('has_error') for c in callbacks):
        flags.append('callback includes error logs')
    limited = bool(re.search(r'timed out|timeout|deadline exceeded|truncat|limit reached', warnings, re.I))
    if limited:
        flags.append('possible timeout or truncation logged')
    if count is not None and count > 0:
        if outcomes - {'paths_returned', 'paths_returned_with_errors'}:
            flags.append('mixed callback outcomes')
        return 'returned', flags
    if outcomes & {'invalid_predicate', 'unsupported_pattern'}:
        return 'rejected', flags
    if limited or 'incomplete_or_timeout' in outcomes:
        return 'incomplete', flags
    if 'backend_error' in outcomes or any(c.get('has_error') for c in callbacks):
        return 'error', flags
    if count == 0 and outcomes == {'empty_callback_no_error_logged'} and not flags:
        return 'empty', flags
    return 'unknown', flags


def rejection_evidence(callbacks):
    """Retain exact error messages and resolve named QEdges against observed graphs."""
    details = []
    for cb in callbacks:
        graph = cb.get('query_graph') or {}
        for message in cb.get('warnings_errors') or []:
            edge_ids = []
            if 'invalid predicates' in message:
                edge_ids = re.findall(r'Edge `([^`]+)`', message)
            elif 'MetaEdges could not be found' in message:
                match = re.search(r'QEdge\(s\):\s*(\[[^\]]*\])', message)
                if match:
                    edge_ids = ast.literal_eval(match.group(1))
            else:
                continue
            edges = []
            for eid in edge_ids:
                edge = graph.get('edges', {}).get(eid)
                if edge is None:
                    edges.append({'edge': eid, 'pattern': None})
                else:
                    edges.append({'edge': eid, 'subject': edge['subject'], 'object': edge['object'],
                        'subject_categories': graph['nodes'][edge['subject']].get('categories', []),
                        'object_categories': graph['nodes'][edge['object']].get('categories', []),
                        'predicates': edge.get('predicates', []),
                        'constraints': edge.get('constraints'), 'qualifier_constraints': edge.get('qualifier_constraints')})
            details.append({'callback_id': cb['callback_id'], 'message': message, 'flagged_edges': edges})
    return details


def summarize(rows, identity):
    counts = Counter(r['category'] for r in rows)
    return dict(identity, rule_evaluations=len(rows), expanded=sum(r['expanded'] for r in rows),
                **{category: counts[category] for category in CATEGORIES},
                returned_with_issues=sum(r['category'] == 'returned' and bool(r['issue_flags']) for r in rows))


def build_analysis(run):
    source = run / 'report.json'
    report = json.loads(source.read_text())
    records, direct = [], []
    for case in report['cases']:
        by_id = {c['callback_id']: c for c in case['callbacks']}
        for rule in case['rule_results']:
            callbacks = [by_id[cid] for cid in rule['callback_ids'] if cid in by_id]
            category, flags = classify(rule, callbacks)
            row = {'environment': case['environment'], 'query': case['query'], 'target': case['target'],
                'target_name': case['target_name'], 'rule': rule['rule'],
                'expanded': rule['expanded_graph_observed'], 'category': category,
                'raw_result_count': rule['raw_result_count'], 'callback_count': rule['callback_count'],
                'callback_ids': rule['callback_ids'], 'outcomes': rule['outcomes'], 'issue_flags': flags,
                'rejections': rejection_evidence(callbacks),
                'warnings_errors': [m for c in callbacks for m in c.get('warnings_errors', [])],
                'observed_query_graphs': [c['query_graph'] for c in callbacks if 'query_graph' in c],
                'response_artifact': f"{case['environment']}/{case['query']}/response.json"}
            (records if rule['rule'] else direct).append(row)
    environment_summary = [summarize([r for r in records if r['environment'] == env], {'environment': env})
                           for env in dict.fromkeys(r['environment'] for r in records)]
    query_summary = []
    for case in report['cases']:
        selected = [r for r in records if r['environment'] == case['environment'] and r['query'] == case['query']]
        summary = summarize(selected, {k: case[k] for k in ('environment', 'query', 'target', 'target_name')})
        summary['expanded_rules'] = sorted(r['rule'] for r in selected if r['expanded'])
        for category in CATEGORIES:
            summary[category + '_rules'] = sorted(r['rule'] for r in selected if r['category'] == category)
        query_summary.append(summary)
    rule_summary = [summarize([r for r in records if r['rule'] == n], {'rule': n})
                    for n in sorted({r['rule'] for r in records})]
    agreements = []
    environments = [s['environment'] for s in environment_summary]
    for query in dict.fromkeys(r['query'] for r in records):
        selected = [s for s in query_summary if s['query'] == query]
        signatures = {json.dumps({k: s[k] for k in ['expanded_rules'] + [x + '_rules' for x in CATEGORIES]}, sort_keys=True)
                      for s in selected}
        agreements.append({'query': query, 'target_name': selected[0]['target_name'],
                           'all_environments_present': len(selected) == len(environments),
                           'same_expansion_and_outcome_groups': len(selected) == len(environments) and len(signatures) == 1})
    result = {'source_report_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'analysis_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'definitions': {
            'expanded': 'Observed callback query graph matched the advertised-release template. Independent of outcome.',
            'returned': 'Positive raw callback count; pre-merge, not unique chemicals or proven final rule contributions.',
            'rejected': 'Logged invalid predicate or unsupported MetaEdge pattern; not an empty successful search.',
            'empty': 'Exactly one identified callback returned zero, without an error or incomplete-search indication in the saved logs.',
            'incomplete': 'Zero/unknown result with a timeout or truncation indication.',
            'error': 'Other logged backend error with no positive callback results.',
            'unknown': 'Missing or ambiguous evidence; never silently counted as empty.'},
        'totals': summarize(records, {}), 'environment_summary': environment_summary,
        'query_summary': query_summary, 'rule_summary': rule_summary, 'environment_agreement': agreements,
        'records': records, 'direct_lookups': direct,
        'limitations': ['No new HTTP requests; this is a re-analysis of the saved run.',
            'All counts in this analysis refer to rule-query evaluations or raw callbacks; direct lookups are separate.',
            'Warnings such as skipping unknown constraints are retained; an empty label does not prove qualifier enforcement.',
            'Unsupported MetaEdges describe service schema compatibility; they do not establish which individual graph records are absent.',
            'No final merged answer is attributed to a specific rule from these counts alone.',
            'A target-specific empty callback does not establish global absence of the rule.']}
    (run / 'rule-outcomes.json').write_text(json.dumps(result, indent=2) + '\n')
    write_csv(run / 'rule-outcomes.csv', [{k: v for k, v in r.items() if k != 'observed_query_graphs'} for r in records])
    write_csv(run / 'rule-outcomes-by-query.csv', query_summary)
    write_csv(run / 'rule-outcomes-by-environment.csv', environment_summary)
    write_csv(run / 'rule-outcomes-by-rule.csv', rule_summary)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=ROOT / 'output/run_002')
    result = build_analysis(parser.parse_args().run)
    print(json.dumps({'totals': result['totals'], 'environments': result['environment_summary']}, indent=2))
