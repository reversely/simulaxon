"""EgoBody room scan reader, the same as isaac/g1_execute.py's (copied, so that script stays untouched)."""
import os
import numpy as np


def load_scan(path):
    """EgoBody's room scan OBJ, read directly (trimesh drops the per-vertex colours). Two kinds: older rooms give a
    colour per vertex ("v x y z r g b"); the 2022 rooms give texture coordinates and an 8k texture (map_Kd)."""
    vs, vts, fs = [], [], []
    for line in open(path):
        if line.startswith('v '): vs.append(line.split()[1:])
        elif line.startswith('vt '): vts.append(line.split()[1:3])
        elif line.startswith('f '): fs.append([w.split('/') for w in line.split()[1:4]])
    v = np.array(vs, float); f = np.array(fs)
    F_ = f[..., 0].astype(np.int64) - 1
    col = v[:, 3:6] if v.shape[1] >= 6 else None
    uv = np.array(vts, float) if vts else None
    Fuv = f[..., 1].astype(np.int64) - 1 if uv is not None and f.shape[-1] > 1 else None
    tex = None
    for line in open(path):
        if line.startswith('mtllib'):
            for m in open(os.path.join(os.path.dirname(path), line.split()[1])):
                if m.startswith('map_Kd'): tex = os.path.join(os.path.dirname(path), m.split()[1])
            break
    return v[:, :3], F_, col, uv, Fuv, tex
