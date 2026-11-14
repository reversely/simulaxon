"""Runs: a plan plus steps, executed by the server so the app shows every step live. Generic: a run is a JSON file in
backend/runs/, nothing here knows what it is about.

A step is {id, title, command} or {id, title, command, items}. `command` is a list run from the repository root; in an
item step it runs once per item of the JSON list in `items` (a file path, read when the step starts), with {item} and
{id} filled in, each item in its own process. A step can name `reload`: a source description reloaded into the store
after the step and after every `reload_every` items, so new samples appear while the run goes on. A step that exits
non-zero stops the run there, with its output kept.
"""
from __future__ import annotations
import json, subprocess, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]; RUNS = ROOT / 'backend' / 'runs'; STATE = ROOT / 'backend' / 'data' / 'runs'
_lock = threading.Lock(); _threads: dict[str, threading.Thread] = {}; _stop: dict[str, bool] = {}; _procs: dict[str, set] = {}


def definitions() -> list[dict]:
    return [json.load(open(f)) | {'file': str(f.relative_to(ROOT))} for f in sorted(RUNS.glob('*.json'))]


def state(name: str) -> dict:
    f = STATE / f'{name}.json'
    return json.load(open(f)) if f.exists() else {'status': 'not started', 'steps': {}}


def _save(name: str, st: dict):
    STATE.mkdir(parents=True, exist_ok=True); tmp = STATE / f'{name}.json.tmp'; json.dump(st, open(tmp, 'w'), indent=1); tmp.replace(STATE / f'{name}.json')


def _log(name: str, line: str):
    with open(STATE / f'{name}.log', 'a') as f: f.write(time.strftime('%H:%M:%S ') + line.rstrip() + '\n')


def log_tail(name: str, n: int = 60) -> list[str]:
    f = STATE / f'{name}.log'
    return open(f).read().splitlines()[-n:] if f.exists() else []


def _run(name: str, run: dict, reload):
    st = state(name); st.update(status='running', started=st.get('started') or time.strftime('%Y-%m-%d %H:%M:%S')); _save(name, st)
    for step in run['steps']:
        s = st['steps'].setdefault(step['id'], {'status': 'waiting'})
        if s['status'] == 'done': continue
        s.update(status='running', started=time.strftime('%H:%M:%S')); _save(name, st); _log(name, f"step {step['id']}: {step['title']}")
        ok = True
        if 'items' in step:
            items = json.load(open(ROOT / step['items'])); s.update(total=len(items))
            done_items = set(s.get('done_items', [])); s['done'] = len(done_items); s['failed'] = 0; s['failed_items'] = []; _save(name, st)
            todo = [(k, it) for k, it in enumerate(items) if str(k) not in done_items]   # failed items are tried again on resume
            stagger, timeout, retries = step.get('stagger_s', 0), step.get('timeout_s'), step.get('retries', 0)
            started = {'n': 0}

            def one(k, it):
                if started['n'] < step.get('workers', 1):   # stagger the first launches: simultaneous Isaac starts hung once
                    with _lock: wait = started['n'] * stagger; started['n'] += 1
                    time.sleep(wait)
                tag = '/'.join(str(it.get(x)) for x in step.get('item_label', ['id']))
                for attempt in range(retries + 1):
                    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f: json.dump([it], f); item_file = f.name
                    cmd = [c.format(item=item_file, id=it.get('id', k)) for c in step['command']]; t0 = time.time()
                    if _stop.get(name): return k, -2, 0.0, tag, 'not started: the run was stopped', attempt
                    try:
                        pr = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True); _procs.setdefault(name, set()).add(pr)
                        so, se = pr.communicate(timeout=timeout); _procs[name].discard(pr)
                        r = subprocess.CompletedProcess(cmd, pr.returncode, so, se); rc = r.returncode
                        res = [l for l in r.stdout.splitlines() if l.startswith(tuple(str(it.get(x)) for x in step.get('item_label', ['id'])[:1]))]   # the item's own result line
                        msg = ' | '.join((res[-1:] or [l for l in r.stdout.splitlines() if l.strip()][-1:]) if rc == 0 else (r.stderr.strip().splitlines()[-3:] or ['no output']))
                    except subprocess.TimeoutExpired:
                        pr.kill(); pr.communicate(); _procs[name].discard(pr); rc, msg = -1, f'timed out after {timeout} s'
                    Path(item_file).unlink(missing_ok=True)
                    if rc == 0 or attempt == retries: return k, rc, time.time() - t0, tag, msg, attempt
                    _log(name, f'  {tag}: attempt {attempt + 1} failed ({msg}); trying again')

            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(step.get('workers', 1)) as ex:
                for fut in as_completed([ex.submit(one, k, it) for k, it in todo]):   # counted as they finish
                    k, rc, secs, tag, msg, attempt = fut.result()
                    with _lock:
                        if rc == 0: s['done'] += 1; s.setdefault('done_items', []).append(str(k))
                        else: s['failed'] += 1; s['failed_items'].append(tag)
                        s['last'] = f'{tag}, {secs:.0f} s'; _save(name, st)
                        _log(name, f'  {tag}: exit {rc}, {secs:.0f} s{", after a retry" if attempt else ""}, {msg}')
                    if step.get('reload') and rc == 0 and s['done'] % step.get('reload_every', 10) == 0: reload(step['reload'])
            ok = s['failed'] <= step.get('max_failed', 0) and not _stop.get(name)
        else:
            # stream the step's output into the log line by line, so a long step shows its progress as it goes
            pr = subprocess.Popen(step['command'], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1); _procs.setdefault(name, set()).add(pr)
            tail = []
            for line in pr.stdout:
                line = line.rstrip()
                if not line or 'warn' in line.lower(): continue   # sklearn FutureWarnings and their 'warnings.warn(' lines
                _log(name, '  ' + line); tail = (tail + [line])[-25:]
                s['output'] = tail; s['last'] = line[:160]; _save(name, st)
            pr.wait(); _procs[name].discard(pr)
            ok = pr.returncode == 0 and not _stop.get(name); s['output'] = tail
        if step.get('reload'): reload(step['reload'])
        s.update(status='done' if ok else 'failed', finished=time.strftime('%H:%M:%S')); _save(name, st)
        if not ok:
            st['status'] = f"stopped at {step['id']}" + (' (stopped from the app)' if _stop.get(name) else ''); _save(name, st); _log(name, f"stopped: step {step['id']} failed"); return
    st['status'] = 'done'; st['finished'] = time.strftime('%Y-%m-%d %H:%M:%S'); _save(name, st); _log(name, 'run done')


def stop(name: str) -> dict:
    """Stops a run: no new items start, and running ones are terminated. Finished items stay done; Resume continues."""
    _stop[name] = True
    for pr in list(_procs.get(name, ())): pr.terminate()
    _log(name, 'stop requested'); return {'stopping': True}


def start(name: str, reload) -> dict:
    _stop[name] = False
    run = next((r for r in definitions() if r['name'] == name), None)
    if not run: raise KeyError(name)
    with _lock:
        if name in _threads and _threads[name].is_alive(): return {'started': False, 'reason': 'already running'}
        t = threading.Thread(target=_run, args=(name, run, reload), daemon=True); _threads[name] = t; t.start()
    return {'started': True}
