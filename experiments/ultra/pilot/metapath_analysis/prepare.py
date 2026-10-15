"""Replay frozen Gandalf walks and cache descriptive metapath diagnostics.

Run with experiments/ultra/.venv/bin/python. Does not alter retrieval or ranking.
"""
from collections import Counter, defaultdict
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'pilot/results/chemical_metapaths_001'
WALKS = ROOT / 'pilot/results/chemical_walks_treats_only_001'
BASE = ROOT / 'pilot/results/chemical_retrieval_001'
SPLITS = ('validation', 'test')
# Reporting buckets, NOT constraints used by the sampler. First matching group wins.
CATEGORY_GROUPS = [
    ('Gene', ['Gene']), ('Protein', ['Protein']), ('Disease', ['Disease']),
    ('PhenotypicFeature', ['PhenotypicFeature']),
    ('ChemicalEntity', ['ChemicalEntity', 'SmallMolecule', 'Drug', 'ChemicalMixture']),
    ('Pathway', ['Pathway']), ('BiologicalProcess', ['BiologicalProcess']),
    ('MolecularActivity', ['MolecularActivity']), ('Cell', ['Cell']),
    ('AnatomicalEntity', ['AnatomicalEntity']), ('OrganismTaxon', ['OrganismTaxon']),
    ('BiologicalEntity', ['BiologicalEntity']), ('NamedThing', ['NamedThing'])]


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def category(categories):
    cats = {c.removeprefix('biolink:') for c in categories}
    return next((name for name, members in CATEGORY_GROUPS if cats.intersection(members)), 'Other')


def signature(nodes, edges, categories, predicates):
    """Edges are in traversal order; endpoints are positions in nodes."""
    result = categories[nodes[0]]
    for step, (h, p, t) in enumerate(edges):
        assert {h, t} == {step, step + 1}
        pred = predicates[p].removeprefix('biolink:')
        result += (f' -[{pred}]-> ' if h == step else f' <-[{pred}]- ') + categories[nodes[step + 1]]
    return result


