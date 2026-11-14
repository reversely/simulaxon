"""HTTP API and web UI for datasets of samples.

usage: python -m vcl.data.server [--port 8791]

  GET  /api/datasets                         every dataset, how it was loaded, sample count
  POST /api/datasets/load                    {source} -> loads or reloads a dataset from backend/sources/<file>.json
  GET  /api/datasets/{name}                  its source description and schema (paths, types, counts)
  POST /api/datasets/{name}/view             {stages, offset, limit} -> samples in the view, count after each stage, facets
  GET  /api/datasets/{name}/samples/{id}     one sample: every field with the file and key it came from, its group
  GET  /api/datasets/{name}/samples/{id}/track?path=   a time track: time axis and values (wide tracks summarised, and said so)
  GET  /api/datasets/{name}/samples/{id}/track_full?path=   every column of a track as float32 bytes (the cortex view)
  GET  /api/runs                             every run: plan, steps, live state, log tail
  POST /api/runs/{name}/start                starts or resumes a run in the server
  POST /api/agent                            {dataset, stages, message, history} -> reply, tool calls, view to show
  GET  /media/{path}                         a media file that some loaded sample points to; nothing else is served
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from . import loaders, runs, store, views

ROOT = Path(__file__).resolve().parents[3]; UI = ROOT / 'app' / 'dist'
PORT = 8791
WIDE = 32   # tracks with more columns than this are returned as mean and spread across columns
app = FastAPI(); _db = store.connect()


def con():
    """One cursor per call: DuckDB refuses concurrent calls on a single connection."""
    return _db.cursor()


def rows(name: str):
    r = store.samples(con(), name)
    if not r: raise HTTPException(404, f'no dataset {name}')
    return r


@app.get('/api/datasets')
def list_datasets():
    return store.datasets(con())


class Load(BaseModel):
    source: str   # a source description under backend/sources/, e.g. backend/sources/so101_sim.json


@app.post('/api/datasets/load')
def load(b: Load):
    """Loads or reloads a dataset from its source description, on the server's own connection (DuckDB allows one writer)."""
    f = (ROOT / b.source).resolve()
    if f.parent != (ROOT / 'backend' / 'sources').resolve() or not f.exists(): raise HTTPException(422, f'not a source description: {b.source}')
    r = loaders.load(f, con())
    return {'name': json.load(open(f))['name'], 'samples': len(r), 'with_media': sum(x['media'] is not None for x in r), 'schema': store.schema(r)}


@app.get('/api/datasets/{name}')
def dataset(name: str):
    d = next((x for x in store.datasets(con()) if x['name'] == name), None)
    if not d: raise HTTPException(404, f'no dataset {name}')
    return {**d, 'schema': [{**e, 'unit': d['source'].get('units', {}).get(e['path']), 'description': d['source'].get('descriptions', {}).get(e['path'])} for e in store.schema(rows(name))]}


class View(BaseModel):
    stages: list[dict] = []
    offset: int = 0
    limit: int = 60


@app.post('/api/datasets/{name}/view')
def view(name: str, v: View):
    try:
        out, trail = views.apply(rows(name), v.stages)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f'stage could not run: {e}')
    src = next((x['source'] for x in store.datasets(con()) if x['name'] == name), {})
    sch = [{**e, 'unit': src.get('units', {}).get(e['path']), 'description': src.get('descriptions', {}).get(e['path'])} for e in (store.schema(out) if out else [])]
    stored = {s['id']: s for s in rows(name)}
    page = [{k: s[k] for k in ('id', 'group', 'slice', 'media', 'media_type')} | {'fields': store.flatten(s['fields']),
             'computed_sources': {k: x for k, x in s['sources'].items() if k not in stored[s['id']]['sources']}}   # fields a stage added, and which stage
            for s in out[v.offset:v.offset + v.limit]]
    return {'count': len(out), 'trail': trail, 'schema': sch, 'facets': views.facets(out, sch), 'samples': page}


