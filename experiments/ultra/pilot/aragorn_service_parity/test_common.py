import unittest
from common import binding_ids, compare_answers, extract_answers, response_issues


class ComparisonTests(unittest.TestCase):
    def test_both_trapi_versions_and_duplicate_answers(self):
        old = {'message': {'results': [{'node_bindings': {'drug': [{'id': 'CHEBI:1'}, {'id': 'CHEBI:1'}]}}]}}
        new = {'message': {'results': [{'node_bindings': {'drug': {'ids': ['CHEBI:1']}}}]}}
        self.assertEqual(extract_answers(old), extract_answers(new))

    def test_missing_results_is_not_an_empty_success(self):
        with self.assertRaises(ValueError):
            extract_answers({'message': {}})

    def test_exact_sets_ignore_order_and_expose_differences(self):
        self.assertTrue(compare_answers({'A', 'B'}, {'B', 'A'})['exact_answer_set_match'])
        result = compare_answers({'A', 'B'}, {'B', 'C'})
        self.assertEqual(result['only_local'], ['A'])
        self.assertEqual(result['only_service'], ['C'])
        self.assertEqual(result['jaccard'], 1/3)

    def test_timeout_is_not_valid_empty_answer_set(self):
        self.assertTrue(response_issues({'status': 'Timeout'}))
        self.assertTrue(response_issues({'status': 'Success', 'logs': [{'level': 'WARNING', 'message': 'Timed out getting lookup callbacks'}]}))
        self.assertFalse(response_issues({'status': 'Success', 'logs': [{'level': 'INFO', 'message': 'Configured timeout: 120'}]}))


if __name__ == '__main__':
    unittest.main()
