"""Adapters (#28): a light map from TRIBE v2's predicted cortex to measured fMRI, fitted on an open dataset and scored on
held-out stimuli. Ported from visual-cortex-lab feasibility/personalize_had.py (the fit "to everyone else", here to the
mean of all people) and score_had.py (features, reliable areas).

Input:  TRIBE v2's prediction per clip, mean over the seconds the clip is on screen, in each of the 360 HCP-MMP1 areas
        (regions.hcp_areas), then averaged over the clips of each category.
Target: the measured response per category and area, mean over people (z-scored per vertex within each run).
Fit:    ridge per area (alphas 0.1 to 100,000, chosen per area by leave-one-out inside the training categories), on
        z-scored inputs. Scored on held-out categories only: by default 10-fold over categories (r per area within each
        held-out fold, averaged over folds, as personalize_had.py scores); or one split, holding out the categories of
        a saved view. Beside it: TRIBE v2 as released (its own prediction for the area, no fit), the same fit with the
        training categories' labels shuffled (mean of 8 permutations per fold; must give about 0), and the noise ceiling. Summaries are medians over
        reliable areas (ceiling above 0.5, somatomotor areas left out), with a 95% interval from resampling areas.
The weights of the fit on every training category are kept, so the adapter can be applied later.

Datasets with measured responses are in SOURCES; the first is the Human Action Dataset (openneuro ds004488, CC0).
"""
from __future__ import annotations
import time
from pathlib import Path
import numpy as np

from ..home import HOME
from . import datasets as dsets, regions

SOMATOMOTOR = {'1', '2', '3a', '3b', '4', '6mp', '6d', '6a', '6v', '6r', '43', 'OP4', 'OP1', 'OP2-3', 'FEF', 'PEF', '55b', '5L', '5m', '5mv', '24dd', '24dv', 'SCEF'}
ALPHAS = np.logspace(-1, 5, 13)
ON_S = (0, 2)   # the seconds a Human Action Dataset clip is on screen
SHUFFLES = 8   # label permutations per fold for the shuffled baseline


def _had() -> dict:
    H = HOME / 'feasibility' / 'data' / 'had'
    M = np.load(H / 'measured.npz', allow_pickle=True)
    return {'title': 'Human Action Dataset, 30 people (Zhou et al., 2023)', 'categories': [str(c) for c in M['cats']], 'areas': [str(p) for p in M['parcels']],
            'measured': M['by_sub'].mean(0).astype(np.float64), 'ceiling': M['ceiling'].astype(np.float64), 'people': int(M['by_sub'].shape[0]),
            'clip_folder': lambda cat: dsets.dataset_dir('openneuro_ds004488') / 'stimuli' / cat.replace(' ', '_'),
            'tribe': lambda cat, clip: H / 'tribe' / f"v_{cat}_id_{clip.stem.split('_id_', 1)[1]}.npy"}   # TRIBE's cache keeps the category's spaces; the fetched clips use underscores


SOURCES = {'openneuro_ds004488': _had}


def has_measured(dataset_id: str) -> bool:
    if dataset_id not in SOURCES: return False
    try: return (HOME / 'feasibility' / 'data' / 'had' / 'measured.npz').exists() and dsets.dataset_dir(dataset_id).exists()
    except ValueError: return False


def features(dataset_id: str, cache: Path, on_event=lambda m: None) -> tuple[dict, np.ndarray, np.ndarray]:
    """The source, TRIBE v2's per-category area means (categories x areas, the source's area order), and the per-category clip counts. Cached."""
    src = SOURCES[dataset_id](); f = cache / f'{dataset_id}_tribe_areas.npz'
    if f.exists():
        z = np.load(f); return src, z['T'], z['n']
    names = list(regions.hcp_names()); masks = regions.hcp_areas(); order = [names.index(a) for a in src['areas']]
    lab = np.full(20484, -1); [lab.__setitem__(masks[i], k) for k, i in enumerate(order)]
    counts = np.bincount(lab[lab >= 0], minlength=len(order))
    T = np.zeros((len(src['categories']), len(order))); n = np.zeros(len(src['categories']), int); t0 = time.time()
    for ci, cat in enumerate(src['categories']):
        rows = []
        for clip in sorted(src['clip_folder'](cat).glob('*.mp4')):
            p = src['tribe'](cat, clip)
            if not p.exists(): continue
            on = np.load(p)[ON_S[0]:ON_S[1]].astype(np.float64).mean(0)
            rows.append(np.bincount(lab[lab >= 0], weights=on[lab >= 0], minlength=len(order)) / counts)
        if rows: T[ci] = np.mean(rows, 0); n[ci] = len(rows)
        if ci % 20 == 0 or ci == len(src['categories']) - 1: on_event({'adapter': dataset_id, 'categories_read': ci + 1, 'total': len(src['categories']), 'seconds': round(time.time() - t0, 1)})
    cache.mkdir(parents=True, exist_ok=True); np.savez(f, T=T, n=n)
    return src, T, n


