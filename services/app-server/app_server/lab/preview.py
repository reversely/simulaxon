"""Live previews: the current parameter values of a project, rendered in Isaac and read by TRIBE, in the fast lane.

One preview per set of values, cached by content: the same values give the same render, clip, response and map, so
undo and repeat cost nothing. Progress is broadcast as events ({"preview": project_id, "stage": ...}) so the room
and the brain beside it update. Results are rows of kind "preview", never mixed into a run's samples.
"""
from __future__ import annotations
import os, shutil
import hashlib, json, subprocess, threading, time
from pathlib import Path
import numpy as np
from ..jobs import Connector, Queue
from . import maps, regions, worlds
from .ingest import FILES, ROOT

FE = ROOT / 'feasibility'
_q: Queue | None = None
_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}   # one render per set of values, however many callers ask
REVISION = 'isaac-6.2.0 scene-worker 3'
on_job = lambda msg: None   # set by the app: every stimulus's stages go to the live workspace   # part of every cache key: a renderer change never reuses an old clip


CONNECTORS = [('isaac_counter', 'renderer', 'isaac-6.2.0-counter'), ('isaac_stage', 'renderer', 'isaac-6.2.0-stage'), ('isaac_body', 'renderer', 'isaac-6.2.0-body'),
              ('tribe_v2', 'neural model', 'tribev2-bf16'), ('cosmos_sim_transfer', 'generator', 'cosmos3-nano-sim-transfer-c3a2e37'),
              ('vjepa_embed', 'neural model', 'vjepa2-vitg-fpc64-256')]


def remote() -> bool:
    """Every connector runs on render-score's queue: on the node it is found through Fuzzball, elsewhere RENDER_SCORE_URL
    names it (on the Spark, the same server started locally)."""
    return bool(os.environ.get('RENDER_SCORE_URL') or os.environ.get('FB_WORKFLOW_ID'))


def queue() -> Queue:
    global _q
    with _lock:
        if _q is None and remote():
            from ..config import render_score_url
            _q = Queue([Connector(cid, kind, '', '', rev, url=render_score_url) for cid, kind, rev in CONNECTORS])
        if _q is None:   # no worker server named: say so rather than start workers from somewhere else
            raise RuntimeError('no worker server: start services/render-score/server.py and set RENDER_SCORE_URL (docs/spark-layout.md)')
        if not getattr(_q, '_holds', False):   # renders made ahead wait for any run in progress (#13)
            from . import runner; _q.hold_ahead = lambda: bool(runner.LIVE); _q._holds = True
        return _q


def _url(p):
    return '/files/' + str(Path(p).resolve().relative_to(FILES.resolve()))


def _ff(*a):
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', *map(str, a)], check=True)


def _clip(res: dict, out: Path) -> Path:
    """3 s of the stimulus (a still, or the 90 motion frames), then 7 s of mid-grey: the paradigm every run uses."""
    clip = out.with_suffix('.mp4')
    if clip.exists(): return clip
    on = out.with_name(out.stem + '_on.mp4'); grey = out.parent / 'grey7.mp4'
    if res.get('frames'): _ff('-framerate', '30', '-i', Path(res['frames']) / 'frame_%03d.png', '-vf', 'scale=832:480,format=yuv420p', '-an', '-c:v', 'libx264', on)
    else: _ff('-loop', '1', '-i', res['rgb'], '-t', '3', '-r', '30', '-vf', 'scale=832:480,format=yuv420p', '-an', '-c:v', 'libx264', on)
    if not grey.exists(): _ff('-f', 'lavfi', '-i', 'color=c=0x808080:s=832x480:r=30', '-t', '7', '-vf', 'format=yuv420p', '-an', '-c:v', 'libx264', grey)
    lst = out.with_suffix('.txt'); lst.write_text(f"file '{on.resolve()}'\nfile '{grey.resolve()}'\n")
    _ff('-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy', clip)
    return clip


