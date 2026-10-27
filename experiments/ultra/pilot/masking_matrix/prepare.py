"""Prepare and independently audit all seven missing masking conditions."""
import argparse
from collections import Counter
from pathlib import Path
import random
import shutil
import time
import numpy as np
from common import ROOT, CONDITIONS, read, save, digest, policy, edge_groups, keep_edges, independent_keep


def main():
    from gandalf import CSRGraph
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--store', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    baseline, out = args.baseline.resolve(), args.output.resolve()
    if out.exists():
        parser.error('Use a new suite directory; preparation does not overwrite existing runs')
    start = time.perf_counter()
    cfg, manifest = read(baseline/'config.json'), read(baseline/'preparation.json')
    reference = read(ROOT/'pilot/studies/full_graph_chemical_disease_4g_results.json')
    assert manifest['complete'] and cfg['training_epochs'] == 0 and cfg['experiment'] == 10
    assert digest(baseline/'config.json') == manifest['config_sha256']
    assert manifest['dataset_sha256'] == reference['comparison']['preparation']['dataset_sha256']
    for name, expected in manifest['dataset_sha256'].items():
        assert digest(baseline/'data'/name) == expected, name
    labels = read(baseline/'data/labels.json')
    candidates = read(baseline/'data/candidates.json')
    predicates = read(baseline/'data/predicates.json')
    baseline_metrics = read(baseline/'evaluation/test/metrics.json')
    assert baseline_metrics['ultra'] == reference['comparison']['results']['test']['ultra']
    assert digest(baseline/'evaluation/test/answer_ranks.csv') == baseline_metrics['answer_ranks_sha256']
    assert digest(ROOT/cfg['checkpoint']) == cfg['checkpoint_sha256']
    print('Loading unmasked Tier 0 source and verifying the frozen chemical/drug labels...', flush=True)
    graph = CSRGraph.load_mmap(args.store.resolve(), mmap_mode='r')
    n, p = graph.num_nodes, len(predicates)
    assert n == cfg['num_nodes'] == 1670341
    assert predicates == [graph.id_to_predicate[i] for i in range(p)]
    target = predicates.index('biolink:treats')
    chemical, disease = np.zeros(n, bool), np.zeros(n, bool)
    for i, props in graph.node_store.iter_properties():
        cats = set(props.get('categories', []))
        chemical[i] = bool(cats & {'biolink:Drug', 'biolink:ChemicalEntity', 'biolink:SmallMolecule'})
        disease[i] = 'biolink:Disease' in cats
    assert np.array_equal(np.flatnonzero(chemical), np.array([c['index'] for c in candidates]))
    assert all(graph.get_node_id(c['index']) == c['id'] for c in candidates)
    assert all(graph.get_node_id(r['drug_index']) == r['drug'] and
               graph.get_node_id(r['disease_index']) == r['disease'] for r in labels)
    sources = np.repeat(np.arange(n, dtype=np.int64), np.diff(graph.fwd_offsets))
    encoded = np.unique((sources * p + graph.fwd_predicates) * n + graph.fwd_targets)
    del sources
    triples = np.column_stack((encoded // (n*p), (encoded // n) % p, encoded % n))
    del encoded
    assert len(triples) == manifest['original_unique_connections'] == 27927289
    eligible = triples[(triples[:, 1] == target) & chemical[triples[:, 0]] & disease[triples[:, 2]]]
    pairs = {(int(h), int(t)) for h, _, t in eligible}
    assert pairs == {(r['drug_index'], r['disease_index']) for r in labels}
    ordered = sorted((graph.get_node_id(h), graph.get_node_id(t)) for h, t in pairs)
    random.Random(731).shuffle(ordered)
    a, b = int(.8*len(ordered)), int(.1*len(ordered))
    expected = {(h,t): 'visible' if i<a else 'validation' if i<a+b else 'test'
                for i,(h,t) in enumerate(ordered)}
    assert expected == {(r['drug'],r['disease']):r['split'] for r in labels}
    groups = edge_groups(triples, labels, n)
    is_treats = triples[:, 1] == target
    row1 = triples[keep_edges(groups, is_treats, 1)]
    assert np.array_equal(row1, np.load(baseline/'data/triples.npy')), 'Reconstructed baseline differs'
    del row1
    out.mkdir(parents=True)
    np.save(out/'source_triples.npy', triples)
    source_hash = digest(out/'source_triples.npy')
    group_counts = {name: {'treats':int(np.count_nonzero((groups == i) & is_treats)),
                           'other':int(np.count_nonzero((groups == i) & ~is_treats))}
                    for i,name in enumerate(['unlabeled','visible','heldout'])}
    suite = {'complete':False, 'name':'Tier 0 labeled-pair masking matrix',
             'baseline':str(baseline), 'source_store':str(args.store.resolve()),
             'source_triples_sha256':source_hash, 'source_unique_connections':len(triples),
             'baseline_dataset_sha256':manifest['dataset_sha256'],
             'baseline_preparation_sha256':digest(baseline/'preparation.json'),
             'baseline_test_metrics_sha256':digest(baseline/'evaluation/test/metrics.json'),
             'baseline_test':baseline_metrics['ultra'], 'nodes':n, 'candidates':len(candidates),
             'pairs':len(labels), 'pair_splits':cfg['pair_splits'], 'groups':group_counts,
             'conditions':{str(row):policy(row) for row in CONDITIONS},
             'evaluation':'Test only; validation and test edges masked together; no selection or training',
             'baseline_reconstructed_exactly':True, 'split_independently_reconstructed':True,
             'source_code_sha256':{f.name:digest(f) for f in [Path(__file__),Path(__file__).with_name('common.py')]}}
    save(out/'suite.json', suite)
    for row in range(2,9):
        tick = time.perf_counter()
        dest = out/f'row_{row:02d}'
        data = dest/'data'
        data.mkdir(parents=True)
        keep = keep_edges(groups, is_treats, row)
        masked = triples[keep]
        np.save(data/'triples.npy', masked)
        active = np.zeros(n, bool)
        active[masked[:,0]] = True
        active[masked[:,2]] = True
        visible_diseases = {r['disease'] for r in labels if r['split']=='visible'} if CONDITIONS[row][0] else set()
        updated = [{**r, 'drug_isolated':not bool(active[r['drug_index']]),
                    'disease_isolated':not bool(active[r['disease_index']]),
                    'disease_has_visible_treatment':r['disease'] in visible_diseases} for r in labels]
        save(data/'labels.json', updated)
        for name in ['candidates.json','predicates.json']:
            shutil.copyfile(baseline/'data'/name, data/name)
        config = {**cfg, 'experiment':'tier0_masking_matrix', 'condition':row, 'policy':policy(row),
                  'mask':policy(row)['scope'], 'suite':str(out)}
        save(dest/'config.json',config)
        removed = Counter(predicates[int(r)] for r in triples[~keep,1])
        info = {'complete':True,'condition':row,'policy':policy(row),
                'source_triples_sha256':source_hash,'original_unique_connections':len(triples),
                'remaining_connections':len(masked),'removed_connections':int((~keep).sum()),
                'removed_by_predicate':dict(removed),'edges_with_inverses':2*len(masked),
                'isolated_candidates':int((~active[chemical]).sum()),
                'config_sha256':digest(dest/'config.json'),
                'dataset_sha256':{f.name:digest(f) for f in sorted(data.iterdir())}}
        save(dest/'preparation.json', info)
        # Independently reconstruct each saved block with directed-key membership.
        saved = np.load(data/'triples.npy', mmap_mode='r')
        cursor = 0
        for start_idx in range(0,len(triples),1000000):
            block = triples[start_idx:start_idx+1000000]
            selected = block[independent_keep(block, labels, n, target, row)]
            assert np.array_equal(saved[cursor:cursor+len(selected)],selected), row
            cursor += len(selected)
        assert cursor == len(saved)
        verification = {'complete':True,'all_saved_triples_independently_checked':True,
                        'unlabeled_pair_edges_unchanged':True,'all_heldout_treats_absent':True,
                        'fixed_nodes_candidates_and_label_splits':True,
                        'dataset_sha256':info['dataset_sha256'],'remaining_connections':cursor,
                        'seconds':time.perf_counter()-tick}
        save(dest/'preparation_verification.json',verification)
        print(f'PREPARED row={row} removed={info["removed_connections"]:,} remaining={cursor:,} isolated_candidates={info["isolated_candidates"]:,}',flush=True)
        del masked, saved
    suite.update(complete=True,preparation_seconds=time.perf_counter()-start)
    save(out/'suite.json',suite)
    print('All seven conditions prepared and independently verified.',flush=True)


if __name__ == '__main__':
    main()
