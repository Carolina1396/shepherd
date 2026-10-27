"""Independently recompute every test rank from saved candidate scores."""
import argparse
from collections import defaultdict
import csv
from pathlib import Path
import numpy as np
from common import read,save,digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    base=parser.parse_args().dataset.resolve()
    manifest=read(base/'preparation.json')
    for name,expected in manifest['dataset_sha256'].items():
        assert digest(base/'data'/name)==expected
    labels,candidates=read(base/'data/labels.json'),read(base/'data/candidates.json')
    positions={r['index']:i for i,r in enumerate(candidates)}
    known=defaultdict(set)
    for r in labels:
        known[r['disease_index']].add(positions[r['drug_index']])
    out=base/'evaluation/test'
    metrics=read(out/'metrics.json')
    assert metrics['complete'] and metrics['evaluated_pairs']==2293
    assert digest(out/'answer_ranks.csv')==metrics['answer_ranks_sha256']
    with (out/'answer_ranks.csv').open() as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==len({(r['drug'],r['disease']) for r in rows})==2293
    truth={(r['drug'],r['disease']):(r['drug_index'],r['disease_index']) for r in labels if r['split']=='test'}
    assert {(r['drug'],r['disease']):(int(r['drug_index']),int(r['disease_index'])) for r in rows}==truth
    queries=defaultdict(list)
    for r in rows:
        queries[int(r['disease_index'])].append(r)
    assert len(queries)==metrics['total_queries']==metrics['scored_queries']==1122
    ranks,macro=[],[]
    for idx,answers in queries.items():
        path=out/'scores'/f'{idx}.npz'
        assert digest(path)==metrics['score_files_sha256'][path.name]==read(path.with_suffix('.json'))['sha256']
        with np.load(path,allow_pickle=False) as data:
            assert int(data['disease_index'])==idx
            scores=data['scores']
        assert scores.shape==(1117832,) and np.isfinite(scores).all()
        known_indices=np.asarray(sorted(known[idx]),dtype=np.int64)
        group=[]
        for row in answers:
            target=positions[int(row['drug_index'])]
            rank=1+int(np.count_nonzero(scores>=scores[target]))-int(np.count_nonzero(scores[known_indices]>=scores[target]))
            assert rank==int(row['rank'])
            ranks.append(rank)
            group.append(1/rank)
        macro.append(float(np.mean(group)))
    ranks=np.asarray(ranks)
    measured={'mrr':float(np.mean(1/ranks)),'hits_at_1':float(np.mean(ranks<=1)),
              'hits_at_3':float(np.mean(ranks<=3)),'hits_at_10':float(np.mean(ranks<=10)),
              'top_10_answers':int(np.sum(ranks<=10)),'disease_macro_mrr':float(np.mean(macro))}
    for k,v in measured.items():
        assert abs(v-metrics['ultra'][k])<1e-12,k
    report={'complete':True,'pairs':2293,'queries':1122,'candidates':1117832,
            'all_score_hashes_verified':True,'all_ranks_recomputed':True,'complete_pair_coverage':True,
            'independent_metrics':measured,'metrics_sha256':digest(out/'metrics.json'),
            'dataset_sha256':manifest['dataset_sha256'],'verifier_sha256':digest(Path(__file__))}
    save(base/'evaluation/verification.json',report)
    print(f'VERIFIED row={read(base/"config.json")["condition"]}: {measured}',flush=True)


if __name__=='__main__':
    main()
