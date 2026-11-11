import json,unittest
from copy import deepcopy
from pathlib import Path
from service_execute import interpret
from build_candidates import build_service
from template_format import make_query

class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.template=json.loads(Path(__file__).with_name('templates.example.json').read_text())['templates'][1]
        self.limits={'max_paths':5000,'max_candidates':1000}
        self.data={'status':'Success','message':{'knowledge_graph':{'nodes':{n:{'name':n} for n in ['D','M','X']},'edges':{
          'a':{'subject':'D','object':'M','predicate':'biolink:affects','sources':[], 'qualifiers':[
           {'qualifier_type_id':'biolink:object_aspect_qualifier','qualifier_value':'activity'},
           {'qualifier_type_id':'biolink:object_direction_qualifier','qualifier_value':'decreased'}]},
          'b':{'subject':'M','object':'X','predicate':'biolink:associated_with','sources':[]}}},
          'results':[{'node_bindings':{n:{'ids':[v]} for n,v in [('drug','D'),('intermediate','M'),('disease','X')]},
           'analyses':[{'edge_bindings':{'drug_edge':{'ids':['a']},'disease_edge':{'ids':['b']}}}]}]}}
    def test_full_path_and_preservation(self):
        r=interpret(self.data,self.template,'X',self.limits)
        self.assertEqual(r['state'],'complete');self.assertEqual(r['paths'],[['D','M','X','a','b']])
        m=build_service('X',[r,r]);self.assertEqual(len(m['results']),1)
        self.assertEqual(len(m['auxiliary_graphs']),1)
        self.assertEqual(m['knowledge_graph']['edges']['a'],self.data['message']['knowledge_graph']['edges']['a'])
    def test_missing_qualifier_rejects_evidence(self):
        self.data['message']['knowledge_graph']['edges']['a'].pop('qualifiers')
        r=interpret(self.data,self.template,'X',self.limits)
        self.assertEqual(r['state'],'invalid_evidence');self.assertEqual(r['paths'],[])
    def test_mismatched_mid_not_joined(self):
        self.data['message']['knowledge_graph']['nodes']['M2']={'name':'M2'}
        self.data['message']['knowledge_graph']['edges']['b']['subject']='M2'
        self.data['message']['results'][0]['node_bindings']['intermediate']['ids'].append('M2')
        r=interpret(self.data,self.template,'X',self.limits)
        self.assertEqual(r['paths'],[])
    def test_limits_and_warning_are_incomplete(self):
        r=interpret(self.data,self.template,'X',{'max_paths':0,'max_candidates':1})
        self.assertEqual(r['state'],'evidence_limit')
        self.data['logs']=[{'level':'WARNING','message':'timeout'}]
        self.assertEqual(interpret(self.data,self.template,'X',self.limits)['state'],'partial')
    def test_reversed_symmetric_edge(self):
        self.template['edges']['drug_edge']={'subject':'drug','object':'intermediate','predicate':'biolink:interacts_with'}
        edge=self.data['message']['knowledge_graph']['edges']['a']
        edge.update(subject='M',object='D',predicate='biolink:directly_physically_interacts_with')
        r=interpret(self.data,self.template,'X',self.limits)
        self.assertEqual(r['state'],'complete')
        self.assertEqual(r['paths'],[['D','M','X','a','b']])
        self.assertEqual(r['knowledge_graph']['edges']['a'],edge)
        self.assertEqual(build_service('X',[r])['knowledge_graph']['edges']['a'],edge)
    def test_reversed_directional_edge_rejected(self):
        self.data['message']['knowledge_graph']['edges']['a'].update(subject='M',object='D')
        self.assertEqual(interpret(self.data,self.template,'X',self.limits)['state'],'invalid_evidence')
    def test_symmetric_unbound_endpoint_rejected(self):
        self.template['edges']['drug_edge']={'subject':'drug','object':'intermediate','predicate':'biolink:interacts_with'}
        self.data['message']['knowledge_graph']['edges']['a'].update(subject='M',object='OTHER',predicate='biolink:interacts_with')
        self.assertEqual(interpret(self.data,self.template,'X',self.limits)['state'],'invalid_evidence')
    def test_explicit_query_not_amie(self):
        q=make_query(self.template,'X')
        self.assertTrue(all(e['knowledge_type']=='lookup' for e in q['message']['query_graph']['edges'].values()))
        self.assertEqual(q['message']['query_graph']['edges']['drug_edge']['constraints'],self.template['edges']['drug_edge']['constraints'])

if __name__=='__main__':unittest.main()
