import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pilot/retrieval'))
sys.path.insert(0, str(ROOT / 'scripts'))
from gandalf import CSRGraph
from masked_graph import mask_pairs
from masking import mask_graph
from metrics import measure, select_matches


class ProtocolTests(unittest.TestCase):
    def graph(self):
        edges = [(0, 1), (0, 1), (0, 1), (1, 0), (1, 0), (2, 1), (0, 3)]
        predicates = [0, 0, 1, 0, 1, 0, 1]
        return CSRGraph(5, edges, predicates, {f'N:{i}': i for i in range(5)},
                        {'biolink:treats': 0, 'biolink:in_clinical_trials_for': 1},
                        node_properties={i: {'categories': ['biolink:NamedThing']} for i in range(5)})

    def test_treats_only_removes_duplicate_and_reverse_treats_but_keeps_other_evidence(self):
        graph = self.graph()
        masked = mask_graph(graph, {(0, 1)}, 'treats_only')
        self.assertEqual(len(masked.fwd_targets), 4)
        for h, t in [(0, 1), (1, 0)]:
            self.assertIsNone(masked._find_edge_index(h, t, 0))
            self.assertIsNotNone(masked._find_edge_index(h, t, 1))
        self.assertIsNotNone(masked._find_edge_index(2, 1, 0))
        self.assertEqual(len(graph.fwd_targets), 7)
        for new, old in enumerate(masked.original_indices):
            self.assertEqual(masked.edge_properties._get_props(new), graph.edge_properties._get_props(int(old)))

    def test_strict_mask_matches_experiment7_mask_and_keeps_visible_treats(self):
        import numpy as np
        graph = self.graph()
        actual = mask_graph(graph, {(0, 1)}, 'all_direct')
        expected, _ = mask_pairs(graph, {(0, 1)})
        for name in ('fwd_offsets', 'fwd_targets', 'fwd_predicates', 'rev_offsets', 'rev_to_fwd'):
            np.testing.assert_array_equal(getattr(actual, name), getattr(expected, name))
        self.assertEqual(len(actual.fwd_targets), 2)
        self.assertIsNotNone(actual._find_edge_index(2, 1, 0))

    def test_global_mask_includes_validation_and_test_pairs(self):
        masked = mask_graph(self.graph(), {(0, 1), (2, 1)}, 'treats_only')
        self.assertNotIn(0, masked.fwd_predicates)
        self.assertEqual(len(masked.fwd_targets), 3)

    def test_no_hidden_pairs_keeps_all_records(self):
        for policy in ('all_direct', 'treats_only'):
            self.assertEqual(len(mask_graph(self.graph(), set(), policy).fwd_targets), 7)

    def test_coverage_distinguishes_context_answers_from_bound_answers(self):
        result = measure({(0, 1, 2), (2, 1, 3)}, 0, {2, 3, 4}, {2, 3, 4}, {3})
        self.assertEqual(result['answers_reached'], 2)
        self.assertEqual(result['answers_bound'], 1)
        self.assertEqual(result['answer_pairs'], 3)
        self.assertEqual(result['answer_coverage'], 2/3)
        empty = measure(set(), 0, {2, 3, 4}, {2, 3, 4}, set())
        self.assertEqual(empty['answer_coverage'], 0)
        self.assertEqual(empty['nodes'], 1)

    def test_match_cap_never_includes_partial_paths_and_preserves_old_selection(self):
        from run import union_units
        groups = [[{'edges': [(0, 0, 1), (1, 0, 2)], 'answers': [2]}],
                  [{'edges': [(0, 0, 3), (3, 0, 4)], 'answers': [4]}]]
        for seed in range(5):
            edges, answers, retained = select_matches(groups, 2, seed)
            self.assertEqual((edges, answers), union_units(groups, 2, seed))
            self.assertEqual(len(edges), 2)
            self.assertEqual(sum(map(len, retained)), 1)


if __name__ == '__main__':
    unittest.main()
