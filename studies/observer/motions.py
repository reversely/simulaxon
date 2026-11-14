"""The observer demo, stage 1 (doc 24 § 13, doc 25): pick the moments and build both motions for both bodies.

Moments, by a fixed rule: among the 345 EgoBody decision points (episodes.npz), the one per recording where the camera
wearer's upper body moves most over the 9 s window (8 s before the decision point to 1 s after: the window the G1 clips
of the mirroring test use), measured as the mean angular speed of the 13 upper-body joints from EgoBody's SMPL-X fits;
then the N recordings whose best moment moves most.

Motions, both from the same fits at 30 fps (the nearest camera frame with a fit within 50 ms, else the last fit held):
  recorded  the wearer's own motion, frame by frame
  robotic   the same poses at keyframes every 0.5 s, joined at constant angular speed (every joint slerped linearly in
            time, pelvis moved linearly), so the poses match the recorded motion at every keyframe and only the timing
            differs: smooth human velocity against constant velocity with abrupt changes (plan 24, replication R4)
Bodies, both driven by the same motion:
  human     SMPL-X v1.1 mesh (the fit's gender, 12 PCA hand components as EgoBody fitted), vertices in the room scan
  g1        13 upper-body joints as 6-D rotations, pelvis and facing in the room scan (what isaac/g1_execute.py reads)

usage (feasibility/.venv): python observer/motions.py [N]    writes OUT/moments.json, moments_items.json, motion/<rec>_<k>.npz
Environment (set by a run): OBS_OUT output folder (default ~/data/observer); OBS_KEY_S keyframe spacing in seconds (0.5);
OBS_MOMENTS a JSON list of {recording, episode} to use instead of the rule (a curated view); OBS_SKIP a JSON list of
'recording#episode' to leave out (moments earlier rounds used).
"""
import glob, json, os, pickle, sys
import numpy as np, torch, smplx
from scipy.spatial.transform import Rotation as Rot, Slerp

ROOT = os.path.expanduser('~/data/egobody'); WORK = os.path.join(ROOT, 'work'); OUT = os.path.expanduser(os.environ.get('OBS_OUT', '~/data/observer'))
MODELS = os.path.expanduser('~/data/body_models/models')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 6
U13 = [2, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
PELVIS = np.array([0.0031, -0.3514, 0.0120])   # SMPL-X neutral pelvis at rest, as isaac/g1_execute.py
KEY = max(2, round(float(os.environ.get('OBS_KEY_S', 0.5)) * 30))   # robotic keyframes, in frames at 30 fps
os.makedirs(os.path.join(OUT, 'motion'), exist_ok=True); os.makedirs(os.path.join(OUT, 'clips'), exist_ok=True)
E = np.load(os.path.join(WORK, 'episodes.npz'), allow_pickle=True)


def cams(rec):
    c = np.load(os.path.join(WORK, 'cams', rec + '.npz'), allow_pickle=True)
    return c, (c['ts'] - c['ts'][0]) / 1e7


# ---- 1. moments (observer/motion_lib.py: the same rule the lab's EgoBody search uses)
from motion_lib import score_moments, pick_moments
SKIP = set(json.load(open(os.environ['OBS_SKIP']))) if os.environ.get('OBS_SKIP') else set()
WANT = [(m['recording'], int(m['episode'])) for m in json.load(open(os.environ['OBS_MOMENTS']))] if os.environ.get('OBS_MOMENTS') else None
if WANT is not None:   # a curated list: those moments, in the curation's order
    sc = [x for x in score_moments(SKIP, WANT) if x[1] is not None]; order = {w: j for j, w in enumerate(WANT)}
    best = sc; pick = sorted(sc, key=lambda x: order[(x[0], x[2])])[:N]
    rule = f'the {len(WANT)} moments of a curated view, in its order, first {N} with enough fitted frames'
else:
    P = pick_moments(N, SKIP); best, pick = P['best_per_recording'], P['picked']
    rule = f'per recording the decision point with the highest median upper-body angular speed over t-8..t+1 s; then the {N} recordings whose best moment moves most'
moments = [dict(rec=r, k=k, t=t, upper_body_speed_rad_s=round(s, 3), fitted_frames=n) for r, s, k, t, n in pick]
json.dump(dict(rule=rule, skipped=len(SKIP), candidates=len(best), keyframe_s=KEY / 30, moments=moments), open(os.path.join(OUT, 'moments.json'), 'w'), indent=1)
json.dump([dict(id=f"{m['rec']}_{m['k']:03d}", rec=m['rec'], k=m['k']) for m in moments], open(os.path.join(OUT, 'moments_items.json'), 'w'), indent=1)
print(f'{len(best)} candidates; picked', [(m['rec'][10:], m['k'], m['upper_body_speed_rad_s']) for m in moments], flush=True)


# ---- 2. motions and bodies per moment (observer/motion_lib.py, shared with the lab's body world)
from motion_lib import build
for m in moments:
    r = build(m['rec'], m['k'], KEY / 30, os.path.join(OUT, 'motion', f"{m['rec']}_{m['k']:03d}.npz"))
    print(m['rec'], m['k'], r, flush=True)
