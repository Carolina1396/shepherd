"""Offline inspection of the release merge filters; does not replay live callbacks.

Extract only the inspected, pure get_promiscuous_qnodes function from saved release
source. Never import or execute the module, worker startup, or network code.
"""
import argparse
import ast
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path

from analyze import expected_graphs

ROOT = Path(__file__).resolve().parent.parent


def inspect_run(output):
    rows = []
    for env in ('development', 'ci_staging', 'test', 'production'):
        directory = output / env
        source = directory / 'release-merge-worker.py'
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'get_promiscuous_qnodes')
        # Restrict extraction to this known pure graph inspection function.
        allowed_calls = {'len', 'defaultdict', 'combinations'}
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id not in allowed_calls:
                    raise ValueError('Unexpected call in release graph inspection function')
                if isinstance(node.func, ast.Attribute) and node.func.attr not in {'items', 'append', 'get'}:
                    raise ValueError('Unexpected method in release graph inspection function')
        namespace = {'defaultdict': defaultdict, 'combinations': combinations}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), namespace)
        request = json.loads((directory / 'q01/request.json').read_text())
        rules = json.loads((directory / 'release-rules.json').read_text())['{"predicate": "biolink:treats"}']
        for number, graph in expected_graphs(request, rules).items():
            if number:
                nodes = namespace['get_promiscuous_qnodes']({'message': {'query_graph': graph}})
                rows.append({'environment':env, 'rule':number, 'candidate_filter_nodes':nodes,
                             'reference_file':str(source.relative_to(output)), 'function_line':function.lineno})
    differences = []
    for number in range(1, 19):
        observed = {r['environment']: r['candidate_filter_nodes'] for r in rows if r['rule'] == number}
        if len({tuple(v) for v in observed.values()}) > 1:
            differences.append({'rule':number, **observed})
    report = {'differences': differences, 'all_rules': rows,
        'interpretation': 'Older release source compares QEdge qualifiers rather than qualifier_constraints; missing fields compare equal. Development compares constraints.qualifiers, so differing qualifier values can exclude a shared node from this filter.',
        'threshold': 'The inspected release filter removes results through a candidate node when its result frequency exceeds MAX_C=10.',
        'limitations': ['Reference-source behavior, not a verified deployed image.',
                       'This identifies which variables are candidates for filtering, not how many raw results were removed.',
                       'Equal live callback counts do not prove equal callback contents.',
                       'The observed final-answer difference is consistent with this filter difference; a causal replay would require raw callback bodies.']}
    (output / 'merge-filter-diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(differences, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output/run_002')
    inspect_run(parser.parse_args().output)
