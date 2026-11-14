"""Datasets of samples with free fields, in DuckDB. Modelled on FiftyOne (research/interface_rebuild.md).

A sample: dataset, id, group and slice (several samples sharing a group are one unit, one slice each), one media file,
and a dict of fields. The schema is never declared: it is read off the values, the way FiftyOne infers fields
(fiftyone/core/odm/utils.py:392). Every field records the file and key it came from, so any value on screen traces to
its source. A value with `_kind: "track"` is a time series kept in its file and read on demand.
"""
from __future__ import annotations
import json
from pathlib import Path
import duckdb
from .config import DATA

DB = DATA / 'log' / 'datasets.duckdb'


def connect(path: Path = DB):
    path.parent.mkdir(parents=True, exist_ok=True)
    db = duckdb.connect(str(path))
    db.execute("""create table if not exists datasets (name text primary key, source json, loaded_at timestamp default now())""")
    db.execute("""create table if not exists samples (dataset text, id text, grp text, slice text, media text, media_type text,
                  fields json, sources json, primary key (dataset, id))""")
    db.execute('alter table samples add column if not exists ord integer')   # load order: samples keep the order of their source
    return db


def replace_dataset(db, name: str, source: dict, samples: list[dict]):
    """Writes a dataset from scratch: its source description (how it was loaded) and every sample."""
    db.execute('begin')
    db.execute('delete from samples where dataset = ?', [name]); db.execute('delete from datasets where name = ?', [name])
    db.execute('insert into datasets (name, source) values (?, ?)', [name, json.dumps(source)])
    db.executemany('insert into samples (dataset, id, grp, slice, media, media_type, fields, sources, ord) values (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                   [[name, s['id'], s.get('group'), s.get('slice'), s.get('media'), s.get('media_type'),
                     json.dumps(s['fields']), json.dumps(s['sources']), i] for i, s in enumerate(samples)])
    db.execute('commit')


def datasets(db):
    rows = db.execute('select d.name, d.source, d.loaded_at, count(s.id) from datasets d left join samples s on s.dataset = d.name group by all order by d.name').fetchall()
    return [{'name': n, 'source': json.loads(src), 'loaded_at': str(t), 'samples': c} for n, src, t, c in rows]


def samples(db, name: str) -> list[dict]:
    rows = db.execute('select id, grp, slice, media, media_type, fields, sources from samples where dataset = ? order by ord, id', [name]).fetchall()
    return [{'id': i, 'group': g, 'slice': sl, 'media': m, 'media_type': mt, 'fields': json.loads(f), 'sources': json.loads(src)}
            for i, g, sl, m, mt, f, src in rows]


# ---------------------------------------------------------------- schema, read off the values
def value_type(v) -> str | None:
    if v is None: return None
    if isinstance(v, bool): return 'bool'
    if isinstance(v, int): return 'int'
    if isinstance(v, float): return 'float'
    if isinstance(v, str): return 'str'
    if isinstance(v, dict) and v.get('_kind') == 'track': return 'track'
    if isinstance(v, list):
        kinds = {value_type(x) for x in v} - {None}
        if kinds <= {'int', 'float'} and kinds: return 'list<float>' if 'float' in kinds else 'list<int>'
        return 'list<str>' if kinds == {'str'} else 'list'
    if isinstance(v, dict): return 'dict'
    return 'other'


def flatten(fields: dict, prefix: str = '') -> dict:
    """Nested dicts become dotted paths; tracks stay whole."""
    out = {}
    for k, v in fields.items():
        if isinstance(v, dict) and v.get('_kind') != 'track': out.update(flatten(v, f'{prefix}{k}.'))
        else: out[f'{prefix}{k}'] = v
    return out


def schema(rows: list[dict]) -> list[dict]:
    """Every field path, its type (or types, if the values disagree) and how many samples have it."""
    seen: dict[str, dict] = {}
    for s in rows:
        for p, v in flatten(s['fields']).items():
            t = value_type(v); e = seen.setdefault(p, {'path': p, 'types': set(), 'count': 0})
            if t: e['types'].add(t); e['count'] += 1
    out = []
    for p, e in seen.items():
        types = sorted(e['types']); out.append({'path': p, 'type': types[0] if len(types) == 1 else 'mixed', 'types': types, 'count': e['count']})
    return sorted(out, key=lambda x: x['path'])
