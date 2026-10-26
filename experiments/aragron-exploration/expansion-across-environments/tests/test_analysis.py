"""Tests for distinctions that could otherwise produce misleading comparisons."""
import copy
import json
import tempfile
from pathlib import Path
import unittest
import sys

EXPERIMENT_ROOT = Path(__file__).resolve().parent.parent
ARAGORN_EXPLORATION_ROOT = EXPERIMENT_ROOT.parent
sys.path.insert(0, str(EXPERIMENT_ROOT / 'scripts'))
from analyze import analyze_case, audit_results, callback_outcome, expected_graphs, graph_key, parse_callbacks


class EvidenceTests(unittest.TestCase):
    def test_version_specific_logging_preserves_query(self):
        from run import make_request
        config = {'workflow': [{'id': 'aragorn.lookup'}], 'parameters': {'log_level': 'DEBUG'}}
        target = {'id': 'MONDO:0008233'}
        modern = make_request(config, target, '2.0.0')
        legacy = make_request(config, target, '1.5.0')
        self.assertEqual(legacy.pop('log_level'), 'DEBUG')
        self.assertEqual(modern, legacy)
        self.assertNotIn('log_level', config)

    def test_trapi_qualifier_formats_preserve_direction_and_value(self):
        graph = {'nodes': {'a': {}, 'b': {}}, 'edges': {'e': {'subject': 'a', 'object': 'b',
                 'predicates': ['biolink:affects'], 'qualifier_constraints': [{'qualifier_set': [
                     {'qualifier_type_id': 'biolink:object_direction_qualifier', 'qualifier_value': 'increased'}]}]}}}
        modern = copy.deepcopy(graph)
        modern['edges']['e'].pop('qualifier_constraints')
        modern['edges']['e']['constraints'] = {'qualifiers': [{'biolink:object_direction_qualifier': 'increased'}]}
        self.assertEqual(graph_key(graph), graph_key(modern))
        modern['edges']['e']['constraints']['qualifiers'][0]['biolink:object_direction_qualifier'] = 'decreased'
        self.assertNotEqual(graph_key(graph), graph_key(modern))
        modern = copy.deepcopy(graph)
        modern['edges']['e'].update(subject='b', object='a')
        self.assertNotEqual(graph_key(graph), graph_key(modern))

    def test_empty_error_timeout_and_missing_are_distinct(self):
        row = {'result_count': 0, 'callback_received': True, 'warnings_errors': []}
        self.assertEqual(callback_outcome(row), 'empty_callback_no_error_logged')
        self.assertEqual(callback_outcome(dict(row, warnings_errors=['MetaEdges could not be found'])), 'unsupported_pattern')
        self.assertEqual(callback_outcome(dict(row, warnings_errors=['Timeout reached'])), 'incomplete_or_timeout')
        self.assertEqual(callback_outcome(dict(row, warnings_errors=['Failed'], has_error=True)), 'backend_error')
        self.assertEqual(callback_outcome({'warnings_errors': []}), 'unknown_no_callback')
        self.assertIsNone(audit_results({})['final_result_count'])

    def test_bindings_match_across_trapi_versions_and_validate_references(self):
        message = {'knowledge_graph': {'nodes': {'C:1': {}, 'D:1': {}}, 'edges': {
            'edge': {'subject': 'C:1', 'object': 'D:1', 'sources': []}}}, 'results': [{
                'node_bindings': {'drug': [{'id': 'C:1'}], 'disease': [{'id': 'D:1'}]},
                'analyses': [{'edge_bindings': {'e': [{'id': 'edge'}]}}]}]}
        modern = copy.deepcopy(message)
        for key, bindings in modern['results'][0]['node_bindings'].items():
            modern['results'][0]['node_bindings'][key] = {'ids': [b['id'] for b in bindings]}
        modern['results'][0]['analyses'][0]['edge_bindings']['e'] = {'ids': ['edge']}
        self.assertEqual(audit_results({'message': message}), audit_results({'message': modern}))
        del modern['knowledge_graph']['edges']['edge']
        self.assertTrue(audit_results({'message': modern})['integrity_errors'])

    def test_unknown_graph_not_misattributed(self):
        expected = {0: {'nodes': {'a': {}, 'b': {}}, 'edges': {'e': {'subject': 'a', 'object': 'b'}}}}
        graph = copy.deepcopy(expected[0]); graph['edges']['e']['object'] = 'a'
        logs = [{'message': '[abc] Got back 0 results.', 'level': 'DEBUG'},
                {'message': f'[abc] for query graph: {graph!r}', 'level': 'DEBUG'}]
        rows, errors = parse_callbacks(logs, expected)
        self.assertIsNone(rows[0]['rule'])
        self.assertFalse(errors)

    def test_top_level_failure_is_not_a_complete_answer_comparison(self):
        path = ARAGORN_EXPLORATION_ROOT / 'output/aragorn-lookup/run_001'
        if not path.exists():
            self.skipTest('Optional historical response fixture not present')
        response = json.loads((path / 'response.json').read_text())
        response['status'] = 'Error'
        rules = json.loads((path / 'release-rules.json').read_text())['{"predicate": "biolink:treats"}']
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            (directory / 'request.json').write_bytes((path / 'request.json').read_bytes())
            (directory / 'response.json').write_text(json.dumps(response))
            (directory / 'status.json').write_text(json.dumps({'status': 'Completed'}))
            (directory / 'submission.json').write_text(json.dumps({'state': 'response_received', 'http_status': 200}))
            row = analyze_case({'name': 'development', 'base_url': 'https://example.invalid'},
                               {'id': 'MONDO:0008233', 'name': 'test'}, directory, rules, 1)
            self.assertTrue(row['complete_callback_observation'])
            self.assertTrue(row['response_query_matches_request'])
            self.assertEqual(row['unique_chemical_count'], 83)
            self.assertFalse(row['complete_for_answer_comparison'])

    def test_cached_real_development_response(self):
        path = ARAGORN_EXPLORATION_ROOT / 'output/aragorn-lookup/run_001'
        if not path.exists():
            self.skipTest('Optional historical response fixture not present')
        response = json.loads((path / 'response.json').read_text())
        request = json.loads((path / 'request.json').read_text())
        rules = json.loads((path / 'release-rules.json').read_text())['{"predicate": "biolink:treats"}']
        rows, errors = parse_callbacks(response['logs'], expected_graphs(request, rules))
        self.assertFalse(errors)
        self.assertEqual(sorted(r['rule'] for r in rows), list(range(19)))
        self.assertEqual(sum(r.get('callback_received', False) for r in rows), 19)
        self.assertEqual(audit_results(response)['unique_chemical_count'], 83)
        self.assertFalse(audit_results(response)['integrity_errors'])


if __name__ == '__main__':
    unittest.main()