def expected_prefixes(nodes, edges, expected):
    """A recovered answer can be an intermediate node of a completed walk."""
    return [(node, nodes[:hop + 1], edges[:hop])
            for hop, node in enumerate(nodes[1:], 1) if node in expected]


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    start = time.perf_counter()
    inputs = [WALKS / 'settings.json', WALKS / 'summary.json', BASE / 'settings.json',
              BASE / 'summary.json', BASE / 'aragorn_rules.json', BASE / 'zero_rule_audit.json', Path(__file__)]
    cfg, old = read(inputs[0]), read(inputs[2])
    prepared = Path(old['dataset']) / 'data'
    inputs += [prepared / 'labels.json', ROOT / 'output/gandalf/full-store/metadata.pkl']
    provenance = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
    if (OUT / 'manifest.json').exists():
        manifest = read(OUT / 'manifest.json')
        assert manifest['inputs'] == provenance, 'Inputs changed; use a new analysis output directory.'
        for name, expected in manifest['outputs'].items():
            assert digest(OUT / name) == expected, f'Cached analysis changed: {name}'
        print('Verified cached metapath analysis:', OUT)
        return
    OUT.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(ROOT / 'pilot/chemical_retrieval'))
    spec = importlib.util.spec_from_file_location('frozen_walk_comparison', ROOT / 'pilot/chemical_retrieval/compare_walks.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    for path, expected in cfg['source_sha256'].items():
        assert digest(ROOT / path) == expected, f'Frozen source changed: {path}'
    for name, expected in cfg['dataset_sha256'].items():
        assert digest(prepared / name) == expected
    assert digest(BASE / 'settings.json') == cfg['baseline_settings_sha256']
    assert digest(BASE / 'summary.json') == cfg['baseline_summary_sha256']
    assert digest(ROOT / 'output/gandalf/full-store/metadata.pkl') == cfg['source_graph_metadata_sha256']
    assert read(WALKS / 'summary.json')['complete']
    labels = read(prepared / 'labels.json')
    truth = {s: defaultdict(set) for s in SPLITS}
    for row in labels:
        if row['split'] in SPLITS:
            truth[row['split']][row['disease']].add(row['drug_index'])
    hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] in SPLITS}
    print('Loading graph and applying the frozen treats-only mask...', flush=True)
    source = module.comparison.CSRGraph.load_mmap(ROOT / 'output/gandalf/full-store', mmap_mode='r')
    graph = module.comparison.mask_graph(source, hidden, 'treats_only')
    assert len(graph.fwd_targets) == read(WALKS / 'source_graph.json')['evidence_records']
    sampler = module.GraphSampler(graph, random.Random(cfg['seed']))
    cats, metadata = {}, {}

    def populate(nodes, detail=False):
        missing = set(nodes) - (metadata.keys() if detail else cats.keys())
        props = graph.get_all_node_properties_batch(missing)
        ids = graph.get_node_ids_batch(missing) if detail else {}
        for n, value in props.items():
            categories = value.get('categories') or []
            cats[n] = category(categories)
            if detail:
                metadata[n] = {'index': int(n), 'id': ids[n], 'name': value.get('name', ids[n]),
                               'category': cats[n], 'categories': categories}

    full_counts, full_diseases = Counter(), Counter()
    prefix_counts = {s: Counter() for s in SPLITS}
    prefix_pairs = {s: Counter() for s in SPLITS}
    prefix_walk_only = {s: Counter() for s in SPLITS}
    rows, witnesses = [], []
    completed = 0
    verified = []
    for number, disease in enumerate(cfg['cohort']):
        wd = WALKS / 'diseases' / f'{number:04d}'
        ad = BASE / 'treats_only/diseases' / f'{number:04d}'
        report, wr, ar = read(wd / 'report.json'), read(wd / 'graph.json'), read(ad / 'graph.json')
        assert digest(wd / 'graph.json') == report['graph_sha256']
        assert digest(ad / 'report.json') == report['aragorn_report_sha256']
        assert digest(ad / 'graph.json') == read(ad / 'report.json')['artifact_sha256']['graph.json']
        verified.append({'disease': disease, 'walk_graph_sha256': digest(wd / 'graph.json'),
                         'aragorn_graph_sha256': digest(ad / 'graph.json')})
        anchor = wr['anchor']
        sampler.rng = random.Random(cfg['seed'] + number)
        walks = [w for _ in range(cfg['attempts']) if (w := sampler.walk(anchor, cfg['walk_length'])) is not None]
        replay = {(nodes[h], p, nodes[t]) for nodes, edges in walks for h, p, t in edges}
        # <= attempts*length == cap: every completed walk fits; union order cannot discard one.
        assert cfg['attempts'] * cfg['walk_length'] <= cfg['edge_cap']
        assert replay == {tuple(e) for e in wr['edges']}, f'Replay differs: {disease}'
        assert len(walks) == report['completed_walks']
        completed += len(walks)
        populate({n for nodes, _ in walks for n in nodes})
        local_full = Counter(signature(n, e, cats, graph.id_to_predicate) for n, e in walks)
        full_counts.update(local_full)
        full_diseases.update(local_full.keys())
        expected = truth['validation'][disease] | truth['test'][disease]
        best, per_pair = {}, defaultdict(set)
        for nodes, edges in walks:
            for chemical, ns, es in expected_prefixes(nodes, edges, expected):
                key = signature(ns, es, cats, graph.id_to_predicate)
                per_pair[chemical].add((len(es), key))
                for split in SPLITS:
                    if chemical in truth[split][disease]:
                        prefix_counts[split][key] += 1
                if chemical not in best or len(es) < len(best[chemical][1]):
                    best[chemical] = (ns, es)
        ar_nodes = {anchor} | {n for h, p, t in ar['edges'] for n in (h, t)}
        walk_nodes = {anchor} | {n for h, p, t in replay for n in (h, t)}
        direct_source = defaultdict(set)
        for neighbor, predicates, offsets in [(graph.fwd_targets, graph.fwd_predicates, graph.fwd_offsets),
                                              (graph.rev_sources, graph.rev_predicates, graph.rev_offsets)]:
            lo, hi = offsets[anchor:anchor + 2]
            for other, pred in zip(neighbor[lo:hi], predicates[lo:hi]):
                if int(other) in expected:
                    direct_source[int(other)].add(graph.id_to_predicate[int(pred)])
        for chem in expected:
            assert 'biolink:treats' not in direct_source[chem]
        populate(expected | {anchor}, detail=True)
        for split in SPLITS:
            assert set(best) & truth[split][disease] == set(report['splits'].get(split, {}).get('recovered_answer_indices', []))
            for chem in sorted(truth[split][disease]):
                wa, aa = chem in walk_nodes, chem in ar_nodes
                group = 'both' if wa and aa else 'walk_only' if wa else 'aragorn_only' if aa else 'neither'
                for hop, key in per_pair[chem]:
                    prefix_pairs[split][key] += 1
                    prefix_walk_only[split][key] += group == 'walk_only'
                rules = [rid for rid, matches in ar['retained_matches_by_rule'].items()
                         if any(chem in match['answers'] for match in matches)]
                witness_id = len(witnesses) if wa else None
                if wa:
                    ns, es = best[chem]
                    populate(ns, detail=True)
                    witnesses.append({'split': split, 'disease': disease, 'chemical': metadata[chem]['id'],
                        'group': group, 'metapath': signature(ns, es, cats, graph.id_to_predicate),
                        'nodes': [metadata[n] for n in ns],
                        'edges': [{'subject_position': h, 'predicate': graph.id_to_predicate[p], 'object_position': t}
                                  for h, p, t in es]})
                rows.append({'split': split, 'disease': disease, 'disease_name': metadata[anchor]['name'],
                    'chemical': metadata[chem]['id'], 'chemical_name': metadata[chem]['name'],
                    'group': group, 'walk_recovered': wa, 'aragorn_recovered': aa,
                    'minimum_sampled_hops': len(best[chem][1]) if wa else 0,
                    'source_has_direct_edge': bool(direct_source[chem]),
                    'source_direct_predicates': ' | '.join(sorted(direct_source[chem])),
                    'aragorn_rule_ids': ','.join(rules), 'witness_id': witness_id})
        if (number + 1) % 100 == 0 or number + 1 == len(cfg['cohort']):
            print(f'Replayed and verified {number + 1}/{len(cfg["cohort"])} diseases; {completed:,} completed walks', flush=True)
    assert completed == read(WALKS / 'summary.json')['completed_walks']
    write_csv(OUT / 'full_walk_metapaths.csv', [dict(metapath=k, completed_walk_occurrences=v,
              diseases=full_diseases[k]) for k, v in full_counts.most_common()])
    write_csv(OUT / 'answer_metapaths.csv', [dict(split=s, metapath=k, hops=k.count(']- ') + k.count(']-> '),
              prefix_occurrences=prefix_counts[s][k], distinct_answer_pairs=v,
              walk_only_answer_pairs=prefix_walk_only[s][k])
              for s in SPLITS for k, v in prefix_pairs[s].most_common()])
    write_csv(OUT / 'answer_diagnostics.csv', rows)
    save(OUT / 'witnesses.json', witnesses)
    save(OUT / 'verified_graphs.json', verified)
    templates = next(iter(read(BASE / 'aragorn_rules.json').values()))
    baseline_summary = read(BASE / 'summary.json')['results']['treats_only']
    audit = read(BASE / 'zero_rule_audit.json')
    catalog = []
    for i, rule in enumerate(templates):
        q = rule['template']['query_graph']
        blockers = []
        for eid, edge in audit['rules'].get(str(i), {}).get('edges', {}).items():
            if edge['counts']['fully_matching_records'] == 0:
                blockers.append({'edge_id': eid, **edge})
        catalog.append({'rule_id': i, 'query_graph': q, 'mined_rule': rule['Rule'],
            'zero_raw_matches': i in audit['zero_rule_ids'], 'blockers': blockers,
            'requires_direct_pair': any({e['subject'], e['object']} == {'$source', '$target'} for e in q['edges'].values()),
            **{s: baseline_summary[s]['rules'][str(i)] for s in SPLITS}})
    save(OUT / 'rule_catalog.json', catalog)
    summary = {'diseases_replayed': len(verified), 'completed_walks_replayed': completed,
               'all_graph_unions_and_walk_counts_exact': True, 'category_priority_groups': CATEGORY_GROUPS,
               'scope': 'Descriptive replay of one frozen seed; prefixes are of actual completed walks, not arbitrary union-graph paths.',
               'splits': {}}
    for split in SPLITS:
        subset = [r for r in rows if r['split'] == split]
        counts = Counter(r['group'] for r in subset)
        frozen = read(WALKS / 'summary.json')['paired_recovery'][split]
        assert all(counts[k] == frozen[k] for k in ('both', 'walk_only', 'aragorn_only', 'neither'))
        summary['splits'][split] = {'pairs': len(subset), 'groups': dict(counts),
            'minimum_sampled_hops': dict(Counter(r['minimum_sampled_hops'] for r in subset)),
            'source_direct_pairs': sum(r['source_has_direct_edge'] for r in subset),
            'recovered_without_source_direct': sum(r['walk_recovered'] and not r['source_has_direct_edge'] for r in subset),
            'walk_only_minimum_hops': dict(Counter(r['minimum_sampled_hops'] for r in subset if r['group'] == 'walk_only'))}
    summary['elapsed_seconds'] = time.perf_counter() - start
    save(OUT / 'summary.json', summary)
    save(OUT / 'manifest.json', {'inputs': provenance, 'outputs': {p.name: digest(p) for p in OUT.iterdir()
                                                               if p.is_file() and p.name != 'manifest.json'}})
    print(json.dumps(summary['splits'], indent=2), flush=True)


if __name__ == '__main__':
    main()
