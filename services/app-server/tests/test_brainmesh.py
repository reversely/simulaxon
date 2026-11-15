"""The fsaverage5 file the page draws brains on (#27): its layout and that it is TRIBE's vertex order."""
import json, struct
import numpy as np
from app_server.lab import brainmesh


def test_mesh_layout():
    b = brainmesh.build(); L = struct.unpack('<I', b[:4])[0]; h = json.loads(b[4:4 + L]); base = 4 + L
    assert (h['n'], h['n_left']) == (20484, 10242)   # TRIBE v2's predictions are 20,484 values, left hemisphere first
    a = {k: np.frombuffer(b, dtype='<' + v['dtype'], count=int(np.prod(v['shape'])), offset=base + v['offset']).reshape(v['shape']) for k, v in h['arrays'].items()}
    assert a['faces'].shape == (40960, 3) and a['faces'].max() == 20483 and a['faces'][:20480].max() == 10241
    pial = a['pial'] / h['scale'] + np.array(h['centre_mm'])   # stored around the half-inflated brain's centre
    assert pial[:10242, 0].max() <= 0.01 and pial[10242:, 0].min() >= -0.01   # hemispheres moved apart until they touch, as TRIBE's plotter does
    assert a['sulc'].min() == 0 and a['sulc'].max() == 255
