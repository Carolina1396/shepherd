"""Run with the existing GPU environment; exercises unchanged ULTRA forward passes."""
import json
from pathlib import Path
import unittest
import numpy as np
import torch
from torch_geometric.data import Data
from evaluate import ROOT, local_graph, make_model, score, filtered_rank
from ultra import tasks


@unittest.skipUnless(torch.cuda.is_available(), 'GPU environment required')
class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(8)
        config=json.loads((ROOT/'output/full-graph-ultra/run_001/config.json').read_text())
        cls.model=make_model().cuda()
        cls.model.load_state_dict(torch.load(ROOT/config['checkpoint'],map_location='cpu')['model'])
        cls.model.eval()

    def test_compact_nodes_match_original_ids_and_preserve_isolated_candidates(self):
        edges=[[15,2,90],[90,3,700],[15,4,300]]
        candidates=np.array([700,300,950,999]); anchor=15
        compact,a,c=local_graph(edges,anchor,candidates,60)
        triples=np.array(edges); e=torch.from_numpy(triples[:,[0,2]].T.copy()); p=torch.from_numpy(triples[:,1].copy())
        expanded=Data(edge_index=torch.cat([e,e.flip(0)],1),edge_type=torch.cat([p,p+60]),num_nodes=1000,num_relations=120)
        expanded=tasks.build_relation_graph(expanded)
        compact_scores,_=score(self.model,compact.cuda(),a,c,2)
        expanded_scores,_=score(self.model,expanded.cuda(),anchor,candidates,2)
        self.assertTrue(np.allclose(compact_scores,expanded_scores,rtol=1e-5,atol=1e-5))
        self.assertEqual(compact.num_nodes,6)
        self.assertEqual(compact.num_edges,6)
        self.assertEqual(len(c),4)

    def test_empty_graph_keeps_all_candidates_and_pessimistic_ties(self):
        candidates=np.arange(1,5327)
        graph,a,c=local_graph([],0,candidates,60)
        scores,_=score(self.model,graph.cuda(),a,c,2)
        self.assertEqual(graph.num_nodes,5327)
        self.assertEqual(graph.num_edges,0)
        self.assertEqual(graph.relation_graph.num_edges,0)
        self.assertTrue(np.isfinite(scores).all())
        self.assertTrue(np.all(scores==scores[0]))
        self.assertEqual(filtered_rank(scores,0,{0,1,2}),5324)

    def test_empty_scores_match_native_kernel_with_disconnected_context(self):
        # An unrelated component cannot send messages to the anchor or candidates.
        # Its relation component also excludes the queried relation and inverse.
        candidates=np.array([1,2,3,4])
        empty,a,c=local_graph([],0,candidates,60)
        separate,b,d=local_graph([[100,3,101]],0,candidates,60)
        empty_scores,_=score(self.model,empty.cuda(),a,c,2)
        native_scores,_=score(self.model,separate.cuda(),b,d,2)
        self.assertTrue(np.allclose(empty_scores,native_scores,rtol=1e-5,atol=1e-5), (empty_scores,native_scores))

    def test_filtering_uses_candidate_order_and_retains_missing_answer(self):
        scores=np.array([0.8,0.1,0.8,0.1])
        self.assertEqual(filtered_rank(scores,1,{1,2}),3)
        self.assertEqual(filtered_rank(scores,0,{0,2}),1)


if __name__=='__main__':unittest.main()