def _ridge(Xtr, Ytr):
    from sklearn.linear_model import RidgeCV
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-8
    m = RidgeCV(alphas=ALPHAS, alpha_per_target=True).fit((Xtr - mu) / sd, Ytr)
    return mu, sd, m


def _r_per_area(P, Y):
    P = (P - P.mean(0)) / (P.std(0) + 1e-12); Y = (Y - Y.mean(0)) / (Y.std(0) + 1e-12)
    return (P * Y).mean(0)


def fit(dataset_id: str, cache: Path, held_out: list[str] | None = None, on_event=lambda m: None) -> dict:
    """Fit and score an adapter. held_out: category names to hold out; None for 10-fold over categories."""
    from sklearn.model_selection import KFold
    src, T, n = features(dataset_id, cache, on_event)
    have = np.flatnonzero(n > 0); cats = [src['categories'][i] for i in have]
    X, Y = T[have], src['measured'][have]; good = (src['ceiling'] > 0.5) & ~np.array([a[2:] in SOMATOMOTOR for a in src['areas']])
    if held_out:
        unknown = sorted(set(held_out) - set(cats))
        if unknown: raise ValueError(f"categories not in the dataset: {', '.join(unknown[:8])}")
        te = np.array([c in set(held_out) for c in cats]); folds = [np.flatnonzero(te)]
        if te.sum() < 5 or (~te).sum() < 20: raise ValueError(f'{int(te.sum())} held-out and {int((~te).sum())} training categories; need at least 5 and 20')
        split = {'kind': 'held-out view', 'held_out': int(te.sum()), 'training': int((~te).sum())}
    else:
        folds = [t for _, t in KFold(10, shuffle=True, random_state=0).split(X)]; split = {'kind': '10-fold over categories', 'held_out': len(cats), 'training': len(cats) - len(folds[0])}
    rng = np.random.default_rng(0); A, R, S = [], [], []
    for te in folds:
        tr = np.setdiff1d(np.arange(len(cats)), te)
        mu, sd, m = _ridge(X[tr], Y[tr]); A.append(_r_per_area(m.predict((X[te] - mu) / sd), Y[te]))
        R.append(_r_per_area(X[te], Y[te]))
        sh = []
        for _ in range(SHUFFLES):   # one permutation is noisy here: a fit to shuffled labels follows TRIBE's shared pattern, with a random sign
            mu2, sd2, m2 = _ridge(X[tr], Y[rng.permutation(tr)]); sh.append(_r_per_area(m2.predict((X[te] - mu2) / sd2), Y[te]))
        S.append(np.mean(sh, 0))
    a, r, s = (np.nan_to_num(np.mean(v, 0)) for v in (A, R, S))
    train = np.flatnonzero(~np.isin(np.arange(len(cats)), folds[0])) if held_out else np.arange(len(cats))
    mu, sd, m = _ridge(X[train], Y[train])

    def summary(v):
        g = v[good]; b = np.median(g[rng.integers(0, len(g), (4000, len(g)))], 1)
        return {'median': round(float(np.median(g)), 6), 'interval_95': [round(float(x), 6) for x in np.percentile(b, [2.5, 97.5])]}   # 6 places: the page rounds to 3, and 4 here made 0.40655 show as 0.406
    return {'source': src['title'], 'people': src['people'], 'categories': len(cats), 'clips': int(n.sum()), 'split': split,
            'input': f'TRIBE v2, mean of seconds {ON_S[0]} to {ON_S[1]} in each of the 360 HCP-MMP1 areas, averaged over each category\'s clips',
            'target': f"measured response, mean of {src['people']} people, 360 HCP-MMP1 areas", 'reliable_areas': int(good.sum()),
            'summary': {'adapter': summary(a), 'tribe_v2': summary(r), 'shuffled': summary(s), 'ceiling': summary(src['ceiling'])},
            'areas': [{'area': src['areas'][i], 'adapter_r': round(float(a[i]), 6), 'tribe_v2_r': round(float(r[i]), 6), 'shuffled_r': round(float(s[i]), 6),
                       'ceiling': round(float(src['ceiling'][i]), 6), 'reliable': bool(good[i])} for i in range(len(src['areas']))],
            'weights': {'mu': mu, 'sd': sd, 'coef': m.coef_, 'intercept': m.intercept_, 'alpha': np.asarray(m.alpha_)}}


def benchmark(row: dict) -> str:
    """What an adapter's scores are (#37): a benchmark on held-out categories of the dataset it was fitted on, the same
    people and kind of stimulus. They say nothing about new stimuli in an experiment, where no measured fMRI exists."""
    where = 'held-out categories' if (row.get('split') or {}).get('kind') != 'held-out view' else 'the held-out categories of a saved view'
    return f"Benchmark: {where} of the {str(row.get('source', 'dataset')).split(',')[0]}"


def area_map(areas: list[dict], key: str) -> np.ndarray:
    """A per-area value spread over its fsaverage5 vertices, for the brain view."""
    names = list(regions.hcp_names()); masks = regions.hcp_areas(); out = np.zeros(20484, np.float32)
    for a in areas: out[masks[names.index(a['area'])]] = a[key]
    return out
