"""A worker that stops answering never stalls the queue (#7): its job fails at the limit, the worker is stopped, and
the next job starts a fresh one. A worker that crashes is replaced the same way.

Run from services/app-server: python -m pytest tests
"""
import json, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from app_server.jobs import Connector, Queue, job_limit

WORKER = '''
import json, sys, time
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    j = json.loads(line)
    if j["inputs"].get("hang"): time.sleep(3600)
    if j["inputs"].get("crash"): sys.exit(3)
    print(json.dumps({"job_id": j["job_id"], "outputs": {"doubled": j["inputs"]["x"] * 2}}), flush=True)
'''


def worker():
    w = Path(tempfile.mkdtemp()) / 'worker.py'; w.write_text(WORKER); return str(w)


class Limits(unittest.TestCase):
    def setUp(self):
        self.q = Queue([Connector('double', 'test', sys.executable, worker(), 'r1', uses_gpu=False, limit_s=2)])

    def test_a_hung_job_fails_at_its_limit_and_the_next_one_runs(self):
        t0 = time.time(); j = self.q.submit('double', {'x': 1, 'hang': True}, {}); j.done.wait(30)
        self.assertEqual(j.status, 'failed'); self.assertTrue(j.timed_out); self.assertIn('limit of 2 s', j.error)
        self.assertLess(time.time() - t0, 10)
        k = self.q.submit('double', {'x': 21}, {}); k.done.wait(30)
        self.assertEqual((k.status, k.outputs), ('done', {'doubled': 42}))

    def test_a_crashed_worker_is_replaced(self):
        j = self.q.submit('double', {'x': 1, 'crash': True}, {}); j.done.wait(30)
        self.assertEqual(j.status, 'failed'); self.assertFalse(j.timed_out)
        k = self.q.submit('double', {'x': 4}, {}); k.done.wait(30)
        self.assertEqual((k.status, k.outputs), ('done', {'doubled': 8}))

    def test_limits_by_kind_and_override(self):
        import os
        self.assertEqual(job_limit(Connector('c', 'generator', '', '', 'r')), 2700.0)
        self.assertEqual(job_limit(Connector('t', 'neural model', '', '', 'r')), 900.0)
        os.environ['SIMULAXON_JOB_LIMIT_S'] = '60'
        try: self.assertEqual(job_limit(Connector('c', 'generator', '', '', 'r')), 60.0)
        finally: del os.environ['SIMULAXON_JOB_LIMIT_S']


class RemoteLimit(unittest.TestCase):
    """render-score's side stops the job and answers 504; the app server's job fails with that message."""
    def test_the_remote_timeout_comes_back_as_the_jobs_error(self):
        far = Queue([Connector('double', 'test', sys.executable, worker(), 'r1', uses_gpu=False, limit_s=2)])

        class H(BaseHTTPRequestHandler):   # the /job contract of services/render-score/server.py, 504 included
            def do_POST(self):
                b = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                j = far.submit(b['connector'], b['inputs'], b['settings'], b['lane']); j.done.wait()
                code, out = (200, j.outputs) if j.status == 'done' else (504 if j.timed_out else 500, {'error': j.error})
                data = json.dumps(out).encode(); self.send_response(code); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *a): pass

        srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            near = Queue([Connector('double', 'test', '', '', 'r1', url=f'http://127.0.0.1:{srv.server_port}')])
            j = near.submit('double', {'x': 1, 'hang': True}, {}); j.done.wait(30)
            self.assertEqual(j.status, 'failed'); self.assertIn('limit of 2 s', j.error)
        finally: srv.shutdown()


if __name__ == '__main__':
    unittest.main()
