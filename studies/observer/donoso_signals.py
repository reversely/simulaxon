"""Run 20 (Donoso's two equations on EgoBody and TRIBE), stage 0: the signals.

For every episode that has TRIBE output (8 s REAL clip of the wearer's view, decision point at its end):
  per second (8 values):  TRIBE per Glasser region (360); partner arousal; wearer head angular speed;
                          V-JEPA 2 change (TRIBE's own features); pixel motion of the clip.
  per decision point:     behavioural uncertainty proxies over the last 2 s, from the HoloLens head and eye stream
                          and the wearer's SMPL-X body (pauses, yaw reversals, gaze dispersion, saccade rate, body
                          acceleration).
HoloLens head_hand_eye.csv layout (HoloLens2ForCV StreamRecorder, checked on the file): col 0 time (100 ns),
  1-16 head 4x4 (row-major, translation in the last column), 17 left-hand flag, 18-433 left joints (26 x 4x4),
  434 right-hand flag, 435-850 right joints, 851 gaze flag, 852-855 gaze origin (x, y, z, 1), 856-859 gaze direction
  (x, y, z, 0), 860 gaze distance. Head and gaze are in the HoloLens world frame (y up). Time is on the same clock as
  the PV frames in work/cams/<rec>.npz, so episode time = (ts - cams.ts[0]) / 1e7.

usage (feasibility/.venv): python egobody/donoso_signals.py    writes ~/data/egobody/work/donoso/signals.npz
"""
import glob, json, os, pickle, subprocess, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.spatial.transform import Rotation as Rot

HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE / 'tribev2-src'))
ROOT = Path('~/data/egobody').expanduser(); WORK = ROOT / 'work'; OUT = WORK / 'donoso'
CACHE = HERE / 'cache_fast'


def parcels():
    from tribev2.utils import get_hcp_labels
    names, idx = [], []
    for h, p in (('left', 'L'), ('right', 'R')):
        for k, v in get_hcp_labels(mesh='fsaverage5', hemi=h).items():
            if k != '?': names.append(f'{p}_{k}'); idx.append(np.asarray(v))
    return names, idx


def load_body(kind, rec):  # as egobody/episodes.py
    for s in ('train', 'val', 'test'):
        d = glob.glob(str(ROOT / f'smplx_{kind}_{s}' / rec / 'body_idx_*' / 'results'))
        if d: break
    else:
        return None
    out = {}
    for f in glob.glob(os.path.join(d[0], 'frame_*', '000.pkl')):
        p = pickle.load(open(f, 'rb')); out[int(f.split('frame_')[1][:5])] = p['body_pose'][0].reshape(21, 3)
    return out


def body_speed(body, frames, ts):  # mean joint angular speed (rad/s) between consecutive fitted frames
    ok = np.array([f in body for f in frames]); f, t = frames[ok], ts[ok]
    R = Rot.from_rotvec(np.stack([body[i] for i in f]).reshape(-1, 3)).as_matrix().reshape(len(f), 21, 3, 3)
    rel = np.einsum('tjab,tjcb->tjac', R[1:], R[:-1])
    ang = np.arccos(np.clip((np.trace(rel, axis1=2, axis2=3) - 1) / 2, -1, 1)).mean(1)
    return (t[1:] + t[:-1]) / 2, ang / np.maximum(np.diff(t), 1e-3)


def hololens(rec, t0):
    f = glob.glob(str(ROOT / 'egocentric_gaze' / rec / '*' / '*_head_hand_eye.csv'))[0]
    a = pd.read_csv(f, header=None).to_numpy(float)[:, :861]
    t = (a[:, 0] - t0) / 1e7
    H = a[:, 1:17].reshape(-1, 4, 4); R, pos = H[:, :3, :3], H[:, :3, 3]
    g_ok = a[:, 851] == 1; g_dir = a[:, 856:859]
    g_dir = g_dir / (np.linalg.norm(g_dir, axis=1, keepdims=True) + 1e-9)
    eye_in_head = np.einsum('nba,nb->na', R, g_dir)  # R^T d
    return dict(t=t, R=R, pos=pos, g_ok=g_ok, eye=eye_in_head)


def angle(a, b):
    return np.degrees(np.arccos(np.clip((a * b).sum(-1), -1, 1)))


def head_kinematics(h):
    t = h['t']; dt = np.maximum(np.diff(t), 1e-3); tm = (t[1:] + t[:-1]) / 2
    rel = np.einsum('nab,nac->nbc', h['R'][:-1], h['R'][1:])
    ang = np.degrees(np.arccos(np.clip((np.trace(rel, axis1=1, axis2=2) - 1) / 2, -1, 1))) / dt
    lin = np.linalg.norm(np.diff(h['pos'], axis=0), axis=1) / dt
    fw = -h['R'][:, :, 2]; yaw = np.unwrap(np.arctan2(fw[:, 0], fw[:, 2]))
    yawv = np.degrees(np.diff(yaw)) / dt
    eye = h['eye']; ev = angle(eye[1:], eye[:-1]) / dt; ev[~(h['g_ok'][1:] & h['g_ok'][:-1])] = np.nan
    return dict(tm=tm, ang=ang, lin=lin, yawv=yawv, eyev=ev)


