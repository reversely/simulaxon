#!/usr/bin/env python3
"""Progress of the weight downloads (fuzzball/weights/*.fz), as a chart in the terminal.

usage: python3 fuzzball/pull-status.py [--watch SECONDS]

Each download runs as a workflow named weights-<n>... (weights-1, weights-w2-vjepa2, ...); the newest one per number
is shown. The Fuzzball CLI reports a download's stage state and times, not bytes, so a finished download shows full and
a running one shows an estimate from the speed of the finished ones, marked "est".
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys, time
from datetime import datetime, timezone

PLAN = [(1, 'TRIBE v2', 0.68), (2, 'V-JEPA 2', 20.6), (3, 'Cosmos3-Nano-Sim-Transfer', 31.9),
        (4, 'Wan2.2 VAE + Cosmos tokenizer', 2.8), (5, 'Nemotron 3 Super NVFP4', 80.4)]   # number, model, GB
FB = shutil.which('fuzzball') or str(__import__('pathlib').Path.home() / 'bin' / 'fuzzball')
NAME = re.compile(r'^weights-w?(\d)\b')


def fb_json(*args):
    r = subprocess.run([FB, *args, '-o', 'json'], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None


def download(wf_id):
    """State, start and end of the workflow's download stages, plus its error."""
    d = fb_json('workflow', 'describe', wf_id) or {}
    st = d.get('status', {}).get('stages', [])
    files = [s for s in st if s.get('kind') == 'STAGE_KIND_FILE']
    wf = next((s for s in st if s.get('kind') == 'STAGE_KIND_WORKFLOW'), {})
    if not files: return {'state': 'waiting', 'start': None, 'end': None, 'error': wf.get('error', '')}
    states = {s['status'] for s in files}
    start = min((ts(s.get('startTime')) for s in files if s.get('startTime')), default=None)
    ends = [ts(s.get('endTime')) for s in files]
    # A download is judged by its file stages: the size report that runs after them can fail on its own.
    if states == {'STAGE_STATUS_FINISHED'}: state = 'done'
    elif 'STAGE_STATUS_FAILED' in states: state = 'failed'
    elif 'STAGE_STATUS_CANCELED' in states or wf.get('status') == 'STAGE_STATUS_FAILED': state = 'cancelled'
    elif start: state = 'downloading'
    else: state = 'queued'
    return {'state': state, 'start': start, 'end': max(ends) if state == 'done' and all(ends) else None,
            'error': next((s['error'] for s in files if s.get('error')), wf.get('error', ''))}


def bar(frac, width, char='█'):
    n = max(0, min(width, round(frac * width)))
    return char * n + '░' * (width - n)


def fmt_dur(sec):
    sec = int(sec); return f'{sec // 3600}h{sec % 3600 // 60:02d}m' if sec >= 3600 else f'{sec // 60}m{sec % 60:02d}s'


def render():
    wfs = fb_json('workflow', 'list') or []
    latest = {}
    for w in sorted(wfs, key=lambda w: w.get('createTime', '')):
        m = NAME.match(w.get('name', ''))
        if m: latest[int(m.group(1))] = w
    now = datetime.now(timezone.utc)
    rows = {n: download(latest[n]['id']) if n in latest else None for n, _, _ in PLAN}
    speeds = [gb / (r['end'] - r['start']).total_seconds() for (n, _, gb) in PLAN for r in [rows[n]]
              if r and r['state'] == 'done' and r['start'] and r['end'] and r['end'] > r['start']]
    rate = sum(speeds) / len(speeds) if speeds else None   # GB per second
    width = max(10, min(40, shutil.get_terminal_size((100, 20)).columns - 70))
    out = [f"Weight downloads into /data/weights      {now.astimezone():%H:%M:%S}" + (f"      measured speed {rate * 1000:.0f} MB/s" if rate else ''), '']
    done_gb = 0.0; total_gb = sum(gb for _, _, gb in PLAN)
    for n, label, gb in PLAN:
        r = rows[n]
        if r is None: frac, note, state = 0, '', 'not started'
        else:
            state = r['state']
            if state == 'done':
                frac = 1; note = fmt_dur((r['end'] - r['start']).total_seconds()) if r['start'] and r['end'] else ''
            elif state == 'downloading':
                el = (now - r['start']).total_seconds()
                frac = min(0.99, el * rate / gb) if rate else 0
                note = f"{fmt_dur(el)} elapsed" + (f", est {frac:.0%}, ~{fmt_dur(max(0, gb / rate - el))} left" if rate else '')
            else:
                frac, note = 0, (r['error'][:60] if r['error'] else '')
        done_gb += gb * frac
        out.append(f"{n} {label:<30} {gb:>5.1f} GB  {bar(frac, width, '▒' if state == 'downloading' else '█')}  {state:<11} {note}")
    out += ['', f"  {'All':<30} {total_gb:>5.1f} GB  {bar(done_gb / total_gb, width)}  {done_gb / total_gb:.0%}" + ('' if rate else '  (no finished download yet to measure speed)')]
    return '\n'.join(out)


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--watch', type=float, help='redraw every SECONDS'); p = a.parse_args()
    if not p.watch: print(render()); sys.exit()
    try:
        while True:
            frame = render(); print('\033[2J\033[H' + frame + f'\n\nRedraws every {p.watch:g} s. Ctrl-C to quit.', flush=True); time.sleep(p.watch)
    except KeyboardInterrupt: print()