@app.get('/api/datasets/{name}/samples/{sid}')
def sample(name: str, sid: str):
    r = rows(name); s = next((x for x in r if x['id'] == sid), None)
    if not s: raise HTTPException(404, f'no sample {sid}')
    # each slice's scalar fields too, so the panel can show the same fields under every slice as the grid shows on tiles
    scal = lambda f: {k: v for k, v in store.flatten(f).items() if store.value_type(v) != 'track'}
    group = [{'id': x['id'], 'slice': x['slice'], 'media': x['media'], 'media_type': x['media_type'], 'fields': scal(x['fields'])} for x in r if x['group'] == s['group']]
    return {**s, 'fields': store.flatten(s['fields']), 'group_members': group}


def track_array(name: str, sid: str, path: str):
    """A track's times (s) and values (time x columns), with its field entry and unit."""
    s = next((x for x in rows(name) if x['id'] == sid), None)
    t = store.flatten(s['fields']).get(path) if s else None
    if not t or store.value_type(t) != 'track': raise HTTPException(404, f'no track {path} on {sid}')
    unit = next((x['source'] for x in store.datasets(con()) if x['name'] == name), {}).get('units', {}).get(path)
    f = ROOT / t['file']
    if t.get('format') == 'csv':
        import csv as _csv
        rows_ = list(_csv.DictReader(open(f)))
        num = lambda x: float(x) if x not in ('', None) else float('nan')
        tt = np.array([num(r[t['time_key']]) for r in rows_]); a = np.array([[num(r[c]) for c in t['columns']] for r in rows_])
    elif f.suffix == '.npz':
        z = np.load(f); a = np.asarray(z[t['key']], float); tt = np.asarray(z[t['time_key']], float) if t.get('time_key') else None
    else:
        a = np.asarray(np.load(f), float); tt = None
    if t.get('format') != 'csv' and tt is None: tt = t.get('offset_s', 0.0) + np.arange(len(a)) / (t.get('rate_hz') or 1.0)
    return tt, a.reshape(len(a), -1), t, unit


@app.get('/api/datasets/{name}/samples/{sid}/track_full')
def track_full(name: str, sid: str, path: str):
    """Every column of a track as float32 bytes (time x columns), for views that need them all, such as the cortex
    (TRIBE: 20,484 vertices a second). Times, shape and source travel in headers."""
    from fastapi import Response
    tt, a, t, unit = track_array(name, sid, path)
    return Response(np.asarray(a, np.float32).tobytes(), media_type='application/octet-stream',
                    headers={'X-Shape': f'{a.shape[0]},{a.shape[1]}', 'X-Time-S': ','.join(f'{x:g}' for x in tt), 'X-Source': t['file'],
                             'Access-Control-Expose-Headers': 'X-Shape, X-Time-S, X-Source'})


@app.get('/api/datasets/{name}/samples/{sid}/track')
def track(name: str, sid: str, path: str):
    tt, a, t, unit = track_array(name, sid, path)
    if a.shape[1] <= WIDE:
        a = np.where(np.isfinite(a), a, None)   # missing readings stay missing, never zero
        return {'time_s': tt.tolist(), 'columns': t.get('columns') or [str(i) for i in range(a.shape[1])], 'values': a.T.tolist(), 'summary': None, 'band': False, 'unit': unit,
                'source': f"{t['file']}{'#' + t['key'] if t.get('key') else ''}"}
    return {'time_s': tt.tolist(), 'columns': ['mean across columns', 'mean minus SD', 'mean plus SD'],
            'values': [a.mean(1).tolist(), (a.mean(1) - a.std(1)).tolist(), (a.mean(1) + a.std(1)).tolist()],
            'summary': f'{a.shape[1]:,} columns per time step, shown as their mean and spread', 'band': True, 'unit': unit, 'source': t['file']}


AGENT_SYSTEM = """You are the agent inside Visual Cortex Lab. People look at datasets of samples (clips, renders, sounds) with fields
and time tracks, including TRIBE v2 predictions of an average viewer's fMRI response. Use the tools to read the data; never
invent a number, and say which field and how many samples each number comes from. Write short plain sentences in plain text: no Markdown, no tables, no asterisks. No verdict
words such as supported, confirmed, refuted or ruled out. To show the person something, build it from stages and call
view_show; that is the only way you change the screen, and every stage you add is visible and removable.
The person is looking at dataset {dataset!r} with these stages: {stages}."""


class Ask(BaseModel):
    dataset: str
    stages: list[dict] = []
    message: str
    history: list[dict] = []


