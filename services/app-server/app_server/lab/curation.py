"""Dataset curation (#22): every file in a dataset becomes an item in the lab's store, with fields read off the file, its
folder and any table beside it, plus tags; views are a dataset and a list of stages, and saved views can be a condition
of an experiment. Every change is a step, so it can be undone. The media stay in the dataset's folder.

A stage is plain data, the same for the page and the agent:

  {"stage": "match",   "path": "category", "op": "==", "value": "house"}   ops: == != < <= > >= in between contains
  {"stage": "exists",  "path": "luminance", "present": true}
  {"stage": "tagged",  "tag": "keep"}                       (or "present": false for items without the tag)
  {"stage": "sort_by", "path": "luminance", "reverse": false}
  {"stage": "group_by","path": "category"}                  items ordered by group, each with its group's size
  {"stage": "take",    "n": 20, "seed": 0}
  {"stage": "exclude", "ids": ["item_..."]}
  {"stage": "select",  "ids": ["item_..."]}

Fields: file, folder, category (the folder an item sits in), media_type, size_mb, width, height, and for images
luminance and contrast (mean and standard deviation of grey level, 0 to 255, on a 256 px copy); for video duration_s,
fps and frames; for a recording (a folder with recording.json, lab/recording.py) streams, n_streams, has_tribe
and duration_s; sha (content hash) and duplicates (how many other items have the same bytes). Columns of a CSV beside the
files whose first matching column names the files become fields too. Each field records where it came from.

Ported from visual-cortex-lab backend/vcl/data (views and schema) onto this store.
"""
from __future__ import annotations
import csv, hashlib, json, math, random, shutil, subprocess, threading, time
from pathlib import Path

from . import datasets as dsets

MEDIA = {'image', 'video', 'audio'}


# ---------------------------------------------------------------- fields read off a file
def _video_meta(p: Path) -> dict:
    if not shutil.which('ffprobe'): return {}
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,avg_frame_rate,nb_frames:format=duration',
                            '-of', 'json', str(p)], capture_output=True, text=True, timeout=30)
        d = json.loads(r.stdout or '{}'); s = (d.get('streams') or [{}])[0]; fr = s.get('avg_frame_rate', '0/1').split('/')
        fps = float(fr[0]) / float(fr[1]) if len(fr) == 2 and float(fr[1]) else None
        out = {'width': s.get('width'), 'height': s.get('height'), 'duration_s': round(float(d.get('format', {}).get('duration', 0)), 3) or None,
               'fps': round(fps, 3) if fps else None, 'frames': int(s['nb_frames']) if str(s.get('nb_frames', '')).isdigit() else None}
        return {k: v for k, v in out.items() if v is not None}
    except Exception:
        return {}


def _image_meta(p: Path) -> dict:
    try:
        from PIL import Image, ImageStat
        with Image.open(p) as im:
            w, h = im.size; g = im.convert('L'); g.thumbnail((256, 256)); st = ImageStat.Stat(g)
            return {'width': w, 'height': h, 'luminance': round(st.mean[0], 2), 'contrast': round(st.stddev[0], 2)}
    except Exception:
        return {}


def read_fields(root: Path, p: Path) -> tuple[dict, dict]:
    """The fields of one file and, for each, where it came from."""
    rel = p.relative_to(root).as_posix(); kind = dsets.kind_of(p.name)
    f = {'file': rel, 'folder': p.parent.relative_to(root).as_posix() if p.parent != root else '', 'media_type': kind, 'size_mb': round(p.stat().st_size / 1e6, 4)}
    src = {'file': 'path in the dataset', 'folder': 'path in the dataset', 'media_type': 'file extension', 'size_mb': 'file size'}
    if p.parent != root: f['category'] = p.parent.name; src['category'] = 'the folder the file is in'
    if kind == 'image':
        m = _image_meta(p); f.update(m); src.update({k: 'read from the image (grey level on a 256 px copy)' if k in ('luminance', 'contrast') else 'read from the image' for k in m})
    elif kind == 'video':
        m = _video_meta(p); f.update(m); src.update({k: 'ffprobe' for k in m})
    h = hashlib.blake2b(digest_size=12)
    with open(p, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''): h.update(chunk)
    f['sha'] = h.hexdigest(); src['sha'] = 'content hash (BLAKE2b) of the bytes'
    return f, src


