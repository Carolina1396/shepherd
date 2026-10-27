"""Scientific protocol checks for the larger candidate-pool sampler."""
import copy
import unittest
import numpy as np
from chemical_finetune.sampling import NegativeSampler


class SamplingTests(unittest.TestCase):
    def test_holdouts_do_not_affect_negatives(self):
        labels = [dict(drug_index=h, disease_index=9, split=s) for h,s in
                  [(10,'visible'), (20,'visible'), (30,'validation'), (40,'test')]]
        candidates = [{'index':h} for h in [10,20,30,40,50]]
        sampler = NegativeSampler(labels, candidates)
        other = NegativeSampler(labels[:2], candidates)
        a = sampler.sample(9, 256, np.random.default_rng(17))
        b = other.sample(9, 256, np.random.default_rng(17))
        np.testing.assert_array_equal(a, b)
        self.assertEqual(set(a), {30,40,50})
        self.assertEqual(len(sampler.train), 2)

    def test_rng_state_restores_exact_draw_sequence(self):
        sampler = NegativeSampler([dict(drug_index=1,disease_index=9,split='visible')],
                                  [{'index':h} for h in range(5)])
        rng = np.random.default_rng(1024)
        sampler.sample(9, 256, rng)
        state = copy.deepcopy(rng.bit_generator.state)
        expected = sampler.sample(9, 256, rng)
        resumed = np.random.default_rng()
        resumed.bit_generator.state = state
        np.testing.assert_array_equal(expected, sampler.sample(9, 256, resumed))

    def test_no_negative_candidate_fails_instead_of_looping(self):
        with self.assertRaises(ValueError):
            NegativeSampler([dict(drug_index=1,disease_index=9,split='visible')],
                            [{'index':1}])


if __name__ == '__main__':
    unittest.main()