@app.post('/api/agent')
def agent(b: Ask):
    """One message to the agent: Claude Code in print mode with only the data tools (vcl/data/agent_tools.py).
    Returns its reply, every tool call it made with its arguments, and the view it asked to show, if any."""
    import os, subprocess, sys, tempfile
    show = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False); show.close(); os.unlink(show.name)
    log = ROOT / 'backend' / 'data' / 'agent_tools.log'   # the tool server's own errors, so a failed start is visible
    cfg = {'mcpServers': {'data': {'command': 'bash', 'args': ['-c', f'cd {ROOT / "backend"} && exec {sys.executable} -m vcl.data.agent_tools http://127.0.0.1:{PORT} {show.name} 2>>{log}'],
                                   'env': {'PYTHONPATH': str(ROOT / 'backend')}}}}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f: json.dump(cfg, f); cfg_path = f.name
    convo = ''.join(f"{'Person' if m.get('who') == 'person' else 'Agent'}: {m.get('text', '')}\n" for m in b.history[-10:])
    prompt = (f'Conversation so far:\n{convo}\n' if convo else '') + f'Person: {b.message}'
    try:
        r = subprocess.run(['claude', '-p', prompt, '--mcp-config', cfg_path, '--strict-mcp-config', '--allowedTools', 'mcp__data',
                            '--disallowedTools', 'Bash', 'Edit', 'Write', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Agent', 'Read', 'Glob', 'Grep',
                            '--append-system-prompt', AGENT_SYSTEM.format(dataset=b.dataset, stages=json.dumps(b.stages)),
                            '--output-format', 'stream-json', '--verbose'], capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        calls, reply = [], ''
        for line in r.stdout.splitlines():
            try: ev = json.loads(line)
            except json.JSONDecodeError: continue
            if ev.get('type') == 'assistant':
                for c in ev.get('message', {}).get('content', []):
                    if c.get('type') == 'tool_use': calls.append({'tool': c['name'].replace('mcp__data__', ''), 'arguments': c.get('input', {})})
            if ev.get('type') == 'result': reply = ev.get('result', '')
        if r.returncode != 0 and not reply: raise HTTPException(502, f'agent failed: {(r.stderr or r.stdout)[-300:]}')
        shown = json.load(open(show.name)) if os.path.exists(show.name) else None
        if shown: shown['stages'] = [{**s, 'by': 'agent'} for s in shown['stages']]
        return {'reply': reply.strip(), 'tool_calls': calls, 'show': shown}
    finally:
        os.unlink(cfg_path)
        if os.path.exists(show.name): os.unlink(show.name)


def _reload(source: str):
    try: loaders.load(ROOT / source, con())
    except Exception as e: runs._log('reload', f'{source}: {e}')


@app.get('/api/runs')
def runs_list():
    """Every run: its plan and steps as written, its live state (status, per-step progress) and the last lines of its log."""
    def text(f): return (ROOT / f).read_text() if f and (ROOT / f).exists() else None
    def art(f):
        p = ROOT / f
        return {'file': f, 'exists': p.exists(), 'content': json.load(open(p)) if p.exists() and p.suffix == '.json' else None}
    return [{**r, 'state': runs.state(r['name']), 'log': runs.log_tail(r['name'], 120), 'plan_text': text(r.get('plan_file')),
             'artifact_files': [art(f) for f in r.get('artifacts', [])],
             'dataset_name': json.load(open(ROOT / r['dataset_source']))['name'] if r.get('dataset_source') and (ROOT / r['dataset_source']).exists() else None} for r in runs.definitions()]


@app.post('/api/runs/{name}/start')
def runs_start(name: str):
    try: return runs.start(name, _reload)
    except KeyError: raise HTTPException(404, f'no run {name}')


@app.post('/api/runs/{name}/stop')
def runs_stop(name: str):
    return runs.stop(name)


@app.get('/media/{path:path}')
def media(path: str):
    if not con().execute('select 1 from samples where media = ? limit 1', [path]).fetchone(): raise HTTPException(404, 'not a sample media file')
    return FileResponse(ROOT / path)


if UI.exists(): app.mount('/', StaticFiles(directory=UI, html=True), name='ui')

if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--port', type=int, default=8791); p = a.parse_args()
    PORT = p.port
    uvicorn.run(app, host='127.0.0.1', port=p.port)
