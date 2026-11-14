"""The observer study's render from the command line: two bodies x two motions per moment, same room, same camera.
The scene is feasibility/observer/body_scene.py, the same code the lab's warm worker uses (backend/workers/isaac_body_worker.py).

For each moment from observer/motions.py, four 9 s clips at 30 fps (8 s before the decision point to 1 s after):
  g1_recorded, g1_robotic, human_recorded, human_robotic
usage (feasibility/isaac, source env.sh): .venv/bin/python ../observer/render.py REC K | --item ITEM_FILE
writes OBS_OUT/clips/<rec>_<k>_<body>_<motion>.mp4 (+ _decision.png) and <rec>_<k>_render.json (OBS_OUT default ~/data/observer)
"""
import argparse, json, os, sys
ap = argparse.ArgumentParser(); ap.add_argument('rec', nargs='?'); ap.add_argument('k', type=int, nargs='?'); ap.add_argument('--item'); ap.add_argument('--res', default='960x540')
a = ap.parse_args()
if a.item: _it = json.load(open(a.item))[0]; a.rec, a.k = _it['rec'], int(_it['k'])   # a run's item file: [{id, rec, k}]
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'egobody')); import memwait; memwait.wait(30, 'observer render')
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'multi_gpu': False, 'extra_args': ['--enable', 'omni.rtx.spg', '--/renderer/multiGpu/enabled=false']})
sys.path.insert(0, HERE)
from body_scene import BodyScene, REVISION

W, H = map(int, a.res.split('x'))
OBS = os.path.expanduser(os.environ.get('OBS_OUT', '~/data/observer')); OUT = os.path.join(OBS, 'clips'); os.makedirs(OUT, exist_ok=True)
scene = BodyScene(app, W, H); info = scene.load(a.rec, a.k, os.path.join(OBS, 'motion', f'{a.rec}_{a.k:03d}.npz'))
print('camera:', info['camera'], flush=True)
log = {**info, 'revision': REVISION, 'clips': {}}
for body in ('g1', 'human'):
    for motion in ('recorded', 'robotic'):
        out = os.path.join(OUT, f'{a.rec}_{a.k:03d}_{body}_{motion}.mp4')
        if os.path.exists(out): log['clips'][f'{body}_{motion}'] = out; continue
        r = scene.render(body, motion, out); log['clips'][f'{body}_{motion}'] = out
        print('wrote', out, r['frames'], 'frames' + (f", worst retarget error {r['retarget_worst_deg']} deg" if body == 'g1' else ''), flush=True)
json.dump(log, open(os.path.join(OUT, f'{a.rec}_{a.k:03d}_render.json'), 'w'), indent=1)
app.close()
