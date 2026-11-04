import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from build_benchmark import APPROVED, CHEMICAL, CONDITION, SOURCE, TREATS, audit_graph, build, split_pairs


class BenchmarkTest(unittest.TestCase):
    def test_split_is_disjoint_complete_and_input_order_independent(self):
        pairs = [(f"D{i}", "C") for i in range(7903)]
        splits = split_pairs(pairs, 42)
        self.assertEqual({k: len(v) for k, v in splits.items()},
                         {"train": 6323, "validation": 790, "test": 790})
        self.assertEqual(splits, split_pairs(reversed(pairs), 42))
        self.assertEqual(set.union(*splits.values()), set(pairs))
        self.assertFalse(splits["train"] & splits["test"])
        self.assertFalse(splits["train"] & splits["validation"])
        self.assertFalse(splits["test"] & splits["validation"])

    def test_graph_blinding_and_independent_leakage_detection(self):
        drugs = {f"D{i}" for i in range(20)}
        pairs = {(drug, "C") for drug in drugs}
        splits = split_pairs(pairs, 42)
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "raw"
            raw.mkdir()
            nodes = [{"id": drug, "category": [CHEMICAL]} for drug in sorted(drugs)]
            nodes += [{"id": "C", "category": [CONDITION]},
                      {"id": "G", "category": ["biolink:Gene"]}]
            (raw / "nodes.jsonl").write_text("".join(json.dumps(n) + "\n" for n in nodes))
            edges = []
            for drug in sorted(drugs):
                # Duplicate approved source rows must not affect the split or graph.
                approved = {"subject": drug, "object": "C", "predicate": TREATS,
                            "clinical_approval_status": APPROVED,
                            "sources": [{"resource_id": SOURCE, "resource_role": "primary_knowledge_source"}]}
                edges.extend([approved, approved])
                # Both reverse non-treatment and other-source treatment must disappear.
                edges.append({"subject": "C", "object": drug, "predicate": "biolink:related_to"})
                edges.append({"subject": drug, "object": "C", "predicate": TREATS,
                              "primary_knowledge_source": "infores:another-source"})
            retained = {"subject": "D0", "object": "G", "predicate": "biolink:interacts_with"}
            edges.append(retained)
            (raw / "edges.jsonl").write_text("".join(json.dumps(e) + "\n" for e in edges))
            out = Path(folder) / "benchmark"
            with contextlib.redirect_stdout(io.StringIO()):
                manifest = build(raw, out, 42)
            self.assertEqual(manifest["approved_pairs"], 20)
            self.assertEqual(manifest["removed_direct_drug_condition_edges"], 80)
            self.assertEqual(manifest["output_edges"], 17)
            self.assertEqual((raw / "nodes.jsonl").read_bytes(), (out / "graph/nodes.jsonl").read_bytes())
            saved = [json.loads(line) for line in (out / "graph/edges.jsonl").read_text().splitlines()]
            self.assertIn(retained, saved)
            self.assertTrue(manifest["leakage_audit"]["passed"])
            # Deliberately inject a reversed held-out pair under a different predicate.
            drug, condition = next(iter(splits["test"]))
            with (out / "graph/edges.jsonl").open("a") as handle:
                handle.write(json.dumps({"subject": condition, "object": drug,
                                         "predicate": "biolink:has_side_effect"}) + "\n")
            with self.assertRaisesRegex(ValueError, "Held-out pair leaked"):
                audit_graph(out / "graph/edges.jsonl", splits, drugs, {"C"})


if __name__ == "__main__":
    unittest.main()
