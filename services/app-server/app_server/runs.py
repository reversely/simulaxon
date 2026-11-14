"""Runs: a plan plus steps, each run submitted to Fuzzball as one workflow, so the app shows every step live. Generic: a
run is a JSON file in services/app-server/runs/, nothing here knows what it is about.

A run definition: {name, title, question, fuzzfile, steps, dataset_source, artifacts, plan_file}. `fuzzfile` is a path
in the repository. Each step is {id, title, command}, where id is a job name in the Fuzzfile and command is what that
job runs, shown in the app. `dataset_source` is a file in sources/, reloaded when the run finishes; `artifacts` are
paths under the data root.

Inside a workflow the Fuzzball CLI reads the injected FB_TOKEN and FB_API_HOST, so every run the app server starts is
recorded as a child of the app server's workflow (fuzzball workflow list --parent <id>).
"""
from __future__ import annotations
import json, subprocess, threading, time
from .config import DATA, FUZZBALL, ROOT, RUNS

STATE = DATA / 'log' / 'runs'
_lock = threading.Lock(); _watch: dict[str, threading.Thread] = {}
DONE = {'STAGE_STATUS_FINISHED': 'done', 'STAGE_STATUS_FAILED': 'failed', 'STAGE_STATUS_CANCELED': 'stopped',
        'STAGE_STATUS_RUNNING': 'running', 'STAGE_STATUS_STARTED': 'running'}


def definitions() -> list[dict]:
    return [json.load(open(f)) | {'file': str(f.relative_to(ROOT))} for f in sorted(RUNS.glob('*.json'))]


def _fb(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run([FUZZBALL, *args], capture_output=True, text=True, timeout=timeout)


def _saved(name: str) -> dict:
    f = STATE / f'{name}.json'
    return json.load(open(f)) if f.exists() else {}


def _save(name: str, st: dict):
    STATE.mkdir(parents=True, exist_ok=True); tmp = STATE / f'{name}.json.tmp'; json.dump(st, open(tmp, 'w'), indent=1); tmp.replace(STATE / f'{name}.json')


def _log(name: str, line: str):
    STATE.mkdir(parents=True, exist_ok=True)
    with open(STATE / f'{name}.log', 'a') as f: f.write(time.strftime('%H:%M:%S ') + line.rstrip() + '\n')


def state(name: str) -> dict:
    """The run's live state, read from its workflow: overall status and one entry per job stage."""
    st = _saved(name)
    if not st.get('workflow'): return {'status': 'not started', 'steps': {}}
    r = _fb('workflow', 'describe', st['workflow'], '-o', 'json')
    if r.returncode != 0: return {**st, 'status': st.get('status', 'unknown'), 'steps': st.get('steps', {})}
    stages = json.loads(r.stdout).get('status', {}).get('stages', [])
    steps = {s['name']: {'status': DONE.get(s['status'], 'waiting'), **({'last': s['error'][:160]} if s.get('error') else {})}
             for s in stages if s.get('kind') == 'STAGE_KIND_JOB'}
    wf = next((s for s in stages if s.get('kind') == 'STAGE_KIND_WORKFLOW'), {})
    status = DONE.get(wf.get('status'), 'running')
    if status == 'failed': status = f"stopped at {next((k for k, v in steps.items() if v['status'] == 'failed'), 'a step')}"
    st.update(status=status, steps=steps)
    if status in ('done', 'stopped') or status.startswith('stopped at'): st.setdefault('finished', time.strftime('%Y-%m-%d %H:%M:%S'))
    _save(name, st)
    return st


def log_tail(name: str, n: int = 60) -> list[str]:
    """The app's own log lines for the run, then the last workflow events."""
    f = STATE / f'{name}.log'; own = open(f).read().splitlines() if f.exists() else []
    wf = _saved(name).get('workflow')
    ev = _fb('workflow', 'events', wf).stdout.splitlines() if wf else []
    return (own + ev)[-n:]


def _watch_until_done(name: str, run: dict, reload):
    while True:
        time.sleep(30)
        s = state(name)['status']
        if s != 'running': break
    _log(name, f'workflow {s}')
    if s == 'done' and run.get('dataset_source'): reload(run['dataset_source'])


def start(name: str, reload) -> dict:
    """Submits the run's Fuzzfile as a new workflow. A run already running is left alone."""
    run = next((r for r in definitions() if r['name'] == name), None)
    if not run: raise KeyError(name)
    with _lock:
        if state(name)['status'] == 'running': return {'started': False, 'reason': 'already running'}
        r = _fb('workflow', 'start', '-n', name, str(ROOT / run['fuzzfile']))
        wf = r.stdout.strip().splitlines()[-1] if r.returncode == 0 and r.stdout.strip() else ''
        if not wf: _log(name, f'start failed: {(r.stderr or r.stdout).strip()[-300:]}'); return {'started': False, 'reason': (r.stderr or r.stdout).strip()[-300:]}
        _save(name, {'workflow': wf, 'status': 'running', 'started': time.strftime('%Y-%m-%d %H:%M:%S'), 'steps': {}})
        _log(name, f'submitted as workflow {wf}')
        t = threading.Thread(target=_watch_until_done, args=(name, run, reload), daemon=True); _watch[name] = t; t.start()
    return {'started': True, 'workflow': wf}


def stop(name: str) -> dict:
    """Stops the run's workflow."""
    wf = _saved(name).get('workflow')
    if not wf: return {'stopping': False}
    r = _fb('workflow', 'stop', wf); _log(name, f'stop requested: {(r.stdout or r.stderr).strip()[-200:]}')
    return {'stopping': r.returncode == 0}
