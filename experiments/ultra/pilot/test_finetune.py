"""Protocol tests for Experiment 5; no graph data or GPU required."""
import unittest

import numpy as np
import torch
from torch_geometric.data import Data

from finetune.run import improved, training_batch, training_loss, training_pools
from ultra.base_nbfnet import BaseNBFNet


class FineTuneTests(unittest.TestCase):
    def test_negatives_use_only_training_labels_and_drug_candidates(self):
        labels = [dict(drug_index=h, disease_index=9, split=s) for h, s in
                  [(0, "visible"), (1, "visible"), (2, "validation"), (3, "test")]]
        train, pools = training_pools(labels, [{"index": h} for h in range(5)])
        self.assertEqual(len(train), 2)
        np.testing.assert_array_equal(pools[9], [2, 3, 4])
        self.assertEqual({r["split"] for r in train}, {"visible"})
        # Changing holdout labels must not influence fitting negatives.
        _, other = training_pools(labels[:2], [{"index": h} for h in range(5)])
        np.testing.assert_array_equal(pools[9], other[9])

    def test_batch_corrupts_drugs_only_and_positive_is_first(self):
        batch = training_batch({"drug_index": 1, "disease_index": 9}, np.array([2, 3]), 4)
        np.testing.assert_array_equal(batch, [[[1, 9, 4], [2, 9, 4], [3, 9, 4]]])

    def test_native_mask_removes_all_direct_relations_both_directions(self):
        model = BaseNBFNet(4, [4], num_relation=4, remove_one_hop=True)
        # Answer pair 0--1 has two predicates and their inverses; 1--2 is context.
        graph = Data(edge_index=torch.tensor([[0, 0, 1, 1, 1, 2], [1, 1, 0, 0, 2, 1]]),
                     edge_type=torch.tensor([0, 1, 2, 3, 0, 2]), num_nodes=4, num_relations=4)
        batch = torch.tensor([[[0, 1, 0], [3, 1, 0]]])
        masked = model.remove_easy_edges(graph, *batch.unbind(-1))
        self.assertEqual(masked.edge_index.tolist(), [[1, 2], [2, 1]])
        self.assertEqual(masked.edge_type.tolist(), [0, 2])
        self.assertEqual(graph.num_edges, 6)

    def test_upstream_weighted_loss_has_finite_nonzero_gradients(self):
        scores = torch.zeros((1, 4), requires_grad=True)
        loss = training_loss(scores, 1.0)
        self.assertAlmostEqual(loss.item(), np.log(2), places=6)
        loss.backward()
        self.assertLess(scores.grad[0, 0], 0)
        self.assertTrue((scores.grad[0, 1:] > 0).all())
        self.assertTrue(torch.isfinite(scores.grad).all())

    def test_partial_or_worse_validation_cannot_select_a_checkpoint(self):
        self.assertFalse(improved({"complete": False, "ultra": {"mrr": 1.0}}, 0.1))
        self.assertFalse(improved({"complete": True, "ultra": {"mrr": 0.1}}, 0.1))
        self.assertTrue(improved({"complete": True, "ultra": {"mrr": 0.2}}, 0.1))


if __name__ == "__main__":
    unittest.main()
