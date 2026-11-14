"""Run the app: the tool API, the event stream, run outputs, brain maps and the web UI on one port.

Usage: SIMULAXON_HOME=... python -m app_server.lab.serve [--port 8790] [--db backend/data/lab_main.duckdb]

lab_main.duckdb is the main store: the lab's store as of 14 Nov 2026 with the replication harness's projects, papers,
samples, analyses, results and maps merged in. lab.duckdb is the store before that merge; lab_harness.duckdb keeps the
harness's own step history.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import uvicorn
from fastapi import Request
from fastapi.staticfiles import StaticFiles
from ..server import create_app
from ..store import Store
from .ingest import DATA, FILES, OUT
from .tools import register

UI = Path(__file__).resolve().parents[4] / 'frontend' / 'dist'   # this repo's built frontend


def make(db: str, port: int = 8790):
    app = create_app(Store(db)); app.state.tools_port = port; register(app.state.tools, app.state.broadcast); app.state.lab_broadcast = app.state.tools.lab_broadcast; app.state.tools.port = port

    @app.post('/agent')
    async def agent(body: dict):
        import asyncio
        from fastapi import HTTPException
        from .agent import ask
        try:
            reply = await asyncio.to_thread(ask, body['project_id'], body['message'], body.get('history', []), f'http://127.0.0.1:{port}')
        except Exception as e:
            raise HTTPException(502, str(e)[-400:])
        return {'reply': reply}

    @app.on_event('startup')
    def _resume_runs():
        """A run cut off by a restart resumes; clips already through Isaac and TRIBE come from the disk cache."""
        from . import runner
        t = app.state.tools
        for p in t.store.list('project'):
            if p.data.get('status') == 'Running' and (p.data.get('pairs') or p.data.get('units') or p.data.get('plan') == 'experiment'):   # matched, factorial and experiments; finished clips come from the cache
                t.call('project_update', 'agent', project_id=p.id, expect_version=p.version, status='Draft')
                runner.start(t, app.state.lab_broadcast, p.id, 'agent')

    from . import sessions

    @app.post('/agent/sessions')
    def session_start(body: dict):
        """A new chat with the agent: {text, mode: discuss or through, project_id?, max_turns?, max_hours?}."""
        return sessions.start(app.state.tools, app.state.lab_broadcast, f'http://127.0.0.1:{port}', body.get('text') or body['goal'], body.get('mode', 'discuss'),
                              body.get('project_id'), int(body.get('max_turns', 40)), float(body.get('max_hours', 8)))

    @app.get('/agent/sessions')
    def session_list(project_id: str | None = None):
        return sessions.listing(project_id)

    @app.get('/agent/sessions/{sid}')
    def session_get(sid: str):
        return sessions.get(sid)

    @app.post('/agent/sessions/{sid}/stop')
    def session_stop(sid: str):
        return sessions.stop(sid)

    @app.post('/agent/sessions/{sid}/message')
    def session_message(sid: str, body: dict):
        """The person's next message: {text, mode: discuss or through}."""
        return sessions.message(app.state.tools, app.state.lab_broadcast, f'http://127.0.0.1:{port}', sid, body['text'], body.get('mode', 'discuss'))

    @app.post('/datasets/upload')
    async def dataset_upload(request: Request, name: str, dataset_id: str | None = None):
        """A file a person adds in a chat, saved into a dataset of uploads (a new one unless dataset_id is given). Body is the raw file."""
        body = await request.body()
        if len(body) > 2e9: from fastapi import HTTPException; raise HTTPException(413, 'Files over 2 GB go through a link instead')
        return sessions.upload(name, body, dataset_id)

    @app.on_event('startup')
    def _resume_sessions():
        sessions.resume_all(app.state.tools, app.state.lab_broadcast, f'http://127.0.0.1:{port}')

    @app.on_event('startup')
    def _prepare_demos():
        app.state.tools.demo_player.prepare_all()

    @app.on_event('shutdown')
    def _stop_workers():
        from . import preview, runner
        runner.SHUTTING_DOWN.set()   # a run cut off here stays Running, so the next start resumes it
        if preview._q:   # warm Isaac and TRIBE workers end with the server, never left holding the GPU
            for w in preview._q.workers.values():
                w.p.terminate()
                try: w.p.wait(timeout=5)
                except Exception: w.p.kill()

    @app.post('/upload')
    async def upload(request: Request, name: str):
        """Save an uploaded model file; the asset_add tool then imports it. Body is the raw file."""
        safe = Path(name).name
        if Path(safe).suffix.lower() not in {'.glb', '.gltf', '.obj', '.ply', '.stl', '.usd', '.usda', '.usdc', '.usdz'}:
            from fastapi import HTTPException
            raise HTTPException(422, 'Use GLB, glTF, OBJ, PLY, STL or USD')
        up = DATA / 'uploads'; up.mkdir(parents=True, exist_ok=True); (up / safe).write_bytes(await request.body())
        return {'file_path': str(up / safe)}

    @app.get('/thumb/{path:path}')
    def thumb(path: str):
        """A 480 px wide JPEG of an image under /files, made once and cached: sample tiles load in a fraction of the time."""
        import hashlib
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
        from PIL import Image
        src = (FILES / path).resolve()
        if not str(src).startswith(str(FILES.resolve())) or not src.is_file(): raise HTTPException(404, 'no such image')
        dst = FILES / 'thumbs' / (hashlib.sha1(f'{path}:{src.stat().st_mtime_ns}'.encode()).hexdigest()[:16] + '.jpg')
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True); im = Image.open(src).convert('RGB'); im.thumbnail((480, 480)); im.save(dst, quality=82)
        return FileResponse(dst, media_type='image/jpeg', headers={'Cache-Control': 'max-age=86400'})

    app.mount('/out', StaticFiles(directory=OUT), name='out')
    app.mount('/index', StaticFiles(directory=OUT.parent / 'indexes'), name='index')
    app.mount('/files', StaticFiles(directory=FILES), name='files')
    if UI.exists(): app.mount('/', StaticFiles(directory=UI, html=True), name='ui')
    return app


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--port', type=int, default=8790); a.add_argument('--db', default=str(DATA / 'lab_main.duckdb'))
    x = a.parse_args(); uvicorn.run(make(x.db, x.port), host='127.0.0.1', port=x.port, timeout_graceful_shutdown=5)   # an open page's event socket never holds a restart
