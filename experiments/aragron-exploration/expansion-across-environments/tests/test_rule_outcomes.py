"""Regression tests for distinctions that matter when interpreting rule coverage."""
import json
from pathlib import Path
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from rule_outcomes import build_analysis, classify, rejection_evidence


def rule(outcome, count=0, observed=True, callbacks=1):
    return {'outcomes': [outcome], 'raw_result_count': count,
            'expanded_graph_observed': observed, 'callback_count': callbacks}


class OutcomeTests(unittest.TestCase):
    def test_rejected_zero_is_not_empty(self):
        cb = [{'warnings_errors': [], 'callback_id': 'abc'}]
        self.assertEqual(classify(rule('invalid_predicate'), cb)[0], 'rejected')
        self.assertEqual(classify(rule('unsupported_pattern'), cb)[0], 'rejected')
        self.assertEqual(classify(rule('empty_callback_no_error_logged'), cb)[0], 'empty')

    def test_missing_or_duplicate_observations_are_not_empty(self):
        cb = [{'warnings_errors': []}]
        self.assertEqual(classify(rule('empty_callback_no_error_logged', observed=False), cb)[0], 'unknown')
        self.assertEqual(classify(rule('empty_callback_no_error_logged', callbacks=0), [])[0], 'unknown')
        self.assertEqual(classify(rule('empty_callback_no_error_logged', callbacks=2), cb*2)[0], 'unknown')

    def test_timeout_and_backend_error_are_not_empty(self):
        self.assertEqual(classify(rule('empty_callback_no_error_logged'), [{'warnings_errors':['Lookup timed out']}])[0], 'incomplete')
        self.assertEqual(classify(rule('backend_error'), [{'warnings_errors':['Backend failed'], 'has_error':True}])[0], 'error')

    def test_positive_partial_results_keep_issues(self):
        category, issues = classify(rule('paths_returned_with_errors', count=7),
            [{'warnings_errors':['Result truncated'], 'has_error':True}])
        self.assertEqual(category, 'returned')
        self.assertIn('callback includes error logs', issues)
        self.assertIn('possible timeout or truncation logged', issues)

    def test_rejection_resolves_only_the_named_edge(self):
        cb = {'callback_id':'abc', 'warnings_errors':["MetaEdges could not be found for the following QEdge(s): ['e1']"],
            'query_graph': {'nodes': {'g': {'categories':['biolink:Gene']}, 'd': {'categories':['biolink:DiseaseOrPhenotypicFeature']}},
                'edges': {'e1': {'subject':'g', 'object':'d', 'predicates':['biolink:genetic_association']},
                          'e2': {'subject':'g', 'object':'d', 'predicates':['biolink:related_to']}}}}
        evidence = rejection_evidence([cb])
        self.assertEqual(len(evidence[0]['flagged_edges']), 1)
        edge = evidence[0]['flagged_edges'][0]
        self.assertEqual(edge['edge'], 'e1')
        self.assertEqual(edge['subject_categories'], ['biolink:Gene'])
        self.assertEqual(edge['object_categories'], ['biolink:DiseaseOrPhenotypicFeature'])

    def test_saved_run_partition_and_each_environment(self):
        source = ROOT / 'output/run_002/report.json'
        if not source.exists():
            self.skipTest('Optional saved main run not present')
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'report.json').write_bytes(source.read_bytes())
            result = build_analysis(root)
            self.assertEqual(result['totals']['expanded'], 720)
            self.assertEqual(len(result['records']), 720)
            self.assertEqual(len(result['direct_lookups']), 40)
            self.assertEqual(len({(r['environment'],r['query'],r['rule']) for r in result['records']}), 720)
            for env in result['environment_summary']:
                self.assertEqual((env['returned'], env['rejected'], env['empty']), (27,80,73))
            for query in result['query_summary']:
                self.assertEqual(query['rejected_rules'], [1,2,3,4,5,7,8,9])
                if query['query']=='q10':
                    self.assertEqual(query['returned_rules'], [])
                    self.assertEqual(query['empty_rules'], [6,10,11,12,13,14,15,16,17,18])
            self.assertTrue(all(r['same_expansion_and_outcome_groups'] for r in result['environment_agreement']))


if __name__ == '__main__':
    unittest.main()
