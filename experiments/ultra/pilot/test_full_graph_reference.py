"""Check bidirectional filtering, completion, and result-integrity behavior."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from run_full_graph_reference import collect_results, digest, validate_resume


class ReferenceResultsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        (self.output / "settings.json").write_text("{}")
        self.labels = [
            {"drug": drug, "drug_index": h, "disease": disease, "disease_index": t, "split": split}
            for drug, h, disease, t, split in [
                ("A", 0, "X", 10, "visible"), ("B", 1, "X", 10, "validation"),
                ("C", 2, "X", 10, "test"), ("C", 2, "Y", 11, "test"),
                ("C", 2, "Z", 12, "visible")]]
        self.candidates = {"disease_to_drug": [{"index": i} for i in range(4)],
                           "drug_to_disease": [{"index": i} for i in range(10, 14)]}

    def score(self, direction, query, values):
        directory = self.output / direction / "scores"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{query}.npz"
        np.savez(path, scores=np.array(values, dtype=float), query_index=query)
        path.with_suffix(".json").write_text(json.dumps({"query_index": query, "sha256": digest(path)}))
        return path

    def all_scores(self):
        self.score("disease_to_drug", 10, [9, 8, 5, 5])
        self.score("disease_to_drug", 11, [6, 2, 5, 1])
        self.score("drug_to_disease", 2, [5, 4, 8, 4])

    def test_partial_run_has_no_final_metrics(self):
        self.score("disease_to_drug", 10, [9, 8, 5, 5])
        self.assertFalse(collect_results(self.output, self.labels, self.candidates))
        self.assertFalse((self.output / "metrics.json").exists())
        self.assertFalse(json.loads((self.output / "progress.json").read_text())["complete"])

    def test_both_directions_filter_all_known_answers_and_count_ties(self):
        self.all_scores()
        self.assertTrue(collect_results(self.output, self.labels, self.candidates))
        report = json.loads((self.output / "metrics.json").read_text())
        self.assertEqual(report["directions"]["disease_to_drug"]["mrr"], 0.5)
        self.assertEqual(report["directions"]["drug_to_disease"]["mrr"], 0.75)
        self.assertEqual(report["combined"]["mrr"], 0.625)
        self.assertEqual(report["combined"]["hits_at_1"], 0.25)
        self.assertEqual(report["combined"]["directional_answers"], 4)
        (self.output / "drug_to_disease/scores/2.npz").unlink()
        with self.assertRaisesRegex(ValueError, "missing score files"):
            collect_results(self.output, self.labels, self.candidates)

    def test_corrupt_scores_are_rejected(self):
        path = self.score("disease_to_drug", 10, [9, 8, 5, 5])
        path.write_bytes(path.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "integrity check failed"):
            collect_results(self.output, self.labels, self.candidates)

    def test_resume_rejects_changed_settings(self):
        path = self.output / "settings.json"
        path.write_text(json.dumps({"checkpoint": "3g", "candidates_sha256": "original"}))
        validate_resume(path, {"checkpoint": "3g", "candidates_sha256": "original"})
        with self.assertRaisesRegex(ValueError, "Resume settings changed"):
            validate_resume(path, {"checkpoint": "4g", "candidates_sha256": "original"})


if __name__ == "__main__":
    unittest.main()
