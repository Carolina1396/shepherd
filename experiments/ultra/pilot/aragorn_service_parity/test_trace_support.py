"""Evidence attribution must reject similar-looking but incompatible paths."""
import copy
import unittest

from trace_support import classify, match_rule, qualifier_match


def fixture():
    nodes = {'A': {'categories': ['Chemical']}, 'E': {'categories': ['Chemical']},
             'I': {'categories': ['Biological']}, 'D': {'categories': ['Disease']}}
    rule = {'nodes': {'drug': {'categories': ['Chemical']}, 'e': {'categories': ['Chemical']},
                      'i': {'categories': ['Biological']}, 'disease': {'ids': ['D'], 'categories': ['Disease']}},
            'edges': {'t': {'subject': 'e', 'object': 'disease', 'forward': ['treats'], 'inverse': ['treated_by'], 'qualifiers': []},
                      'a': {'subject': 'i', 'object': 'drug', 'forward': ['affects'], 'inverse': None,
                            'qualifiers': [{'aspect': ['activity', 'abundance'], 'direction': ['decreased']}]},
                      'b': {'subject': 'i', 'object': 'e', 'forward': ['affects'], 'inverse': None,
                            'qualifiers': [{'aspect': ['activity', 'abundance'], 'direction': ['decreased']}]}}}
    qual = [{'qualifier_type_id': 'aspect', 'qualifier_value': 'activity'},
            {'qualifier_type_id': 'direction', 'qualifier_value': 'decreased'}]
    edges = {'1': {'subject': 'E', 'object': 'D', 'predicate': 'treats'},
             '2': {'subject': 'I', 'object': 'A', 'predicate': 'affects', 'qualifiers': copy.deepcopy(qual)},
             '3': {'subject': 'I', 'object': 'E', 'predicate': 'affects', 'qualifiers': copy.deepcopy(qual)}}
    return rule, nodes, edges


class EvidenceTests(unittest.TestCase):
    def test_qualifiers_prevent_false_rule_attribution(self):
        rule, nodes, edges = fixture()
        self.assertTrue(match_rule(rule, nodes, edges, 'A', 'D')['covers_entire_support_graph'])
        edges['2']['qualifiers'][1]['qualifier_value'] = 'increased'
        self.assertIsNone(match_rule(rule, nodes, edges, 'A', 'D'))
        self.assertIsNotNone(match_rule(rule, nodes, edges, 'A', 'D', True))

    def test_missing_qualifier_and_wrong_category_fail(self):
        rule, nodes, edges = fixture()
        edges['2']['qualifiers'] = []
        self.assertIsNone(match_rule(rule, nodes, edges, 'A', 'D'))
        nodes['I']['categories'] = ['Chemical']
        self.assertIsNone(match_rule(rule, nodes, edges, 'A', 'D', True))

    def test_inverse_allowed_but_arbitrary_reversal_forbidden(self):
        rule, nodes, edges = fixture()
        edges['1'] = {'subject': 'D', 'object': 'E', 'predicate': 'treated_by'}
        self.assertIsNotNone(match_rule(rule, nodes, edges, 'A', 'D'))
        edges['2']['subject'], edges['2']['object'] = 'A', 'I'
        self.assertIsNone(match_rule(rule, nodes, edges, 'A', 'D'))

    def test_shared_intermediate_must_be_consistent(self):
        rule, nodes, edges = fixture()
        nodes['J'] = nodes['I']
        edges['3']['subject'] = 'J'
        self.assertIsNone(match_rule(rule, nodes, edges, 'A', 'D'))

    def test_merged_parallel_evidence_and_unexplained_edges(self):
        rule, nodes, edges = fixture()
        edges['4'] = copy.deepcopy(edges['2'])
        match = match_rule(rule, nodes, edges, 'A', 'D')
        self.assertTrue(match['covers_entire_support_graph'])
        self.assertEqual(match['binding_count'], 2)
        edges['5'] = {'subject': 'I', 'object': 'A', 'predicate': 'unrelated'}
        match = match_rule(rule, nodes, edges, 'A', 'D')
        self.assertFalse(match['covers_entire_support_graph'])
        self.assertEqual(match['unexplained_edge_ids'], ['5'])

    def test_ambiguous_rules_are_both_preserved(self):
        rule, nodes, edges = fixture()
        match = classify({'10': rule, 'other': copy.deepcopy(rule)}, nodes, edges, 'A', 'D')
        self.assertEqual(set(match['full_matches']), {'10', 'other'})
        self.assertIsNone(match_rule(rule, nodes, edges, 'X', 'D'))

    def test_qualifier_or_between_sets_and_and_within_set(self):
        edge = {'qualifiers': [{'qualifier_type_id': 'aspect', 'qualifier_value': 'activity'}]}
        self.assertFalse(qualifier_match(edge, [{'aspect': ['activity'], 'direction': ['decreased']}]))
        self.assertTrue(qualifier_match(edge, [{'aspect': ['abundance']}, {'aspect': ['activity']}]))


if __name__ == '__main__':
    unittest.main()
