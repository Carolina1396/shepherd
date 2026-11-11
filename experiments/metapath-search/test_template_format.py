import json
from pathlib import Path
import unittest
from copy import deepcopy
from template_format import matches_qualifiers, make_query, template_hash, validate_collection, validate_template

D='biolink:object_direction_qualifier'
A='biolink:object_aspect_qualifier'
def stored(**values):
    return [{'qualifier_type_id':k,'qualifier_value':v} for k,v in values.items()]

class FormatTest(unittest.TestCase):
    def setUp(self):
        self.collection=json.loads(Path(__file__).with_name('templates.example.json').read_text())
        self.broad,self.down,self.up=self.collection['templates']
    def test_examples_and_query(self):
        validate_collection(self.collection)
        q=make_query(self.down,'MONDO:0009061')
        e=q['message']['query_graph']['edges']['drug_edge']
        self.assertEqual(e['constraints'],self.down['edges']['drug_edge']['constraints'])
        self.assertEqual(e['knowledge_type'],'lookup')
    def test_missing_is_not_decreased(self):
        edge=self.down['edges']['drug_edge']
        self.assertFalse(matches_qualifiers([],edge))
        self.assertFalse(matches_qualifiers(stored(**{A:'activity'}),edge))
        self.assertFalse(matches_qualifiers(stored(**{A:'activity',D:'increased'}),edge))
        self.assertTrue(matches_qualifiers(stored(**{A:'activity',D:'decreased','biolink:species_context_qualifier':'NCBITaxon:9606'}),edge))
    def test_unconstrained(self):
        self.assertTrue(matches_qualifiers([],self.broad['edges']['drug_edge']))
        self.assertTrue(matches_qualifiers(stored(**{D:'increased'}),self.broad['edges']['drug_edge']))
    def test_or_sets_and_same_record_requirement(self):
        edge={'constraints':{'qualifiers':[{A:'activity',D:'decreased'},{A:'expression',D:'increased'}]}}
        self.assertTrue(matches_qualifiers(stored(**{A:'expression',D:'increased'}),edge))
        self.assertFalse(matches_qualifiers(stored(**{A:'activity',D:'increased'}),edge))
        records=[stored(**{A:'activity'}),stored(**{D:'decreased'})]
        self.assertFalse(any(matches_qualifiers(r,edge) for r in records))
    def test_hash_includes_qualifiers(self):
        self.assertEqual(len({template_hash(t) for t in self.collection['templates']}),3)
        t=deepcopy(self.broad);t['id']='renamed';t['edges']['drug_edge']['constraints']={'qualifiers':[]}
        self.assertEqual(template_hash(t),template_hash(self.broad))
    def test_invalid_constraints_rejected(self):
        for invalid in (None,[{}],{'direction':'decreased'},[{'biolink:object_direction_qualifier':None}]):
            t=deepcopy(self.down);t['edges']['drug_edge']['constraints']['qualifiers']=invalid
            with self.assertRaises(ValueError): validate_template(t)
    def test_arrow_and_effect_direction_are_independent(self):
        t=deepcopy(self.down)
        e=t['edges']['drug_edge'];e['subject'],e['object']=e['object'],e['subject']
        q=make_query(t,'MONDO:1')['message']['query_graph']['edges']['drug_edge']
        self.assertEqual(q['object'],'drug')
        self.assertEqual(q['constraints']['qualifiers'][0][D],'decreased')

if __name__=='__main__': unittest.main()