def _wait(j, on_start, limit_s: float = 3600):
    """Wait for a queued job, calling on_start once the queue actually starts it, so a card says waiting until then."""
    t0 = time.time(); started = False
    while not j.done.wait(1.0):
        if not started and j.status == 'running': on_start(); started = True
        if time.time() - t0 > limit_s: break
    if not started: on_start()


def render_and_read(inputs: dict, out: Path, key: str, lane: str = 'fast', on_render=None, ctx: dict | None = None, on_start=None) -> dict:
    """One stimulus through the whole pipeline: Isaac renders it, the paradigm clip is made, TRIBE reads it.
    Returns the frame, the clip, the response file and the per-vertex readout over the seconds on screen."""
    out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    job = lambda stage, **k: on_job({'key': key, 'stage': stage, 'world': inputs.get('kind'), 'lane': lane, 'elapsed_s': round(time.time() - t0, 1), **(ctx or {}), **k})
    done = {'rgb': out / f'{key}.png', 'clip_on': out / f'{key}_on.mp4', 'preds': out / f'{key}.tribe.npy', 'on': out / f'{key}.on.npy'}
    if not all(p.exists() for p in done.values()):   # the same key rendered for another project or run: link it in rather than render again
        for d in [FILES / 'runs' / 'clips', *(x for x in (FILES / 'previews').glob('*') if x.is_dir()), *(x for x in (FILES / 'runs').glob('*') if x.is_dir())]:
            if d != out and all((d / q.name).exists() for q in done.values()):
                for q in done.values():
                    if not q.exists():
                        try: os.link(d / q.name, q)
                        except OSError: shutil.copy2(d / q.name, q)
                break
    if all(p.exists() for p in done.values()):   # the same inputs and renderer revision already went through Isaac and TRIBE
        if on_render: on_render({'rgb': str(done['rgb']), 'cached': True})
        job('done', cached=True, image=_url(done['rgb']))
        return {'rgb': str(done['rgb']), 'clip_on': str(done['clip_on']), 'preds': str(done['preds']), 'on': np.load(done['on']), 'mask_labels': [], 'cached': True}
    job('waiting')   # queued: the GPU runs one job at a time, runs before previews before options
    if inputs['kind'] == 'body':   # the moment's motion for both bodies, built once per moment and keyframe spacing
        import sys; sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'studies' / 'observer')); from motion_lib import build as build_motion   # Simulaxon's own study code
        mf = FILES / 'motion' / f"{inputs['rec']}_{inputs['k']:03d}_k{inputs['keyframe_s']}.npz"; build_motion(inputs['rec'], inputs['k'], inputs['keyframe_s'], str(mf))
        r = queue().submit('isaac_body', {**inputs, 'motion_file': str(mf), 'out_dir': str(out), 'name': key}, {}, lane=lane)
    else:
        r = queue().submit('isaac_stage' if inputs['kind'] == 'stage' else 'isaac_counter', {**inputs, 'out_dir': str(out), 'name': key}, {}, lane=lane)
    _wait(r, lambda: (job('rendering'), on_start and on_start()))   # on_start: the GPU has taken the render, no longer queued
    if r.status != 'done': raise RuntimeError(r.error or 'render failed')
    if r.outputs.get('clip'):   # a world that renders the whole stimulus clip itself (body): its frame and clip under the usual names
        for src, dst in ((r.outputs['rgb'], done['rgb']), (r.outputs['clip'], done['clip_on'])):
            if not Path(dst).exists(): os.link(src, dst)
        r.outputs = {**r.outputs, 'rgb': str(done['rgb'])}
    if on_render: on_render(r.outputs)
    job('waiting', image=_url(r.outputs['rgb']), render_s=r.outputs.get('render_s'), next='reading')
    clip = Path(r.outputs['clip']) if r.outputs.get('clip') else _clip(r.outputs, out / key)
    n = queue().submit('tribe_v2', {'clip': str(clip)}, {'on_s': r.outputs.get('on_s', [0, 3])}, lane=lane); _wait(n, lambda: job('reading', image=_url(r.outputs['rgb'])))
    if n.status != 'done': raise RuntimeError(n.error or 'TRIBE failed')
    job('done', cached=False, image=_url(r.outputs['rgb']))
    return {'rgb': r.outputs['rgb'], 'clip_on': str(out / f'{key}_on.mp4'), 'preds': n.outputs['response'], 'on': np.load(n.outputs['readout']),
            'mask_labels': r.outputs.get('mask_labels', [])}


