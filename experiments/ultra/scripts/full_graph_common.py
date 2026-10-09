"""Shared split, masking, and ranking rules for full-graph treatment evaluation."""
from collections import defaultdict
import hashlib
import json
import random

import numpy as np


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def split_pairs(pairs, seed=731):
    if len(pairs) != len(set(pairs)):
        raise ValueError("Duplicate treatment pairs")
    ordered = sorted(pairs)
    random.Random(seed).shuffle(ordered)
    n_visible, n_validation = int(0.8 * len(ordered)), int(0.1 * len(ordered))
    return [(h, t, "visible" if i < n_visible else "validation" if i < n_visible + n_validation else "test")
            for i, (h, t) in enumerate(ordered)]


def hidden_pair_mask(heads, tails, hidden, num_nodes):
    """True for every direct connection of a hidden pair, in either direction."""
    keys = np.unique([min(h, t) * num_nodes + max(h, t) for h, t in hidden])
    if not len(keys):
        return np.zeros(len(heads), dtype=bool)
    query = np.minimum(heads, tails) * num_nodes + np.maximum(heads, tails)
    positions = np.searchsorted(keys, query)
    return (positions < len(keys)) & (keys[np.minimum(positions, len(keys) - 1)] == query)


def filtered_rank(scores, target, known):
    keep = np.ones(len(scores), dtype=bool)
    keep[list(known)] = False
    keep[target] = False
    return 1 + int(np.count_nonzero((scores >= scores[target]) & keep))


def summarize(rows, field):
    if not rows:
        return {"answers": 0}
    ranks = np.array([row[field] for row in rows])
    by_disease = defaultdict(list)
    for row in rows:
        by_disease[row["disease"]].append(1 / row[field])
    return {"answers": len(rows), "mrr": float(np.mean(1 / ranks)),
            "hits_at_1": float(np.mean(ranks <= 1)), "hits_at_3": float(np.mean(ranks <= 3)),
            "hits_at_10": float(np.mean(ranks <= 10)), "top_10_answers": int(np.sum(ranks <= 10)),
            "diseases": len(by_disease),
            "disease_macro_mrr": float(np.mean([np.mean(v) for v in by_disease.values()]))}
