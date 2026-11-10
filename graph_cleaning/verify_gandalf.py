"""Load the filtered graph with installed Gandalf and run real lookup smoke tests.

No service is started or reconfigured. BMT may fetch the pinned Biolink schema.
Outputs requests, responses, and a machine-readable verification report.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('GANDALF_OTEL_ENABLED', 'false')
os.environ.setdefault('GANDALF_BIOLINK_VERSION', '4.4.4')
os.environ.setdefault('GANDALF_LOAD_MMAPS_INTO_MEMORY', 'false')
ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph', type=Path, default=ROOT / 'artifacts/gandalf_no_drug_disease')
    args = parser.parse_args()
    from gandalf.graph import CSRGraph
    from gandalf.biolink import make_toolkit
    from gandalf.search.lookup import lookup
    from gandalf.models import MetadataResponse

    print('Loading filtered graph with Gandalf...', flush=True)
    started = time.monotonic()
    graph = CSRGraph.load_mmap(args.graph, mmap_mode='r')
    assert graph.num_nodes == 1_685_344
    assert len(graph.fwd_targets) == 27_435_282
    MetadataResponse.model_validate(graph.graph_metadata)
    print(f'Graph loaded in {time.monotonic()-started:.1f}s; preparing Biolink 4.4.4...', flush=True)
    bmt = make_toolkit()
    queries = [('retained_gene_gene', 'NCBIGene:7157', 'NCBIGene:4193', True)]
    for split in ('train', 'val', 'test'):
        with (ROOT / 'data_split/nonisolated' / f'{split}.csv').open(newline='') as stream:
            row = next(csv.DictReader(stream))
        queries.append((f'forbidden_{split}_pair', row['drug_id'], row['disease_id'], False))
    output = args.graph / 'smoke_queries'
    output.mkdir(exist_ok=True)
    results = []
    for name, subject, obj, positive in queries:
        query = {'message': {'query_graph': {
            'nodes': {'n0': {'ids': [subject]}, 'n1': {'ids': [obj]}},
            'edges': {'e0': {'subject': 'n0', 'object': 'n1', 'knowledge_type': 'lookup'}}}},
            'parameters': {'subclass': False}}
        (output / f'{name}.request.json').write_text(json.dumps(query, indent=2) + '\n')
        began = time.monotonic()
        response = lookup(graph, query, bmt=bmt, subclass=False, dehydrated=False)
        (output / f'{name}.response.json').write_text(json.dumps(response, indent=2) + '\n')
        assert response.get('status') in (None, 'Success', 'OK'), response.get('status')
        message = response['message']
        count = len(message.get('results') or [])
        edges = message.get('knowledge_graph', {}).get('edges', {})
        assert bool(count) == positive, (name, count)
        if positive:
            assert edges and all(e.get('sources') for e in edges.values())
        else:
            assert not edges
        row = {'name': name, 'results': count, 'edges': len(edges),
               'seconds': round(time.monotonic()-began, 3), 'passed': True}
        results.append(row)
        print(json.dumps(row), flush=True)
    report = {'gandalf_module': sys.modules['gandalf.graph'].__file__,
              'biolink_version': '4.4.4', 'nodes': graph.num_nodes,
              'edges': len(graph.fwd_targets), 'metadata_model_valid': True,
              'tests': results, 'seconds': round(time.monotonic()-started, 3)}
    (args.graph / 'gandalf_verification.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()
