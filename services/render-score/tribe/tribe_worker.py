"""Warm worker for tribe_v2. Runs in the feasibility environment (torch 2.9.1 for CUDA 13).

Job inputs:  {"clip": "/path/clip.mp4"}            one clip per job; never concatenate clips
Job settings: {"on_s": [0, 3]}                     seconds the stimulus is on, used for the readout
Outputs:     {"response": "/path/clip.tribe.npy", "seconds": n, "readout": per-vertex mean over on_s saved as .on.npy}
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'feasibility'))
import numpy as np
from fast_tribe import load, predict_clip

model = load(cache_folder=Path(__file__).resolve().parents[2] / 'feasibility' / 'cache_fast')
print(json.dumps({'ready': True}), flush=True)
for line in sys.stdin:
    j = json.loads(line)
    try:
        clip = Path(j['inputs']['clip']); p = predict_clip(model, clip)
        a, b = j['settings'].get('on_s', [0, 3])
        out = clip.with_suffix('.tribe.npy'); np.save(out, p.astype(np.float16))
        on = clip.with_suffix('.on.npy'); np.save(on, p[a:b].mean(0).astype(np.float32))
        print(json.dumps({'job_id': j['job_id'], 'outputs': {'response': str(out), 'readout': str(on), 'seconds': int(len(p))}}), flush=True)
    except Exception as e:
        print(json.dumps({'job_id': j['job_id'], 'error': f'{type(e).__name__}: {e}'}), flush=True)