def _sidecars(root: Path, rels: set[str]) -> tuple[dict, dict]:
    """Columns of CSV files in the dataset whose first column that names the files (by path or file name) is the key."""
    by_name = {Path(r).name: r for r in rels}; extra: dict[str, dict] = {}; src: dict[str, str] = {}
    for c in sorted(root.rglob('*.csv'))[:20]:
        try: rows = list(csv.DictReader(open(c, newline='', encoding='utf-8', errors='replace')))
        except Exception: continue
        if not rows: continue
        key = next((k for k in rows[0] if k and sum(1 for r in rows[:200] if (r.get(k) or '').strip() in rels or Path((r.get(k) or '').strip()).name in by_name) > len(rows[:200]) / 2), None)
        if not key: continue
        for r in rows:
            v = (r.get(key) or '').strip(); rel = v if v in rels else by_name.get(Path(v).name)
            if not rel: continue
            for k, x in r.items():
                if not k or k == key: continue
                x = (x or '').strip()
                try: val = int(x) if x.lstrip('-').isdigit() else float(x)
                except ValueError: val = x if x else None
                if val is not None: extra.setdefault(rel, {})[k] = val; src[k] = f'column {k} of {c.relative_to(root).as_posix()}'
    return extra, src


def index(did: str, on_event=lambda m: None) -> list[dict]:
    """Every media file of a dataset with its fields, ready to store. Runs outside the store's lock."""
    root = dsets.dataset_dir(did)
    if not root.exists(): raise ValueError(f'no dataset {did} on this machine')
    from . import recording
    recs = sorted({m.parent for m in root.rglob(recording.MANIFEST)})   # a recording is one item; its files are not items of their own (#23)
    files = sorted(p for p in root.rglob('*') if p.is_file() and dsets.kind_of(p.name) in MEDIA and not p.name.endswith('.part') and not any(p.is_relative_to(r) for r in recs))
    rels = {p.relative_to(root).as_posix() for p in files} | {r.relative_to(root).as_posix() for r in recs}; extra, xsrc = _sidecars(root, rels)
    out = []; t0 = time.time()
    for i, p in enumerate(files):
        f, src = read_fields(root, p); rel = f['file']
        if rel in extra: f.update(extra[rel]); src.update({k: xsrc[k] for k in extra[rel]})
        out.append({'id': 'item_' + hashlib.sha1(f'{did}/{rel}'.encode()).hexdigest()[:12], 'dataset_id': did, 'path': rel, 'media_type': f['media_type'],
                    'fields': f, 'sources': src, 'ord': i})
        if i % 50 == 0 or i == len(files) - 1: on_event({'dataset': did, 'indexed': i + 1, 'total': len(files), 'seconds': round(time.time() - t0, 1)})
    for r in recs:
        try: f, src = recording.fields(root, r)
        except Exception as e: on_event({'dataset': did, 'skipped': r.relative_to(root).as_posix(), 'reason': str(e)}); continue
        rel = f['file']; video = next(s['file'] for s in recording.read(r)['streams'] if s['kind'] == 'video')
        if rel in extra: f.update(extra[rel]); src.update({k: xsrc[k] for k in extra[rel]})
        out.append({'id': 'item_' + hashlib.sha1(f'{did}/{rel}'.encode()).hexdigest()[:12], 'dataset_id': did, 'path': rel, 'media_type': 'recording',
                    'fields': f, 'sources': src, 'ord': len(out), 'video': f'{rel}/{video}'})
    counts: dict[str, int] = {}
    for x in out: counts[x['fields']['sha']] = counts.get(x['fields']['sha'], 0) + 1
    for x in out: x['fields']['duplicates'] = counts[x['fields']['sha']] - 1; x['sources']['duplicates'] = 'other items with the same content hash'
    return out


