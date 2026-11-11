import unittest
from copy import deepcopy
from build_candidates import build
from evaluate import metrics
class Graph:
    def curie(self,n):return {0:'CHEBI:1',1:'NCBIGene:1',2:'MONDO:1'}[n]
    def node(self,n):return {'name':self.curie(n),'categories':['biolink:NamedThing']}
    def edge(self,n):return str(n),{'subject':self.curie(0 if n==3 else 1),'object':self.curie(1 if n==3 else 2),
        'predicate':'biolink:affects','sources':[{'resource_id':'infores:test','resource_role':'primary_knowledge_source'}],
        'qualifiers':[{'qualifier_type_id':'biolink:object_direction_qualifier','qualifier_value':'decreased'}]}
class PipelineTest(unittest.TestCase):
    def test_support_dedup_preserves_original_evidence(self):
        g=Graph();m=build(g,'MONDO:1',[{'paths':[[0,1,2,3,4]]},{'paths':[[0,1,2,3,4]]}])
        self.assertEqual(len(m['results']),1);self.assertEqual(len(m['auxiliary_graphs']),1)
        self.assertEqual(len(m['knowledge_graph']['edges']),3)
        for eid in ('3','4'):self.assertEqual(m['knowledge_graph']['edges'][eid],g.edge(int(eid))[1])
        result=m['results'][0];eid=result['analyses'][0]['edge_bindings']['e0']['ids'][0]
        support=m['knowledge_graph']['edges'][eid]['attributes'][0]['value']
        for aid in support:
            for edge in m['auxiliary_graphs'][aid]['edges']:self.assertIn(edge,m['knowledge_graph']['edges'])
    def test_macro_does_not_overweight_large_disease(self):
        rows=[{'disease':'A','rank':1,'rr':1,'recovered':True}]*3+[{'disease':'B','rank':None,'rr':0,'recovered':False}]
        m=metrics(rows);self.assertEqual(m['macro_hits_at_10'],0.5);self.assertEqual(m['pair_recovery'],0.75)

class ExecutorTest(unittest.TestCase):
    def test_qualifiers_filter_parallel_records_before_collapsing(self):
        import numpy as np
        from execute import Executor
        import json
        from pathlib import Path
        e=Executor.__new__(Executor)
        e.meta={'predicate_to_idx':{'biolink:affects':1,'biolink:associated_with':2}}
        e.fwd_offsets=np.array([0,2,3,3]);e.fwd_targets=np.array([1,1,2]);e.fwd_predicates=np.array([1,1,2])
        e.rev_offsets=np.array([0,0,2,3]);e.rev_sources=np.array([0,0,1]);e.rev_predicates=np.array([1,1,2]);e.rev_to_fwd=np.array([0,1,2])
        e.edge_quals_idx=np.array([0,1,2]);e.pools={'quals_pool':[
            [{'qualifier_type_id':'biolink:object_aspect_qualifier','qualifier_value':'activity'},{'qualifier_type_id':'biolink:object_direction_qualifier','qualifier_value':'decreased'}],
            [{'qualifier_type_id':'biolink:object_direction_qualifier','qualifier_value':'increased'}],[]]}
        e.drugs=np.array([True,False,False]);e.idx=lambda c:2;e.categories=lambda n:('biolink:Gene',)
        examples=json.loads(Path(__file__).with_name('templates.example.json').read_text())['templates']
        limits={'max_edges':100,'max_candidates':10,'max_paths':10,'seconds':10}
        self.assertEqual(len(e.lookup(examples[0],'D',limits)['paths']),2)
        self.assertEqual(e.lookup(examples[1],'D',limits)['paths'],[[0,1,2,0,2]])
        self.assertEqual(e.lookup(examples[2],'D',limits)['paths'],[])

if __name__=='__main__':unittest.main()
