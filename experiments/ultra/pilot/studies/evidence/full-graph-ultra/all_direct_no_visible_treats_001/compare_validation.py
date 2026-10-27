"""Compare the four frozen masking variants using paired disease resampling."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import csv
import hashlib
import json
import numpy as np

RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]
PATHS = {
    1: Path('/home/agonzalez/shepherd/experiments/ultra/output/full-graph-ultra/run_001'),
    2: ROOT / 'output/full-graph-ultra/treats_only_001',
    3: ROOT / 'output/full-graph-ultra/treats_all_splits_001',
    4: RUN,
}


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert load(RUN / 'validation_verification.json')['passed']
    assert not (RUN / 'test/metrics.json').exists(), 'This report is validation-only'
    rows, metrics, settings = {}, {}, {}
    for variant, directory in PATHS.items():
        metrics[variant] = load(directory / 'validation/metrics.json')
        settings[variant] = load(directory / 'validation/settings.json')
        assert metrics[variant]['complete']
        with (directory / 'validation/answer_ranks.csv').open() as stream:
            records = list(csv.DictReader(stream))
        rows[variant] = {(r['drug'], r['disease']): r for r in records}
        assert len(rows[variant]) == len(records) == 1807
        assert sha(directory / 'validation/answer_ranks.csv') == metrics[variant]['answer_ranks_sha256']
        assert rows[variant].keys() == rows[1].keys()
        for key in ('checkpoint_sha256', 'ultra_commit', 'torch', 'cuda', 'gpu', 'batch_size', 'training_epochs', 'split'):
            assert settings[variant][key] == settings[1][key], key
    keys = sorted(rows[1])
    ranks = np.array([[int(rows[v][k]['ultra_rank']) for v in PATHS] for k in keys])
    values = np.stack([1.0 / ranks, ranks <= 10], axis=2)
    # Shape: answer pair, variant, metric (MRR / Hits@10).
    means = values.mean(axis=0)
    for i, v in enumerate(PATHS):
        np.testing.assert_allclose(means[i], [metrics[v]['ultra']['mrr'], metrics[v]['ultra']['hits_at_10']], rtol=0, atol=1e-14)
    diseases = sorted({k[1] for k in keys})
    positions = {d: i for i, d in enumerate(diseases)}
    groups = np.array([positions[k[1]] for k in keys])
    sums = np.zeros((len(diseases), 4, 2))
    np.add.at(sums, groups, values)
    counts = np.bincount(groups, minlength=len(diseases))
    assert len(diseases) == 986 and counts.sum() == 1807
    seed, replicates = 20261016, 2000
    rng = np.random.default_rng(seed)
    boot = np.empty((replicates, 4, 2))
    for i in range(replicates):
        sample = rng.integers(0, len(diseases), size=len(diseases))
        boot[i] = sums[sample].sum(axis=0) / counts[sample].sum()
    contrasts = {
        'visible_treats_effect_without_other_direct_edges_V1_minus_V4': np.array([1, 0, 0, -1]),
        'visible_treats_effect_with_other_direct_edges_V2_minus_V3': np.array([0, 1, -1, 0]),
        'other_direct_edges_effect_with_visible_treats_V2_minus_V1': np.array([-1, 1, 0, 0]),
        'other_direct_edges_effect_without_visible_treats_V3_minus_V4': np.array([0, 0, 1, -1]),
        'interaction_V2_minus_V3_minus_V1_plus_V4': np.array([-1, 1, -1, 1]),
    }
    effects = {}
    for name, weights in contrasts.items():
        point = np.einsum('v,vm->m', weights, means)
        distribution = np.einsum('v,bvm->bm', weights, boot)
        limits = np.quantile(distribution, [0.025, 0.975], axis=0)
        effects[name] = {metric: {'estimate': float(point[j]), 'ci95': limits[:, j].tolist()}
                         for j, metric in enumerate(('mrr', 'hits_at_10'))}
    transitions = {}
    for baseline in (1, 3):
        old, new = ranks[:, baseline - 1], ranks[:, 3]
        transitions[f'variant_4_vs_{baseline}'] = {
            'rank_improved_pairs': int((new < old).sum()),
            'rank_worsened_pairs': int((new > old).sum()),
            'rank_unchanged_pairs': int((new == old).sum()),
            'entered_top_10': int(((old > 10) & (new <= 10)).sum()),
            'left_top_10': int(((old <= 10) & (new > 10)).sum()),
            'net_top_10_change': int((new <= 10).sum() - (old <= 10).sum()),
        }
    report = {
        'completed_at': datetime.now(ZoneInfo('America/Los_Angeles')).isoformat(),
        'experiment': '2. Full graph', 'split': 'validation', 'checkpoint': 'ULTRA 4g',
        'direction': 'disease_to_drug', 'pairs': 1807, 'diseases': 986, 'candidate_drugs': 5326,
        'training_epochs': 0, 'test_evaluated_for_variant_4': False,
        'variant_definitions': {
            'variant_1': {'visible': 'keep all edges', 'validation_test': 'remove all direct edges'},
            'variant_2': {'visible': 'keep all edges', 'validation_test': 'remove only treats'},
            'variant_3': {'visible': 'remove only treats', 'validation_test': 'remove only treats'},
            'variant_4': {'visible': 'remove only treats', 'validation_test': 'remove all direct edges'},
        },
        'results': {f'variant_{v}': {'ultra': metrics[v]['ultra'], 'degree_baseline': metrics[v]['degree_baseline'],
                    'metrics_sha256': sha(directory / 'validation/metrics.json'),
                    'ranks_sha256': sha(directory / 'validation/answer_ranks.csv')}
                    for v, directory in PATHS.items()},
        'runtime_settings_match': True,
        'graph_comparison': load(RUN / 'comparison_verification.json'),
        'paired_effects': effects, 'paired_rank_transitions': transitions,
        'uncertainty': {'method': 'paired disease-cluster percentile bootstrap; pair-weighted metrics',
                        'replicates': replicates, 'seed': seed, 'confidence_level': 0.95,
                        'scope': 'Exploratory disease-resampling intervals conditional on this fixed graph and split; not split or graph-release uncertainty; no multiple-comparison adjustment'},
        'analysis_script_sha256': sha(Path(__file__)),
    }
    (RUN / 'four_variant_validation_comparison.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'results': {v: r['ultra'] for v, r in report['results'].items()},
                      'paired_effects': effects, 'paired_rank_transitions': transitions}, indent=2))


if __name__ == '__main__':
    main()
