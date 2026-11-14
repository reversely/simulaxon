"""Job queue and warm workers (implementation spec §1, §3, §6).

- Connectors declare a schema and the Python environment that runs them.
- A warm worker is one long-running process per connector, in its own environment, that keeps its
  model or renderer loaded and answers one JSON line per job. Isaac's shader compile and TRIBE's
  model load then happen once.
- The queue has a fast lane (single previews, served first), a batch lane (runs and demo steps), and an ahead lane
  (options and slider steps rendered on a guess, served only when nothing else waits). On a shared Spark only
  one GPU job runs at a time.
- Results are cached by the hash of connector, revision, inputs and settings.
- Fuzzball sizes the container, so the queue does no memory accounting and runs no remote lane.
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
    args: list = field(default_factory=list)   # extra arguments to the worker script


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
    done: threading.Event = field(default_factory=threading.Event)


class Queue:
    def __init__(self, connectors: list[Connector]):
        self.connectors = {c.connector_id: c for c in connectors}
        self.workers: dict[str, WarmWorker] = {}
        self.last_used: dict[str, float] = {}
        self.cache: dict[str, dict] = {}
        self.jobs: dict[str, Job] = {}
        self.q: queue.PriorityQueue = queue.PriorityQueue(); self.n = 0
        self.gpu = threading.Lock()
        self.listeners: list = []
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
        self.n += 1; self.q.put(({'fast': 0, 'batch': 1}.get(lane, 2), self.n, j.job_id))   # fast, then runs and demo steps, then renders made ahead on a guess; self._emit(j)
        return j

    def _event(self, e: dict):
        for f in self.listeners: f(e)

    def _emit(self, j: Job):
        for f in self.listeners: f({'job_id': j.job_id, 'connector_id': j.connector_id, 'status': j.status, 'lane': j.lane, 'cached': j.cached})

    def _loop(self):
        while True:
            _, _, jid = self.q.get(); j = self.jobs[jid]
            c = self.connectors[j.connector_id]
            lock = self.gpu if c.uses_gpu else threading.Lock()
            with lock:
                j.status = 'running'; self._emit(j); t0 = time.time()
                try:
                    w = self.workers.get(c.connector_id)
                    if w is None: w = self.workers.setdefault(c.connector_id, WarmWorker(c))
                    self.last_used[c.connector_id] = time.time()
                    msg = w.run(j.job_id, j.inputs, j.settings)
                    self.last_used[c.connector_id] = time.time()
                    if 'error' in msg: j.status, j.error = 'failed', msg['error']
                    else: j.status, j.outputs = 'done', msg['outputs']; self.cache[j.key] = msg['outputs']
                except Exception as e:
                    j.status, j.error = 'failed', f'{type(e).__name__}: {e}'
                j.seconds = round(time.time() - t0, 3); self._emit(j); j.done.set()

    def close(self):
        for w in self.workers.values(): w.close()
