import csv
import json
from pathlib import Path
import pickle
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import lmdb
import msgpack
import numpy as np

import workflow as w


class RulesTest(unittest.TestCase):
    def test_path_shapes_and_canonicalization(self):
        a = w.path_rule('?a r0 ?b ?b r1 ?c => ?a benchmark:treats ?c')
        b = w.path_rule('?y r1 ?z ?x r0 ?y => ?x benchmark:treats ?z')
        self.assertEqual(a, b)
        self.assertEqual(len(w.path_rule('?a r0 ?b ?c r1 ?b ?c r2 ?d => ?a benchmark:treats ?d')), 3)
        for bad in (
            '?a r0 ?b => ?a benchmark:treats ?b',
            '?a r0 ?b ?b r1 ?c ?a r2 ?c => ?a benchmark:treats ?c',
            '?a r0 ?b ?b r1 ?c ?b r2 ?d => ?a benchmark:treats ?c',
            '?a r0 ?b ?b benchmark:treats ?c => ?a benchmark:treats ?c',
            '?a r0 ?a ?a r1 ?c => ?a benchmark:treats ?c',
            '?a r0 n1 n1 r1 ?c => ?a benchmark:treats ?c',
        ):
            self.assertIsNone(w.path_rule(bad), bad)

    def test_qualifiers(self):
        a = {'qualifier_type_id': 'direction', 'qualifier_value': 'increased'}
        b = {'qualifier_type_id': 'aspect', 'qualifier_value': 'activity'}
        self.assertEqual(w.relation_key('p', [a, b, a]), w.relation_key('p', [b, a]))
        self.assertNotEqual(w.relation_key('p', [a]), w.relation_key('p', [dict(a, qualifier_value='decreased')]))
        self.assertNotEqual(w.relation_key('p', []), w.relation_key('p', [a]))

    def test_split_overlap(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name in ('train', 'val', 'test'):
                (p / f'{name}.csv').write_text('drug_id,disease_id\nC,D\n')
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                w.load_splits(p)

    def test_walks_both_lengths_and_limits(self):
        edges = [(0, 'r0', 1), (1, 'r1', 3), (1, 'r2', 2), (2, 'r1', 3),
                 (4, 'r0', 1), (3, 'r0', 1)]

        def neighbors(node, step, tick):
            for s, r, o in edges:
                tick(1)
                if o == node and r == step['relation']:
                    yield s

        for text in ('?a r0 ?b ?b r1 ?c => ?a benchmark:treats ?c',
                     '?a r0 ?b ?b r2 ?c ?c r1 ?d => ?a benchmark:treats ?d'):
            rule = {'steps': w.path_rule(text)}
            result = w.enumerate_path(rule, 3, neighbors, lambda n: n in (0, 4))
            self.assertEqual(result['candidates'], [0, 4])
            self.assertEqual(result['state'], 'complete')
            self.assertEqual(w.enumerate_path(rule, 3, neighbors, lambda n: True, max_edges=1)['state'], 'edge_limit')
            self.assertEqual(w.enumerate_path(rule, 3, neighbors, lambda n: True, seconds=0)['state'], 'time_limit')
            self.assertEqual(w.enumerate_path(rule, 3, neighbors, lambda n: n in (0, 4), max_candidates=1)['state'], 'candidate_limit')
            for path in result['witnesses'].values():
                self.assertEqual(len(path), len(set(path)))

    def test_process_timeout_failure_and_stream_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            result = w.bounded_process([sys.executable, '-u', '-c', 'import time; print("saved"); time.sleep(30)'],
                                       p / 'out', p / 'err', .2)
            self.assertEqual(result['state'], 'timeout')
            self.assertIn('saved', (p / 'out').read_text())
            result = w.bounded_process([sys.executable, '-c', 'raise RuntimeError("fixture")'],
                                       p / 'out', p / 'err', 3)
            self.assertEqual(result['state'], 'failed')


def fixture(root):
    graph = root / 'graph'
    graph.mkdir()
    splits = root / 'splits'
    splits.mkdir()
    # Three chemical/disease pairs sharing a gene and process. Duplicate source
    # records and differently ordered equivalent qualifiers must collapse.
    cats = ['ChemicalEntity'] * 3 + ['Disease'] * 3 + ['Gene', 'BiologicalProcess']
    edges = [(c, 0, 6, q) for c in range(3) for q in ((0, 1) if c < 2 else (3, 3))]
    edges += [(6, 1, d, 2) for d in range(3, 6)] + [(6, 2, 7, 2)]
    edges += [(7, 1, d, 2) for d in range(3, 6)]
    edges.sort()
    meta = {'num_nodes': 8, 'predicate_to_idx': {'biolink:affects': 0, 'biolink:associated_with': 1,
                                               'biolink:participates_in': 2}}
    q1 = {'qualifier_type_id': 'biolink:object_direction_qualifier', 'qualifier_value': 'decreased'}
    q2 = {'qualifier_type_id': 'biolink:object_aspect_qualifier', 'qualifier_value': 'activity'}
    with (graph / 'metadata.pkl').open('wb') as f:
        pickle.dump(meta, f)
    with (graph / 'edge_property_pools.pkl').open('wb') as f:
        pickle.dump({'quals_pool': [[q1, q2], [q2, q1], [],
                                   [dict(q1, qualifier_value='increased'), q2]]}, f)
    def offsets(nodes):
        return np.r_[0, np.cumsum(np.bincount(nodes, minlength=8))]
    rev = sorted(range(len(edges)), key=lambda i: (edges[i][2], edges[i][1], edges[i][0]))
    arrays = {'fwd_offsets': offsets([s for s, _, _, _ in edges]),
              'fwd_targets': [o for _, _, o, _ in edges], 'fwd_predicates': [r for _, r, _, _ in edges],
              'edge_quals_idx': [q for _, _, _, q in edges],
              'rev_offsets': offsets([edges[i][2] for i in rev]),
              'rev_sources': [edges[i][0] for i in rev], 'rev_predicates': [edges[i][1] for i in rev],
              'rev_to_fwd': rev}
    for name, arr in arrays.items():
        np.save(graph / (name + '.npy'), np.array(arr, dtype=np.int64))
    env = lmdb.open(str(graph / 'node_store.lmdb'), map_size=2**20, max_dbs=3)
    ids, names, props = [env.open_db(n) for n in (b'id_to_idx', b'idx_to_id', b'properties')]
    with env.begin(write=True) as tx:
        for i, cat in enumerate(cats):
            key = i.to_bytes(4, 'big')
            curie = f'FIX:{i}'.encode()
            tx.put(curie, key, db=ids)
            tx.put(key, curie, db=names)
            tx.put(key, msgpack.packb({'categories': ['biolink:' + cat]}), db=props)
    env.close()
    for i, split in enumerate(('train', 'val', 'test')):
        (splits / f'{split}.csv').write_text(f'drug_id,disease_id\nFIX:{i},FIX:{i+3}\n')
    return graph, splits


class IntegrationTest(unittest.TestCase):
    @unittest.skipUnless((w.HERE / 'vendor/amie.jar').exists(), 'Download pinned jar')
    def test_memory_preflight_never_starts_mining(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            graph, splits = fixture(p)
            exported = p / 'export'
            w.export(graph, splits, exported)
            memory = SimpleNamespace(total=32 * 1024**3, available=9 * 1024**3)
            with patch.object(w.psutil, 'virtual_memory', return_value=memory), \
                    patch.object(w, 'bounded_process') as launch, patch('builtins.print'):
                w.mine(exported, p / 'mining', w.HERE / 'vendor/amie.jar')
            launch.assert_not_called()
            status = w.read(p / 'mining/manifest.json')
            self.assertEqual(status['state'], 'blocked_memory')
            self.assertEqual(status['heap_mib'], 16384)

    def test_export_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            graph, splits = fixture(p)
            exported = p / 'export'
            w.export(graph, splits, exported)
            manifest = w.read(exported / 'manifest.json')
            self.assertEqual(manifest['source_edges'] - manifest['evidence_triples'], 3)
            self.assertEqual((exported / 'train.tsv').read_text(), 'n0\tbenchmark:treats\tn3\n')
            self.assertNotIn('benchmark:treats', (exported / 'evidence.tsv').read_text())
            rels = w.read(exported / 'relations.json')
            rid = {r['predicate']: k for k, r in rels.items()
                   if not any(q.get('qualifier_value') == 'increased' for q in r['qualifiers'])}
            mined = p / 'mined'
            mined.mkdir()
            for length in (2, 3):
                run = mined / f'body-{length}'
                run.mkdir()
                body = f'?a {rid["biolink:affects"]} ?b '
                if length == 3:
                    body += f'?b {rid["biolink:participates_in"]} ?x ?x '
                else:
                    body += '?b '
                body += f'{rid["biolink:associated_with"]} ?c => ?a benchmark:treats ?c'
                log = run / 'stdout.txt'
                log.write_text('Rule\tPositive Examples\tStd Confidence\tPCA Confidence\n' + body + '\t12\t0.5\t0.5\n')
                rules, counts = w.parse_rules(log, length, rels)
                self.assertEqual(counts['retained_paths'], 1)
                w.save(run / 'rules.json', rules)
                w.save(run / 'manifest.json', {'rules_sha256': w.digest(run / 'rules.json')})
            w.save(mined / 'manifest.json', {'state': 'complete', 'export_manifest_sha256': w.digest(exported / 'manifest.json')})
            w.validate(exported, mined, p / 'validation')
            report = w.read(p / 'validation/report.json')
            self.assertEqual(report['state'], 'complete')
            self.assertEqual(report['unions']['combined']['pair_recovery'], 1)
            self.assertEqual(report['unions']['combined']['candidate_max'], 2)
            self.assertFalse(report['test_evaluated'])
            # Transfer to another machine must not require editing signed manifests.
            relocated_graph, relocated_splits = p / 'server-graph', p / 'server-splits'
            graph.rename(relocated_graph)
            splits.rename(relocated_splits)
            # Test labels are never opened by validation, even after relocation.
            (relocated_splits / 'test.csv').unlink()
            w.validate(exported, mined, p / 'relocated-validation', relocated_graph, relocated_splits)
            relocated = w.read(p / 'relocated-validation/report.json')
            self.assertEqual(relocated['unions'], report['unions'])
            with (relocated_graph / 'fwd_targets.npy').open('ab') as f:
                f.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'Graph changed'):
                w.validate(exported, mined, p / 'tampered-validation', relocated_graph, relocated_splits)

    @unittest.skipUnless((w.HERE / 'vendor/amie.jar').exists(), 'Download the pinned AMIE jar for smoke test')
    def test_actual_amie_mines_both_lengths(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            rels = {f'r{i}': {'predicate': f'fixture:p{i}', 'qualifiers': []} for i in range(3)}
            for length in (2, 3):
                run = p / str(length)
                run.mkdir()
                evidence, labels = [], []
                for i in range(12):
                    nodes = [f'n{i}_{j}' for j in range(length + 1)]
                    labels.append(f'{nodes[0]}\t{w.TARGET}\t{nodes[-1]}\n')
                    evidence.extend(f'{nodes[j]}\tr{j}\t{nodes[j+1]}\n' for j in range(length))
                (run / 'evidence.tsv').write_text(''.join(evidence))
                (run / 'train.tsv').write_text(''.join(labels))
                command = w.mining_command(w.HERE / 'vendor/amie.jar', run, length, 256)
                result = w.bounded_process(command, run / 'stdout', run / 'stderr', 30)
                self.assertEqual(result['state'], 'complete', (run / 'stderr').read_text())
                rules, counts = w.parse_rules(run / 'stdout', length, rels)
                self.assertGreater(len(rules), 0, (run / 'stdout').read_text())
                self.assertTrue(all(w.TARGET not in json.dumps(r['steps']) for r in rules))


if __name__ == '__main__':
    unittest.main()
