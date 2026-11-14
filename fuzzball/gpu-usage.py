#!/usr/bin/env python3
"""GPU use and running commands of each GPU job, read from the `gpulog` lines fuzzball/gpu-log.sh prints.

usage: python3 fuzzball/gpu-usage.py [WORKFLOW_ID ...] [--watch SECONDS] [--json] [--lines N]

With no workflow IDs it reads every running workflow. Each job (and each task of a task array) gets one row: node,
readings, GPU utilisation and power now / mean / peak, energy used (power integrated over time), container memory, and the busiest commands in the
latest reading. --json prints the same as one JSON document, for scripts and agents.
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys, time
from datetime import datetime

FB = shutil.which('fuzzball') or str(__import__('pathlib').Path.home() / 'bin' / 'fuzzball')
LINE = re.compile(r'gpulog (\S+) (gpu|proc) (.*)$')
KV = re.compile(r'(\w+)=(\S*)')


def fb(*args, timeout=120):
    r = subprocess.run([FB, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout if r.returncode == 0 else ''


def fb_json(*args):
    out = fb(*args, '-o', 'json')
    return json.loads(out) if out.strip() else None


def num(s):
    try: return float(s)
    except (TypeError, ValueError): return None


def parse(log: str) -> list[dict]:
    """The readings in a job's log, oldest first: {time, gpu: {...}, procs: [...]}."""
    readings = {}
    for line in log.splitlines():
        m = LINE.search(line)
        if not m: continue
        t, kind, rest = m.groups()
        r = readings.setdefault(t, {'time': t, 'gpu': {}, 'procs': []})
        if kind == 'gpu':
            r['gpu'] = {k: num(v) for k, v in KV.findall(rest)}
        else:
            head, _, cmd = rest.partition(' cmd=')
            p = {k: num(v) for k, v in KV.findall(head)}
            p['cmd'] = cmd
            r['procs'].append(p)
    return [readings[t] for t in sorted(readings)]


def summarise(readings: list[dict]) -> dict:
    def series(key): return [v for r in readings if (v := r['gpu'].get(key)) is not None]
    def stats(xs): return {'now': xs[-1], 'mean': sum(xs) / len(xs), 'peak': max(xs)} if xs else None
    # Energy: power integrated over the readings (nvidia-smi on the GB10 has no energy counter).
    pw = [(r['time'], r['gpu']['power']) for r in readings if r['gpu'].get('power') is not None]
    t = [datetime.fromisoformat(x.replace('Z', '+00:00')).timestamp() for x, _ in pw]
    energy_wh = sum((t[i + 1] - t[i]) * (pw[i][1] + pw[i + 1][1]) / 2 for i in range(len(pw) - 1)) / 3600 if len(pw) > 1 else None
    return {'readings': len(readings), 'first': readings[0]['time'] if readings else None,
            'last': readings[-1]['time'] if readings else None,
            'util_pct': stats(series('util')), 'power_w': stats(series('power')), 'temp_c': stats(series('temp')),
            'energy_wh': energy_wh,
            'mem_gib': stats([m / 2**30 for m in series('mem')]),
            'procs': readings[-1]['procs'] if readings else []}


def jobs(wf_id: str) -> list[dict]:
    """The workflow's jobs and services, one entry per task of a task array (rank >= 1)."""
    d = fb_json('workflow', 'describe', wf_id) or {}
    stages = [s for s in d.get('status', {}).get('stages', []) if s.get('kind') in ('STAGE_KIND_JOB', 'STAGE_KIND_SERVICE')]
    arrays = {s['name'] for s in stages if s.get('rank', 0) >= 1}
    out = []
    for s in stages:
        if s['name'] in arrays and s.get('rank', 0) == 0: continue   # the array itself, not a task
        if not s.get('details', {}).get('Host'): continue           # never started
        out.append({'workflow': wf_id, 'workflow_name': d.get('name', ''), 'job': s['name'],
                    'task': s['rank'] if s['name'] in arrays else None, 'status': s['status'].replace('STAGE_STATUS_', '').lower(),
                    'node': s['details']['Host'].split(':')[0]})
    return out


def collect(wf_ids: list[str], lines: int) -> list[dict]:
    rows = []
    for wf in wf_ids:
        for j in jobs(wf):
            args = ['workflow', 'log', wf, j['job'], '-n', str(lines)] + (['--task-id', str(j['task'])] if j['task'] else [])
            readings = parse(fb(*args))
            if readings: rows.append({**j, **summarise(readings)})
    return rows


def running() -> list[str]:
    return [w['id'] for w in fb_json('workflow', 'list') or [] if 'STARTED' in str(w.get('status', '')).upper()]


def fmt(st, unit, digits=0):
    return '-' if not st else f"{st['now']:.{digits}f}/{st['mean']:.{digits}f}/{st['peak']:.{digits}f}{unit}"


def render(rows: list[dict]) -> str:
    if not rows: return 'No gpulog readings. GPU jobs log once fuzzball/gpu-log.sh is started in their script.'
    width = shutil.get_terminal_size((120, 20)).columns
    out = [f"{'workflow / job':<34} {'node':<15} {'n':>4}  {'util % now/mean/peak':<20} {'power W now/mean/peak':<22} {'Wh':>6}  {'mem GiB':>7}"]
    for r in rows:
        name = f"{r['workflow_name'][:18]} / {r['job']}" + (f"[{r['task']}]" if r['task'] else '')
        wh = f"{r['energy_wh']:.1f}" if r['energy_wh'] is not None else '-'
        mem = f"{r['mem_gib']['now']:.1f}" if r['mem_gib'] else '-'
        out.append(f"{name[:34]:<34} {r['node']:<15} {r['readings']:>4}  {fmt(r['util_pct'], ''):<20} {fmt(r['power_w'], '', 1):<22} {wh:>6}  {mem:>7}")
        for p in r['procs'][:3]:
            cpu = '-' if p.get('cpu') is None else f"{p['cpu']:.0f}%"
            out.append(f"    {cpu:>5} cpu  {(p.get('rss') or 0) / 2**20:5.1f} GiB  {p['cmd']}"[:width])
    return '\n'.join(out)


if __name__ == '__main__':
    a = argparse.ArgumentParser()
    a.add_argument('workflows', nargs='*', help='workflow IDs; default: every running workflow')
    a.add_argument('--watch', type=float, help='redraw every SECONDS')
    a.add_argument('--json', action='store_true', help='print JSON instead of the table')
    a.add_argument('--lines', type=int, default=3000, help='log lines read per job (default 3000)')
    p = a.parse_args()
    ids = lambda: p.workflows or running()
    if p.json: print(json.dumps(collect(ids(), p.lines), indent=1)); sys.exit()
    if not p.watch: print(render(collect(ids(), p.lines))); sys.exit()
    try:
        while True:
            frame = render(collect(ids(), p.lines))
            print('\033[2J\033[H' + frame + f'\n\nRedraws every {p.watch:g} s. Ctrl-C to quit.', flush=True); time.sleep(p.watch)
    except KeyboardInterrupt: print()
