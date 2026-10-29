"""Compare candidate-identity rankings from the same frozen retrieval."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path

from retrieve import binding_ids, digest, save

ROOT = Path(__file__).resolve().parents[1]


def rank_identities(scores, normalization):
    groups = defaultdict(list)
    for curie, score in scores.items():
        if not math.isfinite(score):
            raise ValueError(f'Nonfinite score: {curie}')
        node = normalization[curie]
        preferred = node['id']['identifier'] if node else curie
        groups[preferred].append((curie, score))
    maxima = {key:max(s for _,s in items) for key,items in groups.items()}
    return {key:dict(score=value, rank=sum(s >= value for s in maxima.values()),
                     source_ids=sorted(c for c,_ in groups[key])) for key,value in maxima.items()}


def score_map(response, answer_node):
    scores = defaultdict(list)
    for result in response['message']['results']:
        values=[a['score'] for a in result.get('analyses') or [] if a.get('score') is not None]
        if not values:
            raise ValueError('ARAGORN returned an answer without a score')
        if not all(math.isfinite(float(v)) for v in values):
            raise ValueError('ARAGORN returned a nonfinite analysis score')
        for curie in binding_ids(result['node_bindings'][answer_node]):
            scores[curie].extend(float(v) for v in values)
    return {key:max(values) for key,values in scores.items()}


def label_metrics(labels, ranks, ks=(1,5,10,20)):
    positives=[r for r in labels if r['evaluation_status']=='eligible' and r['expected_output']=='TopAnswer']
    negatives=[r for r in labels if r['evaluation_status']=='eligible' and r['expected_output']=='NeverShow']
    get_rank=lambda r:ranks.get(r['preferred_id'],{}).get('rank')
    recovered=[get_rank(r) for r in positives if get_rank(r) is not None]
    return dict(eligible_topanswers=len(positives), eligible_nevershow=len(negatives),
        flagged_labels=sum(r['evaluation_status']!='eligible' for r in labels),
        answer_mrr=sum(1/get_rank(r) if get_rank(r) else 0 for r in positives)/len(positives) if positives else None,
        conditional_answer_mrr=sum(1/r for r in recovered)/len(recovered) if recovered else None,
        positive_retrieval_coverage=len(recovered)/len(positives) if positives else None,
        cutoffs={str(k):dict(topanswer_hits=sum(get_rank(r) is not None and get_rank(r)<=k for r in positives),
            topanswer_recall=sum(get_rank(r) is not None and get_rank(r)<=k for r in positives)/len(positives) if positives else None,
            nevershow_hits=sum(get_rank(r) is not None and get_rank(r)<=k for r in negatives)) for k in ks})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval',type=Path,required=True)
    parser.add_argument('--ultra',type=Path,required=True)
    parser.add_argument('--normalization',type=Path,required=True)
    parser.add_argument('--aragorn',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Choose a fresh output directory')
    retrieval=json.loads((args.retrieval/'response.json').read_text())
    attempt=json.loads((args.retrieval/'attempt.json').read_text())
    assert digest(args.retrieval/'response.json')==attempt['response_sha256']
    ultra_report=json.loads((args.ultra/'summary.json').read_text())
    assert digest(args.ultra/'ranking.csv')==ultra_report['artifacts_sha256']['ranking.csv']
    # Bind the ULTRA conversion to this exact frozen retrieval.
    conversion=args.ultra.parent/'ultra_input/conversion.json'
    assert digest(conversion)==ultra_report['conversion_sha256']
    assert json.loads(conversion.read_text())['source_response_sha256']==attempt['response_sha256']
    with (args.ultra/'ranking.csv').open() as stream: rows=list(csv.DictReader(stream))
    scores={'ultra':{r['id']:float(r['score']) for r in rows}}
    names={r['id']:r['name'] for r in rows}
    request=json.loads((args.retrieval/'request.json').read_text())
    answer_node,=[k for k,n in request['message']['query_graph']['nodes'].items() if not n.get('ids')]
    retrieved={c for r in retrieval['message']['results'] for c in binding_ids(r['node_bindings'][answer_node])}
    assert set(scores['ultra'])==retrieved and len(rows)==len(retrieved)
    if args.aragorn:
        ar_attempt=json.loads((args.aragorn/'attempt.json').read_text())
        assert ar_attempt['source_response_sha256']==attempt['response_sha256']
        assert digest(args.aragorn/'response.json')==ar_attempt['response_sha256']
        scored=json.loads((args.aragorn/'response.json').read_text())
        scores['aragorn']=score_map(scored,answer_node)
        assert set(scores['aragorn'])==retrieved,'Scorers have different candidates'
    normalization=json.loads(args.normalization.read_text())
    labels=[dict(a) for a in json.loads((ROOT/'prepared/expected_answers.json').read_text())['answers'] if a['qid']==attempt['qid']]
    assert retrieved|{c for a in labels for c in a['source_ids']} <= set(normalization)
    ranked={name:rank_identities(values,normalization) for name,values in scores.items()}
    for label in labels:
        preferred={normalization[c]['id']['identifier'] if normalization[c] else c for c in label['source_ids']}
        label['evaluation_status']='eligible'
        if label['conflict'] or label['normalization_status']!='resolved' or len(preferred)!=1:
            label['evaluation_status']='flagged_source_label'
        else:
            label['preferred_id']=next(iter(preferred))
        ambiguous=[c for c,n in names.items() if n.casefold() in {n.casefold() for n in label['source_names']}
                   and (normalization[c]['id']['identifier'] if normalization[c] else c)!=label['preferred_id']]
        label['name_only_mismatches']=ambiguous
        if ambiguous and label['preferred_id'] not in ranked['ultra']:
            label['evaluation_status']='flagged_name_identity_mismatch'
        label['ranks']={name:values.get(label['preferred_id'],{}).get('rank') for name,values in ranked.items()}
    keys=sorted(ranked['ultra'],key=lambda k:(ranked['ultra'][k]['rank'],k))
    table=[]
    for key in keys:
        group=ranked['ultra'][key]
        row=dict(preferred_id=key,source_ids=';'.join(group['source_ids']),
                 names=';'.join(sorted({names[c] for c in group['source_ids']})))
        for name in ('ultra','aragorn'):
            row[name+'_score']=ranked[name][key]['score'] if name in ranked else ''
            row[name+'_rank']=ranked[name][key]['rank'] if name in ranked else ''
        table.append(row)
    args.output.mkdir(parents=True)
    with (args.output/'comparison.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(table[0]));writer.writeheader();writer.writerows(table)
    save(args.output/'label_matches.json',labels)
    summary=dict(qid=attempt['qid'],status='matched_scores_available' if args.aragorn else 'awaiting_aragorn_scores',
        raw_candidates=len(retrieved),identity_candidates=len(keys),
        unresolved_candidate_ids=[c for c in sorted(retrieved) if normalization[c] is None],
        metrics={name:label_metrics(labels,ranks) for name,ranks in ranked.items()},
        protocol='Same cached retrieval and candidate IDs; maximum analysis/alias score per identity; unrounded scores; pessimistic ties; missing eligible positives contribute zero; ambiguous/conflicting labels flagged and excluded.',
        evidence='ARAGORN standard scoring includes OmniCorp overlay. ULTRA uses predicate-only retrieved graph with generated conclusions removed.',
        scope='Single-query comparison; cohort aggregation must report missing/failed queries separately.',
        source_response_sha256=attempt['response_sha256'],normalization_sha256=digest(args.normalization),
        normalization_endpoint='https://nodenormalization-sri.renci.org/get_normalized_nodes',
        normalization_options={'conflate':True,'drug_chemical_conflate':True},
        ultra_summary_sha256=digest(args.ultra/'summary.json'),
        aragorn_response_sha256=digest(args.aragorn/'response.json') if args.aragorn else None,
        aragorn_endpoint=ar_attempt['endpoint'] if args.aragorn else None,
        retrieval_endpoint=attempt['endpoint'],
        code_sha256=digest(Path(__file__)))
    save(args.output/'summary.json',summary)
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
