import unittest
import numpy as np
from prepare_ablation import removal_mask


class AblationTests(unittest.TestCase):
    def test_remove_both_directions_but_preserve_indications_and_other_categories(self):
        categories = ['ChemicalSubstance', 'Disease', 'Pathway', 'ChemicalSubstance']
        triples = np.array([[0, 1, 1], [1, 2, 0], [0, 0, 1], [1, 0, 0],
                            [0, 1, 2], [2, 1, 1], [0, 1, 3], [0, 0, 2]])
        self.assertEqual(removal_mask(triples, categories, 0).tolist(),
                         [True, True, False, False, False, False, False, False])


if __name__ == '__main__':
    unittest.main()
