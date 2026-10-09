"""Check held-out split routing and safe reuse of identical disease queries."""
import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from full_graph_common import digest, save
from run_full_graph_ultra import collect_results, reuse_validation_scores


class EvaluationTests(unittest.TestCase):
    def test_only_test_pairs_contribute_to_test_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "test"
            (output / "scores").mkdir(parents=True)
            save(root / "config.json", {})
            save(root / "preparation.json", {})
            labels = [
                {"drug_index": 10, "disease_index": 7, "disease": "a", "split": "visible", "disease_has_visible_treatment": True},
                {"drug_index": 11, "disease_index": 8, "disease": "b", "split": "validation", "disease_has_visible_treatment": False},
                {"drug_index": 12, "disease_index": 7, "disease": "a", "split": "test", "disease_has_visible_treatment": True}]
            np.savez(output / "scores/7.npz", scores=np.array([9., 8., 7.]), disease_index=7, seconds=1.)
            collect_results(root, output, labels, [{"index": i} for i in (10, 11, 12)], np.array([3, 2, 1]), "test")
            metrics = json.loads((output / "metrics.json").read_text())
            self.assertTrue(metrics["complete"])
            self.assertTrue(metrics["test_metrics_computed"])
            self.assertEqual(metrics["evaluated_pairs"], 1)
            self.assertEqual(metrics["ultra"]["mrr"], .5)
            with (output / "answer_ranks.csv").open() as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r["split"] for r in rows], ["test"])

    def test_reuse_requires_same_graph_and_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "validation", root / "test"
            (source / "scores").mkdir(parents=True)
            (output / "scores").mkdir(parents=True)
            keys = ("config_sha256", "preparation_sha256", "common_sha256", "checkpoint_sha256",
                    "ultra_commit", "torch", "cuda", "gpu", "batch_size", "training_epochs")
            settings = dict.fromkeys(keys, "same")
            save(source / "settings.json", {**settings, "split": "validation"})
            np.savez(source / "scores/7.npz", scores=np.array([1., 2.]), disease_index=7, seconds=1.)
            save(source / "metrics.json", {"complete": True, "score_files_sha256": {"7.npz": digest(source / "scores/7.npz")}})
            with self.assertRaises(AssertionError):
                reuse_validation_scores(root, output, [("a", 7)], {**settings, "checkpoint_sha256": "different"})
            self.assertFalse((output / "scores/7.npz").exists())
            reuse_validation_scores(root, output, [("a", 7), ("b", 8)], settings)
            self.assertEqual(digest(source / "scores/7.npz"), digest(output / "scores/7.npz"))
            self.assertEqual(len(json.loads((output / "reused_validation_scores.json").read_text())["files"]), 1)


if __name__ == "__main__":
    unittest.main()
