"""HTTP front of render-score: a scene goes in; it is rendered (Isaac Sim), restyled (Cosmos3-Nano) and read (TRIBE v2);
the paths of the chunk and the prediction under /data come out.

usage: python server.py [--host 0.0.0.0] [--port 8100]

  GET  /health   {"ready": true, "workers": [...]} once the three connectors are defined; workers start on first use
  POST /score    {rec, k, body, motion, motion_file, prompt, name, control?, seed?}
                 -> {render, chunk, prediction, seconds}; render is Isaac's clip, chunk Cosmos's restyle in
                 /data/chunks, prediction TRIBE's response to the chunk in /data/predictions
  POST /job      {connector, inputs, settings, lane?} -> one job on one worker (isaac_body, cosmos, tribe)

Each worker runs in its own environment under /data/envs and keeps its model or renderer loaded (jobs.py). One GPU job
runs at a time. Uses only the standard library, so any of the environments' Pythons can run it.
"""
from __future__ import annotations
import argparse, json, os, shutil, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from jobs import Connector, Queue

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SIMULAXON_DATA', '/data'))
ENVS = Path(os.environ.get('SIMULAXON_ENVS', DATA / 'envs'))
ISAAC_ENV = {'OMNI_KIT_ACCEPT_EULA': 'YES', 'LD_PRELOAD': '/lib/aarch64-linux-gnu/libgomp.so.1'}

CONNECTORS = [
    Connector('isaac_body', 'render', str(ENVS / 'isaac/bin/python'), str(HERE / 'isaac/isaac_body_worker.py'), 'isaac-6.2', env=ISAAC_ENV),
    Connector('cosmos', 'restyle', str(ENVS / 'cosmos/bin/python'), str(HERE / 'cosmos/cosmos_worker.py'), 'cosmos-c3a2e37'),
    Connector('tribe', 'predict', str(ENVS / 'tribe/bin/python'), str(HERE / 'tribe/tribe_worker.py'), 'tribev2-af58661'),
]
Q = Queue(CONNECTORS)


def run(connector: str, inputs: dict, settings: dict, lane: str = 'batch') -> dict:
    j = Q.submit(connector, inputs, settings, lane); j.done.wait()
    if j.status != 'done': raise RuntimeError(f'{connector}: {j.error}')
    return j.outputs


def score(s: dict) -> dict:
    """Render, restyle and read one scene, one stage after the other."""
    t0 = time.time(); name = s['name']
    renders = DATA / 'chunks' / 'renders'; chunks = DATA / 'chunks'; preds = DATA / 'predictions'
    for d in (renders, chunks, preds): d.mkdir(parents=True, exist_ok=True)
    r = run('isaac_body', {k: s[k] for k in ('rec', 'k', 'body', 'motion', 'motion_file')} | {'out_dir': str(renders), 'name': name}, {})
    c = run('cosmos', {'controls': {'rgb': r['clip']}, 'prompt': s['prompt'], 'out_dir': str(chunks), 'name': name},
            {'control': s.get('control', 'edge'), 'seed': int(s.get('seed', 2025))})
    p = run('tribe', {'clip': c['clip']}, {'on_s': r.get('on_s', [1, 9])})
    pred = preds / f'{name}.tribe.npy'; shutil.copyfile(p['response'], pred)
    return {'render': r['clip'], 'chunk': c['clip'], 'prediction': str(pred), 'seconds': round(time.time() - t0, 1)}


class H(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict):
        b = json.dumps(body, default=str).encode()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == '/health': return self._send(200, {'ready': True, 'workers': sorted(Q.workers), 'connectors': [c.connector_id for c in CONNECTORS]})
        self._send(404, {'error': 'not found'})

    def do_POST(self):
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            if self.path == '/score': return self._send(200, score(body))
            if self.path == '/job': return self._send(200, run(body['connector'], body['inputs'], body.get('settings', {}), body.get('lane', 'fast')))
            self._send(404, {'error': 'not found'})
        except (KeyError, ValueError) as e: self._send(422, {'error': f'{type(e).__name__}: {e}'})
        except Exception as e: self._send(500, {'error': f'{type(e).__name__}: {e}'})

    def log_message(self, fmt, *a): print(time.strftime('%H:%M:%S'), self.address_string(), fmt % a, flush=True)


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--host', default='0.0.0.0'); a.add_argument('--port', type=int, default=8100); p = a.parse_args()
    ThreadingHTTPServer((p.host, p.port), H).serve_forever()
