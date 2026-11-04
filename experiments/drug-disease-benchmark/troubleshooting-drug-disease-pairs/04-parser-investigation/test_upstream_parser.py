"""Behavioral tests against the unmodified upstream extraction entry point.

The desired behavior is exclusion of warning text from indications for BOTH
labels. The pinned parser is expected to fail the naproxen test. No xfail,
mocking, AST extraction, or record-class substitution is used here.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE / "upstream"
sys.path.insert(0, str(UPSTREAM / "src"))


class UpstreamParserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        snapshot = json.loads((HERE / "upstream-snapshot.json").read_text())
        for entry in snapshot["files"]:
            actual = hashlib.sha256((UPSTREAM / entry["path"]).read_bytes()).hexdigest()
            if actual != entry["sha256"]:
                raise AssertionError(f"Upstream file modified: {entry['path']}")
        manifest = json.loads((HERE / "manifest.json").read_text())
        for entry in manifest["files"]:
            if entry["path"].startswith("fixtures/"):
                assert hashlib.sha256((HERE / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]

    def extract(self, name):
        import polars as pl
        from dakp_pipeline.extract import spl_xml
        from dakp_pipeline.io.contracts import TaskContext
        from dakp_pipeline.paths import Workdir

        self.assertEqual(Path(spl_xml.__file__).resolve(),
                         (UPSTREAM / "src/dakp_pipeline/extract/spl_xml.py").resolve())
        with tempfile.TemporaryDirectory() as folder:
            ctx = TaskContext(workdir=Path(folder) / "work",
                              fixture_root=HERE / "fixtures", params={})
            Workdir(ctx.workdir).create()
            outputs = spl_xml.extract([ctx.fixture(f"{name}.xml")], ctx)
            sections = next(ref for ref in outputs if ref.uri.name == "spl_sections.parquet")
            return pl.read_parquet(sections.uri).to_dicts()

    def check_label(self, name, terms, legitimate_term):
        rows = self.extract(name)
        indication = " ".join(r["clean_text"] for r in rows if r["loinc_code"] == "34067-9").lower()
        warnings = " ".join(r["clean_text"] for r in rows
                            if r["loinc_code"] in {"34071-1", "43685-7"}).lower()
        self.assertIn(legitimate_term, indication, "Legitimate indication text must be retained")
        for term in terms:
            self.assertIn(term, warnings, "Warning must still be extracted as a warning")
            self.assertFalse(term in indication,
                             f"{name}: {term!r} leaked into LOINC 34067-9 indication output")

    def test_naproxen_warning_must_not_enter_indications(self):
        self.check_label("naproxen", ["heart failure"], "fever")

    def test_donepezil_warning_stays_separate(self):
        self.check_label("donepezil", ["seizure", "convulsion"], "alzheimer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
