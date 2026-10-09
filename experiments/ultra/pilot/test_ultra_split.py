import unittest

import numpy as np

from prepare_ultra import mask_hidden_pairs, split_pairs


class SplitTests(unittest.TestCase):
    def test_disjoint_repeatable_per_disease_split(self):
        pairs = [(f"C{i}", disease) for disease in ("D1", "D2") for i in range(20)]
        labels = split_pairs(pairs, 0.8, 731)
        self.assertEqual(labels, split_pairs(list(reversed(pairs)), 0.8, 731))
        self.assertEqual({(r["chemical"], r["disease"]) for r in labels}, set(pairs))
        for disease in ("D1", "D2"):
            self.assertEqual([sum(r["disease"] == disease and r["split"] == split for r in labels)
                              for split in ("visible", "validation", "test")], [16, 2, 2])

    def test_small_cohort_rounding_keeps_visible_context(self):
        labels = split_pairs([("C1", "D"), ("C2", "D")], 0.8, 731)
        self.assertTrue(all(r["split"] == "visible" for r in labels))
        labels = split_pairs([(f"C{i}", "D") for i in range(5)], 0.8, 731)
        self.assertEqual([sum(r["split"] == split for r in labels)
                          for split in ("visible", "validation", "test")], [4, 0, 1])

    def test_duplicate_labels_are_rejected(self):
        with self.assertRaises(ValueError):
            split_pairs([("C", "D"), ("C", "D")], 0.8, 731)

    def test_all_predicates_and_reverse_edges_of_hidden_pair_are_removed(self):
        triples = np.array([[0, 0, 1], [0, 2, 1], [1, 3, 0], [0, 0, 2], [1, 0, 2]])
        np.testing.assert_array_equal(mask_hidden_pairs(triples, {(0, 1)}),
                                      [False, False, False, True, True])
        self.assertTrue(mask_hidden_pairs(triples, set()).all())


if __name__ == "__main__":
    unittest.main()
