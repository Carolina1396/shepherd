import unittest
import numpy as np
from full_graph_common import filtered_rank, hidden_pair_mask, split_pairs, summarize


class ProtocolTests(unittest.TestCase):
    def test_exact_global_split_and_determinism(self):
        pairs = [(f"drug{i}", f"disease{i % 3538}") for i in range(18079)]
        result = split_pairs(pairs)
        self.assertEqual(result, split_pairs(list(reversed(pairs))))
        self.assertEqual([sum(s == name for _, _, s in result) for name in ("visible", "validation", "test")],
                         [14463, 1807, 1809])
        self.assertEqual({(h, t) for h, t, _ in result}, set(pairs))
        with self.assertRaises(ValueError):
            split_pairs([("a", "b"), ("a", "b")])

    def test_all_direct_predicates_and_directions_masked(self):
        triples = np.array([[1, 0, 2], [1, 1, 2], [2, 3, 1], [1, 0, 3], [2, 0, 3]])
        np.testing.assert_array_equal(hidden_pair_mask(triples[:, 0], triples[:, 2], {(1, 2)}, 4),
                                      [True, True, True, False, False])
        self.assertFalse(hidden_pair_mask(triples[:, 0], triples[:, 2], set(), 4).any())

    def test_filtered_rank_known_answers_and_ties(self):
        scores = np.array([9., 8., 8., 1.])
        self.assertEqual(filtered_rank(scores, 1, {0, 1}), 2)
        self.assertEqual(filtered_rank(scores, 1, {0, 1, 2}), 1)
        self.assertEqual(filtered_rank(scores, 3, {3}), 4)

    def test_pair_and_disease_weighting(self):
        rows = [{"disease": "a", "rank": 1}, {"disease": "a", "rank": 1}, {"disease": "b", "rank": 10}]
        metrics = summarize(rows, "rank")
        self.assertAlmostEqual(metrics["mrr"], .7)
        self.assertAlmostEqual(metrics["disease_macro_mrr"], .55)
        self.assertEqual(metrics["top_10_answers"], 3)


if __name__ == "__main__":
    unittest.main()
