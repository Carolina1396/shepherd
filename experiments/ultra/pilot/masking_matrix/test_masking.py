import unittest
import numpy as np
from common import CONDITIONS, edge_groups, keep_edges, independent_keep


class MaskingTests(unittest.TestCase):
    def setUp(self):
        self.labels = [dict(drug_index=0,disease_index=1,split='visible'),
                       dict(drug_index=2,disease_index=3,split='validation'),
                       dict(drug_index=4,disease_index=5,split='test')]
        self.triples = np.array([[0,0,1],[1,0,0],[0,1,1],[1,2,0],
                                 [2,0,3],[3,0,2],[2,1,3],[3,2,2],
                                 [4,0,5],[5,0,4],[4,1,5],[5,2,4],
                                 [0,0,3],[3,1,0],[1,2,5]])

    def test_all_eight_conditions_and_both_directions(self):
        groups = edge_groups(self.triples,self.labels,6)
        for row,(vt,vo,ho) in CONDITIONS.items():
            with self.subTest(row=row):
                expected = [vt,vt,vo,vo,False,False,ho,ho,False,False,ho,ho,True,True,True]
                keep = keep_edges(groups,self.triples[:,1]==0,row)
                self.assertEqual(keep.tolist(),expected)
                self.assertEqual(independent_keep(self.triples,self.labels,6,0,row).tolist(),expected)

    def test_reversed_label_cannot_cross_splits(self):
        labels = [dict(drug_index=0,disease_index=1,split='visible'),
                  dict(drug_index=1,disease_index=0,split='test')]
        with self.assertRaises(AssertionError):
            edge_groups(self.triples,labels,6)


if __name__=='__main__':
    unittest.main()
