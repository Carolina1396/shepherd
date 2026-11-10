"""Small end-to-end fixture: parallel edges, reversed exclusions and metadata."""
import csv
import json
from pathlib import Path
import pickle
import tempfile
import unittest

import lmdb
import msgpack
import numpy as np

from build_filtered_graph import build, ro_store, read_array


class FilterBuildTest(unittest.TestCase):
    def test_remap_preserves_parallel_edges_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, out, labels = root / 'source', root / 'out', root / 'labels'
            source.mkdir()
            labels.mkdir()
            nodes = [('CHEBI:1', ['biolink:SmallMolecule', 'biolink:ChemicalEntity']),
                     ('MONDO:1', ['biolink:Disease']), ('NCBIGene:1', ['biolink:Gene']),
                     ('CHEBI:2', ['biolink:Drug']), ('HP:1', ['biolink:PhenotypicFeature']),
                     ('NCBIGene:2', ['biolink:Gene'])]
            edges = [(0,1,0), (0,2,1), (0,2,1), (1,0,0), (1,2,2), (3,4,0), (4,3,2)]
            # An isolated first node makes every retained node index change.
            nodes.insert(0, ('NCBIGene:0', ['biolink:Gene']))
            edges = [(s+1, o+1, p) for s, o, p in edges]
            subj, obj, pred = np.array(edges, dtype=np.int32).T
            perm = np.lexsort((pred, subj, obj))
            arrays = {
                'fwd_offsets': np.r_[0, np.cumsum(np.bincount(subj, minlength=7))],
                'fwd_targets': obj, 'fwd_predicates': pred,
                'rev_offsets': np.r_[0, np.cumsum(np.bincount(obj, minlength=7))],
                'rev_sources': subj[perm], 'rev_predicates': pred[perm],
                'rev_to_fwd': perm.astype(np.int32),
                'edge_sources_idx': np.arange(7, dtype=np.int32),
                'edge_quals_idx': np.array([0,1,0,0,0,0,0], dtype=np.int32),
                'edge_kl_at_idx': np.zeros(7, dtype=np.int16),
            }
            for name, value in arrays.items():
                np.save(source / (name + '.npy'), value)
            metadata = {'num_nodes': 7, 'predicate_to_idx': {'biolink:treats':0,
                        'biolink:affects':1, 'biolink:associated_with':2}, 'edge_attributes_format':'json'}
            with (source / 'metadata.pkl').open('wb') as f:
                pickle.dump(metadata, f)
            pools = {'sources_pool': [[{'resource_id':f'infores:source{i}',
                     'resource_role':'primary_knowledge_source'}] for i in range(7)],
                     'quals_pool': [[], [{'qualifier_type_id':'biolink:object_direction_qualifier',
                                         'qualifier_value':'increased'}]],
                     'kl_at_pool':[('knowledge_assertion','manual_agent')]}
            with (source / 'edge_property_pools.pkl').open('wb') as f:
                pickle.dump(pools, f)
            (source / 'graph-metadata.json').write_text('{"@id":"fixture"}')
            (source / 'local-build-complete.json').write_text('{"source_release":"fixture"}')
            with lmdb.open(str(source / 'node_store.lmdb'), max_dbs=3) as env:
                dbs={name:env.open_db(name.encode()) for name in ('properties','idx_to_id','id_to_idx')}
                with env.begin(write=True) as t:
                    for i,(curie,cats) in enumerate(nodes):
                        key=i.to_bytes(4,'big')
                        t.put(key,curie.encode(),db=dbs['idx_to_id'])
                        t.put(curie.encode(),key,db=dbs['id_to_idx'])
                        t.put(key,msgpack.packb({'name':curie,'categories':cats,'attributes':[]}),db=dbs['properties'])
            for name in ('edge_ids.lmdb','edge_properties.lmdb'):
                with lmdb.open(str(source/name)) as env:
                    with env.begin(write=True) as t:
                        for i in range(7):
                            value=(f'edge{i}'.encode() if name=='edge_ids.lmdb' else
                                   json.dumps([{'attribute_type_id':'biolink:has_count',
                                                'original_attribute_name':f'count{i}', 'value':i}]).encode())
                            t.put(i.to_bytes(4,'big'),value)
            for split in ('train','val','test'):
                with (labels/(split+'.csv')).open('w',newline='') as f:
                    w=csv.writer(f)
                    w.writerow(['drug_id','drug_name','disease_id','disease_name'])
                    if split=='train':
                        w.writerow(['CHEBI:1','Drug','MONDO:1','Disease'])
            report=build(source,out,labels,expected=(3,3))
            self.assertEqual(report['removed_edges'],4)
            self.assertEqual(report['removed_nodes'],4)
            self.assertEqual(read_array(out,'original_node_to_filtered').tolist(),[-1,0,1,2,-1,-1,-1])
            self.assertEqual(read_array(out,'edge_sources_idx').tolist(),[1,2,4])
            with ro_store(out/'edge_ids.lmdb') as env:
                with env.begin() as t:
                    self.assertEqual([v.decode() for _,v in t.cursor()],['edge1','edge2','edge4'])
            meta=json.loads((out/'meta_kg.json').read_text())
            affected=next(e for e in meta['edges'] if e['predicate']=='biolink:affects')
            self.assertEqual(affected['qualifiers'][0]['applicable_values'],['increased'])
            self.assertEqual({a['original_attribute_names'][0] for a in affected['attributes']},{'count1','count2'})
            self.assertTrue(report['source_unchanged'])
            with self.assertRaises(ValueError):
                build(source,out,labels,expected=(3,3))


if __name__ == '__main__':
    unittest.main()
