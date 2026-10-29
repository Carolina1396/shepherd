import unittest
from compare_rankers import label_metrics, rank_identities, score_map


class ComparisonTests(unittest.TestCase):
    def test_aliases_use_max_score_and_pessimistic_ties(self):
        norm={'A':{'id':{'identifier':'X'}},'B':{'id':{'identifier':'X'}},'C':{'id':{'identifier':'Y'}}}
        ranks=rank_identities({'A':1.,'B':2.,'C':2.},norm)
        self.assertEqual(len(ranks),2)
        self.assertEqual(ranks['X']['rank'],2)
        self.assertEqual(ranks['X']['score'],2.)

    def test_missing_answers_are_zero_but_flags_excluded(self):
        labels=[dict(preferred_id=i,expected_output='TopAnswer',evaluation_status=status)
                for i,status in [('A','eligible'),('B','eligible'),('C','flagged_source_label')]]
        metrics=label_metrics(labels,{'A':{'rank':2}})
        self.assertEqual(metrics['answer_mrr'],0.25)
        self.assertEqual(metrics['positive_retrieval_coverage'],0.5)
        self.assertEqual(metrics['flagged_labels'],1)
        self.assertIsNone(label_metrics([], {})['answer_mrr'])

    def test_multiple_analyses_and_missing_score(self):
        response={'message':{'results':[{'node_bindings':{'a':{'ids':['A']}},
            'analyses':[{'score':0.2},{'score':0.5}]}]}}
        self.assertEqual(score_map(response,'a'),{'A':0.5})
        response['message']['results'][0]['analyses']=[]
        with self.assertRaises(ValueError):score_map(response,'a')


if __name__=='__main__':unittest.main()
