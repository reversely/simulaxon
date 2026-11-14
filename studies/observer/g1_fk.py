"""Forward kinematics of the G1, from the joint frames in g1_kinematics.json (written by g1_kinematics.py).
A USD physics joint ties a frame on its parent body (pos0, rot0) to one on its child (pos1, rot1); a revolute joint
turns the child about its axis by q (radians) in that frame:  child = parent . T(pos0, rot0) . Rot(axis, q) . T(pos1, rot1)^-1
"""
import json
import numpy as np
from scipy.spatial.transform import Rotation as Rot

AX = {'X': [1, 0, 0], 'Y': [0, 1, 0], 'Z': [0, 0, 1]}


def tf(pos, q_wxyz):
    M = np.eye(4); M[:3, :3] = Rot.from_quat([q_wxyz[1], q_wxyz[2], q_wxyz[3], q_wxyz[0]]).as_matrix(); M[:3, 3] = pos; return M


class G1FK:
    def __init__(self, path, root='pelvis'):
        self.j = json.load(open(path))['joints']; self.root = root
        self.parent = {jj['body1'].split('/')[-1]: (n, jj['body0'].split('/')[-1]) for n, jj in self.j.items() if jj['body0'] and jj['body1']}
        self.fixed = {n: tf(jj['pos0'], jj['rot0']) for n, jj in self.j.items()}
        self.inv1 = {n: np.linalg.inv(tf(jj['pos1'], jj['rot1'])) for n, jj in self.j.items()}

    def chain(self, link):
        out = []
        while link != self.root:
            if link not in self.parent: raise KeyError(f'{link} has no joint path to {self.root}')
            n, link = self.parent[link]; out.append(n)
        return out[::-1]

    def chain_joints(self, links=('left_wrist_roll_link', 'right_wrist_roll_link')):
        return list(dict.fromkeys(n for l in links for n in self.chain(l) if self.j[n]['type'] == 'revolute'))

    def link_world(self, link, q, base=None):
        M = np.eye(4) if base is None else base.copy()
        for n in self.chain(link):
            A = np.eye(4)
            if self.j[n]['type'] == 'revolute': A[:3, :3] = Rot.from_rotvec(np.array(AX[self.j[n]['axis']], float) * q.get(n, 0.0)).as_matrix()
            M = M @ self.fixed[n] @ A @ self.inv1[n]
        return M
