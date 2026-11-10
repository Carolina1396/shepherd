"""Build a separate Gandalf graph with no drug--disease edges or isolated nodes.

Use the existing .local/gandalf-venv Python. No services are changed. All input
stores are opened read-only without LMDB locks; the input must be immutable.
Only trusted Gandalf directories are supported (metadata contains pickle).
The output and its .building sibling must not exist. On failure, the staging
directory is left for inspection; the final path is published only on success.
"""

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import pickle
import shutil
import sys
import time

import lmdb
import msgpack
import numpy as np
import orjson

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'data_split'))
from analyze_graph import DEFAULT_GRAPH, DRUG_CATEGORIES, DISEASE_CATEGORIES, node_masks

CHUNK = 1_000_000


def log(message):
    print(time.strftime('%H:%M:%S'), message, flush=True)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dump(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(data)
    return digest.hexdigest()


def snapshot(path):
    return {str(p.relative_to(path)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in path.rglob('*') if p.is_file()}


def read_array(path, name):
    return np.load(path / (name + '.npy'), mmap_mode='r', allow_pickle=False)


def new_array(path, name, dtype, size):
    return np.lib.format.open_memmap(path / (name + '.npy'), mode='w+',
                                   dtype=dtype, shape=(size,))


def ro_store(path, max_dbs=0):
    return lmdb.open(str(path), readonly=True, lock=False, max_dbs=max_dbs,
                     readahead=False)


def digest_record(digest, key, value):
    digest.update(key)
    digest.update(len(value).to_bytes(8, 'big'))
    digest.update(value)


def descriptors(attributes):
    result = set()
    for attr in attributes:
        if attr.get('original_attribute_name'):
            result.add((attr.get('attribute_type_id', 'biolink:Attribute'),
                        attr.get('attribute_source'), attr['original_attribute_name']))
    return result


def meta_attributes(items):
    result = []
    for type_id, source, name in sorted(items, key=lambda x: (x[0], x[1] or '', x[2])):
        attr = {'attribute_type_id': type_id, 'original_attribute_names': [name],
                'constraint_use': False}
        if source is not None:
            attr['attribute_source'] = source
        result.append(attr)
    return result


def copy_nodes(source, out, node_map):
    log('Copying and remapping nodes; collecting node metadata')
    n = int((node_map >= 0).sum())
    categories, category_names = np.zeros(n, dtype=np.int32), []
    category_ids, prefixes, attributes, counts = {}, defaultdict(set), defaultdict(set), Counter()
    with ro_store(source / 'node_store.lmdb', 3) as src:
        props_db = src.open_db(b'properties', create=False)
        ids_db = src.open_db(b'idx_to_id', create=False)
        with lmdb.open(str(out / 'node_store.lmdb'), max_dbs=3, map_size=16 * 1024**3) as dst:
            dbs = {name: dst.open_db(name.encode()) for name in ('properties', 'idx_to_id', 'id_to_idx')}
            written = 0
            with src.begin() as txn:
                cursor = txn.cursor(db=props_db)
                batch = []
                for key, raw in cursor:
                    old = int.from_bytes(key, 'big')
                    idx = int(node_map[old])
                    if idx < 0:
                        continue
                    curie = txn.get(key, db=ids_db)
                    require(curie is not None, f'Missing node ID: {old}')
                    props = msgpack.unpackb(raw, raw=False)
                    cats = props.get('categories') or ['biolink:NamedThing']
                    if isinstance(cats, str):
                        cats = [cats]
                    cat = cats[0]  # Same primary-category convention as Gandalf metadata.
                    if cat not in category_ids:
                        category_ids[cat] = len(category_names)
                        category_names.append(cat)
                    categories[idx] = category_ids[cat]
                    counts[cat] += 1
                    prefixes[cat].add(curie.decode().split(':')[0])
                    attributes[cat].update(descriptors(props.get('attributes', [])))
                    batch.append((idx.to_bytes(4, 'big'), curie, raw))
                    if len(batch) == 10_000:
                        with dst.begin(write=True) as write:
                            for new_key, node_id, value in batch:
                                write.put(new_key, value, db=dbs['properties'])
                                write.put(new_key, node_id, db=dbs['idx_to_id'])
                                write.put(node_id, new_key, db=dbs['id_to_idx'])
                        written += len(batch)
                        batch.clear()
                with dst.begin(write=True) as write:
                    for new_key, node_id, value in batch:
                        write.put(new_key, value, db=dbs['properties'])
                        write.put(new_key, node_id, db=dbs['idx_to_id'])
                        write.put(node_id, new_key, db=dbs['id_to_idx'])
                written += len(batch)
            require(written == n, 'Node copy count mismatch')
    # Compare every retained node's raw properties and ID maps independently.
    with ro_store(source / 'node_store.lmdb', 3) as src, ro_store(out / 'node_store.lmdb', 3) as dst:
        sp = src.open_db(b'properties', create=False)
        si = src.open_db(b'idx_to_id', create=False)
        dp = dst.open_db(b'properties', create=False)
        di = dst.open_db(b'idx_to_id', create=False)
        dr = dst.open_db(b'id_to_idx', create=False)
        with src.begin() as a, dst.begin() as b:
            for key, value in a.cursor(db=sp):
                idx = int(node_map[int.from_bytes(key, 'big')])
                if idx >= 0:
                    new_key = idx.to_bytes(4, 'big')
                    curie = a.get(key, db=si)
                    require(b.get(new_key, db=dp) == value and b.get(new_key, db=di) == curie
                            and b.get(curie, db=dr) == new_key, 'Node preservation failed')
    meta_nodes = {cat: {'id_prefixes': sorted(prefixes[cat]),
                        'attributes': meta_attributes(attributes[cat])} for cat in sorted(counts)}
    return categories, category_names, meta_nodes, counts


def copy_edge_store(source, out, name, edge_map, triple_codes=None, triple_attrs=None):
    """Stream raw retained values and verify a full destination content digest."""
    log(f'Copying {name} with new edge positions')
    count, digest = 0, hashlib.sha256()
    with ro_store(source / name) as src, lmdb.open(str(out / name), map_size=128 * 1024**3) as dst:
        write = dst.begin(write=True)
        try:
            with src.begin() as read:
                for key, value in read.cursor():
                    idx = int(edge_map[int.from_bytes(key, 'big')])
                    if idx < 0:
                        continue
                    new_key = idx.to_bytes(4, 'big')
                    write.put(new_key, value, append=True)
                    digest_record(digest, new_key, value)
                    if triple_codes is not None:
                        triple_attrs[int(triple_codes[idx])].update(descriptors(orjson.loads(value)))
                    count += 1
                    if count % 50_000 == 0:
                        write.commit()
                        write = dst.begin(write=True)
                    if count % 2_000_000 == 0:
                        log(f'  {name}: {count:,} retained records copied')
            write.commit()
        except BaseException:
            write.abort()
            raise
    expected = digest.hexdigest()
    actual, actual_count = hashlib.sha256(), 0
    with ro_store(out / name) as env:
        with env.begin() as txn:
            for key, value in txn.cursor():
                digest_record(actual, key, value)
                actual_count += 1
    require(actual.hexdigest() == expected and actual_count == count,
            f'{name}: full content verification failed')
    return {'records': count, 'retained_content_sha256': expected, 'verified': True}


def build(source, destination, labels, expected=None):
    started = time.monotonic()
    source, destination = source.resolve(), destination.resolve()
    staging = destination.with_name(destination.name + '.building')
    require(source != destination and source not in destination.parents,
            'Output must be separate from input')
    require(not destination.exists() and not staging.exists(), 'Output/staging already exists')
    require(shutil.disk_usage(destination.parent if destination.parent.exists() else ROOT).free
            > 50 * 1024**3, 'Need at least 50 GiB free for this build')
    original_snapshot = snapshot(source)
    with (source / 'metadata.pkl').open('rb') as stream:
        metadata = pickle.load(stream)
    require(metadata.get('edge_attributes_format') == 'json', 'Expected JSON edge attributes')
    arrays = {name: read_array(source, name) for name in (
        'fwd_offsets', 'fwd_targets', 'fwd_predicates', 'rev_offsets', 'rev_sources',
        'rev_predicates', 'rev_to_fwd', 'edge_sources_idx', 'edge_quals_idx', 'edge_kl_at_idx')}
    n, e = metadata['num_nodes'], len(arrays['fwd_targets'])
    log(f'Classifying {n:,} nodes and filtering {e:,} edges')
    drug, disease = node_masks(source, n)
    keep = np.zeros(e, dtype=bool)
    degrees = np.zeros(n, dtype=np.int64)
    outgoing = np.zeros(n, dtype=np.int64)
    for start in range(0, e, CHUNK):
        end = min(start + CHUNK, e)
        subjects = np.searchsorted(arrays['fwd_offsets'], np.arange(start, end), side='right') - 1
        objects = arrays['fwd_targets'][start:end]
        selected = ~((drug[subjects] & disease[objects]) | (disease[subjects] & drug[objects]))
        keep[start:end] = selected
        counts = np.bincount(subjects[selected], minlength=n)
        outgoing += counts
        degrees += counts + np.bincount(objects[selected], minlength=n)
    node_keep = degrees > 0
    nn, ne = int(node_keep.sum()), int(keep.sum())
    require(nn > 0 and ne > 0, 'Empty filtered graph')
    if expected is not None:
        require((nn, ne) == tuple(expected), f'Unexpected counts: {(nn, ne)} != {expected}')
    log(f'Retain {nn:,} nodes / {ne:,} edges; remove {n-nn:,} nodes / {e-ne:,} edges')
    staging.mkdir(parents=True)
    node_map = np.full(n, -1, dtype=np.int32)
    node_map[node_keep] = np.arange(nn, dtype=np.int32)
    edge_map = np.full(e, -1, dtype=np.int32)
    edge_map[keep] = np.arange(ne, dtype=np.int32)
    np.save(staging / 'original_node_to_filtered.npy', node_map)
    np.save(staging / 'original_edge_to_filtered.npy', edge_map)
    fwd_offsets = np.r_[0, np.cumsum(outgoing[node_keep])]
    np.save(staging / 'fwd_offsets.npy', fwd_offsets)
    for name in ('fwd_targets', 'fwd_predicates', 'edge_sources_idx', 'edge_quals_idx', 'edge_kl_at_idx'):
        output = new_array(staging, name, arrays[name].dtype, ne)
        pos = 0
        for start in range(0, e, CHUNK):
            end = min(start + CHUNK, e)
            values = arrays[name][start:end][keep[start:end]]
            if name == 'fwd_targets':
                values = node_map[values]
            output[pos:pos + len(values)] = values
            pos += len(values)
        output.flush()
        require(pos == ne, 'Forward array size mismatch')
    log('Rebuilding reverse indexes and property alignment')
    reverse = {name: new_array(staging, name, arrays[name].dtype, ne)
               for name in ('rev_sources', 'rev_predicates', 'rev_to_fwd')}
    incoming = np.zeros(nn, dtype=np.int64)
    pos = 0
    for start in range(0, e, CHUNK):
        end = min(start + CHUNK, e)
        old_fwd = arrays['rev_to_fwd'][start:end]
        selected = keep[old_fwd]
        old_objects = np.searchsorted(arrays['rev_offsets'], np.arange(start, end), side='right') - 1
        values = node_map[arrays['rev_sources'][start:end][selected]]
        size = len(values)
        reverse['rev_sources'][pos:pos+size] = values
        reverse['rev_predicates'][pos:pos+size] = arrays['rev_predicates'][start:end][selected]
        reverse['rev_to_fwd'][pos:pos+size] = edge_map[old_fwd[selected]]
        incoming += np.bincount(node_map[old_objects[selected]], minlength=nn)
        pos += size
    require(pos == ne, 'Reverse array size mismatch')
    for array in reverse.values():
        array.flush()
    np.save(staging / 'rev_offsets.npy', np.r_[0, np.cumsum(incoming)])
    shutil.copyfile(source / 'edge_property_pools.pkl', staging / 'edge_property_pools.pkl')
    require(sha256(source / 'edge_property_pools.pkl') == sha256(staging / 'edge_property_pools.pkl'),
            'Source/qualifier/knowledge-level pools differ')
    metadata['num_nodes'] = nn
    with (staging / 'metadata.pkl').open('wb') as stream:
        pickle.dump(metadata, stream)
    categories, category_names, meta_nodes, category_counts = copy_nodes(source, staging, node_map)
    log('Recomputing retained category/predicate triples and qualifier metadata')
    with (staging / 'edge_property_pools.pkl').open('rb') as stream:
        pools = pickle.load(stream)
    quals_pool = pools['quals_pool']
    del pools
    targets = read_array(staging, 'fwd_targets')
    predicates = read_array(staging, 'fwd_predicates')
    qualifiers = read_array(staging, 'edge_quals_idx')
    nc = len(category_names)
    npred = max(metadata['predicate_to_idx'].values()) + 1
    triple_codes = new_array(staging, 'edge_metadata_triples', np.int32, ne)
    require(nc * nc * npred < 2**31, 'Metadata triple encoding exceeds int32')
    triple_counts, examples, triple_quals = Counter(), {}, defaultdict(lambda: defaultdict(set))
    predicate_counts = Counter()
    for start in range(0, ne, CHUNK):
        end = min(start + CHUNK, ne)
        subjects = np.searchsorted(fwd_offsets, np.arange(start, end), side='right') - 1
        code = (categories[subjects] * npred + predicates[start:end]) * nc + categories[targets[start:end]]
        triple_codes[start:end] = code
        values, first, counts = np.unique(code, return_index=True, return_counts=True)
        triple_counts.update({int(k): int(v) for k, v in zip(values, counts)})
        for k, idx in zip(values, first):
            examples.setdefault(int(k), (int(subjects[idx]), int(targets[start+idx])))
        values, counts = np.unique(predicates[start:end], return_counts=True)
        predicate_counts.update({int(k): int(v) for k, v in zip(values, counts)})
        # Aggregate qualifiers once per distinct (category triple, qualifier pool) in each chunk.
        combos = np.unique(code.astype(np.int64) * len(quals_pool) + qualifiers[start:end])
        for combo in combos:
            triple, qidx = divmod(int(combo), len(quals_pool))
            for qualifier in quals_pool[qidx]:
                qtype, value = qualifier.get('qualifier_type_id'), qualifier.get('qualifier_value')
                if qtype:
                    bucket = triple_quals[triple][qtype]
                    if value is not None:
                        bucket.add(value)
    triple_codes.flush()
    del quals_pool
    triple_attrs = defaultdict(set)
    store_checks = {}
    store_checks['edge_ids'] = copy_edge_store(source, staging, 'edge_ids.lmdb', edge_map)
    require(store_checks['edge_ids']['records'] == ne, 'Expected an ID for every retained edge')
    store_checks['edge_attributes'] = copy_edge_store(
        source, staging, 'edge_properties.lmdb', edge_map, triple_codes, triple_attrs)
    id_to_predicate = {v: k for k, v in metadata['predicate_to_idx'].items()}
    def decode(code):
        subject_predicate, obj = divmod(code, nc)
        subject, predicate = divmod(subject_predicate, npred)
        return category_names[subject], id_to_predicate[predicate], category_names[obj]
    meta_edges, examples_out, summary_edges = [], [], []
    with ro_store(staging / 'node_store.lmdb', 3) as env:
        db = env.open_db(b'idx_to_id', create=False)
        with env.begin(db=db) as txn:
            for code in sorted(triple_counts, key=decode):
                subject, predicate, obj = decode(code)
                edge = {'subject': subject, 'predicate': predicate, 'object': obj,
                        'attributes': meta_attributes(triple_attrs[code])}
                qs = triple_quals[code]
                if qs:
                    edge['qualifiers'] = [{'qualifier_type_id': key, 'applicable_values': sorted(values)}
                                          for key, values in sorted(qs.items())]
                meta_edges.append(edge)
                s, o = examples[code]
                examples_out.append({'subject_category': subject, 'object_category': obj,
                                     'predicate': predicate,
                                     'subject_id': txn.get(s.to_bytes(4, 'big')).decode(),
                                     'object_id': txn.get(o.to_bytes(4, 'big')).decode()})
                summary_edges.append({'subject': subject, 'predicate': predicate, 'object': obj,
                                      'count': triple_counts[code]})
    dump(staging / 'meta_kg.json', {'nodes': meta_nodes, 'edges': meta_edges})
    dump(staging / 'sri_testing_data.json', {'edges': examples_out})
    dump(staging / 'graph-metadata.json', {
        '@type': 'Dataset', 'name': 'translator_kg_no_drug_disease',
        'node_count': nn, 'edge_count': ne,
        'predicate_count': len(predicate_counts), 'category_count': len(category_counts),
        'predicates': {id_to_predicate[k]: v for k, v in predicate_counts.items()},
        'categories': dict(category_counts),
        'description': 'Local derived graph: all drug/chemical--disease/phenotype edges and isolated nodes removed.',
        'isBasedOn': json.loads((source / 'graph-metadata.json').read_text()).get('@id', str(source)),
        'schema': {'nodes_summary': {'total_count': nn, 'primary_categories': dict(category_counts)},
                   'edges_summary': {'total_count': ne,
                                     'predicates': {id_to_predicate[k]: v for k, v in predicate_counts.items()}},
                   'edges': summary_edges}})
    log('Verifying all retained arrays, all reverse mappings, and forbidden-edge absence')
    verify = verify_graph(source, staging, arrays, node_map, edge_map, drug, disease, labels)
    require(snapshot(source) == original_snapshot, 'Source file sizes/mtimes changed during build')
    report = {
        'source': str(source), 'destination': str(destination),
        'original_nodes': n, 'original_edges': e, 'nodes': nn, 'edges': ne,
        'removed_nodes': n - nn, 'removed_edges': e - ne,
        'drug_categories': sorted(DRUG_CATEGORIES), 'disease_categories': sorted(DISEASE_CATEGORIES),
        'edge_filter': 'Both directions, all predicates, all sources; any matching node category.',
        'node_filter': 'Remove nodes with zero incident retained edges.',
        'metadata_category_convention': 'Primary category, matching Gandalf.',
        'store_checks': store_checks, 'verification': verify,
        'source_unchanged': True, 'seconds': round(time.monotonic() - started, 3),
        'source_build': json.loads((source / 'local-build-complete.json').read_text()),
    }
    dump(staging / 'filtering_report.json', report)
    staging.rename(destination)
    log(f'Built and verified {destination} in {report["seconds"]:.1f}s')
    return report


def verify_graph(source, out, original, node_map, edge_map, drug, disease, labels):
    arrays = {name: read_array(out, name) for name in original}
    nn, ne = len(arrays['fwd_offsets']) - 1, len(arrays['fwd_targets'])
    selected_nodes = node_map >= 0
    d, c = drug[selected_nodes], disease[selected_nodes]
    old_nodes = np.flatnonzero(selected_nodes)
    old_edges = np.flatnonzero(edge_map >= 0)
    for direction in ('fwd', 'rev'):
        offsets = arrays[f'{direction}_offsets']
        require(offsets[0] == 0 and offsets[-1] == ne and np.all(np.diff(offsets) >= 0),
                f'Invalid {direction} offsets')
    require(np.all(np.diff(arrays['fwd_offsets']) + np.diff(arrays['rev_offsets']) > 0),
            'Isolated nodes remain')
    for start in range(0, ne, CHUNK):
        end = min(start + CHUNK, ne)
        subjects = np.searchsorted(arrays['fwd_offsets'], np.arange(start, end), side='right') - 1
        objects = arrays['fwd_targets'][start:end]
        require(np.all((objects >= 0) & (objects < nn)), 'Invalid target')
        require(not np.any((d[subjects] & c[objects]) | (c[subjects] & d[objects])), 'Forbidden edge remains')
        old = old_edges[start:end]
        require(np.array_equal(old_nodes[subjects], np.searchsorted(original['fwd_offsets'], old, side='right') - 1),
                'Source remapping mismatch')
        require(np.array_equal(objects, node_map[original['fwd_targets'][old]]), 'Target remapping mismatch')
        for name in ('fwd_predicates', 'edge_sources_idx', 'edge_quals_idx', 'edge_kl_at_idx'):
            require(np.array_equal(arrays[name][start:end], original[name][old]), f'{name} mismatch')
        fwd = arrays['rev_to_fwd'][start:end]
        rev_objects = np.searchsorted(arrays['rev_offsets'], np.arange(start, end), side='right') - 1
        require(np.all((fwd >= 0) & (fwd < ne)), 'Invalid reverse map')
        require(np.array_equal(arrays['fwd_targets'][fwd], rev_objects), 'Reverse target mismatch')
        require(np.array_equal(arrays['fwd_predicates'][fwd], arrays['rev_predicates'][start:end]),
                'Reverse predicate mismatch')
        require(np.array_equal(np.searchsorted(arrays['fwd_offsets'], fwd, side='right') - 1,
                               arrays['rev_sources'][start:end]), 'Reverse subject mismatch')
    # Every forward record must have exactly one reverse entry, even parallel edges.
    require(np.all(np.bincount(arrays['rev_to_fwd'], minlength=ne) == 1), 'Reverse mapping is not bijective')
    label_counts, seen, hashes = {}, set(), {}
    with ro_store(out / 'node_store.lmdb', 3) as env:
        db = env.open_db(b'id_to_idx', create=False)
        with env.begin(db=db) as txn:
            for split in ('train', 'val', 'test'):
                path = labels / f'{split}.csv'
                hashes[split] = sha256(path)
                with path.open(newline='') as stream:
                    rows = list(csv.DictReader(stream))
                label_counts[split] = len(rows)
                for row in rows:
                    pair = row['drug_id'], row['disease_id']
                    require(pair not in seen, 'Label pairs overlap')
                    seen.add(pair)
                    for curie in pair:
                        require(txn.get(curie.encode()) is not None, f'Missing label endpoint: {curie}')
    return {'forbidden_edges': 0, 'isolated_nodes': 0, 'all_reverse_mappings_verified': True,
            'all_retained_array_records_verified': True, 'all_retained_node_records_verified': True,
            'label_pairs': label_counts, 'total_label_pairs': len(seen), 'label_csv_sha256': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_GRAPH)
    parser.add_argument('--out', type=Path, default=ROOT / 'artifacts/gandalf_no_drug_disease')
    parser.add_argument('--labels', type=Path, default=ROOT / 'data_split/nonisolated')
    args = parser.parse_args()
    report = build(args.source, args.out, args.labels, expected=(1_685_344, 27_435_282))
    require(report['verification']['total_label_pairs'] == 8345, 'Expected 8,345 label pairs')


if __name__ == '__main__':
    main()
