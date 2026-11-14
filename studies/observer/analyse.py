"""The observer demo, compare and challenge (doc 24 § 13): what the predicted observer cortex does across the 2 x 2.

Cells per moment: human_recorded (Saygin's human), human_robotic (the android: human look, machine motion),
g1_robotic (the robot), g1_recorded (the cell Saygin could not build: robot look, human motion).
Readout: TRIBE's prediction per clip (seconds x 20,484), averaged over seconds 1 to the end (second 0 is onset),
then per Glasser region. Primary region: bilateral AIP, where Saygin et al. 2012 report the android effect.
Action set: bilateral AIP, PFt, PF, PFop, STSdp, STSda, STSvp, STSva, MT, MST, 44, 6v.

Contrasts, paired over moments, 95% bootstrap intervals over moments (5,000), and how many moments agree in sign:
  android   human_robotic - mean(human_recorded, g1_robotic)      Saygin's comparison
  mismatch  (human_robotic + g1_recorded) - (human_recorded + g1_robotic)   look and motion disagree vs agree
  body      mean over motions of human - g1
  motion    mean over bodies of robotic - recorded
Beside every contrast:
  random regions    the percentile of the region set's contrast among 5,000 random sets of the same size
  whole cortex      the same contrast on the whole-cortex mean (a shared shift, not a regional one)
  V-JEPA 2 map      the same contrast through a fixed random projection of TRIBE's own V-JEPA 2 features to the
                    cortex (the features without TRIBE's learned mapping); shown, not a kill condition (owner, 2026-11-14)
  low level         motion energy (mean absolute frame difference) and mean luminance of each clip, same contrasts
usage (feasibility/.venv): python observer/analyse.py   writes ~/data/observer/results.json, cells.csv, per_region.csv,
                                                          contrast_maps.npz
"""
import glob, json, os, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE / 'egobody')); sys.path.insert(0, str(HERE / 'tribev2-src'))
from donoso_signals import parcels, vjepa_index
OUT = Path(os.environ.get('OBS_OUT', '~/data/observer')).expanduser(); CL = OUT / 'clips'
CELLS = ['human_recorded', 'human_robotic', 'g1_recorded', 'g1_robotic']
ACTION = ['AIP', 'PFt', 'PF', 'PFop', 'STSdp', 'STSda', 'STSvp', 'STSva', 'MT', 'MST', '44', '6v']
moments = json.load(open(OUT / 'moments.json'))['moments']
names, pidx = parcels(); nreg = len(names)
ix = {n: i for i, n in enumerate(names)}
AIP = [ix['L_AIP'], ix['R_AIP']]; ACT = [ix[f'{h}_{r}'] for h in 'LR' for r in ACTION]
vidx = vjepa_index()


def lowlevel(mp4):
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=240:135', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                         capture_output=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, 135, 240).astype(np.float32)
    return float(np.abs(np.diff(v, axis=0)).mean()), float(v.mean())


def vjepa(mp4):
    key = str(Path(mp4).resolve())
    if key not in vidx: return None
    folder, dd = vidx[key]
    a = np.array(np.memmap(folder / dd['filename'], dtype=dd['dtype'], mode='r', offset=dd['offset'], shape=tuple(dd['shape'])), dtype=np.float32)
    L = a.shape[1]; k = np.unique([int(i * (L - 1)) for i in (0.5, 0.75, 1.0)]).tolist(); k[-1] += 1
    return np.concatenate([a[:, l1:l2].mean(1) for l1, l2 in zip(k[:-1], k[1:])], axis=1).mean(0)


rows, cortex, feats = [], {}, {}
for m in moments:
    for cell in CELLS:
        mp4 = CL / f"{m['rec']}_{m['k']:03d}_{cell}.mp4"; tr = Path(str(mp4)[:-4] + '.tribe.npy')
        if not tr.exists(): continue
        P = np.load(tr); cx = P[1:].mean(0); cortex[(m['rec'], cell)] = cx
        reg = np.array([cx[i].mean() for i in pidx]); me, lum = lowlevel(mp4); f = vjepa(mp4)
        if f is not None: feats[(m['rec'], cell)] = f
        rows.append(dict(rec=m['rec'], k=m['k'], cell=cell, seconds=len(P), aip=reg[AIP].mean(), action=reg[ACT].mean(),
                         cortex_mean=float(cx.mean()), motion_energy=me, luminance=lum, **{f'r{j}': reg[j] for j in range(nreg)}))
