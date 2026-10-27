"""Eight fixed masking conditions for labeled chemical–disease endpoint pairs."""
from pathlib import Path
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from full_graph_common import digest, hidden_pair_mask, save

# (visible treats, visible other predicates, held-out other predicates).
# Held-out treats are always removed. Unlabeled endpoint pairs are unchanged.
CONDITIONS = {
    1: (True, True, False), 2: (True, True, True),
    3: (True, False, False), 4: (True, False, True),
    5: (False, True, False), 6: (False, True, True),
    7: (False, False, False), 8: (False, False, True),
}


def read(path):
    return json.loads(Path(path).read_text())


def policy(row):
    vt, vo, ho = CONDITIONS[row]
    return dict(visible_treats=vt, visible_other=vo, heldout_treats=False, heldout_other=ho,
                scope='Labeled endpoint pairs only; both directions; unlabeled pairs unchanged')


def edge_groups(triples, labels, n):
    visible = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] == 'visible'}
    hidden = {(r['drug_index'], r['disease_index']) for r in labels if r['split'] != 'visible'}
    assert {frozenset(p) for p in visible}.isdisjoint({frozenset(p) for p in hidden})
    groups = np.zeros(len(triples), dtype=np.uint8)
    groups[hidden_pair_mask(triples[:, 0], triples[:, 2], visible, n)] = 1
    groups[hidden_pair_mask(triples[:, 0], triples[:, 2], hidden, n)] = 2
    return groups


def keep_edges(groups, is_treats, row):
    vt, vo, ho = CONDITIONS[row]
    return ((groups == 0) | ((groups == 1) & np.where(is_treats, vt, vo))
            | ((groups == 2) & ~is_treats & ho))


def independent_keep(triples, labels, n, target, row):
    """Separate directed-key membership implementation used by the full audit."""
    visible, hidden = set(), set()
    for r in labels:
        h, t = r['drug_index'], r['disease_index']
        group = visible if r['split'] == 'visible' else hidden
        group.update((h * n + t, t * n + h))
    keys = triples[:, 0] * n + triples[:, 2]
    v = np.isin(keys, np.asarray(sorted(visible), dtype=np.int64))
    h = np.isin(keys, np.asarray(sorted(hidden), dtype=np.int64))
    target_edge = triples[:, 1] == target
    vt, vo, ho = CONDITIONS[row]
    remove = h & target_edge
    if not vt:
        remove |= v & target_edge
    if not vo:
        remove |= v & ~target_edge
    if not ho:
        remove |= h & ~target_edge
    return ~remove
