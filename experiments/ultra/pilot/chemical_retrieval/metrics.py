"""Pair-weighted coverage and auditable whole-match selection."""
import random


def select_matches(groups, edge_cap, seed):
    rng = random.Random(seed)
    queues = [list(units) for units in groups]
    for units in queues:
        rng.shuffle(units)
    order = list(range(len(queues)))
    rng.shuffle(order)
    edges, answers = set(), set()
    retained = [[] for _ in groups]
    while any(queues):
        for i in order:
            if not queues[i]:
                continue
            unit = queues[i].pop()
            new = {tuple(e) for e in unit['edges']}
            if len(edges | new) <= edge_cap:
                edges.update(new)
                answers.update(unit.get('answers', []))
                retained[i].append(unit)
    return edges, answers, retained


def measure(edges, anchor, candidates, answers, bound):
    nodes = {anchor} | {x for h, p, t in edges for x in (h, t)}
    reached = nodes & candidates
    recovered = answers & reached
    returned = answers & bound
    return {'nodes': len(nodes), 'edges': len(edges), 'candidate_nodes': len(reached),
            'answer_pairs': len(answers), 'answers_reached': len(recovered),
            'answer_coverage': len(recovered)/len(answers) if answers else None,
            'answers_bound': len(returned),
            'bound_answer_coverage': len(returned)/len(answers) if answers else None,
            'recovered_answer_indices': sorted(recovered),
            'bound_answer_indices': sorted(returned)}