def _label(values: dict, assets: dict) -> str:
    """A short name for one stimulus: its asset, then any non-default choice."""
    item = values.get('item') or values.get('hidden') or values.get('moment')
    name = assets.get(item, {}).get('label', item) if item and item != 'none' else 'Whole room'
    extra = [str(values[k]).replace('_', ' ') for k in ('outcome', 'colour', 'camera') if k in values and values[k] not in ('full', 'lands', 'corner_a')]
    extra += [{'human': 'human', 'g1': 'G1'}.get(values['body'], values['body']) + ', ' + values['motion'] + ' motion'] if 'body' in values and 'motion' in values else []
    return ', '.join([name] + extra)


def start(tools, broadcast, project_id: str, actor: str, values: dict | None = None, source: str = 'Preview', lane: str | None = None):
    """Queue a preview of the project's current values, or of given changes to them (a demo preparing a step ahead).
    Returns at once; events report each stage."""
    s = tools.store; row = s.get('project', project_id)
    if row is None: return None   # the project was deleted, for example under a demo written against it
    P = row.data; w = P.get('world')
    if not w: return None
    params = {r.data['name']: r.data['value'] for r in s.list('parameter') if r.data.get('project_id') == project_id}
    params = {**params, **(values or {})}
    inputs = worlds.job(w['kind'], params, tools.all_assets(project_id), w)
    key = hashlib.sha1(json.dumps([REVISION, inputs], sort_keys=True).encode()).hexdigest()[:14]
    out = FILES / 'previews' / project_id; out.mkdir(parents=True, exist_ok=True)

    def run():
        ev = lambda stage, **k: broadcast({'preview': project_id, 'key': key, 'stage': stage, 'actor': actor, 'ahead': values is not None, **k}) if values is None or stage == 'done' else None
        with _lock:
            other = _inflight.get(key); mine = other is None
            if mine: _inflight[key] = threading.Event()
        if not mine:   # the same render is already under way, for a demo preparing ahead or another panel
            ev('underway'); other.wait(3600); ev('done', cached=True); return
        try:
            cached = [r for r in s.list('preview') if r.data.get('key') == key]
            if cached:
                ev('done', cached=True); return
            ev('waiting')   # queued behind whatever the GPU is doing; 'render' once it starts
            res = render_and_read(inputs, out, key, lane or ('batch' if values else 'fast'), lambda o: ev('rendered', image=f"/files/previews/{project_id}/{key}.png", render_s=o.get('render_s')), on_start=lambda: ev('render'),
                                  ctx={'project': project_id, 'title': P.get('title'), 'label': _label(params, tools.all_assets(project_id)), 'source': source, 'actor': actor})
            on = res['on']; ev('drawing'); mp = maps.render(on, 'single', FILES)   # several seconds the first time: the room says so
            tools.call('preview_create', actor, project_id=project_id, key=key, values=params, inputs=inputs,
                       image=f"/files/previews/{project_id}/{key}.png", clip=f"/files/previews/{project_id}/{key}_on.mp4",
                       readout={k: round(v, 4) for k, v in regions.readout(on).items()}, map=mp, mask_labels=res['mask_labels'])
            ev('done')
        except Exception as e:
            ev('failed', error=str(e)[-300:])
        finally:
            with _lock: _inflight.pop(key).set()
    threading.Thread(target=run, daemon=True).start()
    return {'key': key, 'queued': True}
