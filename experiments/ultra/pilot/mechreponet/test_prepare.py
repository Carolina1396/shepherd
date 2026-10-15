import unittest
import numpy as np
from prepare import eligible_pair, split_pairs, hidden_pair_mask


class PreparationTests(unittest.TestCase):
    def test_only_source_chemical_disease_indications_are_targets(self):
        categories={'C':'ChemicalSubstance','D':'Disease','P':'Pathway','A':'AnatomicalEntity'}
        self.assertTrue(eligible_pair('C','indication','D',categories))
        self.assertFalse(eligible_pair('C','indication','P',categories))
        self.assertFalse(eligible_pair('A','indication','D',categories))
        self.assertFalse(eligible_pair('C','treats_CtD','D',categories))

    def test_all_direct_heldout_predicates_and_directions_removed(self):
        triples=np.array([[0,0,1],[1,0,0],[0,1,1],[2,0,1],[0,2,3]])
        mask=hidden_pair_mask(triples[:,0],triples[:,2],{(0,1)},4)
        self.assertEqual(mask.tolist(),[True,True,True,False,False])

    def test_split_is_disjoint_and_deterministic(self):
        pairs={(f'C:{i}',f'D:{i%4}') for i in range(100)}
        a=split_pairs(pairs,731);b=split_pairs(list(reversed(sorted(pairs))),731)
        self.assertEqual(a,b)
        self.assertEqual([sum(s==split for h,t,s in a) for split in ['visible','validation','test']],[80,10,10])
        self.assertEqual(len({(h,t) for h,t,s in a}),100)


if __name__=='__main__':unittest.main()
