"""Freeze reproducible training batches and source hashes; never opens test labels."""
import csv, hashlib, json, random
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def prepare():
    c=json.loads((HERE/'config.json').read_text())
    with (ROOT/c['train']).open() as f: rows=list(csv.DictReader(f))
    ds=sorted({r['disease_id'] for r in rows});rng=random.Random(c['seed'])
    first=sorted(rng.sample(ds,c['batch_size']))
    second=sorted(rng.sample(sorted(set(ds)-set(first)),c['batch_size']))
    manifest={'config_sha256':digest(HERE/'config.json'),'train_sha256':digest(ROOT/c['train']),
              'validation_sha256':digest(ROOT/c['validation']),
              'graph_report_sha256':digest(ROOT/c['graph']/'filtering_report.json'),
              'batches':{'train_a':first,'train_b':second,'debug':first[:3]}}
    p=HERE/'batches.json'
    if p.exists() and json.loads(p.read_text())!=manifest: raise ValueError('Frozen inputs changed; create a new protocol rather than overwrite')
    p.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Prepared train_a, train_b, debug. No test data accessed.')
if __name__=='__main__':prepare()
