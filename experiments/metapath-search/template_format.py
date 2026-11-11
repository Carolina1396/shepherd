"""Two-hop candidate format and exact qualifier matching; standard library only.

TRAPI 2-style constraints.qualifiers: OR over sets, AND within a set.
This is a format/matching contract, not a retrieval or scoring implementation.
"""
from copy import deepcopy
import hashlib
import json


def qualifier_sets(edge):
    """Validate constraints, returning [] for an explicitly unconstrained edge."""
    constraints = edge.get('constraints', {})
    if not isinstance(constraints, dict) or set(constraints) - {'qualifiers'}:
        raise ValueError('Only constraints.qualifiers is supported in version 1')
    sets = constraints.get('qualifiers', [])
    if not isinstance(sets, list):
        raise ValueError('constraints.qualifiers must be a list')
    for group in sets:
        if not isinstance(group, dict) or not group:
            raise ValueError('Each qualifier set must be a nonempty mapping')
        for name, value in group.items():
            if not isinstance(name, str) or not name.startswith('biolink:'):
                raise ValueError('Qualifier names must be Biolink CURIEs')
            if not isinstance(value, str) or not value.strip():
                raise ValueError('Qualifier values must be nonempty strings')
    return sets


def matches_qualifiers(stored_qualifiers, query_edge):
    """Match ONE stored edge record's qualifier list, never union parallel edges.

No constraints accepts qualified and unqualified edges. A requested qualifier
must be explicitly present with the exact value. Extra stored qualifiers are
allowed. No hierarchy expansion, missing-value inference, or value synonyms.
"""
    groups = qualifier_sets(query_edge)
    if not groups:
        return True
    values = {}
    for q in stored_qualifiers or []:
        values.setdefault(q['qualifier_type_id'], set()).add(q['qualifier_value'])
    return any(all(v in values.get(k, set()) for k, v in group.items()) for group in groups)


def validate_template(template):
    if not isinstance(template, dict) or set(template) != {'id', 'intermediate_category', 'edges'}:
        raise ValueError('Template needs exactly id, intermediate_category, edges')
    if not isinstance(template['id'], str) or not template['id'].strip():
        raise ValueError('Template id must be nonempty')
    cat = template['intermediate_category']
    if not isinstance(cat, str) or not cat.startswith('biolink:'):
        raise ValueError('Intermediate category must be a Biolink CURIE')
    edges = template['edges']
    if not isinstance(edges, dict) or set(edges) != {'drug_edge', 'disease_edge'}:
        raise ValueError('Exactly drug_edge and disease_edge are required')
    for name, endpoint in [('drug_edge', 'drug'), ('disease_edge', 'disease')]:
        edge = edges[name]
        if not isinstance(edge, dict) or not {'subject', 'object', 'predicate'} <= set(edge) or set(edge) - {'subject', 'object', 'predicate', 'constraints'}:
            raise ValueError('Unsupported edge fields')
        if {edge['subject'], edge['object']} != {endpoint, 'intermediate'}:
            raise ValueError('Edges must form drug--intermediate--disease; entity IDs are forbidden')
        if not isinstance(edge['predicate'], str) or not edge['predicate'].startswith('biolink:'):
            raise ValueError('Predicate must be a Biolink CURIE')
        qualifier_sets(edge)
    return template


def validate_collection(collection):
    if not isinstance(collection, dict) or set(collection) != {'format_version', 'templates'} or collection['format_version'] != 1:
        raise ValueError('Expected format_version=1 and templates')
    if not isinstance(collection['templates'], list):
        raise ValueError('templates must be a list')
    seen = set()
    for t in collection['templates']:
        validate_template(t)
        if t['id'] in seen:
            raise ValueError('Duplicate template id')
        seen.add(t['id'])
    return collection


def template_hash(template):
    """Stable semantic hash: includes constraints; excludes descriptive id."""
    validate_template(template)
    obj = deepcopy(template)
    obj.pop('id')
    for edge in obj['edges'].values():
        groups = qualifier_sets(edge)
        canonical = sorted({json.dumps(g, sort_keys=True, separators=(',', ':')) for g in groups})
        edge.pop('constraints', None)
        if canonical:
            edge['constraints'] = {'qualifiers': [json.loads(g) for g in canonical]}
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def make_query(template, disease_id):
    """Construct an explicit lookup query, not an inferred/AMIE expansion query.

Qualifier meanings remain relative to each edge's actual subject/object.
Service hierarchy and distinct-node semantics need independent verification.
"""
    validate_template(template)
    edges = {}
    for name, edge in template['edges'].items():
        converted = {k:deepcopy(edge[k]) for k in ('subject', 'object')}
        converted.update(predicates=[edge['predicate']], knowledge_type='lookup')
        if qualifier_sets(edge):
            converted['constraints'] = deepcopy(edge['constraints'])
        edges[name] = converted
    return {'message': {'query_graph': {'nodes': {
        'drug': {'categories': ['biolink:ChemicalEntity']},
        'intermediate': {'categories': [template['intermediate_category']]},
        'disease': {'categories': ['biolink:DiseaseOrPhenotypicFeature'], 'ids': [disease_id]},
    }, 'edges': edges}}, 'parameters': {'tiers': [0]}}
