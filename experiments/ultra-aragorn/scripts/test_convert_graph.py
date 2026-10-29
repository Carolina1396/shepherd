import copy
import unittest
from convert_graph import convert


def fixture():
    request = {'message': {'query_graph': {'nodes': {'a': {}, 'd': {'ids': ['D']}},
        'edges': {'e': {'subject': 'a', 'object': 'd', 'predicates': ['biolink:treats']}}}}}
    edges = {
        'conclusion': {'subject': 'A', 'object': 'D', 'predicate': 'biolink:treats',
            'attributes': [{'attribute_type_id': 'biolink:support_graphs', 'value': ['outer']}]},
        'nested': {'subject': 'A', 'object': 'G', 'predicate': 'biolink:affects',
            'attributes': [{'attribute_type_id': 'biolink:support_graphs', 'value': ['inner']}]},
        'evidence': {'subject': 'A', 'object': 'G', 'predicate': 'biolink:affects'},
        'path': {'subject': 'G', 'object': 'D', 'predicate': 'biolink:associated_with'},
        'direct': {'subject': 'A', 'object': 'D', 'predicate': 'biolink:treats'},
        'isolated_conclusion': {'subject': 'B', 'object': 'D', 'predicate': 'biolink:treats',
                               'knowledge_level': 'logical_entailment'},
    }
    response = {'message': {'knowledge_graph': {'nodes': {n: {} for n in ['A', 'B', 'G', 'D']}, 'edges': edges},
        'auxiliary_graphs': {'outer': {'edges': ['nested', 'path']}, 'inner': {'edges': ['evidence']}},
        'results': [{'node_bindings': {'a': {'ids': [n]}, 'd': {'ids': ['D']}},
                     'analyses': [{'edge_bindings': {'e': {'ids': [e]}}}]} for n, e in
                    [('A', 'conclusion'), ('B', 'isolated_conclusion')]]}}
    return response, request


class ConversionTests(unittest.TestCase):
    def test_nested_evidence_and_real_direct_edge_survive_conclusion_removal(self):
        response, request = fixture()
        result = convert(response, request)
        kept = {e for p in result['triple_provenance'] for e in p['source_edge_ids']}
        self.assertEqual(kept, {'evidence', 'path', 'direct'})
        self.assertEqual(set(result['removed_edges']), {'conclusion', 'nested', 'isolated_conclusion'})
        self.assertEqual([c['id'] for c in result['candidates']], ['A', 'B'])
        self.assertTrue(result['candidates'][1]['isolated'])
        self.assertTrue(result['candidates'][0]['direct_treats_evidence'])

    def test_duplicate_evidence_triples_keep_provenance(self):
        response, request = fixture()
        response['message']['knowledge_graph']['edges']['duplicate'] = copy.deepcopy(
            response['message']['knowledge_graph']['edges']['evidence'])
        result = convert(response, request)
        self.assertEqual(len(result['triples']), 3)
        self.assertIn(['duplicate', 'evidence'], [p['source_edge_ids'] for p in result['triple_provenance']])

    def test_missing_support_edge_fails_closed(self):
        response, request = fixture()
        del response['message']['knowledge_graph']['edges']['evidence']
        with self.assertRaisesRegex(ValueError, 'Incomplete evidence'):
            convert(response, request)

    def test_empty_evidence_preserves_nodes_and_target_relation(self):
        response, request = fixture()
        response['message']['knowledge_graph']['edges'] = {'isolated_conclusion':
            response['message']['knowledge_graph']['edges']['isolated_conclusion']}
        response['message']['auxiliary_graphs'] = {}
        response['message']['results'] = response['message']['results'][1:]
        result = convert(response, request)
        self.assertEqual(result['triples'], [])
        self.assertEqual(result['predicates'], ['biolink:treats'])
        self.assertEqual(result['candidates'][0]['id'], 'B')


if __name__ == '__main__':
    unittest.main()
