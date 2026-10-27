"""Experiment 6 masking tests, independent of the real graph."""
import unittest
import numpy as np
from no_direct_edges.run import direct_drug_disease_mask


class NoDirectEdgesTests(unittest.TestCase):
    def test_every_predicate_both_directions_but_indirect_context_survives(self):
        drug = np.array([True, False, False, False, True])
        disease = np.array([False, True, False, True, False])
        # 0--1 and 4--3 are direct pairs; other connections are needed context.
        edges = np.array([[0, 0, 1], [1, 3, 0], [0, 7, 1], [3, 2, 4],
                          [0, 0, 2], [2, 0, 1], [0, 1, 4], [1, 0, 3]])
        np.testing.assert_array_equal(direct_drug_disease_mask(edges, drug, disease),
                                      [True, True, True, True, False, False, False, False])

    def test_global_scope_includes_pairs_without_treatment_labels(self):
        drug = np.array([True, False, False])
        disease = np.array([False, True, False])
        edges = np.array([[0, 59, 1], [1, 59, 0], [0, 59, 2]])
        np.testing.assert_array_equal(direct_drug_disease_mask(edges, drug, disease), [True, True, False])

    def test_overlapping_categories_and_empty_edges(self):
        drug = np.array([True, True, False])
        disease = np.array([True, False, True])
        edges = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 2]])
        self.assertTrue(direct_drug_disease_mask(edges, drug, disease).all())
        self.assertEqual(direct_drug_disease_mask(np.empty((0, 3), dtype=int), drug, disease).size, 0)


if __name__ == "__main__":
    unittest.main()
