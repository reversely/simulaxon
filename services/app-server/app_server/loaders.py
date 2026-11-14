"""Loaders per file layout, never per run. Each reads a source description (backend/sources/<name>.json) and writes samples.

  folders   one folder per sample: a JSON file of fields, a media file or an image sequence, optional arrays of tracks
  table     one row per sample in a CSV or TSV: a column naming the media file, the other columns as fields,
            optional per-row array files as tracks

Paths in a source are relative to the data root (config.DATA, /data on the cluster). Every field records where it came from as "file#key".

usage: python -m app_server.loaders services/app-server/sources/<name>.json [...]
"""
from __future__ import annotations
import csv, json, re, subprocess, sys
from pathlib import Path
import numpy as np
from . import store
from .config import DATA

VIDEO, IMAGE = {'.mp4', '.mov', '.webm', '.mkv'}, {'.png', '.jpg', '.jpeg', '.webp'}


def rel(p: Path) -> str:
    return str(Path(p).resolve().relative_to(DATA.resolve()))


def media_type(p: Path) -> str:
    s = p.suffix.lower(); return 'video' if s in VIDEO else 'image' if s in IMAGE else 'audio' if s in {'.wav', '.mp3', '.flac'} else 'file'


def encode_sequence(folder: Path, pattern: str, fps: float, out_name: str) -> Path:
    """An image sequence becomes one MP4 beside it, once. The derived file is recorded as made from the sequence."""
    out = folder / out_name
    if not out.exists():
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(fps), '-i', str(folder / pattern),
                        '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-an', str(out)], check=True)
    return out


def track(file: Path, key: str | None, rate_hz: float | None, offset_s: float, shape, columns=None, time_key: str | None = None) -> dict:
    return {'_kind': 'track', 'file': rel(file), 'key': key, 'rate_hz': rate_hz, 'offset_s': offset_s, 'shape': list(shape),
            'columns': columns, 'time_key': time_key}


def tracks_from_npz(f: Path, spec: dict) -> dict:
    """Every array in the file whose first axis runs along the time key becomes a track."""
    z = np.load(f); tk = spec.get('time_key'); names = spec.get('columns', {})
    n = len(z[tk]) if tk else None; out = {}
    for k in z.files:
        if k == tk: continue
        a = z[k]
        if n is not None and (a.ndim == 0 or len(a) != n): continue
        cols = names.get(k) or ([f'{k}[{i}]' for i in range(a.shape[1])] if a.ndim == 2 else None)
        out[k] = track(f, k, spec.get('rate_hz'), spec.get('offset_s', 0.0), a.shape, cols, tk)
    return out


def load_folders(src: dict) -> list[dict]:
    """One folder per sample (sample_glob may span levels, such as "*/c*"). Options: fields_file, extra_fields_files (read
    when present, such as results written later), media (one file or image sequence) or media_slices (several, each its
    own sample in the folder's group), tracks (an .npz), group_regex on the folder's path below root."""
    root = DATA / src['root']; rows = []
    g = re.compile(src['group_regex']) if src.get('group_regex') else None
    for d in sorted(p for p in root.glob(src['sample_glob']) if p.is_dir()):
        ff = d / src['fields_file']
        if not ff.exists(): continue
        fields = json.load(open(ff)); sources = {k: f'{rel(ff)}#{k}' for k in fields}
        for extra in src.get('extra_fields_files', []):
            if (d / extra).exists():
                ex = json.load(open(d / extra)); fields.update(ex); sources.update({k: f'{rel(d / extra)}#{k}' for k in ex})
        t = src.get('tracks')
        if t and (d / t['file']).exists():
            tr = tracks_from_npz(d / t['file'], t); fields.update(tr); sources.update({k: f"{rel(d / t['file'])}#{k}" for k in tr})
        relp = str(d.relative_to(root)); grp, sl = relp, None
        if g:
            mm = g.fullmatch(relp)
            if mm: grp, sl = mm.group('group'), (mm.groupdict().get('slice') or src.get('default_slice'))
        slices = src.get('media_slices') or {None: src.get('media', {})}
        for name, m in slices.items():
            src_note = None
            if m.get('sequence') and (d / (m['sequence'] % 0)).exists():
                media = encode_sequence(d, m['sequence'], m['fps'], m.get('encode_to', 'video.mp4')); src_note = f"made from {rel(d)}/{m['sequence']} at {m['fps']} fps"
            elif m.get('file'): media = d / m['file']
            else: media = None
            s_ = '/'.join(x for x in (sl, name) if x) or None
            rows.append({'id': relp + (f'/{name}' if name else ''), 'group': grp, 'slice': s_, 'media': rel(media) if media and media.exists() else None,
                         'media_type': media_type(media) if media else None, 'fields': fields, 'sources': {**sources, **({'_media': src_note} if src_note else {})}})
    return rows


