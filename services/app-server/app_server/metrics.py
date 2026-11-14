"""What the dashboard shows, all of it read from /data and from Fuzzball. Nothing here is kept only in memory.

  /data/log/metrics/gpu/<workflow>_<job>_<task>.jsonl   one GPU sample per line, written by fuzzball/gpu-log.sh in
                                                         every GPU job: t, node, gpu_util_pct, power_w, temp_c,
                                                         mem_used_bytes, ...
  /data/log/metrics/planner.jsonl                        the planner's vLLM counters, sampled here every 15 s
  runs                                                   each run's steps with start and end times, from
                                                         fuzzball workflow describe (runs.py keeps the workflow IDs)
  /data/weights                                          what is on the volume, by folder
"""
from __future__ import annotations
import json, re, subprocess, threading, time, urllib.request
from datetime import datetime
from pathlib import Path
from .config import DATA, FUZZBALL, PLANNER_URL
from . import runs

M = DATA / 'log' / 'metrics'
PLANNER_FILE = M / 'planner.jsonl'
VLLM = {   # vLLM's Prometheus metric -> the dashboard's name
    'vllm:num_requests_running': 'requests_running', 'vllm:num_requests_waiting': 'requests_waiting',
    'vllm:generation_tokens_total': 'generation_tokens_total', 'vllm:prompt_tokens_total': 'prompt_tokens_total',
    'vllm:kv_cache_usage_perc': 'kv_cache_usage', 'vllm:gpu_cache_usage_perc': 'kv_cache_usage',
}


def _ts(s: str | None) -> float | None:
    return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp() if s else None


def _tail(f: Path, n: int) -> list[dict]:
    """The last n JSON lines of a file; a line cut off mid-write is skipped."""
    out = []
    for line in f.read_text(errors='replace').splitlines()[-n:]:
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass
    return out


def gpu(limit: int = 720) -> list[dict]:
    """Every GPU job's samples, newest file first: the last `limit` samples per job (3 hours at 15 s)."""
    d = M / 'gpu'
    if not d.exists(): return []
    out = []
    for f in sorted(d.glob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:24]:
        rows = _tail(f, limit)
        if not rows: continue
        last = rows[-1]
        out.append({'file': f.name, 'workflow': last.get('workflow'), 'job': last.get('job'), 'task': last.get('task'), 'node': last.get('node'),
                    'updated': f.stat().st_mtime, 'samples': [{k: r.get(k) for k in ('t', 'gpu_util_pct', 'power_w', 'temp_c', 'mem_used_bytes')} for r in rows]})
    return out


def run_steps() -> list[dict]:
    """Each run's latest workflow, with every job stage's start and end (render tasks one by one)."""
    out = []
    for r in runs.definitions():
        wf = runs._saved(r['name']).get('workflow')
        if not wf: out.append({'name': r['name'], 'title': r['title'], 'workflow': None, 'status': 'not started', 'steps': []}); continue
        p = subprocess.run([FUZZBALL, 'workflow', 'describe', wf, '-o', 'json'], capture_output=True, text=True, timeout=60)
        if p.returncode != 0: out.append({'name': r['name'], 'title': r['title'], 'workflow': wf, 'status': 'unknown', 'steps': []}); continue
        st = json.loads(p.stdout).get('status', {}).get('stages', [])
        wfs = next((s for s in st if s.get('kind') == 'STAGE_KIND_WORKFLOW'), {})
        jobs = [s for s in st if s.get('kind') == 'STAGE_KIND_JOB']
        seen: dict[str, int] = {}; steps = []
        for s in jobs:
            n = seen[s['name']] = seen.get(s['name'], -1) + 1   # a task array lists the array, then each task, under one name
            label = s['name'] if n == 0 else f"{s['name']} task {n}"
            steps.append({'label': label, 'job': s['name'], 'array': n == 0 and sum(j['name'] == s['name'] for j in jobs) > 1,
                          'status': s['status'].replace('STAGE_STATUS_', '').lower(), 'start': _ts(s.get('startTime')), 'end': _ts(s.get('endTime'))})
        out.append({'name': r['name'], 'title': r['title'], 'workflow': wf, 'status': wfs.get('status', '').replace('STAGE_STATUS_', '').lower(),
                    'start': _ts(wfs.get('startTime')), 'end': _ts(wfs.get('endTime')), 'steps': steps})
    return out


def planner(limit: int = 720) -> list[dict]:
    return _tail(PLANNER_FILE, limit) if PLANNER_FILE.exists() else []


def weights() -> list[dict]:
    """Each folder under /data/weights with its size and file count."""
    out = []
    for d in sorted(p for p in (DATA / 'weights').glob('*') if p.is_dir() and p.name != 'hf'):
        size = n = 0
        for f in d.rglob('*'):
            if f.is_file() and not f.is_symlink(): size += f.stat().st_size; n += 1
        out.append({'name': d.name, 'bytes': size, 'files': n})
    return out


def _sample_planner():
    """Reads the planner's /metrics and appends the counters the dashboard charts. A planner that is down adds nothing."""
    base = PLANNER_URL.rsplit('/v1', 1)[0]
    try:
        text = urllib.request.urlopen(base + '/metrics', timeout=5).read().decode()
    except OSError:
        return
    row: dict = {'t': time.time()}
    for line in text.splitlines():
        m = re.match(r'^([a-z_:]+)(?:\{[^}]*\})?\s+([0-9.eE+-]+)$', line)
        if m and m.group(1) in VLLM: row[VLLM[m.group(1)]] = row.get(VLLM[m.group(1)], 0.0) + float(m.group(2))
    if len(row) > 1:
        M.mkdir(parents=True, exist_ok=True)
        with open(PLANNER_FILE, 'a') as f: f.write(json.dumps(row) + '\n')


def start_sampler(every_s: float = 15.0):
    def loop():
        while True:
            _sample_planner(); time.sleep(every_s)
    threading.Thread(target=loop, daemon=True).start()
