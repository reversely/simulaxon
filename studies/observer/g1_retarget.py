"""Retarget an SMPL-X upper-body pose (test 19's 13 joints, 6-D each) to the G1 by matching limb directions.

Directions, not joint angles, are matched: the G1's shoulder and elbow axes differ from SMPL-X's, and decomposing the
human rotations into the G1's joint angles directly (Euler angles) put a forearm that hung down pointing up (2026-11-14).
  waist: the G1's three waist joints fitted to the human torso's rotation relative to the pelvis (spine1 . spine2 . spine3)
  arms:  each arm's shoulder pitch, roll, yaw and elbow fitted, waist held, so the G1's upper arm (shoulder to elbow) and
         forearm (elbow to wrist) point where the human's do, in the pelvis frame; bounded by the G1's joint limits
Each fit reports its remaining angle error per limb. Forward kinematics: g1_fk.py, checked against Isaac's link poses.
SMPL-X frame: x left, y up, z forward; the G1's: x forward, y left, z up. Rest pose: SMPL-X arms along +x (left), -x (right).
"""
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation as Rot
from g1_fk import G1FK

U = [2, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]   # SMPL-X body_pose indices of the 13 predicted joints
Ui = {j: i for i, j in enumerate(U)}
A = np.array([[0, 0, 1], [1, 0, 0], [0, 1, 0]], float)  # SMPL-X axes -> G1 axes


def six2mats(x):
    x = np.asarray(x, float).reshape(13, 3, 2); a_, b_ = x[..., 0], x[..., 1]
    a_ = a_ / np.linalg.norm(a_, axis=-1, keepdims=True); b_ = b_ - (a_ * b_).sum(-1, keepdims=True) * a_; b_ = b_ / np.linalg.norm(b_, axis=-1, keepdims=True)
    return np.stack([a_, b_, np.cross(a_, b_)], -1)


def human_targets(six):
    """Torso rotation and unit limb directions of the human pose, in the G1's pelvis axes."""
    R = six2mats(six); sp = R[Ui[2]] @ R[Ui[5]] @ R[Ui[8]]
    t = {'torso': A @ sp @ A.T}
    for side, col, sh, el, rest in (('left', 12, 15, 17, [1, 0, 0]), ('right', 13, 16, 18, [-1, 0, 0])):
        up = sp @ R[Ui[col]] @ R[Ui[sh]]
        t[side + '_upper'] = A @ up @ np.array(rest, float)
        t[side + '_fore'] = A @ up @ R[Ui[el]] @ np.array(rest, float)
    return t


def angle(a, b):
    return float(np.degrees(np.arccos(np.clip(a @ b / np.linalg.norm(a) / np.linalg.norm(b), -1, 1))))


class Retarget:
    WAIST = ['waist_yaw_joint', 'waist_roll_joint', 'waist_pitch_joint']

    def __init__(self, kin_json):
        self.fk = G1FK(kin_json)
        self.lim = {n: (np.radians(j['lower']), np.radians(j['upper'])) for n, j in self.fk.j.items() if j['type'] == 'revolute'}
        self.arm = {s: [f'{s}_shoulder_pitch_joint', f'{s}_shoulder_roll_joint', f'{s}_shoulder_yaw_joint', f'{s}_elbow_joint'] for s in ('left', 'right')}
        self.T0 = self.fk.link_world('torso_link', {})[:3, :3]

    def jpos(self, n, q):  # a joint's position in the pelvis frame
        parent = self.fk.j[n]['body0'].split('/')[-1]
        M = np.eye(4) if parent == self.fk.root else self.fk.link_world(parent, q)
        return (M @ self.fk.fixed[n])[:3, 3]

    def limbs(self, s, q):
        sh, el, wr = (self.jpos(f'{s}_{n}_joint', q) for n in ('shoulder_pitch', 'elbow', 'wrist_roll'))
        return (el - sh) / np.linalg.norm(el - sh), (wr - el) / np.linalg.norm(wr - el)

    def bounds(self, names):
        lo = np.array([self.lim[n][0] for n in names]); hi = np.array([self.lim[n][1] for n in names]); return lo, hi

    def fit(self, six, prev=None):
        """prev: the previous frame's joint angles. For a motion, each frame starts from the last one, so the arms move
        continuously instead of jumping between equally good solutions; the usual starts are tried too if that fit is poor."""
        t = human_targets(six); q = {}
        lo, hi = self.bounds(self.WAIST)
        def rw(x):
            Rg = self.fk.link_world('torso_link', dict(zip(self.WAIST, x)))[:3, :3] @ self.T0.T
            return Rot.from_matrix(Rg.T @ t['torso']).as_rotvec()
        w0 = np.array([prev[n] for n in self.WAIST]) if prev else np.zeros(3)
        w = least_squares(rw, np.clip(w0, lo + 1e-6, hi - 1e-6), bounds=(lo, hi)); q.update(zip(self.WAIST, w.x))
        err = {'torso_deg': float(np.degrees(np.linalg.norm(rw(w.x))))}
        for s in ('left', 'right'):
            names = self.arm[s]; lo, hi = self.bounds(names)
            def ra(x):
                u, f = self.limbs(s, {**q, **dict(zip(names, x))}); return np.r_[u - t[s + '_upper'], f - t[s + '_fore']]
            best = None
            starts = [[0, 0, 0, 0], [0, 0, 0, 1.0], [-1.0, 0, 0, 1.0], [0, 0.8 if s == 'left' else -0.8, 0, 1.0], [-1.5, 0, 0, 0.3]]
            if prev:
                best = least_squares(ra, np.clip(np.array([prev[n] for n in names]), lo + 1e-6, hi - 1e-6), bounds=(lo, hi))
                if best.cost < 1e-4: starts = []   # under about 1 degree off: keep the continuous solution
            for x0 in starts:
                r = least_squares(ra, np.clip(np.array(x0, float), lo + 1e-6, hi - 1e-6), bounds=(lo, hi))
                if best is None or r.cost < best.cost: best = r
            q.update(zip(names, best.x))
            u, f = self.limbs(s, q)
            err[s + '_upper_deg'] = angle(u, t[s + '_upper']); err[s + '_fore_deg'] = angle(f, t[s + '_fore'])
        return q, err
