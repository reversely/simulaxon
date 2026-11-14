"""Warm Isaac Sim worker for the body world (backend/vcl/lab/worlds.py, kind "body"). Runs in /data/envs/isaac
with OMNI_KIT_ACCEPT_EULA=YES and the libgomp preload.

One job is one cell: an EgoBody moment acted out by one body with one motion, in the scan of the real room, filmed from
the partner's eye (studies/observer/body_scene.py, the same code observer/render.py uses).
Job inputs:  {rec, k, body: human|g1, motion: recorded|robotic, motion_file (npz from observer/motion_lib.py), out_dir, name}
Outputs:     {clip: 9 s mp4 at 30 fps, rgb: the decision-point frame, on_s: [1, 9], frames, camera, seated, render_s, ...}
The stage is rebuilt only when the moment changes, so the four cells of one moment share one load.
"""
import json, sys, time
from pathlib import Path
from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'multi_gpu': False, 'extra_args': ['--enable', 'omni.rtx.spg', '--/renderer/multiGpu/enabled=false']})
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'studies' / 'observer'))
from body_scene import BodyScene, REVISION

scene = BodyScene(app)
print(json.dumps({'ready': True, 'revision': REVISION}), flush=True)
for line in sys.stdin:
    j = json.loads(line)
    try:
        x = j['inputs']; t0 = time.time()
        scene.load(x['rec'], int(x['k']), x['motion_file'])
        out = scene.render(x['body'], x['motion'], str(Path(x['out_dir']) / f"{x['name']}.mp4"))
        print(json.dumps({'job_id': j['job_id'], 'outputs': {**out, 'render_s': round(time.time() - t0, 1), 'revision': REVISION}}, default=str), flush=True)
    except Exception as e:
        import traceback; traceback.print_exc(file=sys.stderr)
        print(json.dumps({'job_id': j['job_id'], 'error': f'{type(e).__name__}: {e}'}), flush=True)
