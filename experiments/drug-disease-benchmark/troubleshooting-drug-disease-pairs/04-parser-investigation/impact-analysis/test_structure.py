import unittest
import gzip
import hashlib
import json
from pathlib import Path
from scan_structure import inspect_xml


class StructureTest(unittest.TestCase):
    def test_saved_structural_examples(self):
        folder = Path(__file__).resolve().parent / 'structure-examples'
        manifest = json.loads((folder / 'manifest.json').read_text())
        warning_labels = 0
        for entry in manifest:
            raw = gzip.decompress((folder / entry['file']).read_bytes())
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['xml_sha256'])
            _, _, hits = inspect_xml(raw)
            self.assertTrue(hits, entry['set_id'])
            warning_labels += any(h['warning_code'] for h in hits)
        self.assertEqual(len(manifest), 5)
        self.assertEqual(warning_labels, 2)

    def test_nested_and_sibling_warning_differ(self):
        for nested in [True, False]:
            warning = '<component><section><code code="34071-1"/><title>Warnings</title></section></component>'
            xml = '<document xmlns="urn:hl7-org:v3"><section><code code="34067-9"/><text>Uses</text>'
            xml += warning + '</section>' if nested else '</section>' + warning
            _, count, hits = inspect_xml((xml + '</document>').encode())
            self.assertEqual(count, 1)
            self.assertEqual(any(h['warning_code'] for h in hits), nested)

    def test_warning_heading_and_precaution_are_distinguished(self):
        xml = b'''<document xmlns="urn:hl7-org:v3"><section><code code="34067-9"/>
        <component><section><title>Warnings</title></section></component>
        <component><section><code code="42232-9"/><title>Precautions</title></section></component>
        </section></document>'''
        _, _, hits = inspect_xml(xml)
        self.assertEqual(len(hits), 2)
        self.assertFalse(any(h['warning_code'] for h in hits))
        self.assertEqual(sum(h['warning_heading'] for h in hits), 1)


if __name__ == '__main__':
    unittest.main()
