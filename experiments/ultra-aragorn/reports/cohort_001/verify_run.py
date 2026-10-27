import csv, json, hashlib, math
from pathlib import Path
from collections import defaultdict
from bisect import bisect_right
root=Path(__file__).resolve().parents[2]
cohort=root/'results/cohort_001'
s=json.loads((cohort/'summary.json').read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest={}; verified=[]
def check(p, expected=None):
 h=digest(p)
 if expected: assert h==expected, str(p)
 manifest[str(p.relative_to(root))]=h
for q in s['queries']:
 if q['status']!='complete': continue
 r,u,a,c=map(lambda k:Path(q[k]),['retrieval','ultra','aragorn','comparison'])
 cs=json.loads((c/'summary.json').read_text()); us=json.loads((u/'summary.json').read_text())
 check(r/'response.json',cs['source_response_sha256'])
 check(a/'response.json',cs['aragorn_response_sha256'])
 check(u/'summary.json',cs['ultra_summary_sha256'])
 check(u/'ranking.csv',us['artifacts_sha256']['ranking.csv'])
 check(cohort/f"query_{q['qid']:03d}/normalization_response.json",cs['normalization_sha256'])
 rows=list(csv.DictReader((c/'comparison.csv').open()))
 assert len(rows)==q['identities']
 assert len({r['preferred_id'] for r in rows})==len(rows)
 for ranker in ['ultra','aragorn']:
  vals=sorted(float(row[ranker+'_score']) for row in rows)
  assert all(map(math.isfinite,vals))
  for row in rows:
   assert int(row[ranker+'_rank'])==bisect_right([-v for v in vals[::-1]],-float(row[ranker+'_score']))
 for name in ['summary.json','comparison.csv','label_matches.json']: check(c/name)
 verified.append(q['qid'])
labels=json.loads((cohort/'label_matches.json').read_text())
seen=set()
for a in labels:
 if a['evaluation_status']=='eligible':
  key=(a['qid'],a['preferred_id']);assert key not in seen, key;seen.add(key)
positive=[a for a in labels if a['evaluation_status']=='eligible' and a['expected_output']=='TopAnswer']
for ranker in ['ultra','aragorn']:
 value=sum(1/a['ranks'][ranker] if a['ranks'][ranker] else 0 for a in positive)/len(positive)
 assert math.isclose(value,s['metrics'][ranker]['answer_mrr'])
for name in ['summary.json','comparison.csv','label_matches.json','settings.json']:check(cohort/name)
report=dict(verified_matched_queries=len(verified),qids=verified,all_queries_processed=s['all_queries_processed'],
 checks=['retrieval and scoring provenance hashes','ULTRA ranking hash','joint normalization hash','finite scores','unique normalized candidates','pessimistic ranks recomputed','no duplicate eligible labels after joint normalization','aggregate answer MRR recomputed'],artifacts_sha256=manifest)
(cohort/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='artifacts_sha256'},indent=2))
