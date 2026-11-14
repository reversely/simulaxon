"""Prometheus exporter for Simulaxon's jobs, and Prometheus's list of what else to scrape.

usage: python3 exporter.py [--port 19100]

  GET /metrics   the latest reading of every GPU job that logged in the last STALE_S seconds (fuzzball/gpu-log.sh writes
                 them to /data/log/metrics/gpu), and the state of every job in the team's running workflows
                 and every workflow that failed in the last FAIL_WINDOW_S seconds: the step that failed, Fuzzball's error
                 and the last lines of that step's log
  GET /targets   Prometheus HTTP service discovery: every running service that serves its own /metrics (the planner's
                 vLLM), addressed as <service>.<workflow id>, which resolves from any workflow in the group

Fuzzball state comes from the Fuzzball CLI, which inside a workflow reads the injected FB_TOKEN and FB_API_HOST. It is
refreshed every REFRESH_S seconds in the background, so a scrape never waits on the CLI. Standard library only.
"""
from __future__ import annotations
import argparse, json, os, shutil, subprocess, threading, time, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GPU_DIR = Path(os.environ.get('SIMULAXON_DATA', '/data')) / 'log' / 'metrics' / 'gpu'
STALE_S = 60          # a GPU file not written for this long belongs to a job that has ended
REFRESH_S = 30
FAIL_WINDOW_S = 24 * 3600
SCRAPE = {'planner': 8000}   # service name -> port of its own Prometheus /metrics
CLI_URL = 'https://ui.fb-hack.civilfritz.net/api/download/cli/linux/arm64'

GPU = [('gpu_util_pct', 'simulaxon_gpu_utilization_percent', 'Share of time a kernel ran on the GPU (nvidia-smi).'),
       ('power_w', 'simulaxon_gpu_power_watts', 'GPU power draw.'),
       ('temp_c', 'simulaxon_gpu_temperature_celsius', 'GPU temperature.'),
       ('sm_clock_mhz', 'simulaxon_gpu_sm_clock_mhz', 'GPU SM clock.'),
       ('mem_used_bytes', 'simulaxon_job_memory_bytes', "The job's cgroup memory; the GB10 shares it with the GPU.")]

_state = {'workflows': {}, 'jobs': [], 'targets': [], 'failures': [], 'updated': 0.0, 'error': ''}
_failed: dict[str, list[dict]] = {}   # workflow id -> its failed steps; a finished workflow never changes
_lock = threading.Lock()


def fuzzball() -> str:
    """The CLI: on PATH, the copy the app server keeps on /data, or one downloaded to /tmp with the workflow's token."""
    for c in (os.environ.get('FUZZBALL'), shutil.which('fuzzball'), '/data/bin/fuzzball', '/tmp/fuzzball'):
        if c and os.access(c, os.X_OK): return c
    req = urllib.request.Request(CLI_URL, headers={'Cookie': 'fwi.access-token=' + os.environ['FB_TOKEN']})
    Path('/tmp/fuzzball.part').write_bytes(urllib.request.urlopen(req, timeout=600).read())
    os.chmod('/tmp/fuzzball.part', 0o755); os.replace('/tmp/fuzzball.part', '/tmp/fuzzball')
    return '/tmp/fuzzball'


