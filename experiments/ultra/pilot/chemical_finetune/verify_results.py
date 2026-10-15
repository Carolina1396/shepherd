"""Recompute every rank and metric independently from completed score vectors."""
import argparse,csv,hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,required=True)
output=parser.parse_args().output.resolve()
settings=json.loads((output/'settings.json').read_text())
base=Path(settings['prepared_dataset'])
done=json.loads((output/'completed.json').read_text())
assert not settings['smoke_test']
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
labels=read(base/'data/labels.json');candidates=read(base/'data/candidates.json')
positions={r['index']:i for i,r in enumerate(candidates)}
known=defaultdict(set)
for r in labels:known[r['disease_index']].add(positions[r['drug_index']])
assert sha(output/'best.pt')==done['checkpoint_sha256']
assert read(output/'test/result.json')['checkpoint_sha256']==done['checkpoint_sha256']
checks=[(0,read(base/'evaluation/validation/metrics.json')['ultra']['mrr'])]
for path in sorted(output.glob('validation_step_*/metrics.json')):
 report=read(path);assert report['complete']
 checks.append((int(path.parent.name.split('_')[-1]),report['ultra']['mrr']))
selected=max(checks,key=lambda item:item[1])
assert selected[0]==done['best_step'] and selected[1]==done['best_validation_mrr']
validation_dir=base/'evaluation/validation' if done['best_step']==0 else output/f"validation_step_{done['best_step']:06d}"
verified={}
for split in ['validation','test']:
 out=validation_dir if split=='validation' else output/'test'
 metrics=read(out/'metrics.json')
 assert metrics['complete']
 assert sha(out/'answer_ranks.csv')==metrics['answer_ranks_sha256']
 with (out/'answer_ranks.csv').open() as f:rows=list(csv.DictReader(f))
 assert len(rows)==len({(r['drug'],r['disease']) for r in rows})
 assert {(r['drug'],r['disease']) for r in rows}=={(r['drug'],r['disease']) for r in labels if r['split']==split}
 by_query=defaultdict(list)
 for r in rows:by_query[int(r['disease_index'])].append(r)
 ranks=[]
 for idx,answers in by_query.items():
  path=out/'scores'/f'{idx}.npz'
  assert sha(path)==metrics['score_files_sha256'][path.name]==read(path.with_suffix('.json'))['sha256']
  with np.load(path,allow_pickle=False) as data:
   assert int(data['disease_index'])==idx
   scores=data['scores']
  assert scores.shape==(len(candidates),) and np.isfinite(scores).all()
  known_positions=np.fromiter(known[idx],dtype=np.int64)
  for row in answers:
   target=positions[int(row['drug_index'])]
   rank=1+int(np.count_nonzero(scores>=scores[target]))-int(np.count_nonzero(scores[known_positions]>=scores[target]))
   assert rank==int(row['rank'])
   ranks.append(rank)
 ranks=np.asarray(ranks)
 measured={'mrr':float(np.mean(1/ranks)),'hits_at_1':float(np.mean(ranks<=1)), 'hits_at_3':float(np.mean(ranks<=3)),'hits_at_10':float(np.mean(ranks<=10)),'top_10_answers':int(np.sum(ranks<=10))}
 for key,value in measured.items():assert abs(value-metrics['ultra'][key])<1e-12
 verified[split]={'pairs':len(ranks),'queries':len(by_query),'candidates':len(candidates),'independent_metrics':measured,'all_score_hashes_verified':True,'all_ranks_recomputed':True,'complete_pair_coverage':True}
 print(split,json.dumps(verified[split]),flush=True)
report={'complete':True,'splits':verified}
(output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
