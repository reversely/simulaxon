"""source_search (design spec §6.4, implementation spec §4): a sequence of filters over a source index.

Filters are data, not code, so nothing here knows about food:
    {"label": "Under 30 cm", "field": "size_m", "op": "<", "value": 0.30, "why": "{size_m:.2f} m"}
Each step returns its query, the count kept, and every removed row with a reason built from "why".
"""
from __future__ import annotations
from pathlib import Path
import numpy as np, pandas as pd

OPS = {'<': np.less, '<=': np.less_equal, '>': np.greater, '>=': np.greater_equal, '==': np.equal, '!=': np.not_equal}
from .home import HOME
INDEXES = HOME / 'feasibility' / 'indexes'


def load_source(source_id: str) -> pd.DataFrame:
    if source_id == 'palatial':
        cat = pd.read_parquet(INDEXES / 'palatial/catalog.parquet'); emb = pd.read_parquet(INDEXES / 'palatial/embeddings.parquet')
        d = cat.merge(emb[['record_id', 'p_food', 'p_text', 'has_text', 'label_mismatch']], left_on='catalog_id', right_on='record_id')
        d['size_m'] = d[['bounds_x_m', 'bounds_y_m', 'bounds_z_m']].max(axis=1)
        return d.rename(columns={'catalog_id': 'id'})
    if source_id == 'sage10k':
        return pd.read_parquet(INDEXES / 'sage10k/scenes.parquet').rename(columns={'record_id': 'id'})
    if source_id == 'simready':
        return pd.read_parquet(INDEXES / 'simready/records.parquet').rename(columns={'record_id': 'id'})
    raise KeyError(f'no source {source_id}')


def _mask(d: pd.DataFrame, f: dict) -> np.ndarray:
    col, op, v = d[f['field']], f['op'], f['value']
    if op == 'in': return col.isin(v).values
    if op == 'not in': return ~col.isin(v).values
    if op == 'contains': return col.astype(str).str.contains(v, case=False, regex=False).values
    if op == 'not contains': return ~col.astype(str).str.contains(v, case=False, regex=False).values
    if op == 'any contains': return col.apply(lambda xs: any(v in str(x) for x in (xs if isinstance(xs, (list, np.ndarray)) else [xs]))).values
    if op in OPS: return OPS[op](col.values.astype(float), float(v))
    raise ValueError(f'unknown operator {op}')


def run(d: pd.DataFrame, filters: list[dict], name_field: str = 'name', max_removed: int = 50) -> dict:
    steps = [{'label': f'Search {len(d):,} records', 'query': 'all', 'kept': len(d), 'removed': 0, 'removed_rows': []}]
    cur = d
    for f in filters:
        keep = _mask(cur, f)
        gone = cur[~keep]
        rows = [{'id': r['id'], 'name': r.get(name_field), 'reason': f.get('why', '').format(**{k: (r[k] if not isinstance(r[k], float) or not np.isnan(r[k]) else None) for k in r.index}) if f.get('why') else ''}
                for _, r in gone.head(max_removed).iterrows()]
        q = f"{f['field']} {f['op']} {f['value']!r}"
        steps.append({'label': f.get('label', q), 'query': q, 'kept': int(keep.sum()), 'removed': int((~keep).sum()), 'removed_rows': rows})
        cur = cur[keep]
    return {'steps': steps, 'ids': cur['id'].tolist()}
