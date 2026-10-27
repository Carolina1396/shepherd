"""Pure helpers for the ten-disease service/local answer-set comparison."""
import ast
import copy
import json
import logging
from pathlib import Path
from string import Template


def make_query(disease, timeout=120):
    return {'message': {'query_graph': {
        'nodes': {'drug': {'categories': ['biolink:Drug', 'biolink:ChemicalEntity', 'biolink:SmallMolecule']},
                  'disease': {'ids': [disease], 'categories': ['biolink:Disease']}},
        'edges': {'treats': {'subject': 'drug', 'object': 'disease',
                           'predicates': ['biolink:treats'], 'knowledge_type': 'inferred'}}}},
        'workflow': [{'id': 'aragorn.lookup'}],
        'parameters': {'tiers': [0], 'gandalf': True, 'subclass': False, 'timeout': timeout,
                       'bypass_cache': True, 'log_level': 'INFO'},
        'submitter': 'shepherd-ultra-ten-disease-parity'}


def worker_expansion(query, worker_path):
    """Execute the checkout's pure expansion helpers without worker startup/DB imports.

    This is only an expansion audit. Actual service answers are obtained by HTTP.
    """
    tree = ast.parse(worker_path.read_text(), filename=str(worker_path))
    names = {'get_infer_parameters', 'get_rule_key', 'expand_aragorn_query'}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names
             or isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'RULE_KEY_QUALIFIERS' for t in n.targets)]
    namespace = {'json': json, 'copy': copy, 'logging': logging, 'Path': Path,
                 'Template': Template, '__file__': str(worker_path)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(worker_path), 'exec'), namespace)
    return namespace['expand_aragorn_query'](copy.deepcopy(query), logging.getLogger('parity.expansion'))


def binding_ids(binding):
    if isinstance(binding, dict):
        if 'ids' in binding:
            return set(binding['ids'])
        return {binding['id']} if binding.get('id') else set()
    if isinstance(binding, list):
        return set().union(*(binding_ids(item) for item in binding)) if binding else set()
    raise ValueError(f'Unsupported node binding: {type(binding).__name__}')


def extract_answers(response, answer_node='drug'):
    message = response.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('results'), list):
        raise ValueError('No valid TRAPI result list')
    answers = set()
    for result in message['results']:
        bindings = result.get('node_bindings') or {}
        if answer_node not in bindings:
            raise ValueError(f'Result missing answer node {answer_node}')
        answers.update(binding_ids(bindings[answer_node]))
    return answers


def response_issues(response):
    issues = []
    status = response.get('status')
    if status and str(status).lower() not in ('success', 'ok', 'completed'):
        issues.append(f'status={status}')
    for entry in response.get('logs') or []:
        message = str(entry.get('message', ''))
        lowered = message.lower()
        if str(entry.get('level', '')).upper() in ('ERROR', 'CRITICAL') or any(
                word in lowered for word in ('timed out', 'timeout', 'truncat', 'abandoned')):
            # A configured timeout alone does not indicate a failed query.
            if 'timed out' in lowered or 'truncat' in lowered or 'abandoned' in lowered or str(entry.get('level', '')).upper() in ('ERROR', 'CRITICAL'):
                issues.append(message)
    return issues


def compare_answers(local, service):
    union = local | service
    return {'local_answers': len(local), 'service_answers': len(service),
            'intersection': len(local & service), 'exact_answer_set_match': local == service,
            'both_empty': not union, 'jaccard': len(local & service)/len(union) if union else 1.0,
            'only_local': sorted(local-service), 'only_service': sorted(service-local)}
