"""Checks for the section-context distinctions this audit depends on."""
import gzip
from pathlib import Path
import tempfile
import unittest

from audit import parse_sections, normalized


class SectionContextTest(unittest.TestCase):
    def test_possessive_disease_names(self):
        self.assertEqual(normalized("Alzheimer’s disease"), normalized("Alzheimer disease"))

    def parse(self, xml):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.xml.gz"
            with gzip.open(path, "wt") as handle:
                handle.write(xml)
            return parse_sections(path)

    def test_nested_sections_keep_parent_context(self):
        result = self.parse('''<document xmlns="urn:hl7-org:v3"><component><section>
          <code code="34067-9"/><title>Indications</title>
          <component><section><title>Population</title><text>Treat condition A.</text></section></component>
          </section></component><component><section><code code="43685-7"/><title>Warnings</title>
          <component><section><title>Cardiac effects</title><text>Condition B risk.</text></section></component>
          </section></component></document>''')
        self.assertEqual([r["group"] for r in result if r["text"]], ["indication", "safety"])

    def test_indication_heading_without_body_is_retained(self):
        result = self.parse('''<document xmlns="urn:hl7-org:v3"><section>
          <code code="34067-9"/><title>Indications</title>
          <component><section><title>Retinopathy of Prematurity</title></section></component>
          </section></document>''')
        self.assertEqual(result[-1]["group"], "indication")
        self.assertIn("Retinopathy of Prematurity", result[-1]["title"])

    def test_warning_is_not_indication_and_other_text_stays_other(self):
        result = self.parse('''<document xmlns="urn:hl7-org:v3">
          <section><code code="34071-1"/><title>Warnings</title><text>Heart failure.</text></section>
          <section><title>Clinical studies</title><text>Heart failure.</text></section>
          </document>''')
        self.assertEqual([r["group"] for r in result], ["safety", "other"])

    def test_known_naproxen_xml(self):
        source = Path(__file__).resolve().parent.parent / "04-parser-investigation/fixtures/naproxen.xml"
        result = self.parse(source.read_text())
        self.assertTrue(any("heart failure" in normalized(s["text"]) and s["group"] == "safety" for s in result))
        self.assertFalse(any("heart failure" in normalized(s["text"]) and s["group"] == "indication" for s in result))
        self.assertTrue(any("toothache" in normalized(s["text"]) and s["group"] == "indication" for s in result))


if __name__ == "__main__":
    unittest.main()
