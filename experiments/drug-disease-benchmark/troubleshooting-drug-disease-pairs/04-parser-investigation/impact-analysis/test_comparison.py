import tempfile
from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

from analyze import PARSER, cut_safety, extract_text


class ComparisonTest(unittest.TestCase):
    def test_original_and_comparison_inputs(self):
        from loguru import logger
        logger.disable("dakp_pipeline")
        for drug, legitimate, warning, nested in [
            ("naproxen", "fever", "heart failure", True),
            ("donepezil", "alzheimer", "convulsion", False),
        ]:
            with self.subTest(drug=drug), tempfile.TemporaryDirectory() as folder:
                source = PARSER / "fixtures" / f"{drug}.xml"
                root = ET.parse(source).getroot()
                original_xml = ET.tostring(root)
                comparison, removed = cut_safety(root)
                self.assertEqual(ET.tostring(root), original_xml, "Original XML tree must remain intact")
                self.assertEqual(bool(removed), nested)
                folder = Path(folder)
                altered = folder / "comparison.xml"
                ET.ElementTree(comparison).write(altered, encoding="utf-8", xml_declaration=True)
                before = extract_text(source, folder / "original").lower()
                after = extract_text(altered, folder / "comparison").lower()
                self.assertEqual(warning in before, nested)
                self.assertNotIn(warning, after)
                self.assertIn(legitimate, before)
                self.assertIn(legitimate, after)
                if not nested:
                    self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
