import unittest
from retrieve import binding_ids, inspect


class InspectionTests(unittest.TestCase):
    def test_deployed_trapi_2_bindings(self):
        self.assertEqual(binding_ids({'ids': ['A', 'B']}), ['A', 'B'])
        self.assertEqual(binding_ids([{'id': 'A'}]), ['A'])

    def test_candidates_come_from_bindings_and_nested_support_is_checked(self):
        request = {'message': {'query_graph': {'nodes': {'a': {}, 'd': {'ids': ['D']}}}}}
        response = {'message': {
            'knowledge_graph': {'nodes': {'A': {}, 'D': {}, 'intermediate': {}},
                'edges': {'answer': {'subject': 'A', 'object': 'D', 'predicate': 'treats',
                    'attributes': [{'attribute_type_id': 'biolink:support_graphs', 'value': ['g']}]},
                    'support': {'subject': 'A', 'object': 'intermediate', 'predicate': 'affects',
                    'attributes': [{'attribute_type_id': 'biolink:support_graphs', 'value': ['missing']}]}}},
            'auxiliary_graphs': {'g': {'edges': ['support']}},
            'results': [{'node_bindings': {'a': [{'id': 'A'}]},
                         'analyses': [{'edge_bindings': {'e': [{'id': 'answer'}]}}]}]}}
        result = inspect(response, request)
        self.assertEqual(result['candidate_ids'], ['A'])
        self.assertEqual(result['bound_edges_with_support_graphs'], 1)
        self.assertEqual(result['reference_issues'], ['edge support: missing support graph missing'])

    def test_missing_message_is_not_successful_empty_retrieval(self):
        request = {'message': {'query_graph': {'nodes': {'a': {}, 'd': {'ids': ['D']}}}}}
        self.assertTrue(inspect({'status': 'Error'}, request)['reference_issues'])


if __name__ == '__main__':
    unittest.main()