def fb_json(*args):
    r = subprocess.run([fuzzball(), *args, '-o', 'json'], capture_output=True, text=True, timeout=60)
    if r.returncode != 0: raise RuntimeError(f"fuzzball {' '.join(args)}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def ts(s: str | None) -> float:
    from datetime import datetime
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() if s else 0.0


def failed_steps(w: dict) -> list[dict]:
    """A failed workflow's failed steps (or the workflow itself when no step failed), each with Fuzzball's error and
    the last lines of its log, where the real cause usually is (a segfault, a missing file)."""
    d = fb_json('workflow', 'describe', w['id']) or {}
    st = d.get('status', {}).get('stages', [])
    bad = [s for s in st if s.get('status') == 'STAGE_STATUS_FAILED' and s.get('kind') in ('STAGE_KIND_JOB', 'STAGE_KIND_SERVICE')]
    # Steps cancelled because another step failed only repeat that failure; keep the step that failed first.
    bad = [s for s in bad if not (s.get('error') or '').startswith('cancelled due to workflow error')] or bad
    bad = bad or [s for s in st if s.get('status') == 'STAGE_STATUS_FAILED'][:1]
    out = []
    for s in bad:
        task = s.get('rank', 0) if any(x['name'] == s['name'] and x.get('rank', 0) >= 1 for x in st) else 0
        tail = ''
        if s.get('kind') in ('STAGE_KIND_JOB', 'STAGE_KIND_SERVICE'):
            r = subprocess.run([fuzzball(), 'workflow', 'log', w['id'], s['name'], '-n', '3'] + (['--task-id', str(task)] if task else []),
                               capture_output=True, text=True, timeout=60)
            tail = ' | '.join(l.strip() for l in r.stdout.splitlines() if l.strip() and not l.startswith('gpulog'))
        out.append({'workflow': w['id'], 'workflow_name': w.get('name', ''), 'job': s['name'] if s.get('kind') != 'STAGE_KIND_WORKFLOW' else '',
                    'task': str(task), 'error': (s.get('error') or d.get('error') or '')[:200], 'log_tail': tail[-200:],
                    'ended': ts(s.get('endTime') or d.get('endTime'))})
    return out


def refresh():
    """Running workflows, their jobs and services with node and status, the services Prometheus should scrape, and the
    workflows that failed in the last FAIL_WINDOW_S seconds."""
    wfs, jobs, targets, failures = {}, [], [], []
    listed = fb_json('workflow', 'list') or []
    for w in listed:
        if 'FAILED' in str(w.get('status', '')) and time.time() - ts(w.get('createTime')) < FAIL_WINDOW_S:
            if w['id'] not in _failed: _failed[w['id']] = failed_steps(w)
            failures += _failed[w['id']]
    for w in listed:
        if 'STARTED' not in str(w.get('status', '')): continue
        wfs[w['id']] = w.get('name', '')
        d = fb_json('workflow', 'describe', w['id']) or {}
        stages = [s for s in d.get('status', {}).get('stages', []) if s.get('kind') in ('STAGE_KIND_JOB', 'STAGE_KIND_SERVICE')]
        arrays = {s['name'] for s in stages if s.get('rank', 0) >= 1}
        for s in stages:
            if s['name'] in arrays and s.get('rank', 0) == 0: continue
            host = (s.get('details') or {}).get('Host', '')
            jobs.append({'workflow': w['id'], 'workflow_name': wfs[w['id']], 'job': s['name'],
                         'task': str(s['rank']) if s['name'] in arrays else '0', 'node': host.split(':')[0],
                         'kind': 'service' if s['kind'] == 'STAGE_KIND_SERVICE' else 'job',
                         'status': s['status'].replace('STAGE_STATUS_', '').lower()})
            if s['kind'] == 'STAGE_KIND_SERVICE' and s['name'] in SCRAPE and s['status'] == 'STAGE_STATUS_STARTED':
                targets.append({'targets': [f"{s['name']}.{w['id']}:{SCRAPE[s['name']]}"],
                                'labels': {'workflow': w['id'], 'workflow_name': wfs[w['id']], 'job_name': s['name'],
                                           'node': host.split(':')[0]}})
    with _lock: _state.update(workflows=wfs, jobs=jobs, targets=targets, failures=failures, updated=time.time(), error='')


def refresher():
    while True:
        try: refresh()
        except Exception as e:   # keep serving the last good state; the error shows as a metric
            with _lock: _state['error'] = str(e)[:200]
        time.sleep(REFRESH_S)


def esc(v) -> str:
    return str(v).replace('\\', '\\\\').replace('"', '\\"').replace('\n', ' ')


def labels(**kv) -> str:
    return '{' + ','.join(f'{k}="{esc(v)}"' for k, v in kv.items()) + '}'


def last_line(f: Path) -> dict | None:
    """The file's last complete JSON line, read from its end so long files cost the same as short ones."""
    with open(f, 'rb') as fh:
        fh.seek(0, 2); fh.seek(max(0, fh.tell() - 65536))
        for line in reversed(fh.read().splitlines()):
            try: return json.loads(line)
            except ValueError: continue
    return None


def metrics() -> str:
    with _lock: st = {k: v for k, v in _state.items()}
    nodes = {(j['workflow'], j['job'], j['task']): j['node'] for j in st['jobs']}
    out, now = [], time.time()
    series = {m: [] for _, m, _ in GPU}; procs = []
    for f in GPU_DIR.glob('*.jsonl') if GPU_DIR.exists() else []:
        try:
            if now - f.stat().st_mtime > STALE_S: continue
            r = last_line(f)
        except OSError: continue
        if not r: continue
        wf, job, task = r.get('workflow', ''), r.get('job', ''), str(r.get('task', 0))
        lab = dict(workflow=wf, workflow_name=st['workflows'].get(wf, ''), job=job, task=task, node=nodes.get((wf, job, task), ''))
        for key, name, _ in GPU:
            if isinstance(r.get(key), (int, float)): series[name].append((lab, r[key]))
        for rank, p in enumerate(r.get('top') or [], 1):
            procs.append((dict(lab, rank=rank, pid=p.get('pid', ''), cmd=str(p.get('cmd', ''))[:160]), p.get('cpu_pct', 0) or 0))
    for key, name, help_ in GPU:
        out += [f'# HELP {name} {help_}', f'# TYPE {name} gauge'] + [f'{name}{labels(**l)} {v}' for l, v in series[name]]
    out += ['# HELP simulaxon_job_process_cpu_percent CPU share of the busiest processes in each GPU job; cmd is the command line.',
            '# TYPE simulaxon_job_process_cpu_percent gauge'] + [f'simulaxon_job_process_cpu_percent{labels(**l)} {v}' for l, v in procs]
    out += ['# HELP simulaxon_job_info A job or service in a running workflow; status is its stage status.',
            '# TYPE simulaxon_job_info gauge'] + [f"simulaxon_job_info{labels(**{k: j[k] for k in ('workflow', 'workflow_name', 'job', 'task', 'node', 'kind', 'status')})} 1" for j in st['jobs']]
    out += ['# HELP simulaxon_workflow_failure_timestamp_seconds When a step of a recently failed workflow failed, with the error and its log\'s last lines.',
            '# TYPE simulaxon_workflow_failure_timestamp_seconds gauge'] + [f"simulaxon_workflow_failure_timestamp_seconds{labels(**{k: f[k] for k in ('workflow', 'workflow_name', 'job', 'task', 'error', 'log_tail')})} {f['ended']:.0f}" for f in st['failures']]
    out += ['# HELP simulaxon_exporter_fuzzball_age_seconds Seconds since the Fuzzball state was last read.',
            '# TYPE simulaxon_exporter_fuzzball_age_seconds gauge', f"simulaxon_exporter_fuzzball_age_seconds {now - st['updated'] if st['updated'] else -1:.0f}",
            '# HELP simulaxon_exporter_fuzzball_error 1 when the last Fuzzball read failed.',
            '# TYPE simulaxon_exporter_fuzzball_error gauge', f"simulaxon_exporter_fuzzball_error{labels(error=st['error'])} {1 if st['error'] else 0}"]
    return '\n'.join(out) + '\n'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/metrics'): body, ctype = metrics(), 'text/plain; version=0.0.4'
        elif self.path.startswith('/targets'):
            with _lock: body = json.dumps(_state['targets'])
            ctype = 'application/json'
        elif self.path.startswith('/health'): body, ctype = 'ok\n', 'text/plain'
        else: self.send_error(404); return
        data = body.encode(); self.send_response(200)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(data))); self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a): pass


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--port', type=int, default=19100); p = a.parse_args()
    threading.Thread(target=refresher, daemon=True).start()
    ThreadingHTTPServer(('0.0.0.0', p.port), Handler).serve_forever()