# ---------------------------------------------------------------- schema, read off the values
def value_type(v) -> str | None:
    if v is None: return None
    if isinstance(v, bool): return 'bool'
    if isinstance(v, int): return 'int'
    if isinstance(v, float): return 'float'
    if isinstance(v, str): return 'str'
    if isinstance(v, list): return 'list'
    return 'other'


def schema(items: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for s in items:
        for p, v in {**s['fields'], 'tags': s.get('tags') or None}.items():
            t = value_type(v); e = seen.setdefault(p, {'path': p, 'types': set(), 'count': 0})
            if t: e['types'].add(t); e['count'] += 1
    out = [{'path': p, 'type': sorted(e['types'])[0] if len(e['types']) == 1 else ('mixed' if e['types'] else 'none'), 'count': e['count']} for p, e in seen.items()]
    return sorted(out, key=lambda x: x['path'])


# ---------------------------------------------------------------- views
def get(s: dict, path: str):
    return s.get('tags') if path == 'tags' else s['fields'].get(path)


def test(v, op: str, x) -> bool:
    if v is None: return False
    try:
        if op == '==': return v == x
        if op == '!=': return v != x
        if op == '<': return v < x
        if op == '<=': return v <= x
        if op == '>': return v > x
        if op == '>=': return v >= x
        if op == 'in': return v in x
        if op == 'between': return x[0] <= v <= x[1]
        if op == 'contains': return str(x).lower() in str(v).lower()
    except TypeError:
        return False
    raise ValueError(f'unknown op {op}; use == != < <= > >= in between contains')


def text(v) -> str:
    return ('true' if v else 'false') if isinstance(v, bool) else str(v)


def describe(st: dict) -> str:
    """A stage in words, for the view bar."""
    k = st.get('stage')
    if k == 'match':
        v = st['value']; v = f'{text(v[0])} to {text(v[1])}' if st['op'] == 'between' else ', '.join(map(text, v)) if st['op'] == 'in' else text(v)
        word = {'==': 'is', '!=': 'is not', 'contains': 'contains', 'in': 'is one of', 'between': 'from'}.get(st['op'], st['op'])
        return f"{st['path']} {word} {v}"
    if k == 'exists': return f"{st['path']} {'present' if st.get('present', True) else 'missing'}"
    if k == 'tagged': return f"tagged {st['tag']}" if st.get('present', True) else f"not tagged {st['tag']}"
    if k == 'sort_by': return f"sorted by {st['path']}{', largest first' if st.get('reverse') else ''}"
    if k == 'group_by': return f"grouped by {st['path']}"
    if k == 'take': return f"{st['n']} at random (seed {st.get('seed', 0)})"
    if k == 'exclude': return f"without {len(st['ids'])} picked"
    if k == 'select': return f"only {len(st['ids'])} picked"
    return str(k)


def apply(items: list[dict], stages: list[dict], emb: tuple[list[str], 'object'] | None = None) -> tuple[list[dict], list[dict]]:
    """The items after every stage, and the count after each stage. emb: (item ids, unit vectors) for similar_to."""
    trail = [{'stage': 'dataset', 'text': 'all items', 'count': len(items)}]
    for st in stages or []:
        k = st.get('stage')
        if k == 'similar_to':   # most like one item, by V-JEPA 2 vectors (embedding_create); items without a vector go last
            if emb is None: raise ValueError('no embeddings for this dataset yet: run embedding_create first')
            import numpy as np
            row = {i: n for n, i in enumerate(emb[0])}
            if st['id'] not in row: raise ValueError(f"item {st['id']} has no embedding")
            sims = np.asarray(emb[1], np.float32) @ np.asarray(emb[1][row[st['id']]], np.float32)
            have = [{**s, 'fields': {**s['fields'], 'similarity': round(float(sims[row[s['id']]]), 4)}} for s in items if s['id'] in row]
            items = sorted(have, key=lambda s: -s['fields']['similarity']) + [s for s in items if s['id'] not in row]
            trail.append({'stage': k, 'text': f"most like {st.get('label') or st['id']}", 'count': len(items)}); continue
        if k == 'match': items = [s for s in items if test(get(s, st['path']), st['op'], st['value'])]
        elif k == 'exists': items = [s for s in items if (get(s, st['path']) not in (None, [])) == st.get('present', True)]
        elif k == 'tagged': items = [s for s in items if (st['tag'] in (s.get('tags') or [])) == st.get('present', True)]
        elif k == 'sort_by':
            have = [s for s in items if get(s, st['path']) is not None]; miss = [s for s in items if get(s, st['path']) is None]
            items = sorted(have, key=lambda s: get(s, st['path']), reverse=st.get('reverse', False)) + miss
        elif k == 'group_by':
            groups: dict = {}
            for s in items: groups.setdefault(text(get(s, st['path'])), []).append(s)
            items = [{**s, 'group': {'value': g, 'size': len(v)}} for g, v in sorted(groups.items()) for s in v]
        elif k == 'take': items = random.Random(st.get('seed', 0)).sample(items, min(int(st['n']), len(items)))
        elif k == 'exclude': ids = set(st['ids']); items = [s for s in items if s['id'] not in ids]
        elif k == 'select': ids = set(st['ids']); items = [s for s in items if s['id'] in ids]
        else: raise ValueError(f'unknown stage {k}; use match, exists, tagged, sort_by, group_by, take, exclude or select')
        trail.append({'stage': k, 'text': describe(st), 'count': len(items)})
    return items, trail


def facets(items: list[dict], sch: list[dict], bins: int = 24) -> dict:
    """Per field, over the items in the view: numbers a histogram with its edges, the rest value counts."""
    out = {}
    for e in sch:
        p, t = e['path'], e['type']
        if p in ('file', 'sha'): continue
        vals = [get(s, p) for s in items]
        if t == 'list': vals = [x for v in vals if isinstance(v, list) for x in v]; t = 'str'
        present = [v for v in vals if v is not None]
        f = {'count': len(present), 'missing': max(0, len(items) - len(present)) if e['type'] != 'list' else 0}
        if t in ('int', 'float') and present:
            lo, hi = min(present), max(present); w = (hi - lo) / bins or 1; h = [0] * bins
            for v in present: h[min(int((v - lo) / w), bins - 1)] += 1
            f.update(kind='numeric', min=lo, max=hi, edges=[lo + i * w for i in range(bins + 1)], hist=h)
        elif t in ('str', 'bool'):
            c: dict = {}
            for v in present: c[text(v)] = c.get(text(v), 0) + 1
            f.update(kind='values', values=sorted(c.items(), key=lambda kv: -kv[1])[:40], distinct=len(c))
        else:
            f.update(kind=t)
        out[p] = f
    return out


def public(s: dict) -> dict:
    """An item as the page and the agent see it: its media under /files, fields, tags and where each field came from."""
    from urllib.parse import quote
    rel = quote(f"{s['dataset_id']}/{s['path']}")
    if s['media_type'] == 'recording':   # the manifest, and the first video's frame as the thumbnail (#23)
        vid = quote(f"{s['dataset_id']}/{s.get('video', '')}")
        return {'id': s['id'], 'dataset_id': s['dataset_id'], 'path': s['path'], 'media_type': 'recording', 'media': f'/datasets/media/{rel}/recording.json',
                'thumb': f'/datasets/thumb/{vid}' if s.get('video') else None, 'fields': s['fields'], 'tags': s.get('tags') or [], 'sources': s.get('sources') or {},
                **({'group': s['group']} if 'group' in s else {})}
    return {'id': s['id'], 'dataset_id': s['dataset_id'], 'path': s['path'], 'media_type': s['media_type'], 'media': f'/datasets/media/{rel}',
            'thumb': f'/datasets/thumb/{rel}' if s['media_type'] in ('image', 'video') else None, 'fields': s['fields'],
            'tags': s.get('tags') or [], 'sources': s.get('sources') or {}, **({'group': s['group']} if 'group' in s else {})}
