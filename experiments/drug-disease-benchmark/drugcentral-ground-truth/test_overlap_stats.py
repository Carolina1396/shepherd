"""Check status isolation, source roles, directions, and duplicate edge counting."""

import csv
import json
from pathlib import Path
import tempfile
import unittest

from overlap_stats import analyze, read_status_pairs


class StatusOverlapTest(unittest.TestCase):
    def test_off_label_subset(self):
        records = []
        for drug, status, source in [
            ("D1", "approved_for_condition", "drugcentral"),
            ("D2", "off_label_use", "drugcentral"),
            ("D3", "off_label_use", "drugcentral"),
            ("D4", "off_label_use", "ttd"),
        ]:
            records.append({"subject": drug, "object": "C1",
                            "predicate": "biolink:treats", "clinical_approval_status": status,
                            "sources": [{"resource_id": "infores:" + source,
                                         "resource_role": "primary_knowledge_source"},
                                        {"resource_id": "infores:drugcentral",
                                         "resource_role": "supporting_data_source"}]})
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "edges.jsonl"
            raw.write_text("".join(json.dumps(r) + "\n" for r in records))
            edges = Path(folder) / "edges.tsv"
            with edges.open("w", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["subject", "object", "predicate", "primary_knowledge_source", "direction"])
                for r in records:
                    writer.writerow([r["subject"], r["object"], r["predicate"],
                                     r["sources"][0]["resource_id"], "drug->disease"])
                for drug in ["D1", "D2", "D2", "D4"]:
                    writer.writerow(["C1", drug, "biolink:has_side_effect", "infores:sider", "disease->drug"])
                writer.writerow(["D2", "C1", "biolink:treats", "infores:ttd", "drug->disease"])
            statuses = read_status_pairs(raw)
            self.assertNotIn(("D4", "C1"), statuses["off_label_use"])
            counts, sources, predicates = analyze(edges, statuses["off_label_use"])
            self.assertEqual(counts["drugcentral_treats_pairs"], 2)
            self.assertEqual(counts["non_treats_pairs"], 1)
            self.assertEqual(counts["other_treats_pairs"], 1)
            self.assertEqual(counts["either_overlap_pairs"], 1)
            self.assertEqual(counts["no_other_edge_pairs"], 1)
            self.assertEqual(sources, {"ttd": 1})
            self.assertEqual(predicates, {"has_side_effect": 1})


if __name__ == "__main__":
    unittest.main()
