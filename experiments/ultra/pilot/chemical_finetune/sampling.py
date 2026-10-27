"""Uniform typed negatives without allocating one million-node pool per disease."""
from collections import defaultdict
import numpy as np


class NegativeSampler:
    def __init__(self, labels, candidates):
        self.train = [row for row in labels if row['split'] == 'visible']
        self.candidates = np.asarray([row['index'] for row in candidates], dtype=np.int64)
        if not self.train or not len(self.candidates):
            raise ValueError('Training requires visible positives and candidates')
        if len(np.unique(self.candidates)) != len(self.candidates):
            raise ValueError('Candidate IDs must be unique')
        known = defaultdict(set)
        for row in self.train:
            known[row['disease_index']].add(row['drug_index'])
        positives = np.array(sorted(set().union(*known.values())), dtype=np.int64)
        if not np.isin(positives, self.candidates).all():
            raise ValueError('A visible positive is outside the candidate pool')
        if any(len(answers) == len(self.candidates) for answers in known.values()):
            raise ValueError('A training disease has no eligible negatives')
        self.known = {d: np.array(sorted(answers), dtype=np.int64) for d, answers in known.items()}

    def sample(self, disease, count, rng):
        if count < 1:
            raise ValueError('Negative count must be positive')
        excluded = self.known[disease]
        chunks = []
        remaining = count
        while remaining:
            draws = self.candidates[rng.integers(len(self.candidates), size=remaining)]
            accepted = draws[~np.isin(draws, excluded)]
            chunks.append(accepted)
            remaining -= len(accepted)
        return np.concatenate(chunks)
