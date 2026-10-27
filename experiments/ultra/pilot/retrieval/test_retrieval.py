import json
from pathlib import Path
import random
import unittest

import numpy as np
from gandalf import CSRGraph
from masked_graph import mask_pairs
from run import cohort_from_labels, coverage, queries_for_disease, union_units, GraphSampler


class RetrievalTests(unittest.TestCase):
    def graph(self):
        edges=[(0,1),(0,1),(1,0),(1,2),(2,3),(3,0),(4,1)]
        predicates=[0,1,0,1,1,1,0]
        return CSRGraph(5,edges,predicates,{f'N:{i}':i for i in range(5)},
                        {'biolink:treats':0,'biolink:related_to':1},
                        node_properties={i:{'categories':['biolink:NamedThing'],'name':str(i)} for i in range(5)})

    def test_mask_removes_all_predicates_and_reverse_edges_preserving_other_pairs(self):
        graph=self.graph();masked,removed=mask_pairs(graph,{(0,1)})
        self.assertEqual(removed,3)
        self.assertEqual(len(graph.fwd_targets),7)
        self.assertEqual(len(masked.fwd_targets),4)
        self.assertIsNone(masked._find_edge_index(0,1,0))
        self.assertIsNone(masked._find_edge_index(0,1,1))
        self.assertIsNone(masked._find_edge_index(1,0,0))
        self.assertIsNotNone(masked._find_edge_index(4,1,0))
        for i,old in enumerate(masked.original_indices):
            self.assertEqual(masked.edge_properties._get_props(i),graph.edge_properties._get_props(int(old)))

    def test_native_walk_never_crosses_a_hidden_pair(self):
        masked,_=mask_pairs(self.graph(),{(0,1)})
        sampler=GraphSampler(masked,random.Random(0))
        completed=0
        for i in range(100):
            walk=sampler.walk(1,3)
            if walk is None:continue
            completed+=1;nodes,edges=walk
            for h,p,t in edges:self.assertNotEqual({nodes[h],nodes[t]},{0,1})
        self.assertGreater(completed,0)

    def test_cohort_is_fixed_validation_only_and_independent_of_answer_count(self):
        labels=[{'disease':f'D:{i}','split':'validation'} for i in range(80)]
        selected=cohort_from_labels(labels,50,7317)
        self.assertEqual(selected,cohort_from_labels(list(reversed(labels))+labels[:3]+[{'disease':'TEST','split':'test'}],50,7317))
        self.assertEqual(len(set(selected)),50)

    def test_whole_match_budget_and_coverage_count_missed_answers(self):
        groups=[[{'edges':[(0,1,2),(2,1,3)],'answers':[3]}],
                [{'edges':[(0,1,4),(4,1,5)],'answers':[5]}]]
        edges,answers=union_units(groups,2,10)
        self.assertEqual(len(edges),2)
        report=coverage(edges,0,{3,5},{3,5},answers)
        self.assertEqual(report['answers_reached'],1)
        self.assertEqual(report['answer_coverage'],0.5)

    def test_actual_templates_preserved_and_disease_only_pinned(self):
        path=Path(__file__).resolve().parents[4]/'workers/aragorn_lookup/rules_with_types_cleaned_finalized.json'
        rules=json.loads(path.read_text())['{"predicate": "biolink:treats"}']
        queries=queries_for_disease('MONDO:example',rules)
        self.assertEqual(len(queries),19)
        self.assertEqual(sum(q['requires_direct_pair'] for q in queries),9)
        for q in queries:
            nodes=q['query']['query_graph']['nodes']
            self.assertEqual(nodes['disease']['ids'],['MONDO:example'])
            self.assertNotIn('ids',nodes['drug'])


if __name__=='__main__':unittest.main()
