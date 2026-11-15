"""Run the app: the tool API, the event stream, run outputs, brain maps and the web UI on one port.

Usage: SIMULAXON_HOME=... python -m app_server.lab.serve [--host 127.0.0.1] [--port 8790] [--db backend/data/lab_main.duckdb]

On the cluster (fuzzball/simulaxon.fz) it listens on 0.0.0.0:8791 with SIMULAXON_HOME=/data and the store at
/data/log/lab.duckdb. It also submits the Fuzzball runs in services/app-server/runs/ (GET /api/runs, POST
/api/runs/{name}/start and /stop, runs.py), and /dashboard sends people to Grafana's endpoint on the cluster.

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
        from fastapi import HTTPException
        from . import datasets
        if dataset_id is not None:
            try: datasets.dataset_dir(dataset_id)   # checked before the body is read
            except ValueError as e: raise HTTPException(422, str(e))
        tmp = DATA / 'uploads' / 'incoming' / f'{uuid.uuid4().hex[:8]}_{Path(name).name}'
        await receive(request, tmp)
        try: return await asyncio.to_thread(sessions.upload_file, name, tmp, dataset_id)
        except ValueError as e: raise HTTPException(422, str(e))   # such as an archive too large to unpack

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

    @app.get('/datasets/thumb/{path:path}')
    def dataset_thumb(path: str):
        """A 320 px JPEG of a dataset's image, or of a video's frame at 0.5 s, made once and cached (#22)."""
        import hashlib, subprocess
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
        from PIL import Image
        from .datasets import HERE as FETCHED, kind_of
        src = (FETCHED / path).resolve()
        if not src.is_relative_to(FETCHED.resolve()) or not src.is_file(): raise HTTPException(404, 'no such file')
        dst = FILES / 'thumbs' / ('d_' + hashlib.sha1(f'{path}:{src.stat().st_mtime_ns}'.encode()).hexdigest()[:16] + '.jpg')
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            if kind_of(src.name) == 'video':
                subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', '0.5', '-i', str(src), '-frames:v', '1', '-vf', 'scale=320:-2', str(dst)], timeout=60)
                if not dst.exists(): raise HTTPException(404, 'no frame in this video')
            else:
                im = Image.open(src).convert('RGB'); im.thumbnail((320, 320)); im.save(dst, quality=80)
        return FileResponse(dst, media_type='image/jpeg', headers={'Cache-Control': 'max-age=86400'})

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

    @app.get('/api/brain/mesh')
    def brain_mesh():
        """The fsaverage5 cortex the page draws brains on (#27): lab/brainmesh.py, built once."""
        from fastapi.responses import FileResponse
        from . import brainmesh
        return FileResponse(brainmesh.path(FILES), media_type='application/octet-stream', headers={'Cache-Control': 'max-age=31536000, immutable'})

    @app.get('/api/brain/preds/{sample_id}')
    def brain_preds(sample_id: str):
        """A sample's TRIBE v2 predictions as stored (.npy, seconds by 20,484 fsaverage5 vertices), for the brain player (#27)."""
        from fastapi import HTTPException
        from fastapi.responses import FileResponse
        row = app.state.tools.store.get('sample', sample_id)
        p = Path(row.data['preds']) if row is not None and row.data.get('preds') else None
        if p is None or not p.is_file(): raise HTTPException(404, f'no predictions for {sample_id}')
        return FileResponse(p, media_type='application/octet-stream', headers={'Cache-Control': 'max-age=86400'})

    @app.get('/api/brain/contrast/{project_id}/{index}')
    def brain_contrast(project_id: str, index: int):
        """Fig. 2's contrast number `index` (from 0, run_get's order) as per-vertex values (.npy, float32), from export.contrast_maps (#27)."""
        import io
        import numpy as np
        from fastapi import HTTPException
        from fastapi.responses import Response
        from . import export
        if app.state.tools.store.get('project', project_id) is None: raise HTTPException(404, f'no project {project_id}')
        ms = export.contrast_maps(app.state.tools.store, project_id)
        if not 0 <= index < len(ms): raise HTTPException(404, f'no contrast {index} for {project_id}')
        buf = io.BytesIO(); np.save(buf, np.asarray(ms[index]['map'], np.float32))
        return Response(buf.getvalue(), media_type='application/octet-stream', headers={'Cache-Control': 'no-cache'})

    @app.get('/api/brain/adapter/{adapter_id}/{key}')
    def brain_adapter(adapter_id: str, key: str):
        """An adapter's evaluation spread over the cortex (#28): key adapter_r, tribe_v2_r or gain (adapter minus TRIBE v2), per HCP-MMP1 area (.npy, float32)."""
        import io
        import numpy as np
        from fastapi import HTTPException
        from fastapi.responses import Response
        from . import adapter
        row = app.state.tools.store.get('adapter', adapter_id)
        if row is None: raise HTTPException(404, f'no adapter {adapter_id}')
        if key not in ('adapter_r', 'tribe_v2_r', 'gain'): raise HTTPException(404, 'key is adapter_r, tribe_v2_r or gain')
        areas = [{**a, 'gain': a['adapter_r'] - a['tribe_v2_r']} for a in row.data['areas']]
        buf = io.BytesIO(); np.save(buf, adapter.area_map(areas, key)); return Response(buf.getvalue(), media_type='application/octet-stream', headers={'Cache-Control': 'max-age=86400'})

    @app.get('/api/recording/{sample_id}')
    def recording_download(sample_id: str):
        """A sample as a recording (#23, lab/recording.py): its clip, TRIBE v2 predictions, audio if any, and its regions' responses by second, zipped."""
        import re as _re
        from fastapi import HTTPException
        from fastapi.responses import Response
        from . import recording, regions
        S = app.state.tools.store; row = S.get('sample', sample_id)
        if row is None: raise HTTPException(404, f'no sample {sample_id}')
        d = row.data; url = d.get('clip') or ''
        base = {'/files/': FILES, '/out/': OUT}; pre = next((k for k in base if url.startswith(k)), None)
        clip = (base[pre] / url[len(pre):]).resolve() if pre else None
        if clip is None or not clip.is_file() or not d.get('preds') or not Path(d['preds']).is_file(): raise HTTPException(404, f'{sample_id} has no clip and predictions to record')
        P = S.get('project', d.get('project_id', '')); title = f"{P.data['title']}: {d.get('label', sample_id)}" if P else d.get('label', sample_id)
        data = recording.export(d, clip, title, list((d.get('readout') or {}).keys()), regions.mask_for)
        name = (_re.sub(r'[^A-Za-z0-9]+', '_', d.get('label') or sample_id).strip('_')[:60] or sample_id) + '.rec.zip'
        return Response(data, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{name}"'})

    @app.get('/api/results/{project_id}/download/{name}')
    def results_download(project_id: str, name: str):
        """One file of a finished run's results, or all.zip with every one (#20): built from the store, as run_get lists them."""
        import mimetypes, re as _re
        from fastapi import HTTPException
        from fastapi.responses import FileResponse, Response
        from . import export
        T = app.state.tools
        try: rec = T.call('run_get', 'person', project_id=project_id)
        except Exception as e: raise HTTPException(404, str(e))
        fs = export.files(rec, export.contrast_maps(T.store, project_id)); folder = _re.sub(r'[^A-Za-z0-9]+', '_', rec['project']['title']).strip('_')[:60] or project_id
        if name == 'all.zip':
            return Response(export.zipped(fs, folder), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{folder}.zip"'})
        if name not in fs: raise HTTPException(404, f'no file {name} for this run')
        data = fs[name]; head = {'Content-Disposition': f'attachment; filename="{name}"'}; mt = mimetypes.guess_type(name)[0] or 'application/octet-stream'
        return FileResponse(data, media_type=mt, headers=head) if not isinstance(data, (bytes, bytearray)) else Response(bytes(data), media_type=mt, headers=head)

    from .. import runs

    def _grafana_on_cluster() -> str | None:
        """The live endpoint of the running observability workflow's Grafana. Its URL changes with every restart, so it
        is looked up per request; the injected workflow token may list endpoints (In-Workflow API Access)."""
        import json, subprocess
        from ..config import FUZZBALL
        try:
            p = subprocess.run([FUZZBALL, 'workflow', 'endpoints', 'list', '-o', 'json'], capture_output=True, text=True, timeout=30)
            eps = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return None
        g = [e for e in eps if e.get('serviceName') == 'grafana' and e.get('url')]
        return g[0]['url'].rstrip('/') if g else None

    @app.get('/dashboard')
    def dashboard_page():
        """The cluster dashboard is Grafana's (fuzzball/observability.fz): GPU jobs, the planner, failures, nodes. It always
        goes to Grafana's endpoint on the cluster; when none is live it says so rather than sending people elsewhere."""
        from fastapi.responses import HTMLResponse, RedirectResponse
        url = _grafana_on_cluster()
        if url: return RedirectResponse(f'{url}/d/simulaxon')
        return HTMLResponse('<!doctype html><title>Dashboard</title><p>Grafana is not running on the cluster. Start it with '
                            '<code>fuzzball workflow start -n observability fuzzball/observability.fz</code>.</p>', status_code=503)

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
    from .datasets import HERE as FETCHED
    FETCHED.mkdir(parents=True, exist_ok=True)
    app.mount('/datasets/media', StaticFiles(directory=FETCHED), name='dataset_media')   # a dataset's own files, for curation (#22)
    if UI.exists(): app.mount('/', StaticFiles(directory=UI, html=True), name='ui')
    return app


if __name__ == '__main__':
    a = argparse.ArgumentParser(); a.add_argument('--host', default='127.0.0.1'); a.add_argument('--port', type=int, default=8790); a.add_argument('--db', default=str(DATA / 'lab_main.duckdb'))
    x = a.parse_args(); Path(x.db).parent.mkdir(parents=True, exist_ok=True)
    uvicorn.run(make(x.db, x.port), host=x.host, port=x.port, timeout_graceful_shutdown=5)   # an open page's event socket never holds a restart
