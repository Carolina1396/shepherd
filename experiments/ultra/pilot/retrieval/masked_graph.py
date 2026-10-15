"""Read-only masked CSR view; native Gandalf sampler and lookup remain unchanged."""
import copy
import numpy as np
from gandalf import CSRGraph


class RemappedDetails:
    def __init__(self, original, indices):
        self.original, self.indices = original, indices

    def get(self, index):
        return self.original.get(int(self.indices[index]))

    def _batch(self, indices, method):
        mapping = {int(i): int(self.indices[i]) for i in indices}
        values = getattr(self.original, method)(mapping.values())
        return {i: values[j] for i, j in mapping.items() if j in values}

    def get_batch(self, indices):
        return self._batch(indices, 'get_batch')

    def get_json_batch(self, indices):
        return self._batch(indices, 'get_json_batch')


class MaskedCSRGraph(CSRGraph):
    def get_edge_ids_batch(self, indices):
        mapping = {int(i): int(self.original_indices[i]) for i in indices}
        ids = self.original_graph.get_edge_ids_batch(mapping.values())
        return {i: ids[j] for i, j in mapping.items() if j in ids}

    def get_edge_id(self, index):
        return self.original_graph.get_edge_id(int(self.original_indices[index]))


def mask_pairs(graph, hidden):
    """Remove held-out unordered pairs under all predicates, preserving record weights."""
    n = graph.num_nodes
    keys = np.array(sorted({min(h, t)*n+max(h, t) for h, t in hidden}), dtype=np.int64)
    keep = np.ones(len(graph.fwd_targets), dtype=bool)
    for start in range(0, len(keep), 1_000_000):
        end = min(start+1_000_000, len(keep))
        heads = np.searchsorted(graph.fwd_offsets, np.arange(start, end), side='right')-1
        tails = graph.fwd_targets[start:end].astype(np.int64)
        encoded = np.minimum(heads, tails)*n+np.maximum(heads, tails)
        if len(keys):
            positions = np.searchsorted(keys, encoded)
            keep[start:end] = ~((positions < len(keys)) & (keys[np.minimum(positions, len(keys)-1)] == encoded))
    masked = MaskedCSRGraph.__new__(MaskedCSRGraph)
    masked.__dict__.update(graph.__dict__)
    masked.original_graph = graph
    masked.original_indices = np.flatnonzero(keep)
    cumulative = np.concatenate(([0], np.cumsum(keep, dtype=np.int64)))
    masked.fwd_offsets = cumulative[graph.fwd_offsets]
    masked.fwd_targets = np.asarray(graph.fwd_targets)[keep]
    masked.fwd_predicates = np.asarray(graph.fwd_predicates)[keep]
    reverse_keep = keep[graph.rev_to_fwd]
    masked.rev_offsets = np.concatenate(([0], np.cumsum(reverse_keep, dtype=np.int64)))[graph.rev_offsets]
    masked.rev_sources = np.asarray(graph.rev_sources)[reverse_keep]
    masked.rev_predicates = np.asarray(graph.rev_predicates)[reverse_keep]
    masked.rev_to_fwd = (cumulative[graph.rev_to_fwd[reverse_keep]+1]-1).astype(np.int32)
    masked.edge_properties = copy.copy(graph.edge_properties)
    for name in ('_sources_idx', '_quals_idx', '_kl_at_idx'):
        setattr(masked.edge_properties, name, np.asarray(getattr(graph.edge_properties, name))[keep])
    if graph.lmdb_store is not None:
        masked.lmdb_store = RemappedDetails(graph.lmdb_store, masked.original_indices)
    assert len(masked.fwd_targets) == len(masked.rev_sources)
    assert int(masked.fwd_offsets[-1]) == len(masked.fwd_targets)
    # Every reverse edge must map to the correct surviving forward edge.
    for start in range(0, len(masked.rev_sources), 1_000_000):
        end = min(start+1_000_000, len(masked.rev_sources))
        positions = masked.rev_to_fwd[start:end]
        targets = np.searchsorted(masked.rev_offsets, np.arange(start, end), side='right')-1
        assert np.array_equal(masked.fwd_targets[positions], targets)
        assert np.array_equal(masked.fwd_predicates[positions], masked.rev_predicates[start:end])
        heads = np.searchsorted(masked.fwd_offsets, positions, side='right')-1
        assert np.array_equal(heads, masked.rev_sources[start:end])
    return masked, int((~keep).sum())
