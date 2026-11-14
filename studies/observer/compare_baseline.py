"""Onboarding step 7's baseline: the cluster run's TRIBE predictions against the Spark's, clip by clip.

For every clip both runs predicted, the per-vertex Pearson r between the two (seconds x 20,484) responses, taken over
time at each vertex, then summarised across vertices. Same weights and inputs should give r near 1.0.

usage: python studies/observer/compare_baseline.py [SPARK_CLIPS] [CLUSTER_CLIPS]
       defaults: /data/studies/observer/observer/clips and /data/studies/observer/cluster-run/clips
"""
import glob, os, sys
import numpy as np

A = sys.argv[1] if len(sys.argv) > 1 else '/data/studies/observer/observer/clips'
B = sys.argv[2] if len(sys.argv) > 2 else '/data/studies/observer/cluster-run/clips'


def per_vertex_r(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    x = x - x.mean(0); y = y - y.mean(0)
    den = np.sqrt((x * x).sum(0) * (y * y).sum(0))
    return np.where(den > 0, (x * y).sum(0) / np.where(den > 0, den, 1), np.nan)


rows = []
for fa in sorted(glob.glob(os.path.join(A, '*.tribe.npy'))):
    fb = os.path.join(B, os.path.basename(fa))
    if not os.path.exists(fb): continue
    a, b = np.load(fa).astype(np.float64), np.load(fb).astype(np.float64)
    n = min(len(a), len(b)); r = per_vertex_r(a[:n], b[:n])
    rows.append((os.path.basename(fa)[:-len('.tribe.npy')], len(a), len(b), np.nanmedian(r), np.nanpercentile(r, 5)))
    print(f'{rows[-1][0]:<52} seconds {len(a)}/{len(b)}  median r {rows[-1][3]:.4f}  5th percentile {rows[-1][4]:.4f}')
if not rows: sys.exit(f'no clip predicted in both {A} and {B}')
med = np.array([r[3] for r in rows])
print(f'{len(rows)} clips in both; median of per-clip median r {np.median(med):.4f}, lowest {med.min():.4f}')
