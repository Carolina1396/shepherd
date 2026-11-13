"""Small independent traversal/counting checks; no real graph required."""
import itertools
import unittest

import numpy as np

import analyze as a


class Fixture:
    # d=0, target=4; two-hop via 1, three-hop via 2 and 3.
    def __init__(self):
        self.node_class = np.array([0, 1, 0, 1, 2])
        self.chemical = {0}
        self.edges = [(0, 1, 10, 1), (0, 1, 10, 2), (0, 1, 10, 1),
                      (1, 4, 11, 0), (0, 2, 12, 0), (2, 3, 10, 1),
                      (3, 4, 11, 0), (0, 0, 12, 0), (1, 1, 10, 0)]

    def idx(self, s):
        return {'drug': 0, 'disease': 4}.get(s)

    def arrays(self, i):
        out = []
        for direction in (1, -1):
            rows = [(e[1] if direction == 1 else e[0], j)
                    for j, e in enumerate(self.edges) if e[0 if direction == 1 else 1] == i]
            out.append((np.array([n for n, j in rows], dtype=int),
                        np.array([j for n, j in rows], dtype=int), direction))
        return out

    def edge(self, j, direction):
        _, _, p, q = self.edges[j]
        return direction, p, q

    def adjacency(self, i):
        result = {}
        for ns, es, di in self.arrays(i):
            for n, e in zip(ns, es):
                if n != i:
                    result.setdefault(int(n), set()).add(self.edge(int(e), di))
        return result

    def degree(self, i):
        return sum(len(ns) for ns, _, _ in self.arrays(i))

    def volume(self, ns):
        return sum(self.degree(i) for i in ns)


class Tests(unittest.TestCase):
    def test_exact_counts_qualifiers_and_duplicate_sources(self):
        g = Fixture()
        row = {'drug_id': 'drug', 'disease_id': 'disease'}
        two = a.enumerate_pair(g, row, 2)
        self.assertEqual(two['state'], 'complete')
        self.assertEqual(two['node_sequences'], 1)
        self.assertEqual([len(t) for t in two['tables']], [1, 2])
        self.assertEqual(two['no_chemical_node_sequences'], 1)
        three = a.enumerate_pair(g, row, 3)
        self.assertEqual(three['state'], 'complete')
        self.assertEqual(three['node_sequences'], 1)
        self.assertEqual(three['no_chemical_node_sequences'], 0)

    def test_matches_independent_brute_force_both_endpoint_orders(self):
        g = Fixture()
        for d, z in [(0, 4), (4, 0)]:
            for h in (2, 3):
                expected = set()
                for mids in itertools.product(range(5), repeat=h-1):
                    ns = (d,) + mids + (z,)
                    if all(v != w and w in g.adjacency(v) for v, w in zip(ns, ns[1:])):
                        expected.add(ns)
                budget = {'start': a.time.monotonic(), 'edges': 0}
                actual = list(a.walks(g, d, z, h, budget, a.LIMITS[h]))
                self.assertEqual({ns for ns, edges in actual}, expected)
                for ns, edges in actual:
                    for v, w, available in zip(ns, ns[1:], edges):
                        self.assertEqual(available, g.adjacency(v)[w])

    def test_missing_endpoint_and_limit_are_not_zero_path_completions(self):
        g = Fixture()
        row = {'drug_id': 'absent', 'disease_id': 'disease'}
        self.assertEqual(a.enumerate_pair(g, row, 2)['state'], 'missing_endpoint')
        saved = a.LIMITS[3]
        try:
            a.LIMITS[3] = dict(saved, walks=0)
            result = a.enumerate_pair(g, {'drug_id': 'drug', 'disease_id': 'disease'}, 3)
            self.assertEqual(result['state'], 'walk_limit')
            self.assertEqual(result['tables'], [[], []])
        finally:
            a.LIMITS[3] = saved


if __name__ == '__main__':
    unittest.main()
