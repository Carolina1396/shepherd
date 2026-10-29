import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from run_cohort import aggregate, process


class CohortTests(unittest.TestCase):
    def test_fresh_query_zero_uses_live_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def fake_run(script, argv, log, **kwargs):
                self.assertEqual(script, 'retrieve.py')
                self.assertEqual(argv[argv.index('--qid')+1], 0)
                output=Path(argv[argv.index('--output')+1])
                self.assertEqual(output.parent, root/'query_000')
                output.mkdir()
                (output/'inspection.json').write_text(json.dumps(dict(
                    reference_issues=[], candidates=0, problem_logs=[])))
            with patch('run_cohort.run', side_effect=fake_run) as run:
                result=process(0,root)
            self.assertEqual(result['status'],'empty_retrieval')
            run.assert_called_once()

    def test_failure_is_counted_separately_from_missing_positive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);q=root/'query_001';q.mkdir();comparison=q/'comparison';comparison.mkdir()
            (q/'status.json').write_text(json.dumps(dict(qid=1,status='complete',comparison=str(comparison))))
            labels=[dict(qid=1,preferred_id=i,expected_output='TopAnswer',evaluation_status='eligible',
                         ranks={'ultra':u,'aragorn':a}) for i,u,a in [('A',1,2),('B',None,None)]]
            (comparison/'label_matches.json').write_text(json.dumps(labels))
            (comparison/'comparison.csv').write_text('preferred_id,ultra_rank,aragorn_rank\nA,1,2\n')
            failed=root/'query_002';failed.mkdir();(failed/'status.json').write_text(json.dumps(dict(qid=2,status='failed')))
            report=aggregate(root,[1,2,3])
            self.assertEqual(report['status_counts'],{'complete':1,'failed':1,'pending':1})
            self.assertEqual(report['metrics']['ultra']['answer_mrr'],0.5)
            self.assertEqual(report['metrics']['aragorn']['answer_mrr'],0.25)
            self.assertFalse(report['all_queries_processed'])


if __name__=='__main__':unittest.main()
