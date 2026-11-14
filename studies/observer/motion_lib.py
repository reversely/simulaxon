"""Body and motion for one EgoBody moment, shared by observer/motions.py (command line) and the lab's body world
(backend/vcl/lab/preview.py, before a render).

For the camera wearer's 9 s around a decision point (8 s before to 1 s after, 30 fps; the nearest camera frame with a
fit within 50 ms, else the last fit held), two motions:
  recorded  the wearer's own motion, frame by frame
  robotic   the same poses at keyframes every keyframe_s, joined at constant angular speed (every joint slerped linearly
            in time, pelvis moved linearly), so the poses match at every keyframe and only the timing differs
and two bodies driven by each: the SMPL-X human (vertices in the room scan; the fit's gender; 12 PCA hand components as
EgoBody fitted) and the Unitree G1 (13 upper-body joints as 6-D rotations, pelvis and facing in the room scan).
"""
from __future__ import annotations
import glob, os, pickle
import numpy as np
from scipy.spatial.transform import Rotation as Rot, Slerp

ROOT = os.path.expanduser('~/data/egobody'); WORK = os.path.join(ROOT, 'work'); MODELS = os.path.expanduser('~/data/body_models/models')
U13 = [2, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
PELVIS = np.array([0.0031, -0.3514, 0.0120])   # SMPL-X neutral pelvis at rest, as isaac/g1_execute.py
ROT = ('global_orient', 'body_pose', 'jaw_pose', 'leye_pose', 'reye_pose')
LIN = ('transl', 'left_hand_pose', 'right_hand_pose', 'expression')
_models = {}


def decision_time(rec: str, k: int) -> float:
    E = np.load(os.path.join(WORK, 'episodes.npz'), allow_pickle=True)
    i = np.where((E['rec'] == rec) & (E['k'] == k))[0]
    if not len(i): raise KeyError(f'no EgoBody decision point {rec} #{k}')
    return float(E['t'][i[0]])


def _model(g):
    import smplx
    if g not in _models: _models[g] = smplx.create(MODELS, model_type='smplx', gender=g, ext='npz', use_pca=True, num_pca_comps=12)
    return _models[g]


def build(rec: str, k: int, keyframe_s: float, dst: str) -> dict:
    """Writes dst (npz) with both motions for both bodies; returns a summary. Skips the work if dst exists."""
    if os.path.exists(dst): return {'file': dst, 'cached': True}
    import torch
    t = decision_time(rec, k)
    c = np.load(os.path.join(WORK, 'cams', rec + '.npz'), allow_pickle=True); ts = (c['ts'] - c['ts'][0]) / 1e7; T = c['T_scene_kin']
    d = glob.glob(os.path.join(ROOT, f'smplx_camera_wearer_*/{rec}/body_idx_*/results'))[0]
    taus = t - 8.0 + np.arange(30 * 9 + 1) / 30; fits, last, held = [], None, 0
    for tau in taus:
        j = int(np.argmin(np.abs(ts - tau))); f = os.path.join(d, f"frame_{int(c['frame'][j]):05d}", '000.pkl')
        b = pickle.load(open(f, 'rb')) if abs(ts[j] - tau) < 0.05 and os.path.exists(f) else None
        if b is None: held += 1; b = last
        fits.append(b); last = b if b is not None else last
    first = next(b for b in fits if b is not None); fits = [b if b is not None else first for b in fits]
    g = first['gender']; n = len(fits); KEY = max(2, round(keyframe_s * 30))
    rec_p = {kk: np.stack([b[kk][0] for b in fits]) for kk in ROT + LIN}
    keys = np.unique(np.r_[np.arange(0, n, KEY), n - 1]); rob_p = {}
    for kk in ROT:
        J = rec_p[kk].reshape(n, -1, 3); outj = np.zeros_like(J)
        for jj in range(J.shape[1]): outj[:, jj] = Slerp(keys, Rot.from_rotvec(J[keys, jj]))(np.arange(n)).as_rotvec()
        rob_p[kk] = outj.reshape(n, -1)
    for kk in LIN:
        rob_p[kk] = np.stack([np.interp(np.arange(n), keys, rec_p[kk][keys, q]) for q in range(rec_p[kk].shape[1])], 1)
    save = dict(taus=taus, decision_t=t, frames_without_fit=held, gender=g, keyframes=keys, keyframe_s=KEY / 30)
    for name, P in (('recorded', rec_p), ('robotic', rob_p)):
        Rg = Rot.from_rotvec(P['global_orient']).as_matrix()
        save[f'{name}_six'] = Rot.from_rotvec(P['body_pose'].reshape(n, 21, 3)[:, U13].reshape(-1, 3)).as_matrix()[..., :2].reshape(n, 13 * 6)
        save[f'{name}_pel'] = (np.c_[PELVIS + P['transl'], np.ones(n)] @ T.T)[:, :3]
        save[f'{name}_fwd'] = (T[:3, :3] @ (Rg @ np.array([0, 0, 1.0])).T).T
        args = {kk: torch.tensor(P[kk], dtype=torch.float32) for kk in ROT + LIN}
        args['betas'] = torch.tensor(np.repeat(first['betas'], n, 0), dtype=torch.float32)
        with torch.no_grad(): v = _model(g)(**args).vertices.numpy()
        save[f'{name}_verts'] = ((v @ T[:3, :3].T) + T[:3, 3]).astype(np.float32)
    save['faces'] = _model(g).faces.astype(np.int32)
    gap = np.linalg.norm(save['recorded_verts'] - save['robotic_verts'], axis=2).mean(1); save['vertex_gap_m'] = gap
    os.makedirs(os.path.dirname(dst), exist_ok=True); tmp = dst + '.tmp.npz'; np.savez_compressed(tmp, **save); os.replace(tmp, dst)
    return {'file': dst, 'cached': False, 'frames': n, 'frames_without_fit': held, 'gender': g,
            'gap_mean_cm': round(float(gap.mean() * 100), 2), 'gap_at_keyframes_cm': round(float(gap[keys].max() * 100), 3)}


def score_moments(skip=(), want=None) -> list[tuple]:
    """Every decision point's upper-body angular speed over its 9 s window (median over frames of the mean speed of the 13
    upper-body joints), from the cached fits: (rec, speed, k, t, fitted frames). want: only these (rec, k); skip: 'rec#k'."""
    E = np.load(os.path.join(WORK, 'episodes.npz'), allow_pickle=True); out = []
    for rec in sorted(set(E['rec'])):
        if want is not None and rec not in {r for r, _ in want}: continue
        fc = np.load(os.path.join(WORK, 'fits_cache', f'camera_wearer_{rec}.npz'))
        c = np.load(os.path.join(WORK, 'cams', rec + '.npz'), allow_pickle=True); ts = (c['ts'] - c['ts'][0]) / 1e7
        pos = {int(f): i for i, f in enumerate(fc['frame'])}
        for i in np.where(E['rec'] == rec)[0]:
            k = int(E['k'][i]); t = float(E['t'][i])
            if (want is not None and (rec, k) not in want) or f'{rec}#{k}' in skip: continue
            sel = [(ts[j], pos[int(f)]) for j, f in enumerate(c['frame']) if t - 8 <= ts[j] <= t + 1 and int(f) in pos]
            if len(sel) < 100: out.append((rec, None, k, t, len(sel))); continue
            R = [Rot.from_rotvec(fc['pose'][q][U13]) for _, q in sel]; tt = [x for x, _ in sel]
            sp = float(np.median([np.mean((R[j].inv() * R[j + 1]).magnitude()) / max(tt[j + 1] - tt[j], 1e-3) for j in range(len(R) - 1)]))
            out.append((rec, sp, k, t, len(sel)))
    return out


def pick_moments(n: int, skip=()) -> dict:
    """The rule: per recording the moment that moves most, then the n recordings whose best moment moves most."""
    sc = score_moments(skip)
    ok = [x for x in sc if x[1] is not None]
    best = [max((x for x in ok if x[0] == r), key=lambda x: x[1]) for r in sorted({x[0] for x in ok})]
    best.sort(key=lambda x: -x[1])
    return {'scored': sc, 'with_fits': ok, 'best_per_recording': best, 'picked': best[:n]}
