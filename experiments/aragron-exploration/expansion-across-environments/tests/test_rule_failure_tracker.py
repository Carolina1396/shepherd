"""Integrity checks for the systematic rule-failure investigation tracker."""
import csv
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
TRACKER = ROOT / 'followups/rule-failure-analysis'
EXPECTED = {1, 2, 3, 4, 5, 7, 8, 9, 12, 13, 16}


class RuleFailureTrackerTests(unittest.TestCase):
    def test_each_problematic_rule_is_tracked_once(self):
        with (TRACKER / 'status.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        rules = [int(row['rule']) for row in rows]
        self.assertEqual(set(rules), EXPECTED)
        self.assertEqual(len(rules), len(EXPECTED))

    def test_each_status_points_to_an_investigation_readme(self):
        with (TRACKER / 'status.csv').open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            state_directory = 'not-tested' if row['followup_state'] == 'not_tested' else 'tested'
            readme = TRACKER / state_directory / row['shared_investigation'] / 'README.md'
            self.assertTrue(readme.exists(), f"Missing tracker README for rule {row['rule']}: {readme}")


if __name__ == '__main__':
    unittest.main()
