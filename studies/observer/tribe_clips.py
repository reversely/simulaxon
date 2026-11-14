"""Test 19: TRIBE v2 (fast path: bf16 V-JEPA 2, one decode), video only, on every MP4 in a folder.
One timeline per clip, many clips per call: the batched path checked in test 17 (tribe_had.py --check).
Writes <clip>.tribe.npy (seconds x 20484) beside each clip; resumable. V-JEPA 2 features land in cache_fast,
keyed by the clip's path, as test 18 reads them.
usage (feasibility/.venv): python egobody/tribe_clips.py CLIP_DIR [BATCH] [--wait [--until N]]   (--wait: keep polling for new clips; --until: stop at N)
"""
import glob, os, sys, time
from pathlib import Path
import numpy as np, pandas as pd
here = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(here)); sys.path.insert(0, str(here / 'tribev2-src'))
from fast_tribe import load
sys.path.insert(0, str(here / 'egobody')); import memwait
from neuralset.events.utils import standardize_events

d = sys.argv[1]; batch = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 25; wait = '--wait' in sys.argv
until = int(sys.argv[sys.argv.index('--until') + 1]) if '--until' in sys.argv else 0  # with --wait: stop once this many predictions exist
model = load(cache_folder=str(here / 'cache_fast'))


def predict_batch(paths):
    ev = standardize_events(pd.DataFrame([{'type': 'Video', 'filepath': str(p), 'start': 0.0, 'timeline': f't{i}', 'subject': 'default'}
                                          for i, p in enumerate(paths)]))
    p, segs = model.predict(ev, verbose=False)
    tl = np.array([s.timeline for s in segs])
    return [p[tl == f't{i}'] for i in range(len(paths))]


while True:
    todo = sorted(p for p in glob.glob(os.path.join(d, '*.mp4')) if not os.path.exists(p[:-4] + '.tribe.npy'))
    for k in range(0, len(todo), batch):
        memwait.wait(label='TRIBE batch'); chunk = todo[k:k + batch]; t0 = time.time()
        try:  # the GPU is shared: a failed batch (e.g. out of memory) waits and is retried next round
            ys = predict_batch([os.path.abspath(p) for p in chunk]); fails = 0
        except Exception as e:
            fails = globals().get('fails', 0) + 1
            print(f'batch failed ({fails} in a row): {type(e).__name__}: {str(e)[:200]}', flush=True)
            if fails >= 5: sys.exit(1)
            import torch; torch.cuda.empty_cache(); time.sleep(300); continue
        for p, y in zip(chunk, ys):
            np.save(p[:-4] + '.tribe.npy', np.asarray(y, np.float32))
        print(f'{d}: {k + len(chunk)}/{len(todo)} this round, batch of {len(chunk)} in {time.time() - t0:.0f} s', flush=True)
    if not wait and not any(not os.path.exists(p[:-4] + '.tribe.npy') for p in todo): break
    if not wait and globals().get('fails', 0): continue
    if until and len(glob.glob(os.path.join(d, '*.tribe.npy'))) >= until: break
    if not todo: time.sleep(120)
print('done', d)
