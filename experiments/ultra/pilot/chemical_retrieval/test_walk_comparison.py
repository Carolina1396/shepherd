import random
import unittest

from compare_walks import GraphSampler, check_edges, comparison, graph_metric, sample


class WalkComparisonTests(unittest.TestCase):
    def test_sampling_obeys_mask_and_preserves_other_direct_evidence(self):
        # A single surviving three-edge chain can be walked from the disease.
        source = comparison.CSRGraph(4, [(1, 0), (0, 1), (1, 0), (2, 1), (3, 2)],
            [0, 0, 1, 1, 1], {f'N:{i}': i for i in range(4)},
            {'biolink:treats': 0, 'biolink:related_to': 1},
            node_properties={i: {'categories': ['biolink:NamedThing']} for i in range(4)})
        graph = comparison.mask_graph(source, {(1, 0)}, 'treats_only')
        sampler = GraphSampler(graph, random.Random(7317))
        first, completed, _ = sample(sampler, 0, 3, 100, 3000, 7317)
        second, repeated, _ = sample(sampler, 0, 3, 100, 3000, 7317)
        self.assertEqual(first, {(1, 1, 0), (2, 1, 1), (3, 1, 2)})
        self.assertGreater(completed, 0)
        self.assertEqual((first, completed), (second, repeated))
        check_edges(first, graph, {(1, 0)}, 0, 3000)
        with self.assertRaises(AssertionError):
            check_edges({(1, 0, 0)}, source, {(1, 0)}, 0, 3000)
        # Whole paths cannot fit in a two-edge budget; partial paths are excluded.
        capped, _, _ = sample(sampler, 0, 3, 100, 2, 7317)
        self.assertEqual(capped, set())

    def test_unrecovered_candidates_stay_in_denominator(self):
        value = graph_metric({(1, 1, 0), (2, 1, 1)}, 0, {1, 2, 3}, {1, 3})
        self.assertEqual(value['answer_pairs'], 2)
        self.assertEqual(value['answers_reached'], 1)
        self.assertEqual(value['answer_coverage'], 0.5)
        self.assertNotIn('answers_bound', value)
        self.assertEqual(graph_metric(set(), 0, {1, 2, 3}, {1, 3})['answer_coverage'], 0)


if __name__ == '__main__':
    unittest.main()
