"""Run the app: the tool API, the event stream, run outputs, brain maps and the web UI on one port.

Usage: SIMULAXON_HOME=... python -m app_server.lab.serve [--host 127.0.0.1] [--port 8790] [--db backend/data/lab_main.duckdb]

On the cluster (fuzzball/simulaxon.fz) it listens on 0.0.0.0:8791 with SIMULAXON_HOME=/data and the store at
/data/log/lab.duckdb. It also submits the Fuzzball runs in services/app-server/runs/ (GET /api/runs, POST
/api/runs/{name}/start and /stop, runs.py), and /dashboard sends people to the cluster dashboard in Grafana (GRAFANA_URL).

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
from ..config import UI   # the built frontend: SIMULAXON_UI, or this repo's frontend/dist
from .ingest import DATA, FILES, OUT
from .tools import register


UPLOAD_WIRE_LIMIT = 2_000_000_000    # bytes on the wire, compressed or not
UPLOAD_FILE_LIMIT = 20_000_000_000   # bytes on disk after a gzip upload is unpacked


async def receive(request, dest: Path) -> int:
    """Stream a request body to dest, never holding it in memory. A body sent with Content-Encoding: gzip (the browser
    compresses large uploads) is unpacked on the way, a slice at a time. Returns the bytes written; 413 past a limit."""
    import zlib
    from fastapi import HTTPException
    d = zlib.decompressobj(wbits=31) if request.headers.get('content-encoding', '').lower() == 'gzip' else None
    dest.parent.mkdir(parents=True, exist_ok=True); part = dest.with_name(dest.name + '.part'); wire = wrote = 0
    def put(f, b):
        nonlocal wrote
        wrote += len(b)
        if wrote > UPLOAD_FILE_LIMIT: raise HTTPException(413, f'The file unpacks to over {UPLOAD_FILE_LIMIT // 10**9} GB; use a link instead')
        f.write(b)
    try:
        with open(part, 'wb') as f:
            async for chunk in request.stream():
                wire += len(chunk)
                if wire > UPLOAD_WIRE_LIMIT: raise HTTPException(413, 'Files over 2 GB, even compressed, go through a link instead')
                if d is None: put(f, chunk); continue
                data = chunk
                while data:   # at most 16 MB unpacked per step, so a small body that expands hugely is caught early
                    put(f, d.decompress(data, 1 << 24)); data = d.unconsumed_tail
            if d is not None: put(f, d.flush())
        part.replace(dest); return wrote
    except zlib.error as e:
        raise HTTPException(422, f'the upload says gzip but is not: {e}')
    finally:
        if part.exists(): part.unlink()


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
                try:
                    t.call('project_update', 'agent', project_id=p.id, expect_version=p.version, status='Draft')
                    runner.start(t, app.state.lab_broadcast, p.id, 'agent')
                except Exception as e:   # one project that can no longer run must not keep the server from starting
                    print(f'run of {p.id} not resumed: {type(e).__name__}: {e}', flush=True)

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
        """A file a person adds in a chat, saved into a dataset of uploads (a new one unless dataset_id is given). Body is
        the raw file, or the file gzipped with Content-Encoding: gzip; it streams to disk."""
        import asyncio, uuid
        tmp = DATA / 'uploads' / 'incoming' / f'{uuid.uuid4().hex[:8]}_{Path(name).name}'
        await receive(request, tmp)
        return await asyncio.to_thread(sessions.upload_file, name, tmp, dataset_id)

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
                p = getattr(w, 'p', None)   # remote workers (render-score) have no process here
                if p is None: continue
                p.terminate()
                try: p.wait(timeout=5)
                except Exception: p.kill()

    @app.post('/upload')
    async def upload(request: Request, name: str):
        """Save an uploaded model file; the asset_add tool then imports it. Body is the raw file."""
        safe = Path(name).name
        if Path(safe).suffix.lower() not in {'.glb', '.gltf', '.obj', '.ply', '.stl', '.usd', '.usda', '.usdc', '.usdz'}:
            from fastapi import HTTPException
            raise HTTPException(422, 'Use GLB, glTF, OBJ, PLY, STL or USD')
        up = DATA / 'uploads'; await receive(request, up / safe)   # streamed, and unpacked if sent gzipped
        return {'file_path': str(up / safe)}

    @app.get('/thumb/{path:path}')
    def thumb(path: str):
        """A 480 px wide JPEG of an image under /files, made once and cached: sample tiles load in a fraction of the time."""
        import hashlib
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
        from PIL import Image
        src = (FILES / path).resolve()
        if not src.is_relative_to(FILES.resolve()) or not src.is_file(): raise HTTPException(404, 'no such image')
        dst = FILES / 'thumbs' / (hashlib.sha1(f'{path}:{src.stat().st_mtime_ns}'.encode()).hexdigest()[:16] + '.jpg')
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True); im = Image.open(src).convert('RGB'); im.thumbnail((480, 480)); im.save(dst, quality=82)
        return FileResponse(dst, media_type='image/jpeg', headers={'Cache-Control': 'max-age=86400'})

    from .. import runs
    from ..config import GRAFANA_URL

    @app.get('/dashboard')
    def dashboard_page():
        """The cluster dashboard is Grafana's (fuzzball/observability.fz): GPU jobs, the planner, failures, nodes."""
        from fastapi import HTTPException
        from fastapi.responses import RedirectResponse
        if not GRAFANA_URL: raise HTTPException(404, 'No dashboard here: GRAFANA_URL is empty in this place')
        return RedirectResponse(f'{GRAFANA_URL}/d/simulaxon')

    @app.get('/api/runs')
    def runs_list():
        """Studies submitted to Fuzzball as workflows (services/app-server/runs/*.json), with each step's status."""
        return [{**r, 'state': runs.state(r['name']), 'log': runs.log_tail(r['name'], 120)} for r in runs.definitions()]

    @app.post('/api/runs/{name}/start')
    def runs_start(name: str):
        from fastapi import HTTPException
        try: return runs.start(name, lambda source: None)   # the lab has no data-browser source to reload when a run ends
        except KeyError: raise HTTPException(404, f'no run {name}')

    @app.post('/api/runs/{name}/stop')
    def runs_stop(name: str):
        return runs.stop(name)

    for d in (OUT, OUT.parent / 'indexes', FILES): d.mkdir(parents=True, exist_ok=True)   # an empty home starts with nothing in them
    app.mount('/out', StaticFiles(directory=OUT), name='out')
    app.mount('/index', StaticFiles(directory=OUT.parent / 'indexes'), name='index')
    app.mount('/files', StaticFiles(directory=FILES), name='files')
    if UI.exists(): app.mount('/', StaticFiles(directory=UI, html=True), name='ui')
    return app


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--host', default='127.0.0.1'); a.add_argument('--port', type=int, default=8790); a.add_argument('--db', default=str(DATA / 'lab_main.duckdb'))
    x = a.parse_args(); Path(x.db).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(make(x.db, x.port), host=x.host, port=x.port, timeout_graceful_shutdown=5)   # an open page's event socket never holds a restart