_INT = re.compile(r'-?(0|[1-9][0-9]*)'); _FLOAT = re.compile(r'-?(0|[1-9][0-9]*)?\.[0-9]+([eE][-+]?[0-9]+)?|-?(0|[1-9][0-9]*)[eE][-+]?[0-9]+|-?(0|[1-9][0-9]*)\.')


def _num(v: str):
    """Table text to a value. Only plain decimal numbers become numbers: "01_001" and "007" stay text (ids), and an
    empty cell or "nan" is missing, never a number."""
    if v is None or v.strip() == '' or v.strip().lower() in ('nan', 'na', 'null', 'none'): return None
    t = v.strip()
    if _INT.fullmatch(t): return int(t)
    if _FLOAT.fullmatch(t): return float(t)
    return v


def _rows(f: Path):
    """Rows of a CSV, TSV or JSON list, with where each came from."""
    if f.suffix == '.json':
        return [(r, f'item {i}') for i, r in enumerate(json.load(open(f)))]
    return [({k: _num(v) for k, v in r.items()}, f'row {i + 2}') for i, r in enumerate(csv.DictReader(open(f), delimiter='\t' if f.suffix == '.tsv' else ','))]


def _fmt(template: str, r: dict, replace=None) -> str:
    """A path or name template filled from the row. `replace` rewrites the row's text values as they are written on disk."""
    v = {k: (x.replace(*replace) if replace and isinstance(x, str) else x) for k, x in r.items()}
    return template.format(**v)


def csv_track(f: Path, time_column: str):
    """A CSV with a time column: every other numeric column is a series."""
    with open(f) as fh:
        head = next(csv.reader(fh))
    return [c for c in head if c != time_column]


def load_table(src: dict) -> list[dict]:
    """One sample per row of a CSV, TSV or JSON list. Options:
      filter         {column: value}: keep only rows that match
      id, group, slice   templates filled from the row (id defaults to the media file's stem)
      media          a path template, or media_column + media_root + media_glob to search for it
      media_name_replace  [old, new] applied to row text when filling media and track templates
      require_media  drop rows whose media file does not exist
      tracks         [{name, file, format: npy | csv, time_column, rate_hz, offset_s}] per row
    """
    f = DATA / src['file']; rows = []; rp = src.get('media_name_replace')
    for r, where in _rows(f):
        if any(r.get(k) != v for k, v in src.get('filter', {}).items()): continue
        if src.get('media'): media = DATA / _fmt(src['media'], r, rp)
        else: media = next(iter((DATA / src['media_root']).glob(_fmt(src.get('media_glob', '**/{%s}' % src['media_column']), r, rp))), None)
        if media is not None and not media.exists(): media = None
        if src.get('require_media') and media is None: continue
        fields = dict(r); sources = {k: f'{rel(f)}#{where}, {"key" if f.suffix == ".json" else "column"} {k}' for k in r}
        for t in src.get('tracks', []):
            raw_stem = Path(str(r[src['media_column']])).stem if src.get('media_column') else (media.stem if media else '')
            tf = DATA / _fmt(t['file'], {**r, 'stem': raw_stem})   # track names follow the row as written, not the media rewrite
            if not tf.exists(): continue
            if t.get('format', 'npy') == 'csv':
                cols = csv_track(tf, t['time_column'])
                fields[t['name']] = {**track(tf, None, t.get('rate_hz'), t.get('offset_s', 0.0), [sum(1 for _ in open(tf)) - 1, len(cols)], cols, t['time_column']), 'format': 'csv'}
            else:
                a = np.load(tf, mmap_mode='r'); fields[t['name']] = track(tf, None, t.get('rate_hz'), t.get('offset_s', 0.0), a.shape, None)
            sources[t['name']] = rel(tf)
        sid = _fmt(src['id'], r) if src.get('id') else Path(str(r[src['media_column']])).stem if src.get('media_column') else (media.stem if media else where)
        rows.append({'id': sid, 'group': _fmt(src['group'], r) if src.get('group') else sid, 'slice': _fmt(src['slice'], r) if src.get('slice') else None,
                     'media': rel(media) if media else None, 'media_type': media_type(media) if media else None, 'fields': fields, 'sources': sources})
    return rows


LOADERS = {'folders': load_folders, 'table': load_table}


def load(source_file: Path, db=None):
    src = json.load(open(source_file)); db = db or store.connect()
    rows = LOADERS[src['loader']](src)
    store.replace_dataset(db, src['name'], {**src, 'source_file': source_file.name}, rows)
    sch = store.schema(rows)
    print(f"{src['name']}: {len(rows)} samples, {sum(r['media'] is not None for r in rows)} with media, {len(sch)} fields")
    for e in sch: print(f"  {e['path']:<28} {e['type']:<12} {e['count']}")
    return rows


if __name__ == '__main__':
    db = store.connect()
    for a in sys.argv[1:]: load(Path(a), db)
