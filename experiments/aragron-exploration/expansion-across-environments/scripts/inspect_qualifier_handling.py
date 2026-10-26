"""Offline diagnostic of the saved unknown-constraints warnings.

Uses saved callback graphs, a pinned Retriever validator, the installed TOM
models, and a local Gandalf checkout. No queries are submitted to services.
This is a component reproduction, not proof of deployed image contents.
"""
import argparse
import ast
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

from analyze import expected_graphs, parse_callbacks, RULE_KEY

ROOT = Path(__file__).resolve().parent.parent
SELECTED = (12, 13, 16, 18)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def without_qualifiers(graph):
    graph = copy.deepcopy(graph)
    for edge in graph['edges'].values():
        constraints = edge.get('constraints', {})
        constraints.pop('qualifiers', None)
        if not constraints:
            edge.pop('constraints', None)
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gandalf-source', type=Path, required=True)
    parser.add_argument('--output', type=Path,
                        default=ROOT / 'output/qualifier-investigation')
    args = parser.parse_args()
    sys.path.insert(0, str(args.gandalf_source.resolve()))
    from gandalf.search.edge_constraints import EdgeConstraints
    from translator_tom.v1_6 import Biolink, Message, QEdge, QEdgeID, Query, QueryGraph

    # Execute the actual standalone validation function without importing the
    # Retriever application or initializing its database/network dependencies.
    validator = args.output / 'source/src__retriever__lookup__validate.py'
    tree = ast.parse(validator.read_text())
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'validate_qedge')
    namespace = dict(Biolink=Biolink, QueryGraph=QueryGraph, QEdgeID=QEdgeID, QEdge=QEdge)
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(validator), 'exec'), namespace)
    validate_qedge = namespace['validate_qedge']

    run = ROOT / 'output/run_002'
    cases, checks, input_hashes = [], [], {}
    warning_totals = {}
    for environment in ('development', 'ci_staging', 'test', 'production'):
        folder = run / environment
        if not folder.exists():
            raise RuntimeError(f'Missing environment: {folder}')
        rule_path = folder / 'release-rules.json'
        rules = json.loads(rule_path.read_text())[RULE_KEY]
        input_hashes[str(rule_path.relative_to(ROOT))] = sha256(rule_path)
        warning_totals[environment] = {}
        for response_path in sorted(folder.glob('q*/response.json')):
            request_path = response_path.with_name('request.json')
            request = json.loads(request_path.read_text())
            response = json.loads(response_path.read_text())
            for path in (request_path, response_path):
                input_hashes[str(path.relative_to(ROOT))] = sha256(path)
            callbacks, errors = parse_callbacks(response['logs'], expected_graphs(request, rules))
            assert not errors, errors
            by_rule = {row['rule']: row for row in callbacks if row.get('rule') is not None}
            assert len(by_rule) == 19
            for number, row in by_rule.items():
                warnings = [w for w in row['warnings_errors']
                            if 'skipping unknown fields (constraints)' in w]
                warning_totals[environment][number] = warning_totals[environment].get(number, 0) + len(warnings)
            if environment != 'development':
                continue
            graphs = [by_rule[n]['query_graph'] for n in SELECTED]
            same_without = all(without_qualifiers(g) == without_qualifiers(graphs[0]) for g in graphs)
            assert same_without
            cases.append(dict(query=response_path.parent.name,
                              target=request['message']['query_graph']['nodes']['disease']['ids'][0],
                              same_graph_after_removing_only_qualifiers=same_without,
                              raw_counts={n: by_rule[n]['result_count'] for n in SELECTED},
                              callback_ids={n: by_rule[n]['callback_id'] for n in SELECTED}))
            for number in SELECTED:
                graph = by_rule[number]['query_graph']
                parsed = Query.model_validate({'message': {'query_graph': graph}})
                qgraph = parsed.message.query_graph.model_copy(deep=True)
                # Equivalent model assembly/serialization to GandalfQuery and
                # GandalfDriver; Retriever's additional parameters are irrelevant
                # to the QEdge fields under examination here.
                outbound = Query.model_construct(message=Message.model_construct(query_graph=qgraph))
                wire_graph = json.loads(outbound.to_json(as_str=True))['message']['query_graph']
                for edge_id in ('edge_1', 'edge_2'):
                    edge = qgraph.edges[edge_id]
                    before = edge.to_dict()
                    warnings, problems = validate_qedge(qgraph, edge_id, edge)
                    assert all(problems.values()), problems
                    expected_warning = f'Edge `{edge_id}`: skipping unknown fields (constraints)'
                    assert expected_warning in warnings
                    assert edge.to_dict() == before
                    wire = wire_graph['edges'][edge_id]
                    assert wire['constraints'] == graph['edges'][edge_id]['constraints']
                    constraints = EdgeConstraints.parse(wire)
                    values = wire['constraints']['qualifiers'][0]
                    props = {'qualifiers': [dict(qualifier_type_id=k, qualifier_value=v)
                                            for k, v in values.items()]}
                    wrong = copy.deepcopy(props)
                    for qualifier in wrong['qualifiers']:
                        if qualifier['qualifier_type_id'] == 'biolink:object_direction_qualifier':
                            qualifier['qualifier_value'] = ('increased' if qualifier['qualifier_value'] == 'decreased' else 'decreased')
                    matched = constraints.permits(None, props, 0)
                    wrong_matched = constraints.permits(None, wrong, 0)
                    absent_matched = constraints.permits(None, {'qualifiers': []}, 0)
                    unqualified_matched = EdgeConstraints.parse({}).permits(None, wrong, 0)
                    assert matched and not wrong_matched and not absent_matched and unqualified_matched
                    checks.append(dict(query=response_path.parent.name, rule=number, edge=edge_id,
                                       reproduced_warning=expected_warning,
                                       retriever_recognized_qualifiers=list(edge.qualifier_constraints_list),
                                       constraints_preserved=True, gandalf_parsed_qualifiers=list(constraints.qualifiers),
                                       matching_edge_accepted=matched, wrong_direction_accepted=wrong_matched,
                                       missing_qualifiers_accepted=absent_matched,
                                       wrong_direction_accepted_without_constraints=unqualified_matched))

    commit = subprocess.check_output(['git', '-C', str(args.gandalf_source), 'rev-parse', 'HEAD'], text=True).strip()
    source_paths = [args.gandalf_source / f'gandalf/search/{name}.py'
                    for name in ('edge_constraints', 'qualifiers', 'lookup')]
    output = dict(
        translator_tom_version=importlib.metadata.version('translator-tom'),
        gandalf_commit=commit,
        gandalf_source_hashes={str(p): sha256(p) for p in source_paths},
        retriever_validator_sha256=sha256(validator),
        input_hashes=input_hashes,
        observed_warning_totals=warning_totals,
        observed_comparisons=cases,
        component_checks=checks,
        limitations=[
            'The deployed Retriever, TOM and Gandalf revisions are not independently verified.',
            'Component checks exercise serialization, the actual validation function, and direct qualifier matching; not a hosted request or full graph traversal.',
            'Controlled matcher checks use literal qualifier values before Biolink descendant expansion.',
            'Saved rule comparisons are observational, not randomized or replayed controls.',
            'These findings do not establish that every qualifier condition was enforced in every hosted callback.',
        ],
    )
    args.output.mkdir(parents=True, exist_ok=True)
    path = args.output / 'diagnostic.json'
    path.write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(dict(output=str(path), component_checks=len(checks),
                          observed_comparisons=cases, warning_totals=warning_totals), indent=2))


if __name__ == '__main__':
    main()
