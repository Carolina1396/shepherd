import unittest
import numpy as np
from full_graph_common import evaluation_edge_mask, filtered_rank, held_out_edge_mask, hidden_pair_mask, split_pairs, summarize


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

    def test_masking_variants_keep_visible_pairs_and_indirect_context(self):
        # Predicate 0 is treats. Hidden pairs include validation and test.
        triples = np.array([[1, 0, 2], [2, 0, 1], [1, 1, 2], [2, 2, 1],
                            [3, 0, 4], [4, 1, 3],
                            [1, 0, 5], [1, 1, 5], [5, 2, 1], [2, 1, 5]])
        for mode, expected in (
            ("all-direct", [True, True, True, True, True, True, False, False, False, False]),
            ("treats-only", [True, True, False, False, True, False, False, False, False, False]),
        ):
            with self.subTest(mode=mode):
                mask = held_out_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2],
                                         {(1, 2), (3, 4)}, 6, 0, mode)
                np.testing.assert_array_equal(mask, expected)
                self.assertFalse(held_out_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2],
                                                    set(), 6, 0, mode).any())
        with self.assertRaises(ValueError):
            held_out_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2], {(1, 2)}, 6, 0, "unknown")

    def test_pair_and_disease_weighting(self):
        rows = [{"disease": "a", "rank": 1}, {"disease": "a", "rank": 1}, {"disease": "b", "rank": 10}]
        metrics = summarize(rows, "rank")
        self.assertAlmostEqual(metrics["mrr"], .7)
        self.assertAlmostEqual(metrics["disease_macro_mrr"], .55)
        self.assertEqual(metrics["top_10_answers"], 3)

    def test_remove_treats_from_all_target_splits_but_not_outside_pairs(self):
        # Hidden (1, 2), visible (3, 4), outside (1, 5); treats is predicate 0.
        triples = np.array([[1, 0, 2], [2, 0, 1], [1, 1, 2],
                            [3, 0, 4], [4, 0, 3], [3, 1, 4], [4, 2, 3],
                            [1, 0, 5], [5, 0, 1]])
        expected = {
            "all-direct": [True, True, True, False, False, False, False, False, False],
            "treats-only": [True, True, False, False, False, False, False, False, False],
            "treats-only-all-splits": [True, True, False, True, True, False, False, False, False],
            "all-direct-no-visible-treats": [True, True, True, True, True, False, False, False, False],
        }
        for mode, mask in expected.items():
            with self.subTest(mode=mode):
                actual = evaluation_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2],
                                              {(1, 2)}, {(3, 4)}, 6, 0, mode)
                np.testing.assert_array_equal(actual, mask)

    def test_variant_4_bidirectional_hidden_edges_and_empty_splits(self):
        triples = np.array([[1, 0, 2], [2, 1, 1], [3, 0, 4], [4, 2, 3], [5, 0, 6]])
        for hidden, visible, expected in (
            ({(1, 2)}, {(3, 4)}, [True, True, True, False, False]),
            (set(), {(3, 4)}, [False, False, True, False, False]),
            ({(1, 2)}, set(), [True, True, False, False, False]),
            (set(), set(), [False, False, False, False, False]),
        ):
            np.testing.assert_array_equal(
                evaluation_edge_mask(triples[:, 0], triples[:, 1], triples[:, 2],
                                     hidden, visible, 7, 0, "all-direct-no-visible-treats"), expected)


if __name__ == "__main__":
    unittest.main()
