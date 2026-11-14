"""Selection: screen many stimuli in silico, then pick the ones that drive two regions together or apart.

The relational procedure of Gifford et al. 2025 (Nature Human Behaviour), applied to any screened set:
  align up        both regions high        align down      both regions low
  A over B        A high while B low       B over A        B high while A low
Each region's readout is z-scored across the screened set. Each condition keeps the k best stimuli and is compared with
the same statistic over random sets of k, drawn without optimisation, as the baseline. The share of random sets at least
as extreme is reported, never a verdict.
"""
from __future__ import annotations
import numpy as np

CONDITIONS = {'align_up': (1, 1), 'align_down': (-1, -1), 'a_over_b': (1, -1), 'b_over_a': (-1, 1)}
NAMES = {'align_up': 'Both high', 'align_down': 'Both low', 'a_over_b': 'First high, second low', 'b_over_a': 'Second high, first low'}


def select(ids: list[str], a: np.ndarray, b: np.ndarray, k: int = 5, n_random: int = 10000, seed: int = 0) -> dict:
    za, zb = (a - a.mean()) / (a.std() or 1), (b - b.mean()) / (b.std() or 1)
    rng = np.random.default_rng(seed); rand = np.array([rng.choice(len(ids), k, replace=False) for _ in range(n_random)])
    out = {}
    for c, (sa, sb) in CONDITIONS.items():
        score = sa * za + sb * zb; top = np.argsort(-score)[:k]
        obs = score[top].mean(); null = score[rand].mean(1)
        out[c] = {'name': NAMES[c], 'ids': [ids[i] for i in top], 'mean_a': round(float(a[top].mean()), 4), 'mean_b': round(float(b[top].mean()), 4),
                  'score': round(float(obs), 3), 'random_95': [round(float(np.percentile(null, 2.5)), 3), round(float(np.percentile(null, 97.5)), 3)],
                  'share_random_at_least': float((null >= obs).mean())}
    return {'k': k, 'n': len(ids), 'n_random': n_random, 'conditions': out,
            'points': [{'id': i, 'a': round(float(x), 4), 'b': round(float(y), 4)} for i, x, y in zip(ids, a, b)]}
