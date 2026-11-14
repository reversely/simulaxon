"""The one queue run remotely: a connector with a url sends each job to another queue's /job, as the app server does
with render-score on the cluster.

Run from services/app-server: python -m unittest discover tests
"""
import json, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from app_server.jobs import Connector, Queue

WORKER = '''
import json, sys
print(json.dumps({"ready": True}), flush=True)
for line in sys.stdin:
    j = json.loads(line)
    if j["inputs"].get("fail"): print(json.dumps({"job_id": j["job_id"], "error": "asked to fail"}), flush=True)
    else: print(json.dumps({"job_id": j["job_id"], "outputs": {"doubled": j["inputs"]["x"] * 2, "settings": j["settings"]}}), flush=True)
'''


class Remote(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        w = Path(tempfile.mkdtemp()) / 'worker.py'; w.write_text(WORKER)
        far = Queue([Connector('double', 'test', sys.executable, str(w), 'r1', uses_gpu=False)])   # render-score's side
        cls.lanes = []

        class H(BaseHTTPRequestHandler):   # the same /job contract as services/render-score/server.py
            def do_POST(self):
                b = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                cls.lanes.append(b['lane'])
                j = far.submit(b['connector'], b['inputs'], b['settings'], b['lane']); j.done.wait()
                code, out = (200, j.outputs) if j.status == 'done' else (500, {'error': j.error})
                data = json.dumps(out).encode(); self.send_response(code); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
            def log_message(self, *a): pass

        cls.srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.near = Queue([Connector('double', 'test', '', '', 'r1', url=f'http://127.0.0.1:{cls.srv.server_port}')])   # the app server's side

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_outputs_come_back_with_lane_and_settings(self):
        j = self.near.submit('double', {'x': 21}, {'k': 1}, lane='fast'); j.done.wait(30)
        self.assertEqual((j.status, j.outputs), ('done', {'doubled': 42, 'settings': {'k': 1}}))
        self.assertEqual(self.lanes[-1], 'fast')

    def test_remote_error_is_the_jobs_error(self):
        j = self.near.submit('double', {'x': 1, 'fail': True}, {}); j.done.wait(30)
        self.assertEqual((j.status, j.error), ('failed', 'asked to fail'))

    def test_unreachable_remote_fails_the_job(self):
        q = Queue([Connector('double', 'test', '', '', 'r1', url='http://127.0.0.1:9')])
        j = q.submit('double', {'x': 1}, {}); j.done.wait(30)
        self.assertEqual(j.status, 'failed'); self.assertIn('unreachable', j.error)


if __name__ == '__main__':
    unittest.main()
