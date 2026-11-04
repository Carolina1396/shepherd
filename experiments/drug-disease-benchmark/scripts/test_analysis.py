"""Small end-to-end checks for baseline extraction and approval summaries."""
import csv
import gzip
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class AnalysisTest(unittest.TestCase):
    def test_json_spacing_does_not_change_counts_or_source_overlap(self):
        nodes = [
            {"id": "CHEBI:1", "category": ["biolink:ChemicalEntity", "biolink:SmallMolecule"]},
            {"id": "MONDO:1", "category": ["biolink:DiseaseOrPhenotypicFeature", "biolink:Disease"]},
        ]
        edges = [{"subject": "CHEBI:1", "object": "MONDO:1", "predicate": "biolink:treats",
                  "clinical_approval_status": "approved_for_condition",
                  "sources": [{"resource_id": source, "resource_role": "primary_knowledge_source"}]}
                 for source in ["infores:drugcentral", "infores:multiomics-drugapprovals"]]
        edges.append({"subject": "MONDO:1", "object": "CHEBI:1", "predicate": "biolink:related_to"})
        with tempfile.TemporaryDirectory() as folder:
            tables = []
            for label, separators in [("compact", (",", ":")), ("spaced", (", ", ": "))]:
                raw = Path(folder) / label
                raw.mkdir()
                for name, records in [("nodes", nodes), ("edges", edges)]:
                    (raw / f"{name}.jsonl").write_text("".join(
                        json.dumps(row, separators=separators) + "\n" for row in records))
                out = raw / "out"
                for script, option in [("extract_drug_disease_edges.py", "--out"),
                                       ("describe_drug_disease_edges.py", "--results")]:
                    subprocess.run([sys.executable, str(HERE / script), str(raw), option, str(out)],
                                   check=True, capture_output=True, text=True)
                tables.append({f.name: f.read_text() for f in out.glob("*.csv")})
                with gzip.open(out / "drug_disease_edges.tsv.gz", "rt") as stream:
                    rows = list(csv.DictReader(stream, delimiter="\t"))
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[-1]["direction"], "disease->drug")
                with (out / "approved_overlap.csv").open() as stream:
                    overlap = {r["source"]: r for r in csv.DictReader(stream)}
                self.assertEqual(overlap["drugcentral"]["multiomics-drugapprovals"], "1")
                self.assertEqual(overlap["union"]["drugcentral"], "1")
            self.assertEqual(tables[0], tables[1])


if __name__ == "__main__":
    unittest.main()
