"""Development tier comparison. Offline by default; explicit --submit sends once per case.

Default arm omits all tier controls. Tier 1 arm explicitly selects Tier 1 and
prevents fallback so a positive result cannot silently come from Tier 0.
Saved submission markers prevent retries even after ambiguous network failures.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
FOLLOWUP_ROOT = HERE.parent
EXPERIMENT_ROOT = FOLLOWUP_ROOT.parent.parent
sys.path.insert(0, str(EXPERIMENT_ROOT / 'scripts'))
from run import snapshot, submit_one, save, now, digest, RULE_KEY
from analyze import analyze_case, read, write_csv
from rule_outcomes import build_analysis


def configurations():
    original = read(EXPERIMENT_ROOT / 'config.json')
    base = {**original, 'environments': [original['environments'][0]],
            'submitter': 'aragorn-development-tier-selection-2026-10-20'}
    parameters = {k: v for k, v in base['parameters'].items()
                  if k not in ('tier', 'tiers', 'tier_fallback')}
    return {
        'default': {**base, 'parameters': parameters},
        'tier1': {**base, 'parameters': {**parameters, 'tier': 1, 'tiers': [1], 'tier_fallback': False}},
    }


def analyze(output):
    cases = []
    for arm, config in configurations().items():
        folder = output / arm
        if not (folder / 'release-rules.json').exists():
            continue
        rules = read(folder / 'release-rules.json')[RULE_KEY]
        for index, target in enumerate(config['targets'], 1):
            directory = folder / f'q{index:02d}'
            if not (directory / 'submission.json').exists():
                continue
            env = {**config['environments'][0], 'name': arm}
            case = analyze_case(env, target, directory, rules, index)
            messages = [l.get('message', '') for l in read(directory / 'response.json', {}).get('logs', [])]
            execution_logs = [m for m in messages if re.search(r'Begin processing tier[- ]\d+ job', m, re.I)]
            case['failed_dispatches'] = sum('Failed to do lookup' in m for m in messages)
            case['tier_execution_logs'] = execution_logs
            case['executed_tiers'] = sorted({int(re.search(r'tier[- ](\d+)', m, re.I)[1]) for m in execution_logs})
            case['tier_execution_counts'] = dict(Counter(re.search(r'tier[- ](\d+)', m, re.I)[1] for m in execution_logs))
            cases.append(case)
    save(output / 'report.json', {'created_utc': now(), 'cases': cases})
    outcomes = build_analysis(output)
    baseline = [c for c in read(EXPERIMENT_ROOT / 'output/run_002/report.json')['cases'] if c['environment'] == 'development']
    comparison = []
    for case in cases:
        old = next(c for c in baseline if c['query'] == case['query'])
        row = {k: case[k] for k in ('environment', 'query', 'target_name', 'http_status', 'query_status',
                                    'executed_tiers', 'tier_execution_counts', 'observed_rule_count',
                                    'received_callbacks', 'failed_dispatches', 'positive_rules', 'unique_chemical_count',
                                    'complete_for_answer_comparison')}
        comparable = case['complete_for_answer_comparison'] and old['complete_for_answer_comparison']
        row.update(baseline_positive_rules=old['positive_rules'], baseline_unique_chemicals=old['unique_chemical_count'],
                   newly_positive_rules=sorted(set(case['positive_rules']) - set(old['positive_rules'])) if comparable else None,
                   lost_positive_rules=sorted(set(old['positive_rules']) - set(case['positive_rules'])) if comparable else None,
                   same_final_chemical_ids=({a['id'] for a in case['answers']} == {a['id'] for a in old['answers']}) if comparable else None,
                   same_all_callback_counts=([r['raw_result_count'] for r in case['rule_results']] ==
                                             [r['raw_result_count'] for r in old['rule_results']]) if comparable else None)
        comparison.append(row)
    save(output / 'comparison.json', comparison)
    write_csv(output / 'comparison.csv', comparison)
    print(json.dumps({'summary': outcomes['environment_summary'], 'cases': comparison}, indent=2), flush=True)
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--submit', action='store_true')
    parser.add_argument('--arm', choices=['default', 'tier1', 'both'], default='both')
    parser.add_argument('--limit', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10:
        parser.error('--limit must be 1..10')
    output = FOLLOWUP_ROOT / 'output/run_001'
    output.mkdir(parents=True, exist_ok=True)
    if args.submit:
        import httpx
        configs = configurations()
        frozen = output / 'config.json'
        if frozen.exists() and read(frozen) != configs:
            raise ValueError('Run configuration changed; create a new output directory')
        save(frozen, configs)
        if not (output / 'manifest.json').exists():
            save(output / 'manifest.json', {'created_utc': now(), 'maximum_outer_requests': 20,
                 'maximum_expanded_lookups': 380, 'environment': 'Development only',
                 'runner_sha256': digest(Path(__file__)), 'baseline': '../../../../output/run_002',
                 'scope': 'Original inferred treats queries; hosted ARAGORN expansion, retrieval and merge. No scoring, masking, scheduling or automatic retries.'})
        with httpx.Client(timeout=210) as client:
            for arm, config in configs.items():
                if args.arm not in (arm, 'both'):
                    continue
                env = config['environments'][0]
                snapshot(client, env, output / arm)
                for index, target in enumerate(config['targets'][:args.limit], 1):
                    submit_one(client, env, target, config, output / arm / f'q{index:02d}')
                    analyze(output)
    else:
        analyze(output)


if __name__ == '__main__':
    main()
