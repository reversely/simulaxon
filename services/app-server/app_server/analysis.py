"""Analyses (design spec §7, implementation spec milestone M4).

Every kind returns a value with a bootstrap 95% interval, n, and how many units agree in sign, never a verdict.
Kinds:
  paired        mean of a - b over matched units (food and its matched object)
  two_group     mean(a) - mean(b) for unmatched groups
  regression    slope of response on a measured feature, optionally with the group as a covariate
  shuffle_null  observed two-group difference against the distribution under shuffled labels
"""
from __future__ import annotations
import numpy as np


def _boot(stat, arrays, n=5000, seed=0):
    rng = np.random.default_rng(seed); out = []
    for _ in range(n):
        idx = [rng.integers(0, len(a), len(a)) for a in arrays]
        out.append(stat(*[a[i] for a, i in zip(arrays, idx)]))
    return [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]


def paired(a, b, seed=0) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float); d = a - b
    return {'kind': 'paired', 'value': float(d.mean()), 'interval_95': _boot(lambda x: x.mean(), [d], seed=seed), 'n': int(len(d)), 'units_positive': int((d > 0).sum())}


def two_group(a, b, seed=0) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float)
    return {'kind': 'two_group', 'value': float(a.mean() - b.mean()), 'interval_95': _boot(lambda x, y: x.mean() - y.mean(), [a, b], seed=seed), 'n': [int(len(a)), int(len(b))]}


def regression(y, x, group=None, seed=0) -> dict:
    y, x = np.asarray(y, float), np.asarray(x, float)
    X = np.column_stack([np.ones_like(x), x] + ([np.asarray(group, float)] if group is not None else []))
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    def stat(i): return np.linalg.lstsq(X[i], y[i], rcond=None)[0][1]
    rng = np.random.default_rng(seed); boots = [stat(rng.integers(0, len(y), len(y))) for _ in range(3000)]
    out = {'kind': 'regression', 'slope': float(beta[1]), 'interval_95': [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))], 'n': int(len(y))}
    if group is not None: out['group_coefficient'] = float(beta[2])
    return out


def shuffle_null(a, b, n=5000, seed=0) -> dict:
    a, b = np.asarray(a, float), np.asarray(b, float); obs = a.mean() - b.mean(); pool = np.concatenate([a, b]); rng = np.random.default_rng(seed)
    null = []
    for _ in range(n):
        p = rng.permutation(pool); null.append(p[:len(a)].mean() - p[len(a):].mean())
    null = np.asarray(null)
    return {'kind': 'shuffle_null', 'value': float(obs), 'null_95': [float(np.percentile(null, 2.5)), float(np.percentile(null, 97.5))],
            'share_of_shuffles_at_least_as_large': float((np.abs(null) >= abs(obs)).mean()), 'n': [int(len(a)), int(len(b))]}


KINDS = {'paired': paired, 'two_group': two_group, 'regression': regression, 'shuffle_null': shuffle_null}
