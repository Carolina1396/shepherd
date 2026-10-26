import json,yaml,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[2];p=root/'output/predicate-model-audit'
model=yaml.safe_load((p/'source/biolink-model.yaml').read_text());slots=model['slots'];meta=json.loads((root/'output/rules-01-02-09-controls/run_001/metadata-before.json').read_text())
def descend(name):
 found={name}
 while True:
  more={k for k,v in slots.items() if v.get('is_a') in found or set(v.get('mixins',[]))&found}
  if more<=found:return found
  found|=more
out={}
for name in ['similar to','has output','affects response to']:
 ds=descend(name);curies={'biolink:'+n.replace(' ','_') for n in ds};inverses={k for k,v in slots.items() if v.get('inverse') in ds}|{slots[n]['inverse'] for n in ds if slots[n].get('inverse')}
 hits=[e for e in meta['schema']['edges'] if e['predicate'] in curies]
 out[name]={'definition':slots.get(name),'descendants':sorted(ds),'inverse_slots':sorted(inverses),'metadata_matches':hits,'metadata_reported_records':sum(e['count'] for e in hits)}
inventory_path=root.parent/'output/tier0-20260621/inventory.json'
inventory=json.loads(inventory_path.read_text())
for name,result in out.items():
    inverse_curies={'biolink:'+n.replace(' ','_') for n in result['inverse_slots']}
    result['inverse_metadata_matches']=[e for e in meta['schema']['edges'] if e['predicate'] in inverse_curies]
    terms={'biolink:'+n.replace(' ','_') for n in result['descendants']}|inverse_curies
    result['local_inventory_exact_counts']={term:inventory['predicate_counts'].get(term,0) for term in sorted(terms)}
manifest={'model_url':'https://raw.githubusercontent.com/biolink/biolink-model/v4.3.2/biolink-model.yaml','retriever_commit':'ef1a18745405dd3f4798cabe392f807aa0f3e739','deployed_source_identity_verified':False,'hashes':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (p/'source').iterdir()}}
(p/'findings.json').write_text(json.dumps(out,indent=2));(p/'provenance.json').write_text(json.dumps(manifest,indent=2))
for n,v in out.items():print(n,v['descendants'],v['inverse_slots'],v['metadata_reported_records'])
