"""Convert cached TRAPI evidence to ULTRA arrays without using benchmark labels."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from retrieve import binding_ids, digest, inspect, save


def convert(response, request):
    audit = inspect(response, request)
    if audit['reference_issues']:
        raise ValueError(f"Incomplete evidence: {audit['reference_issues']}")
    message = response['message']
    kg = message['knowledge_graph']
    qedge, = request['message']['query_graph']['edges'].values()
    if qedge['predicates'] != ['biolink:treats']:
        raise ValueError('Only chemical-subject treatment queries supported')
    answer_key, anchor_key = qedge['subject'], qedge['object']
    qnodes = request['message']['query_graph']['nodes']
    if qnodes[answer_key].get('ids') or len(qnodes[anchor_key].get('ids', [])) != 1:
        raise ValueError('Expected one pinned disease and an unpinned chemical subject')
    anchors, candidates = set(), set()
    for result in message.get('results') or []:
        candidates.update(binding_ids(result['node_bindings'][answer_key]))
        anchors.update(binding_ids(result['node_bindings'][anchor_key]))
    if not candidates:
        raise ValueError('No candidate bindings; do not fabricate a scoring dataset')
    if len(anchors) != 1:
        raise ValueError(f'Expected one returned disease identity, found {sorted(anchors)}')
    anchor, = anchors
    if anchor != qnodes[anchor_key]['ids'][0]:
        raise ValueError('Returned disease ID changed; verify equivalence before conversion')
    nodes = sorted(kg['nodes'])
    node_index = {nid: i for i, nid in enumerate(nodes)}
    removed, retained = {}, {}
    for eid, edge in kg['edges'].items():
        support = any(a.get('attribute_type_id') == 'biolink:support_graphs'
                      for a in edge.get('attributes') or [])
        levels = {edge.get('knowledge_level')}
        levels.update(a.get('value') for a in edge.get('attributes') or []
                      if a.get('attribute_type_id') == 'biolink:knowledge_level')
        reasons = []
        if support:
            reasons.append('support_graph_conclusion')
        if 'logical_entailment' in levels:
            reasons.append('logical_entailment')
        if reasons:
            removed[eid] = reasons
        else:
            retained[eid] = edge
    predicates = sorted({e['predicate'] for e in retained.values()} | {'biolink:treats'})
    relation_index = {p: i for i, p in enumerate(predicates)}
    provenance = defaultdict(list)
    for eid, edge in retained.items():
        triple = (node_index[edge['subject']], relation_index[edge['predicate']], node_index[edge['object']])
        provenance[triple].append(eid)
    triples = sorted(provenance)
    active = {i for h, _, t in triples for i in (h, t)}
    direct_pairs = {(e['subject'], e['object']) for e in retained.values() if e['predicate']=='biolink:treats'}
    candidates = [dict(id=c, index=node_index[c], name=kg['nodes'][c].get('name'),
                       isolated=node_index[c] not in active,
                       direct_treats_evidence=(c, anchor) in direct_pairs) for c in sorted(candidates)]
    return dict(nodes=[dict(id=n, index=i, name=kg['nodes'][n].get('name')) for i, n in enumerate(nodes)],
        predicates=predicates, candidates=candidates, triples=triples,
        anchor=dict(id=anchor, index=node_index[anchor]), target_relation=relation_index['biolink:treats'],
        removed_edges=removed,
        triple_provenance=[dict(triple=list(t), source_edge_ids=sorted(provenance[t])) for t in triples],
        summary=dict(nodes=len(nodes), candidates=len(candidates), source_edges=len(kg['edges']),
            removed_conclusion_edges=len(removed), retained_evidence_records=len(retained),
            unique_directed_triples=len(triples), edges_with_inverses=2*len(triples),
            original_relations=len(predicates), relations_with_inverses=2*len(predicates),
            isolated_candidates=sum(c['isolated'] for c in candidates),
            candidates_with_direct_treats=sum(c['direct_treats_evidence'] for c in candidates),
            retained_records_with_qualifiers=sum(bool(e.get('qualifiers')) for e in retained.values()),
            retained_predicates=dict(Counter(e['predicate'] for e in retained.values())),
            service_problem_logs=len(audit['problem_logs']),
            candidate_identity_policy='Preserve all returned CURIEs; cross-CURIE normalization/deduplication pending before evaluation',
            evidence_policy='Remove support-graph conclusions and logical entailments; retain all other returned evidence',
            representation='Predicate-only triples; qualifiers and evidence provenance remain in raw response',
            empty_graph=not triples))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrieval', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; choose a fresh directory')
    import numpy as np
    source = args.retrieval
    attempt = json.loads((source/'attempt.json').read_text())
    for filename, key in [('request.json','request_sha256'), ('response.json','response_sha256')]:
        if digest(source/filename) != attempt[key]:
            raise ValueError(f'Source hash changed: {filename}')
    result = convert(json.loads((source/'response.json').read_text()),
                     json.loads((source/'request.json').read_text()))
    out = args.output
    out.mkdir(parents=True)
    triples = np.asarray(result.pop('triples'), dtype=np.int64).reshape(-1, 3)
    np.save(out/'triples.npy', triples)
    num_relations = len(result['predicates'])
    edges = triples[:, [0, 2]].T
    np.save(out/'edge_index.npy', np.concatenate([edges, edges[::-1]], axis=1))
    np.save(out/'edge_type.npy', np.concatenate([triples[:, 1], triples[:, 1]+num_relations]))
    for field in ('nodes', 'predicates', 'candidates', 'removed_edges', 'triple_provenance'):
        save(out/f'{field}.json', result.pop(field))
    save(out/'config.json', dict(anchor=result['anchor'], target_relation=result['target_relation'],
        num_nodes=result['summary']['nodes'], num_relations=2*num_relations,
        array_layout='triples: [head, relation, tail]; model query batch: [head, tail, relation]',
        relation_graph='Build with ultra.tasks.build_relation_graph from edge_index and edge_type before inference'))
    report = dict(**result['summary'], source_request_sha256=attempt['request_sha256'],
        source_response_sha256=attempt['response_sha256'],
        code_sha256={p.name:digest(p) for p in [Path(__file__),Path(__file__).with_name('retrieve.py')]},
        artifacts_sha256={p.name:digest(p) for p in sorted(out.iterdir())})
    save(out/'conversion.json', report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
