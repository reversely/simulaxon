"""Job queue and warm workers (implementation spec §1, §3, §6).

- Connectors declare a schema and the Python environment that runs them.
- A warm worker is one long-running process per connector, in its own environment, that keeps its
  model or renderer loaded and answers one JSON line per job. Isaac's shader compile and TRIBE's
  model load then happen once.
- The queue has a fast lane (single previews, served first), a batch lane (runs and demo steps), and an ahead lane
  (options and slider steps rendered on a guess, served only when nothing else waits). On a shared Spark only
  one GPU job runs at a time.
- Results are cached by the hash of connector, revision, inputs and settings.
- One machine, shared memory: each connector declares the memory its warm worker holds. Before a worker
  starts, the queue unloads idle warm workers, least recently used first, until the new one fits beside
  everything else on the machine (Ollama included) with some headroom. If it still does not fit, the job
  waits, then fails with the numbers. Nothing outside the queue is ever stopped.
- Remote batch lane: a connector may also have a remote runner (Cosmos on Modal, vcl/remote.py). Batch-lane jobs
  for it go there in chunks, so one remote container loads the model once per chunk, and they take no local GPU
  time or memory. Fast-lane jobs always run here, so editing and previews stay local. Each remote runner has a
  spending limit; once the next chunk would pass it, jobs run locally instead and the event says so.
"""
from __future__ import annotations
import hashlib, json, subprocess, threading, time, uuid, queue
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Connector:
    connector_id: str
    kind: str
    python: str            # interpreter of the connector's own environment
    worker: str            # worker script path
    revision: str
    uses_gpu: bool = True
    env: dict = field(default_factory=dict)
    memory_gb: float = 0.0  # what the warm worker holds; 0 means small enough to ignore
    args: list = field(default_factory=list)   # extra arguments to the worker script


def memory_available_gb() -> float:
    """MemAvailable from /proc/meminfo. On the GB10 the CPU and GPU share this memory."""
    for line in open('/proc/meminfo'):
        if line.startswith('MemAvailable:'): return int(line.split()[1]) / 1024 / 1024
    raise RuntimeError('MemAvailable not found in /proc/meminfo')


def _protocol(line: str):
    """Workers like Isaac Sim print their own logs to stdout. Only JSON objects are protocol messages."""
    line = line.strip()
    if not (line.startswith('{') and line.endswith('}')): return None
    try: return json.loads(line)
    except ValueError: return None


class WarmWorker:
    """One subprocess speaking JSON lines: {"job_id", "inputs", "settings"} -> {"job_id", "outputs"} or {"job_id", "error"}."""
    def __init__(self, c: Connector):
        import os
        self.c = c
        self.p = subprocess.Popen([c.python, c.worker, *c.args], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1,
                                  env={**os.environ, **c.env})
        while True:
            line = self.p.stdout.readline()
            if not line: raise RuntimeError(f'{c.connector_id} worker exited before it was ready')
            msg = _protocol(line)
            if msg and msg.get('ready') is True: break

    def run(self, job_id: str, inputs: dict, settings: dict) -> dict:
        self.p.stdin.write(json.dumps({'job_id': job_id, 'inputs': inputs, 'settings': settings}) + '\n'); self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line: raise RuntimeError(f'{self.c.connector_id} worker exited')
            msg = _protocol(line)
            if msg and msg.get('job_id') == job_id and ('outputs' in msg or 'error' in msg): return msg

    def close(self):
        try: self.p.stdin.close(); self.p.wait(timeout=30)
        except Exception: self.p.kill()


@dataclass
class Job:
    job_id: str
    connector_id: str
    inputs: dict
    settings: dict
    lane: str
    key: str
    status: str = 'queued'
    outputs: dict | None = None
    error: str | None = None
    cached: bool = False
    seconds: float | None = None
    where: str = 'local'     # 'local' or the remote runner's name
    done: threading.Event = field(default_factory=threading.Event)


