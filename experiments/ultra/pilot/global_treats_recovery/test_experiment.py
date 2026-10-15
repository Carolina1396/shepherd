import random
from pathlib import Path
import tempfile
import unittest

import experiment as e


class GlobalTreatsTests(unittest.TestCase):
    def graph(self):
        # Includes duplicate evidence, reverse-only treats, an out-of-scope target,
        # and a chemical that becomes isolated after masking.
        edges = [(0, 1), (0, 1), (1, 0), (0, 1), (2, 1), (1, 3), (4, 1), (0, 5), (6, 1), (0, 2)]
        predicates = [0, 0, 0, 1, 0, 0, 0, 0, 0, 2]
        cats = ['Drug', 'Disease', 'ChemicalEntity', 'SmallMolecule', 'Protein', 'PhenotypicFeature', 'Drug']
        return e.CSRGraph(7, edges, predicates, {f'N:{i}': i for i in range(7)},
            {'biolink:treats': 0, 'biolink:in_clinical_trials_for': 1, 'biolink:related_to': 2},
            node_properties={i: {'categories': ['biolink:' + c]} for i, c in enumerate(cats)})

    def prepare(self):
        graph = self.graph()
        chemical, disease = e.categories(graph)
        targets, hidden, removed = e.target_inventory(graph, chemical, disease)
        masked = e.mask_graph(graph, hidden, 'treats_only')
        return graph, masked, chemical, disease, targets, removed

    def test_all_labels_and_exact_global_mask(self):
        graph, masked, chemical, disease, targets, removed = self.prepare()
        self.assertEqual(targets, {(0, 1), (2, 1), (6, 1)})
        self.assertEqual(removed, 6)
        report = e.verify_mask(graph, masked, chemical, disease, removed)
        self.assertEqual(report['remaining_scoped_treats_records'], 0)
        self.assertIsNone(masked._find_edge_index(1, 3, 0))  # reverse-only edge
        self.assertIsNotNone(masked._find_edge_index(0, 1, 1))  # related treatment predicate
        self.assertIsNotNone(masked._find_edge_index(4, 1, 0))  # Protein, out of scope
        self.assertIsNotNone(masked._find_edge_index(0, 5, 0))  # not Disease
        self.assertEqual(len(graph.fwd_targets), 10)  # source remains intact

    def test_isolated_answers_stay_in_denominator_and_sampler_uses_mask(self):
        _, masked, chemical, disease, targets, _ = self.prepare()
        edges, _, _ = e.sample(e.GraphSampler(masked, random.Random(1)), 1, 3, 1000, 3000, 1)
        e.check_edges(edges, masked, chemical, disease, 3000)
        result = e.measure(edges, 1, {0, 2, 3, 6}, {h for h, t in targets}, set())
        self.assertEqual(result['answer_pairs'], 3)
        self.assertNotIn(6, result['recovered_answer_indices'])
        self.assertLess(result['answer_coverage'], 1)
        empty = e.measure(set(), 1, {0, 2, 3, 6}, {h for h, t in targets}, set())
        self.assertEqual(empty['answer_pairs'], 3)
        self.assertEqual(empty['answers_reached'], 0)

    def test_verifier_rejects_mask_that_keeps_one_training_like_pair(self):
        graph, _, chemical, disease, _, removed = self.prepare()
        incomplete = e.mask_graph(graph, {(0, 1)}, 'treats_only')
        with self.assertRaises(AssertionError):
            e.verify_mask(graph, incomplete, chemical, disease, removed)

    def test_summary_keeps_misses_and_distinguishes_partial_from_complete(self):
        graph, masked, chemical, disease, _, removed = self.prepare()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            settings = {'edge_cap': 3000}
            e.save(out / 'settings.json', settings)
            e.save(out / 'mask_verification.json', e.verify_mask(graph, masked, chemical, disease, removed))
            args = (out, [(0, 'N:1', 1)], {1: {0, 2, 6}}, {0, 2, 3, 6}, settings, masked, chemical, disease)
            partial = e.summarize(*args)
            self.assertFalse(partial['complete'])
            self.assertEqual(partial['expected_pairs'], 3)
            self.assertEqual(partial['evaluated_pairs'], 0)
            directory = out / 'diseases/00000'
            directory.mkdir(parents=True)
            e.save(directory / 'graph.json', {'disease': 'N:1', 'anchor': 1,
                'gandalf_walks': {'edges': [[0, 1, 1]]},
                'aragorn_rules': {'edges': [], 'bound': [], 'retained_matches_by_rule': {}}})
            e.save(directory / 'rules.json', [])
            results = {method: dict(e.measure(edges, 1, {0, 2, 3, 6}, {0, 2, 6}, set()), seconds=0)
                       for method, edges in [('gandalf_walks', {(0, 1, 1)}), ('aragorn_rules', set())]}
            e.save(directory / 'report.json', {'disease': 'N:1', 'anchor': 1,
                'results': results, 'completed_walks': 0,
                'artifact_sha256': {name: e.digest(directory / name) for name in ('graph.json', 'rules.json')}})
            summary = e.summarize(*args)
            self.assertTrue(summary['complete'])
            self.assertEqual(summary['evaluated_pairs'], 3)
            self.assertEqual(summary['results']['gandalf_walks']['answer_coverage'], 1/3)
            self.assertEqual(summary['results']['aragorn_rules']['answer_pairs'], 3)
            self.assertEqual(summary['results']['aragorn_rules']['empty_graphs'], 1)
            self.assertEqual(summary['paired_recovery'], {'gandalf_only': 1, 'neither': 2})


if __name__ == '__main__':
    unittest.main()