def behaviour_window(h, k, t1, t2):
    m = (k['tm'] > t1) & (k['tm'] <= t2)
    if m.sum() < 30: return dict(pause=np.nan, yaw_rev=np.nan, gaze_disp=np.nan, saccades=np.nan, head_speed=np.nan)
    dur = t2 - t1
    pause = np.mean((k['ang'][m] < 10) & (k['lin'][m] < 0.05))
    v = np.convolve(k['yawv'][m], np.ones(5) / 5, mode='same'); big = np.abs(v) > 5
    s = np.sign(v[big]); yaw_rev = (np.diff(s) != 0).sum() / dur
    g = (h['t'] > t1) & (h['t'] <= t2) & h['g_ok']
    if g.sum() >= 30:
        e = h['eye'][g]; mu = e.mean(0); mu /= np.linalg.norm(mu); gaze_disp = angle(e, mu).mean()
        ev = k['eyev'][m]; fast = np.nan_to_num(ev) > 60; saccades = (np.diff(fast.astype(int)) == 1).sum() / dur
    else:
        gaze_disp = saccades = np.nan
    return dict(pause=pause, yaw_rev=yaw_rev, gaze_disp=gaze_disp, saccades=saccades, head_speed=k['ang'][m].mean())


def per_second(x_t, x, s0):  # mean of x over each of the 8 seconds of a clip starting at s0
    out = np.full(8, np.nan)
    for s in range(8):
        m = (x_t > s0 + s) & (x_t <= s0 + s + 1)
        if m.sum(): out[s] = np.nanmean(x[m])
    return out


def vjepa_index():
    vidx = {}
    for info in CACHE.glob('neuralset.extractors.video.HuggingFaceVideo*/*/*-info.jsonl'):
        for line in open(info): r = json.loads(line); vidx[r['#key'].rsplit('_', 2)[0]] = (info.parent, r['data'])
    return vidx


def vjepa_change(vidx, c):  # V-JEPA 2 features as the bench groups them; relative change between consecutive seconds
    if str(Path(c).resolve()) not in vidx: return np.full(8, np.nan)
    folder, dd = vidx[str(Path(c).resolve())]
    a = np.array(np.memmap(folder / dd['filename'], dtype=dd['dtype'], mode='r', offset=dd['offset'], shape=tuple(dd['shape'])), dtype=np.float32)
    L = a.shape[1]; k = np.unique([int(i * (L - 1)) for i in (0.5, 0.75, 1.0)]).tolist(); k[-1] += 1
    f = np.concatenate([a[:, l1:l2].mean(1) for l1, l2 in zip(k[:-1], k[1:])], axis=1)  # (16 time, D)
    f = f.reshape(8, 2, -1).mean(1)
    ch = np.full(8, np.nan); ch[1:] = np.linalg.norm(np.diff(f, axis=0), axis=1) / np.linalg.norm(f, axis=1).mean()
    return ch


def pixel_motion(c):  # mean absolute grey-level difference between frames, per second (64 x 36, 15 fps)
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', c, '-vf', 'scale=64:36,format=gray', '-r', '15', '-f', 'rawvideo', '-'],
                         capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64).astype(np.float32)
    d = np.abs(np.diff(fr, axis=0)).mean((1, 2)); t = (np.arange(1, len(fr)) + 0.5) / 15
    return per_second(t, d, 0.0)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    E = dict(np.load(WORK / 'episodes.npz', allow_pickle=True))
    clip = np.array([str(WORK / 'clips' / 'REAL' / f'{r}_{int(k):03d}.mp4') for r, k in zip(E['rec'], E['k'])])
    have = np.array([os.path.exists(c[:-4] + '.tribe.npy') for c in clip])
    E = {k: v[have] for k, v in E.items()}; clip = clip[have]; n = len(clip)
    print(f'{n} episodes with TRIBE, {len(set(E["rec"]))} recordings', flush=True)
    names, idx = parcels()
    T = np.stack([np.stack([np.load(c[:-4] + '.tribe.npy')[:, i].mean(1) for i in idx], 1) for c in clip])  # (n, 8, 360)
    beh = {k: np.full(n, np.nan) for k in ('pause', 'yaw_rev', 'gaze_disp', 'saccades', 'head_speed')}
    sec = {k: np.full((n, 8), np.nan) for k in ('partner_arousal', 'head_speed', 'vjepa_change', 'pixel_motion')}
    vidx = vjepa_index()
    for rec in sorted(set(E['rec'])):
        cam = np.load(WORK / 'cams' / f'{rec}.npz'); t0 = cam['ts'][0]; ts = (cam['ts'] - t0) / 1e7
        h = hololens(rec, t0); k = head_kinematics(h)
        body = load_body('interactee', rec)
        bt, bs = body_speed(body, cam['frame'], ts) if body else (np.array([]), np.array([]))
        for i in np.where(E['rec'] == rec)[0]:
            t, s0 = float(E['t'][i]), float(E['clip_start'][i])
            for kk, v in behaviour_window(h, k, t - 2, t).items(): beh[kk][i] = v
            sec['partner_arousal'][i] = per_second(bt, bs, s0)
            sec['head_speed'][i] = per_second(k['tm'], k['ang'], s0)
            sec['vjepa_change'][i] = vjepa_change(vidx, clip[i])
            sec['pixel_motion'][i] = pixel_motion(clip[i])
        print(rec, (E['rec'] == rec).sum(), 'episodes', flush=True)
    beh['body_acc'] = E['P'][:, 79].astype(float)  # wearer's mean angular acceleration over the last 2 s (SMPL-X)
    np.savez(OUT / 'signals.npz', rec=E['rec'], scene=E['scene'], k=E['k'], t=E['t'], clip=clip, parcel=np.array(names),
             T=T.astype(np.float32), **{f'beh_{k}': v for k, v in beh.items()}, **{f'sec_{k}': v for k, v in sec.items()})
    print('wrote', OUT / 'signals.npz')


if __name__ == '__main__':
    main()