class Queue:
    def __init__(self, connectors: list[Connector], memory_fn=memory_available_gb, headroom_gb: float = 8.0,
                 wait_s: float = 600.0, poll_s: float = 15.0, remotes: dict | None = None, remote_wait_s: float = 2.0):
        self.connectors = {c.connector_id: c for c in connectors}
        self.workers: dict[str, WarmWorker] = {}
        self.last_used: dict[str, float] = {}
        self.memory_fn, self.headroom_gb, self.wait_s, self.poll_s = memory_fn, headroom_gb, wait_s, poll_s
        self.evictions: list[dict] = []
        self.cache: dict[str, dict] = {}
        self.jobs: dict[str, Job] = {}
        self.q: queue.PriorityQueue = queue.PriorityQueue(); self.n = 0
        self.gpu = threading.Lock()
        self.last_live, self.hold_s = 0.0, 3.0   # renders made ahead hold off this long after a fast or batch job, so its follow-up (a render's TRIBE read) goes first
        self.listeners: list = []
        self.remotes = remotes or {}; self.remote_wait_s = remote_wait_s
        self.remote_q: dict[str, queue.Queue] = {k: queue.Queue() for k in self.remotes}
        for k in self.remotes: threading.Thread(target=self._remote_loop, args=(k,), daemon=True).start()
        self.t = threading.Thread(target=self._loop, daemon=True); self.t.start()

    def key(self, connector_id: str, inputs: dict, settings: dict) -> str:
        c = self.connectors[connector_id]
        return hashlib.sha256(json.dumps([connector_id, c.revision, inputs, settings], sort_keys=True).encode()).hexdigest()

    def submit(self, connector_id: str, inputs: dict, settings: dict, lane: str = 'batch') -> Job:
        k = self.key(connector_id, inputs, settings)
        j = Job('job_' + uuid.uuid4().hex[:10], connector_id, inputs, settings, lane, k)
        self.jobs[j.job_id] = j
        if k in self.cache:
            j.outputs, j.status, j.cached = self.cache[k], 'done', True; j.done.set(); self._emit(j); return j
        r = self.remotes.get(connector_id)
        if lane == 'batch' and r is not None and r.can_afford(1):
            j.where = r.name; self.remote_q[connector_id].put(j.job_id); self._emit(j); return j
        if lane == 'batch' and r is not None:
            self._event({'event': 'remote limit reached', 'connector_id': connector_id, 'spent_usd': round(r.spent_usd, 2), 'limit_usd': r.limit_usd})
        self.n += 1; self.q.put(({'fast': 0, 'batch': 1}.get(lane, 2), self.n, j.job_id))   # fast, then runs and demo steps, then renders made ahead on a guess; self._emit(j)
        return j

    def _event(self, e: dict):
        for f in self.listeners: f(e)

    def _remote_loop(self, cid: str):
        """Collect batch jobs for a remote runner for remote_wait_s, then send up to chunk of them at once."""
        r, rq = self.remotes[cid], self.remote_q[cid]
        while True:
            ids = [rq.get()]; t_end = time.time() + self.remote_wait_s
            while len(ids) < r.chunk:
                try: ids.append(rq.get(timeout=max(0.0, t_end - time.time())))
                except queue.Empty: break
            js = [self.jobs[i] for i in ids]
            if not r.can_afford(len(js)):   # the limit was reached while these waited: run them here
                self._event({'event': 'remote limit reached', 'connector_id': cid, 'spent_usd': round(r.spent_usd, 2), 'limit_usd': r.limit_usd})
                for j in js: j.where = 'local'; self.n += 1; self.q.put((1, self.n, j.job_id))
                continue
            for j in js: j.status = 'running'; self._emit(j)
            t0 = time.time()
            try: msgs = r.run_batch([(j.job_id, j.inputs, j.settings) for j in js])
            except Exception as e: msgs = [{'job_id': j.job_id, 'error': f'{type(e).__name__}: {e}'} for j in js]
            by = {m['job_id']: m for m in msgs}
            for j in js:
                m = by.get(j.job_id, {'error': 'no result from the remote runner'})
                if 'error' in m: j.status, j.error = 'failed', m['error']
                else: j.status, j.outputs = 'done', m['outputs']; self.cache[j.key] = m['outputs']
                j.seconds = round(time.time() - t0, 3); self._emit(j)
                if j.lane in ('fast', 'batch'): self.last_live = time.time()
                j.done.set()

    def _emit(self, j: Job):
        for f in self.listeners: f({'job_id': j.job_id, 'connector_id': j.connector_id, 'status': j.status, 'lane': j.lane, 'cached': j.cached, 'where': j.where})

    def _loop(self):
        while True:
            pri, n, jid = self.q.get(); j = self.jobs[jid]
            if pri == 2 and time.time() - self.last_live < self.hold_s:   # an ahead job waits while a preview or run is between its steps
                self.q.put((pri, n, jid)); time.sleep(0.25); continue
            c = self.connectors[j.connector_id]
            lock = self.gpu if c.uses_gpu else threading.Lock()
            with lock:
                j.status = 'running'; self._emit(j); t0 = time.time()
                try:
                    w = self.workers.get(c.connector_id)
                    if w is None:
                        self._make_room(c); w = self.workers.setdefault(c.connector_id, WarmWorker(c))
                    self.last_used[c.connector_id] = time.time()
                    msg = w.run(j.job_id, j.inputs, j.settings)
                    self.last_used[c.connector_id] = time.time()
                    if 'error' in msg: j.status, j.error = 'failed', msg['error']
                    else: j.status, j.outputs = 'done', msg['outputs']; self.cache[j.key] = msg['outputs']
                except Exception as e:
                    j.status, j.error = 'failed', f'{type(e).__name__}: {e}'
                j.seconds = round(time.time() - t0, 3); self._emit(j)
                if j.lane in ('fast', 'batch'): self.last_live = time.time()   # before done: the waiting preview's next step lands inside the hold
                j.done.set()

    def _make_room(self, c: Connector):
        """Unload idle workers, least recently used first, until c fits. Runs inside the job loop, so every
        other worker is idle here."""
        need = c.memory_gb + self.headroom_gb
        if c.memory_gb <= 0: return
        deadline = time.time() + self.wait_s
        while True:
            have = self.memory_fn()
            if have >= need: return
            idle = sorted((k for k in self.workers if k != c.connector_id), key=lambda k: self.last_used.get(k, 0))
            if idle:
                k = idle[0]; self.workers.pop(k).close()
                self.evictions.append({'unloaded': k, 'for': c.connector_id, 'available_gb': round(have, 1), 'needed_gb': need})
                for f in self.listeners: f({'event': 'unloaded', 'connector_id': k, 'for': c.connector_id})
                continue
            if time.time() >= deadline:
                raise RuntimeError(f'{c.connector_id} needs {c.memory_gb:g} GB plus {self.headroom_gb:g} GB headroom; '
                                   f'{have:.0f} GB is available after unloading every idle worker')
            time.sleep(self.poll_s)

    def close(self):
        for w in self.workers.values(): w.close()
