"""Prometheus exporter for Simulaxon's jobs, and Prometheus's list of what else to scrape.

usage: python3 exporter.py [--port 19100]

  GET /metrics   the latest reading of every GPU job that logged in the last STALE_S seconds (fuzzball/gpu-log.sh writes
                 them to /data/log/metrics/gpu), and the state of every job in the team's running workflows
                 and every workflow that failed in the last FAIL_WINDOW_S seconds: the step that failed, Fuzzball's error
                 and the last lines of that step's log
                 Each node the team uses: whether its node_exporter answers, memory available, load and the jobs on it,
                 with one state per node (unreachable, memory pressure, in use, idle). Fuzzball's own node status is
                 refused to workflow tokens, so the state comes from the node's own readings.
                 Each step of the running workflows and of the study workflows of the last STUDY_WINDOW_S seconds as a
                 state (waiting, running, finished, failed, canceled), and the size of each folder in /data/weights.
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
DATA = Path(os.environ.get('SIMULAXON_DATA', '/data'))
# The team's nodes by host name, as `name=ip,...`; nodes that run the team's jobs are added as they appear.
NODES = dict(x.split('=', 1) for x in os.environ.get('SIMULAXON_NODES', 'CIQ-CHI-SPARK25=192.168.99.34,CIQ-CHI-SPARK26=192.168.99.35').split(',') if '=' in x)
NODE_NAMES = {ip: name for name, ip in NODES.items()}
NODE_EXPORTER_PORT = 9100        # every Fuzzball compute node runs node_exporter there
PRESSURE = 0.10                  # memory available below this share of the total counts as memory pressure
NODE_STATES = {'unreachable': 0, 'memory pressure': 1, 'in use': 2, 'idle': 3}
STEP_STATES = {'waiting': 0, 'running': 1, 'finished': 2, 'failed': 3, 'canceled': 4}
STUDY_NAMES = set(os.environ.get('SIMULAXON_STUDIES', 'observer').split(','))
STUDY_WINDOW_S = 6 * 3600
WEIGHTS_EVERY_S = 600
CLI_URL = 'https://ui.fb-hack.civilfritz.net/api/download/cli/linux/arm64'

GPU = [('gpu_util_pct', 'simulaxon_gpu_utilization_percent', 'Share of time a kernel ran on the GPU (nvidia-smi).'),
       ('power_w', 'simulaxon_gpu_power_watts', 'GPU power draw.'),
       ('temp_c', 'simulaxon_gpu_temperature_celsius', 'GPU temperature.'),
       ('sm_clock_mhz', 'simulaxon_gpu_sm_clock_mhz', 'GPU SM clock.'),
       ('mem_used_bytes', 'simulaxon_job_memory_bytes', "The job's cgroup memory; the GB10 shares it with the GPU.")]

_state = {'workflows': {}, 'jobs': [], 'targets': [], 'failures': [], 'steps': [], 'nodes': [], 'weights': {}, 'weights_at': 0.0,
          'updated': 0.0, 'error': ''}
_failed: dict[str, list[dict]] = {}   # workflow id -> its failed steps; a finished workflow never changes
_done_steps: dict[str, list[dict]] = {}   # finished study workflow id -> its steps; they never change
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
                    'task': str(task) if task else '', 'error': (s.get('error') or d.get('error') or '')[:200], 'log_tail': tail[-200:],
                    'ended': ts(s.get('endTime') or d.get('endTime'))})
    return out


def step_state(status: str) -> str:
    s = status.replace('STAGE_STATUS_', '').lower()
    return {'started': 'running', 'unspecified': 'waiting', 'pending': 'waiting'}.get(s, s if s in STEP_STATES else 'waiting')


def workflow_steps(w: dict) -> list[dict]:
    """Every job of a workflow, task-array tasks one by one, with its state and node."""
    d = fb_json('workflow', 'describe', w['id']) or {}
    st = [s for s in d.get('status', {}).get('stages', []) if s.get('kind') == 'STAGE_KIND_JOB']
    arrays = {s['name'] for s in st if s.get('rank', 0) >= 1}
    return [{'workflow': w['id'], 'workflow_name': w.get('name', ''), 'job': s['name'], 'task': str(s['rank']) if s['name'] in arrays else '',
             'node': NODE_NAMES.get(ip := ((s.get('details') or {}).get('Host') or '').split(':')[0], ip), 'state': step_state(s.get('status', ''))}
            for s in st if not (s['name'] in arrays and s.get('rank', 0) == 0)]


def node_readings(jobs: list[dict]) -> list[dict]:
    """Each node's node_exporter readings and the team's jobs running on it, with one state for the node."""
    ips = dict(NODES)
    for j in jobs:
        if j['node'] and j['node'] not in ips.values(): ips[j['node']] = j['node']
    out = []
    for name, ip in sorted(ips.items()):
        on = sorted(f"{j['workflow_name']}/{j['job']}{' task ' + j['task'] if j['task'] else ''}" for j in jobs if j['node'] == ip and j['status'] == 'started')
        r = {'node': name, 'ip': ip, 'jobs': on, 'reachable': False}
        try:
            text = urllib.request.urlopen(f'http://{ip}:{NODE_EXPORTER_PORT}/metrics', timeout=5).read().decode()
            v = {}
            for line in text.splitlines():
                for k in ('node_memory_MemTotal_bytes', 'node_memory_MemAvailable_bytes', 'node_load1'):
                    if line.startswith(k + ' '): v[k] = float(line.split()[-1])
            r.update(reachable=True, mem_total=v.get('node_memory_MemTotal_bytes'), mem_avail=v.get('node_memory_MemAvailable_bytes'), load1=v.get('node_load1'))
        except Exception:
            pass
        ratio = r['mem_avail'] / r['mem_total'] if r.get('mem_total') and r.get('mem_avail') is not None else None
        r['state'] = 'unreachable' if not r['reachable'] else 'memory pressure' if ratio is not None and ratio < PRESSURE else 'in use' if on else 'idle'
        out.append(r)
    return out


def weights_sizes() -> dict[str, int]:
    out = {}
    for d in sorted(p for p in (DATA / 'weights').glob('*') if p.is_dir() and p.name not in ('hf',)):
        out[d.name] = sum(f.stat().st_size for f in d.rglob('*') if f.is_file() and not f.is_symlink())
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
                         'task': str(s['rank']) if s['name'] in arrays else '', 'node': host.split(':')[0],
                         'kind': 'service' if s['kind'] == 'STAGE_KIND_SERVICE' else 'job',
                         'status': s['status'].replace('STAGE_STATUS_', '').lower()})
            if s['kind'] == 'STAGE_KIND_SERVICE' and s['name'] in SCRAPE and s['status'] == 'STAGE_STATUS_STARTED':
                targets.append({'targets': [f"{s['name']}.{w['id']}:{SCRAPE[s['name']]}"],
                                'labels': {'workflow': w['id'], 'workflow_name': wfs[w['id']], 'job_name': s['name'],
                                           'node': host.split(':')[0]}})
    steps = []
    for w in listed:   # study workflows: running ones fresh, finished ones once
        if w.get('name') not in STUDY_NAMES or time.time() - ts(w.get('createTime')) > STUDY_WINDOW_S: continue
        if 'STARTED' in str(w.get('status', '')): steps += workflow_steps(w)
        else:
            if w['id'] not in _done_steps: _done_steps[w['id']] = workflow_steps(w)
            steps += _done_steps[w['id']]
    nodes = node_readings(jobs)
    weights, weights_at = _state['weights'], _state['weights_at']
    if time.time() - weights_at > WEIGHTS_EVERY_S: weights, weights_at = weights_sizes(), time.time()
    with _lock: _state.update(workflows=wfs, jobs=jobs, targets=targets, failures=failures, steps=steps, nodes=nodes, weights=weights,
                              weights_at=weights_at, updated=time.time(), error='')


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
    if not st['updated']: return '# waiting for the first Fuzzball read, so every series carries its workflow name\n'
    nodes = {(j['workflow'], j['job'], j['task'] or '0'): j['node'] for j in st['jobs']}
    out, now = [], time.time()
    series = {m: [] for _, m, _ in GPU}; procs = []
    for f in GPU_DIR.glob('*.jsonl') if GPU_DIR.exists() else []:
        try:
            if now - f.stat().st_mtime > STALE_S: continue
            r = last_line(f)
        except OSError: continue
        if not r: continue
        wf, job, task = r.get('workflow', ''), r.get('job', ''), str(r.get('task', 0))
        # task is empty for a job that is not a task array (gpu-log.sh writes 0; array tasks count from 1)
        lab = dict(workflow=wf, workflow_name=st['workflows'].get(wf, ''), job=job, task='' if task == '0' else task,
                   node=nodes.get((wf, job, task), ''))
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
    out += ['# HELP simulaxon_node_state The node\'s state: 0 unreachable, 1 memory pressure, 2 in use, 3 idle; state names it.',
            '# TYPE simulaxon_node_state gauge'] + [f"simulaxon_node_state{labels(node=n['node'], ip=n['ip'], state=n['state'], jobs=', '.join(n['jobs']) or 'none')} {NODE_STATES[n['state']]}" for n in st['nodes']]
    for key, name, help_ in (('mem_avail', 'simulaxon_node_memory_available_bytes', 'Memory the node can still hand out (node_exporter MemAvailable). On the GB10 the GPU uses this memory.'),
                             ('mem_total', 'simulaxon_node_memory_total_bytes', 'The node\'s memory, shared by CPU and GPU on the GB10.'),
                             ('load1', 'simulaxon_node_load1', 'The node\'s one-minute load average.')):
        out += [f'# HELP {name} {help_}', f'# TYPE {name} gauge'] + [f"{name}{labels(node=n['node'], ip=n['ip'])} {n[key]}" for n in st['nodes'] if n.get(key) is not None]
    out += ['# HELP simulaxon_node_running_jobs The team\'s jobs and services running on the node.', '# TYPE simulaxon_node_running_jobs gauge'] + \
           [f"simulaxon_node_running_jobs{labels(node=n['node'], ip=n['ip'])} {len(n['jobs'])}" for n in st['nodes']]
    out += ['# HELP simulaxon_step_state A study step: 0 waiting, 1 running, 2 finished, 3 failed, 4 canceled.', '# TYPE simulaxon_step_state gauge'] + \
           [f"simulaxon_step_state{labels(**{k: s[k] for k in ('workflow', 'workflow_name', 'job', 'task', 'node', 'state')})} {STEP_STATES[s['state']]}" for s in st['steps']]
    out += ['# HELP simulaxon_weights_bytes Size of each folder in /data/weights.', '# TYPE simulaxon_weights_bytes gauge'] + \
           [f"simulaxon_weights_bytes{labels(folder=k)} {v}" for k, v in st['weights'].items()]
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
