import unittest
from prepare import category, expected_prefixes, signature


class PathTests(unittest.TestCase):
    def test_direction_and_intermediate_answers(self):
        nodes = [101, 202, 303, 404]
        edges = [(1, 9, 0), (1, 8, 2), (3, 7, 2)]
        prefixes = expected_prefixes(nodes, edges, {202, 404, 999})
        self.assertEqual([(n, len(e)) for n, _, e in prefixes], [(202, 1), (404, 3)])
        self.assertEqual(signature(nodes, edges, {101: 'Disease', 202: 'Chemical', 303: 'Gene', 404: 'Chemical'},
                                   {9: 'biolink:applied_to_treat', 8: 'biolink:affects', 7: 'biolink:affects'}),
                         'Disease <-[applied_to_treat]- Chemical -[affects]-> Gene <-[affects]- Chemical')

    def test_category_ancestors_do_not_hide_gene(self):
        self.assertEqual(category(['biolink:NamedThing', 'biolink:BiologicalEntity', 'biolink:Gene']), 'Gene')
        self.assertEqual(category(['biolink:Drug', 'biolink:ChemicalEntity']), 'ChemicalEntity')
        self.assertEqual(category([]), 'Other')


if __name__ == '__main__':
    unittest.main()
