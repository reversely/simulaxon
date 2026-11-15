"""Recordings (#23): streams on one clock, in the lab's own format.

A recording is a folder (or a .zip of one) holding recording.json and its stream files:

  {"format": "simulaxon.recording", "version": 1, "title": "...", "duration_s": 8.0,
   "streams": [
     {"name": "video",   "kind": "video",  "file": "video.mp4"},
     {"name": "tribe",   "kind": "tribe",  "file": "tribe.npy", "rate_hz": 1, "space": "fsaverage5", "model": "TRIBE v2"},
     {"name": "audio",   "kind": "audio",  "file": "audio.wav"},
     {"name": "regions", "kind": "table",  "file": "regions.csv", "time_column": "t"},
     {"name": "events",  "kind": "events", "file": "events.csv", "time_column": "t", "label_column": "label"}],
   "source": {...}}

Every stream may carry start_s, its offset on the recording's clock (default 0). A recording needs at least one video;
a tribe stream is seconds by 20,484 fsaverage5 vertices, as TRIBE v2 writes it. A table holds any channels over time
(robot state, actions, region responses), one column each beside the time column; events are labelled moments.
A sample with a clip and its predictions exports as one (export()); the dataset importer reads one as one item.
"""
from __future__ import annotations
import csv, io, json, subprocess, zipfile
from pathlib import Path
import numpy as np

FORMAT, VERSION, MANIFEST = 'simulaxon.recording', 1, 'recording.json'
KINDS = ('video', 'tribe', 'audio', 'table', 'events')


def read(folder: Path) -> dict:
    """The manifest of the recording in `folder`, checked: known kinds, every file inside the folder and present, one video."""
    m = json.loads((folder / MANIFEST).read_text())
    if m.get('format') != FORMAT: raise ValueError(f"{folder.name}: not a {FORMAT} manifest")
    streams = m.get('streams') or []
    for s in streams:
        if s.get('kind') not in KINDS: raise ValueError(f"{folder.name}: stream {s.get('name')} has kind {s.get('kind')}; known: {', '.join(KINDS)}")
        p = (folder / str(s.get('file', ''))).resolve()
        if not p.is_relative_to(folder.resolve()) or not p.is_file(): raise ValueError(f"{folder.name}: stream {s.get('name')} names a missing file {s.get('file')}")
    if not any(s['kind'] == 'video' for s in streams): raise ValueError(f'{folder.name}: a recording needs at least one video stream')
    return m


def fields(root: Path, folder: Path) -> tuple[dict, dict]:
    """A recording's fields for the dataset index, and where each came from."""
    m = read(folder); rel = folder.relative_to(root).as_posix(); kinds = [s['kind'] for s in m['streams']]
    size = sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
    f = {'file': rel, 'folder': folder.parent.relative_to(root).as_posix() if folder.parent != root else '', 'media_type': 'recording',
         'size_mb': round(size / 1e6, 4), 'streams': ', '.join(s['name'] for s in m['streams']), 'n_streams': len(kinds), 'has_tribe': 'tribe' in kinds}
    src = {k: 'path in the dataset' for k in ('file', 'folder')} | {'media_type': MANIFEST, 'size_mb': 'size of the files', 'streams': MANIFEST, 'n_streams': MANIFEST, 'has_tribe': MANIFEST}
    if folder.parent != root: f['category'] = folder.parent.name; src['category'] = 'the folder the recording is in'
    if m.get('duration_s') is not None: f['duration_s'] = float(m['duration_s']); src['duration_s'] = MANIFEST
    if m.get('title'): f['title'] = m['title']; src['title'] = MANIFEST
    import hashlib
    h = hashlib.blake2b(digest_size=12)
    for p in sorted(x for x in folder.rglob('*') if x.is_file()): h.update(p.relative_to(folder).as_posix().encode()); h.update(p.read_bytes())
    f['sha'] = h.hexdigest(); src['sha'] = 'content hash (BLAKE2b) of every file'
    return f, src


def _duration(p: Path) -> float | None:
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    try: return round(float(r.stdout.strip()), 3)
    except ValueError: return None


def _has_audio(p: Path) -> bool:
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def export(sample: dict, clip: Path, title: str, regions: list[str], mask_for) -> bytes:
    """One sample as a recording, zipped: its clip, its TRIBE v2 predictions, the clip's audio if it has any, and the
    response of each region it was read in, second by second (mean over the region's vertices, TRIBE's own units)."""
    preds = np.load(sample['preds']); dur = _duration(clip)
    streams = [{'name': 'video', 'kind': 'video', 'file': 'video.mp4'},
               {'name': 'tribe', 'kind': 'tribe', 'file': 'tribe.npy', 'rate_hz': 1, 'space': 'fsaverage5', 'model': 'TRIBE v2', 'units': "TRIBE v2's own units, average viewer"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as z:
        z.write(clip, 'video.mp4')
        b = io.BytesIO(); np.save(b, preds); z.writestr('tribe.npy', b.getvalue())
        if _has_audio(clip):
            wav = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(clip), '-vn', '-c:a', 'pcm_s16le', '-f', 'wav', '-'], capture_output=True, check=True).stdout
            z.writestr('audio.wav', wav); streams.append({'name': 'audio', 'kind': 'audio', 'file': 'audio.wav'})
        cols = []
        for r in regions:
            try: cols.append((r, mask_for(r)))
            except Exception: continue
        if cols:
            s = io.StringIO(); w = csv.writer(s); w.writerow(['t'] + [r for r, _ in cols])
            for i in range(len(preds)): w.writerow([i] + [f'{float(preds[i][m].mean()):.6f}' for _, m in cols])
            z.writestr('regions.csv', s.getvalue()); streams.append({'name': 'regions', 'kind': 'table', 'file': 'regions.csv', 'time_column': 't', 'units': "TRIBE v2's own units"})
        man = {'format': FORMAT, 'version': VERSION, 'title': title, 'duration_s': max(dur or 0, float(len(preds))), 'streams': streams,
               'source': {k: sample.get(k) for k in ('project_id', 'condition', 'label', 'index')}}
        z.writestr(MANIFEST, json.dumps(man, indent=1))
    return buf.getvalue()
