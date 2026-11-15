"""The files a run's results download as (#20): each table as CSV, each contrast over the whole cortex as raw fsaverage5
values (.npy) and as the four rendered views (PNG), the 360 HCP areas for each contrast, the run settings as JSON, and
everything as one zip. Built from the store and the trials' saved predictions, so a download matches the record rather
than the screen.

The owner: "Downloadable, so in a dropdown, not taking over the whole page."
"""
from __future__ import annotations
import csv, io, json, re, zipfile
from pathlib import Path
import numpy as np

from . import regions, templates
from .ingest import FILES

_cache: dict[tuple, list[dict]] = {}


def words(name) -> str:
    """A stored contrast or condition name as words (#39), as the page shows it (api.ts words): faces_vs_objects reads
    "Faces against objects"; a name with a space is the project's own wording."""
    s = str(name or '')
    if '_' not in s or re.search(r'\s', s): return s
    w = re.sub(r'_+', ' ', re.sub(r'_(vs|versus|minus|against)_', ' against ', s, flags=re.I)).strip()
    return w[:1].upper() + w[1:]


def _slug(s: str) -> str:
    return re.sub(r'[^A-Za-z0-9]+', '_', s).strip('_')[:60] or 'contrast'


def contrast_maps(store, project_id: str) -> list[dict]:
    """Each paired contrast as a per-vertex map: the weighted condition means of the trials' predictions over the
    analysis's read-out window. Cached per set of analyses, so a rerun recomputes and a page reload does not."""
    P = store.get('project', project_id).data
    analyses = [r for r in store.list('analysis') if r.data.get('project_id') == project_id and r.data.get('kind') == 'paired']
    key = (project_id, tuple(f'{a.id}:{a.version}' for a in analyses))
    if key in _cache: return _cache[key]
    samples = sorted((r.data for r in store.list('sample') if r.data.get('project_id') == project_id), key=lambda d: d.get('index', 0))
    conds = list(dict.fromkeys(x['condition'] for x in samples))
    cells = {}
    if P.get('template_id'):
        try: cells = {c['id']: c['label'] for c in (templates.get(P['template_id']).get('cells') or [])}
        except Exception: cells = {}
    loaded: dict[str, np.ndarray] = {}
    def pred(p):
        if p not in loaded: loaded[p] = np.load(p)
        return loaded[p]
    out = []
    for a in analyses:
        w = a.data.get('weights') or ({conds[0]: 1, conds[1]: -1} if len(conds) == 2 else None)   # matched plans: first minus second
        if not w: continue
        w = {cells.get(k, k): v for k, v in w.items()}
        lo, hi = (a.data.get('window_s') or [0, None])[:2]
        means = {}
        for c in w:
            xs = [pred(x['preds'])[lo:hi].mean(0) for x in samples if x['condition'] == c and x.get('preds') and Path(x['preds']).exists()]
            if xs: means[c] = np.mean(xs, 0)
        if len(means) != len(w): continue
        D = sum(wt * means[c] for c, wt in w.items()).astype(np.float32)
        res = next((r for r in store.list('result') if r.data.get('analysis_id') == a.id), None)
        views = (store.get('neural_map', res.data['map_id']).data.get('views') if res and res.data.get('map_id') and store.get('neural_map', res.data['map_id']) else None) or {}
        out.append({'title': a.data.get('title'), 'weights': w, 'window_s': [lo, hi], 'map': D, 'views': views})
    _cache[key] = out
    return out


def areas(D: np.ndarray) -> list[dict]:
    """The contrast in each of the 360 HCP-MMP1 areas, highest first, with its rank."""
    vals = [(n, float(D[m].mean())) for n, m in zip(regions.hcp_names(), regions.hcp_areas())]
    vals.sort(key=lambda x: -x[1])
    return [{'area': n, 'value': round(v, 5), 'rank': i + 1} for i, (n, v) in enumerate(vals)]


def _csv(header: list[str], rows: list[list]) -> bytes:
    f = io.StringIO(); w = csv.writer(f); w.writerow(header); w.writerows(rows); return f.getvalue().encode()


def files(record: dict, maps: list[dict]) -> dict[str, bytes | Path]:
    """Every file the Download menu offers, by name: bytes, or a path to an existing rendered view."""
    c = record['contrasts']; t = record['trials']; regs = record['regions_read']
    out: dict[str, bytes | Path] = {
        'table1_regions_and_contrasts.csv': _csv(['contrast', 'region', 'named_by', 'tribe_value', 'ci95_low', 'ci95_high', 'n', 'n_by_condition', 'units_above_zero',
                                                 'rank_among_360_areas_pct', 'shuffled_labels_ci95_low', 'shuffled_labels_ci95_high', 'shuffles_at_least_as_far',
                                                 'video_features_random_map', 'window_start_s', 'window_end_s'],
                                                [[words(r['contrast']), r['region'], r.get('named_by') or '', r['value'], r['ci_low'], r['ci_high'], r['n'],
                                                  '; '.join(f'{words(k)}: {v}' for k, v in (r.get('n_by_condition') or {}).items()), r['units_positive'], r['area_rank_pct'],
                                                  r['shuffled_low'], r['shuffled_high'], r['shuffled_at_least_as_far'], r['vjepa_random_map'],
                                                  (r.get('window_s') or [None, None])[0], (r.get('window_s') or [None, None])[1]] for r in c]),
        'table2_trials.csv': _csv(['trial', 'unit', 'condition', 'label', 'source', 'clip', *regs],
                                  [[x['index'], x['unit'], words(x['condition']), x['label'], x.get('origin') or '', x.get('clip') or '', *[x['readout'].get(r) for r in regs]] for x in t]),
        'run_settings.json': json.dumps({k: record[k] for k in ('project', 'made', 'stimuli', 'regions_named', 'missing')}, indent=1, default=str).encode(),
    }
    if maps:
        out['fig3_areas_by_contrast.csv'] = _csv(['contrast', 'area', 'value', 'rank'], [[words(m['title']), a['area'], a['value'], a['rank']] for m in maps for a in areas(m['map'])])
    for i, m in enumerate(maps, 1):
        buf = io.BytesIO(); np.save(buf, m['map']); out[f'fig2_map{i}_{_slug(m["title"])}.npy'] = buf.getvalue()
        for v, p in (m.get('views') or {}).items():
            if (FILES / p).exists(): out[f'fig2_map{i}_{_slug(m["title"])}_{v}.png'] = FILES / p
    return out


def zipped(fs: dict[str, bytes | Path], folder: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in fs.items():
            if isinstance(data, Path): z.write(data, f'{folder}/{name}')
            else: z.writestr(f'{folder}/{name}', data)
    return buf.getvalue()