D = pd.DataFrame(rows)
done = D.groupby('rec').cell.nunique(); full = done[done == 4].index.tolist()
print(f'{len(D)} clips with TRIBE; moments with all four cells: {len(full)} of {len(moments)}', flush=True)
D = D[D.rec.isin(full)]
if not full: sys.exit('no complete moment yet')
if feats:
    Fk = list(feats); Fm = np.stack([feats[k] for k in Fk])
    Mp = np.random.default_rng(1800).standard_normal((Fm.shape[1], 20484)).astype(np.float32) / np.sqrt(Fm.shape[1])
    RV = Fm @ Mp; vreg = {k: np.array([RV[n][i].mean() for i in pidx]) for n, k in enumerate(Fk)}
    D['vjepa_aip'] = [vreg[(r, c)][AIP].mean() if (r, c) in vreg else np.nan for r, c in zip(D.rec, D.cell)]
    D['vjepa_action'] = [vreg[(r, c)][ACT].mean() if (r, c) in vreg else np.nan for r, c in zip(D.rec, D.cell)]


def cell_table(col):
    return D.pivot(index='rec', columns='cell', values=col)[CELLS]


CON = {'android': lambda T: T.human_robotic - (T.human_recorded + T.g1_robotic) / 2,
       'mismatch': lambda T: (T.human_robotic + T.g1_recorded) - (T.human_recorded + T.g1_robotic),
       'body': lambda T: (T.human_recorded + T.human_robotic - T.g1_recorded - T.g1_robotic) / 2,
       'motion': lambda T: (T.human_robotic + T.g1_robotic - T.human_recorded - T.g1_recorded) / 2}
rng = np.random.default_rng(0); n = len(full); boots = [rng.integers(0, n, n) for _ in range(5000)]


def summary(v):
    v = np.asarray(v, float); b = [v[i].mean() for i in boots]
    return dict(mean=round(float(v.mean()), 5), ci95=[round(float(np.percentile(b, 2.5)), 5), round(float(np.percentile(b, 97.5)), 5)],
                positive=f'{int((v > 0).sum())} of {len(v)}')


reg_cols = [f'r{j}' for j in range(nreg)]
per_reg = {cn: np.stack([f(cell_table(c)).values for c in reg_cols], 1) for cn, f in CON.items()}   # moments x regions
rr = np.random.default_rng(1)
res = dict(moments=full, clips=len(D), seconds_read='1 to end (second 0 is onset)', contrasts={})
for cn, f in CON.items():
    R = per_reg[cn].mean(0); out = {}
    for sname, idxs in (('AIP', AIP), ('action set', ACT)):
        val = R[idxs].mean(); rand = np.array([R[rr.choice(nreg, len(idxs), replace=False)].mean() for _ in range(5000)])
        out[sname] = dict(**summary(f(cell_table('aip' if sname == 'AIP' else 'action'))),
                          random_region_percentile=round(float((rand < val).mean() * 100), 1))
    out['whole cortex'] = summary(f(cell_table('cortex_mean')))
    out['AIP minus whole cortex'] = summary(f(cell_table('aip')) - f(cell_table('cortex_mean')))
    if 'vjepa_aip' in D: out['V-JEPA 2 random map, AIP'] = summary(f(cell_table('vjepa_aip')).dropna())
    out['motion energy'] = summary(f(cell_table('motion_energy'))); out['luminance'] = summary(f(cell_table('luminance')))
    res['contrasts'][cn] = out
    print(f"\n{cn}: AIP {out['AIP']['mean']:+.4f} {out['AIP']['ci95']} ({out['AIP']['positive']}), random-region pct {out['AIP']['random_region_percentile']}; "
          f"action set {out['action set']['mean']:+.4f} {out['action set']['ci95']}; whole cortex {out['whole cortex']['mean']:+.4f}; "
          f"motion energy {out['motion energy']['mean']:+.3f}", flush=True)
res['cells_mean'] = {col: {c: round(float(v), 5) for c, v in cell_table(col).mean().items()} for col in ('aip', 'action', 'cortex_mean', 'motion_energy', 'luminance')}
json.dump(res, open(OUT / 'results.json', 'w'), indent=1)
D.drop(columns=reg_cols).to_csv(OUT / 'cells.csv', index=False)
pd.DataFrame({'region': names, **{cn: per_reg[cn].mean(0) for cn in CON}}).to_csv(OUT / 'per_region.csv', index=False)
class Cells:   # the cells as attributes, so the same contrast functions apply to whole-cortex maps (moments x vertices)
    def __init__(self, d): self.__dict__.update(d)


Tc = Cells({c: np.stack([cortex[(r, c)] for r in full]) for c in CELLS})
np.savez(OUT / 'contrast_maps.npz', **{cn: f(Tc).mean(0) for cn, f in CON.items()})
print('\nsaved', OUT / 'results.json', flush=True)
