"""A planner that answers with an error is reported with its status and its own message; only a planner that can't be
reached is reported as unreachable (#8)."""
import json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from app_server.lab import planner_agent


def fake_planner(code, body):
    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length'])); data = json.dumps(body).encode()
            self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *a): pass
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize('code, body, said', [
    (400, {'object': 'error', 'message': "This model's maximum context length is 65536 tokens.", 'code': 400}, 'maximum context length is 65536'),
    (500, {'error': {'message': 'engine is dead'}}, 'engine is dead'),
])
def test_an_error_answer_is_reported_as_what_it_said(monkeypatch, code, body, said):
    srv = fake_planner(code, body)
    try:
        monkeypatch.setattr(planner_agent, 'PLANNER_URL', f'http://127.0.0.1:{srv.server_port}/v1')
        with pytest.raises(RuntimeError) as e: planner_agent.chat([{'role': 'user', 'content': 'hi'}], [])
        msg = str(e.value)
        assert f'refused the request ({code})' in msg and said in msg and 'unreachable' not in msg
    finally: srv.shutdown()


def test_a_planner_that_cannot_be_reached_is_unreachable(monkeypatch):
    monkeypatch.setattr(planner_agent, 'PLANNER_URL', 'http://127.0.0.1:9/v1')
    with pytest.raises(RuntimeError) as e: planner_agent.chat([{'role': 'user', 'content': 'hi'}], [])
    assert 'unreachable' in str(e.value)
