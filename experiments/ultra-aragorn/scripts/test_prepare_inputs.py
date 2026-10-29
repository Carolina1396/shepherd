"""Regression checks for identity merging and contradictory benchmark judgments."""
import unittest
from prepare_inputs import group_labels


def row(identifier, label, qid='0', asset='a'):
    return dict(output_id=identifier, expected_output=label, qid=qid,
                asset_id=asset, output_name=identifier)


class LabelPreparationTests(unittest.TestCase):
    def test_alias_duplicates_merge_but_different_queries_stay_separate(self):
        mapping = {key: {'id': {'identifier': 'canonical'}} for key in ['TEST:A', 'TEST:B']}
        result = group_labels([row('TEST:A', 'TopAnswer'), row('TEST:B', 'TopAnswer', asset='b'),
                               row('TEST:A', 'NeverShow', qid='1')], mapping)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['source_asset_ids'], ['a', 'b'])
        self.assertEqual(result[0]['expected_output'], 'TopAnswer')
        self.assertEqual(result[1]['expected_output'], 'NeverShow')

    def test_conflicting_alias_labels_are_not_silently_selected(self):
        mapping = {key: {'id': {'identifier': 'canonical'}} for key in ['TEST:A', 'TEST:B']}
        result, = group_labels([row('TEST:A', 'TopAnswer'), row('TEST:B', 'NeverShow')], mapping)
        self.assertTrue(result['conflict'])
        self.assertIsNone(result['expected_output'])

    def test_unresolved_ids_are_preserved_separately(self):
        result = group_labels([row('TEST:A', 'TopAnswer'), row('TEST:B', 'NeverShow')], {'TEST:A': None, 'TEST:B': None})
        self.assertEqual(len(result), 2)
        self.assertEqual({r['preferred_id'] for r in result}, {'TEST:A', 'TEST:B'})
        self.assertTrue(all(r['normalization_status'] == 'unresolved' for r in result))

    def test_missing_identifier_suffix_cannot_merge_different_assets(self):
        result = group_labels([row('PUBCHEM.COMPOUND:', 'NeverShow', asset='a'),
                               row('PUBCHEM.COMPOUND:', 'NeverShow', asset='b')],
                              {'PUBCHEM.COMPOUND:': None})
        self.assertEqual(len(result), 2)
        self.assertTrue(all(r['malformed_id'] for r in result))


if __name__ == '__main__':
    unittest.main()
