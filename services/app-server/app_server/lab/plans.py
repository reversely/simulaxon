"""One builder per sampling plan type. Each turns finished runs into rows: samples, analyses, results, neural maps.

Builders know plan shapes, never studies:
  matched        units, each seen in condition a and condition b (pairs of items, or the same item with two outcomes)
  leave_one_out  one reference sample and one sample per hidden object
  factorial      units, each seen in every cell of two crossed factors (a moment acted out by two bodies with two motions)
Readouts are TRIBE v2 output units averaged over the seconds the stimulus is on.
"""
from __future__ import annotations
import math
from pathlib import Path
import numpy as np
from . import regions, maps

Z = 1.959964 + 0.841621   # two-sided 5% test at 80% power


def _boot_mean(v: np.ndarray, rng, n=5000) -> list[float]:
    b = [rng.choice(v, len(v)).mean() for _ in range(n)]
    return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]


def pairs_needed(v: np.ndarray) -> int | None:
    m, s = float(v.mean()), float(v.std(ddof=1))
    if m == 0 or not np.isfinite(s): return None
    return int(min(10_000, math.ceil((Z * s / abs(m)) ** 2) + 1))


def matched(store, step, project_id: str, units: list[dict], window: tuple[int, int], labels: tuple[str, str], files: Path, out_url) -> dict:
    """units: [{unit, a: {label, image, clip, preds}, b: {...}}]. Writes samples and the paired, items_needed and time_course analyses."""
    rng = np.random.default_rng(0); lo, hi = window; M = regions.masks()
    A = np.stack([np.load(u['a']['preds']) for u in units]); B = np.stack([np.load(u['b']['preds']) for u in units])   # units x seconds x vertices
    on_a, on_b = A[:, lo:hi].mean(1), B[:, lo:hi].mean(1); D = on_a - on_b
    for i, u in enumerate(units):
        for cond, on in (('a', on_a[i]), ('b', on_b[i])):
            x = u[cond]
            store.create(step, 'sample', {'project_id': project_id, 'index': 2 * i + (cond == 'b'), 'unit': u['unit'], 'condition': labels[cond == 'b'],
                                          'label': x['label'], 'image': out_url(x['image']), 'clip': out_url(x.get('clip')), 'preds': str(x['preds']),
                                          'readout': {r: round(float(on[m].mean()), 4) for r, m in M.items()}},
                         depends_on=[('project', project_id)])
    rows = []
    for r, m in M.items():
        v = D[:, m].mean(1)
        rows.append({'region': r, 'value': round(float(v.mean()), 4), 'interval_95': [round(x, 4) for x in _boot_mean(v, rng)], 'n': len(v),
                     'units_positive': int((v > 0).sum()), 'per_unit': [round(float(x), 4) for x in v],
                     'pairs_needed': pairs_needed(v)})
    rows.sort(key=lambda x: -abs(x['value']))
    mp = maps.render(D.mean(0), 'contrast', files)
    nm = store.create(step, 'neural_map', {'project_id': project_id, 'title': f'{labels[0]} minus {labels[1].lower()}', 'kind': 'contrast', **mp}, depends_on=[('project', project_id)])
    an = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'paired', 'title': f'{labels[0]} minus {labels[1].lower()}', 'window_s': list(window),
                                         'units': 'TRIBE output units, mean over the seconds on screen'}, depends_on=[('project', project_id)])
    store.create(step, 'result', {'analysis_id': an.id, 'project_id': project_id, 'regions': rows, 'map_id': nm.id}, depends_on=[('analysis', an.id)])
    an2 = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'items_needed', 'title': 'Pairs needed',
                                          'method': 'Paired test, two-sided 5%, 80% power, from the mean and spread of pair differences in TRIBE'},
                       depends_on=[('project', project_id)])
    store.create(step, 'result', {'analysis_id': an2.id, 'project_id': project_id,
                                  'regions': [{'region': x['region'], 'pairs_needed': x['pairs_needed'], 'value': x['value'], 'n': x['n']} for x in rows]},
                 depends_on=[('analysis', an2.id)])
    secs = min(A.shape[1], B.shape[1]); tc = []
    for r, m in M.items():
        a_t, b_t = A[:, :secs][:, :, m].mean(2), B[:, :secs][:, :, m].mean(2)
        tc.append({'region': r, 'a': [round(float(x), 4) for x in a_t.mean(0)], 'b': [round(float(x), 4) for x in b_t.mean(0)],
                   'diff_interval_95': [[round(x, 4) for x in _boot_mean(a_t[:, t] - b_t[:, t], rng, 1000)] for t in range(secs)]})
    an3 = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'time_course', 'title': 'Response by second', 'labels': list(labels),
                                          'window_s': list(window)}, depends_on=[('project', project_id)])
    store.create(step, 'result', {'analysis_id': an3.id, 'project_id': project_id, 'seconds': secs, 'regions': tc}, depends_on=[('analysis', an3.id)])
    return {'units': len(units), 'clips': 2 * len(units)}


def leave_one_out(store, step, project_id: str, full: dict, objects: list[dict], window: tuple[int, int], files: Path, out_url) -> dict:
    """full: {label, image, preds}. objects: [{path, label, description, image, preds, pixels, bbox_px}]. Writes the per_object analysis."""
    lo, hi = window; M = regions.masks()
    F = np.load(full['preds'])[lo:hi].mean(0)
    store.create(step, 'sample', {'project_id': project_id, 'index': 0, 'unit': 'full', 'condition': 'Full room', 'label': full['label'],
                                  'image': out_url(full['image']), 'clip': out_url(full.get('clip')), 'preds': str(full['preds']),
                                  'readout': {r: round(float(F[m].mean()), 4) for r, m in M.items()}}, depends_on=[('project', project_id)])
    effects, all_d = [], []
    for k, o in enumerate(objects, 1):
        H = np.load(o['preds'])[lo:hi].mean(0); d = F - H; all_d.append(d)
        store.create(step, 'sample', {'project_id': project_id, 'index': k, 'unit': o['path'], 'condition': 'Hidden', 'label': o['label'],
                                      'image': out_url(o['image']), 'clip': out_url(o.get('clip')), 'preds': str(o['preds']),
                                      'readout': {r: round(float(H[m].mean()), 4) for r, m in M.items()}}, depends_on=[('project', project_id)])
        effects.append({'object': o['path'], 'label': o['label'], 'description': o.get('description', ''), 'pixels': o['pixels'],
                        'share_of_frame': round(o['pixels'] / (832 * 480), 4), 'bbox_px': o['bbox_px'],
                        'regions': {r: round(float(d[m].mean()), 4) for r, m in M.items()},
                        'whole_cortex': round(float(np.abs(d).mean()), 4)})
    vmax = float(np.percentile(np.abs(np.stack(all_d)), 99))
    for e, d in zip(effects, all_d):
        mp = maps.render(d, 'contrast', files, vmax=vmax)
        e['map_id'] = store.create(step, 'neural_map', {'project_id': project_id, 'title': f"Full room minus room without {e['label']}", 'kind': 'contrast', **mp},
                                   depends_on=[('project', project_id)]).id
    px = np.array([e['pixels'] for e in effects], float); wc = np.array([e['whole_cortex'] for e in effects])
    size_r = float(np.corrcoef(px, wc)[0, 1]) if len(effects) > 2 else None
    an = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'per_object', 'title': 'Effect of each object',
                                         'window_s': list(window), 'units': 'Full room minus the room without the object, TRIBE output units'},
                      depends_on=[('project', project_id)])
    full_map = maps.render(F, 'single', files)
    nm = store.create(step, 'neural_map', {'project_id': project_id, 'title': 'Full room', 'kind': 'single', **full_map}, depends_on=[('project', project_id)])
    store.create(step, 'result', {'analysis_id': an.id, 'project_id': project_id, 'objects': effects, 'map_id': nm.id,
                                  'size_correlation': round(size_r, 3) if size_r is not None else None},
                 depends_on=[('analysis', an.id)])
    return {'objects': len(objects), 'clips': len(objects) + 1}


def selection(store, step, project_id: str, items: list[dict], a_region: str, b_region: str, k: int, window: tuple[int, int], files: Path, out_url) -> dict:
    """items: [{id, label, image, preds}]. One sample per stimulus, then the selection analysis over two regions."""
    from .selection import select
    lo, hi = window; M = regions.masks(); ra, rb = [], []
    for i, it in enumerate(items):
        on = np.load(it['preds'])[lo:hi].mean(0); rd = {r: round(float(on[m].mean()), 4) for r, m in M.items()}
        ra.append(rd[a_region]); rb.append(rd[b_region])
        store.create(step, 'sample', {'project_id': project_id, 'index': i, 'unit': it['id'], 'condition': 'Screened', 'label': it['label'],
                                      'image': out_url(it['image']), 'clip': out_url(it.get('clip')), 'preds': str(it['preds']), 'readout': rd},
                     depends_on=[('project', project_id)])
    res = select([it['id'] for it in items], np.array(ra), np.array(rb), k)
    an = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'selection', 'title': f'{a_region} and {b_region}', 'regions': [a_region, b_region],
                                         'window_s': list(window), 'method': 'z-scored readouts; k best per condition against 10,000 random sets'},
                      depends_on=[('project', project_id)])
    store.create(step, 'result', {'analysis_id': an.id, 'project_id': project_id, **res}, depends_on=[('analysis', an.id)])
    return {'units': len(items), 'clips': 0}


def factorial(store, step, project_id: str, units: list[dict], window: tuple[int, int], cells: list[dict], contrasts: list[dict], files: Path, out_url) -> dict:
    """units: [{unit, cells: {cell_id: {label, image, clip, preds}}}]; cells: [{id, label}] in display order;
    contrasts: [{title, weights: {cell_id: w}}], the first one primary. Every unit is seen in every cell. Each contrast
    is written as a paired analysis (its per-unit weighted sum of cell readouts, per region, with a 95% interval), with
    its brain map; the primary one also gets units needed and a time course (its positive cells against its negative)."""
    rng = np.random.default_rng(0); lo, hi = window; M = regions.masks()
    R = {c['id']: np.stack([np.load(u['cells'][c['id']]['preds']) for u in units]) for c in cells}   # units x seconds x vertices
    on = {c: v[:, lo:hi].mean(1) for c, v in R.items()}
    # baselines beside every contrast (plan principle 3): the clips' motion energy and brightness, the same video
    # features TRIBE reads through a random cortex map (no learned mapping), and each region's rank among TRIBE's 360 areas
    stats = {c['id']: np.array([_clip_stats(u['cells'][c['id']]['clip']) for u in units]) for c in cells}   # units x (motion, brightness)
    vj = _vjepa_random_map({c['id']: [u['cells'][c['id']]['preds'] for u in units] for c in cells})
    areas = regions.hcp_areas()
    for i, u in enumerate(units):
        for j, c in enumerate(cells):
            x = u['cells'][c['id']]
            store.create(step, 'sample', {'project_id': project_id, 'index': len(cells) * i + j, 'unit': u['unit'], 'condition': c['label'],
                                          'label': x['label'], 'image': out_url(x['image']), 'clip': out_url(x.get('clip')), 'preds': str(x['preds']),
                                          'readout': {r: round(float(on[c['id']][i][m].mean()), 4) for r, m in M.items()}},
                         depends_on=[('project', project_id)])
    out = []
    for n, ct in enumerate(contrasts):
        D = sum(w * on[c] for c, w in ct['weights'].items())
        area_vals = np.array([D[:, a].mean() for a in areas])
        Dv = sum(w * vj[c] for c, w in ct['weights'].items()) if vj else None
        rows = []
        for r, m in M.items():
            v = D[:, m].mean(1)
            rows.append({'region': r, 'value': round(float(v.mean()), 4), 'interval_95': [round(x, 4) for x in _boot_mean(v, rng)], 'n': len(v),
                         'units_positive': int((v > 0).sum()), 'per_unit': [round(float(x), 4) for x in v], 'pairs_needed': pairs_needed(v),
                         'area_rank_pct': round(float((area_vals < v.mean()).mean() * 100), 1),
                         'vjepa_random_map': round(float(Dv[:, m].mean()), 4) if Dv is not None else None})
        def row(name, v, units_txt):
            return {'name': name, 'value': round(float(v.mean()), 4), 'interval_95': [round(x, 4) for x in _boot_mean(v, rng)], 'units_positive': int((v > 0).sum()), 'n': len(v), 'units': units_txt}
        baselines = [row('Whole cortex', D.mean(1), 'TRIBE units'),
                     row('Motion energy of the clips', sum(w * stats[c][:, 0] for c, w in ct['weights'].items()), 'grey levels per frame'),
                     row('Brightness of the clips', sum(w * stats[c][:, 1] for c, w in ct['weights'].items()), 'grey levels')]
        rows.sort(key=lambda x: -abs(x['value']))
        mp = maps.render(D.mean(0), 'contrast', files)
        nm = store.create(step, 'neural_map', {'project_id': project_id, 'title': ct['title'], 'kind': 'contrast', **mp}, depends_on=[('project', project_id)])
        an = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'paired', 'title': ct['title'], 'window_s': list(window), 'weights': ct['weights'],
                                             'units': 'TRIBE units, mean of seconds 1 to 9'}, depends_on=[('project', project_id)])
        store.create(step, 'result', {'analysis_id': an.id, 'project_id': project_id, 'regions': rows, 'map_id': nm.id, 'baselines': baselines,
                                      'baselines_note': 'Each region also carries its rank among the 360 HCP areas TRIBE reports, and the same contrast from V-JEPA 2 features through a fixed random cortex map'},
                     depends_on=[('analysis', an.id)])
        out.append(an.id)
        if n == 0:
            an2 = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'items_needed', 'title': 'Moments needed',
                                                  'method': 'Paired test, two-sided 5%, 80% power, from the mean and spread of per-moment values in TRIBE'},
                               depends_on=[('project', project_id)])
            store.create(step, 'result', {'analysis_id': an2.id, 'project_id': project_id,
                                          'regions': [{'region': x['region'], 'pairs_needed': x['pairs_needed'], 'value': x['value'], 'n': x['n']} for x in rows]},
                         depends_on=[('analysis', an2.id)])
            pos = [c for c, w in ct['weights'].items() if w > 0]; neg = [c for c, w in ct['weights'].items() if w < 0]
            lab = {c['id']: c['label'] for c in cells}; secs = min(v.shape[1] for v in R.values()); tc = []
            for r, m in M.items():
                a_t = np.mean([R[c][:, :secs][:, :, m].mean(2) for c in pos], 0); b_t = np.mean([R[c][:, :secs][:, :, m].mean(2) for c in neg], 0)
                tc.append({'region': r, 'a': [round(float(x), 4) for x in a_t.mean(0)], 'b': [round(float(x), 4) for x in b_t.mean(0)],
                           'diff_interval_95': [[round(x, 4) for x in _boot_mean(a_t[:, t] - b_t[:, t], rng, 1000)] for t in range(secs)]})
            an3 = store.create(step, 'analysis', {'project_id': project_id, 'kind': 'time_course', 'title': 'Response by second',
                                                  'labels': [' and '.join(lab[c] for c in pos), ' and '.join(lab[c] for c in neg)], 'window_s': list(window)},
                               depends_on=[('project', project_id)])
            store.create(step, 'result', {'analysis_id': an3.id, 'project_id': project_id, 'seconds': secs, 'regions': tc}, depends_on=[('analysis', an3.id)])
    return {'units': len(units), 'clips': len(units) * len(cells), 'analyses': out}


def _clip_stats(mp4) -> tuple[float, float]:
    """Mean absolute frame-to-frame change and mean brightness of a clip, in grey levels, at 240 x 135."""
    import subprocess
    raw = subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', str(mp4), '-vf', 'scale=240:135', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'], capture_output=True).stdout
    v = np.frombuffer(raw, np.uint8).reshape(-1, 135, 240).astype(np.float32)
    return float(np.abs(np.diff(v, axis=0)).mean()), float(v.mean())


def _vjepa_random_map(preds: dict) -> dict | None:
    """The V-JEPA 2 features TRIBE read for each clip (its cache), averaged over time, through a fixed random projection
    onto the 20,484 vertices: per cell, units x vertices. None when any clip's features are missing."""
    import sys
    from pathlib import Path
    from ..home import HOME; fe = HOME / 'feasibility'
    sys.path.insert(0, str(fe / 'egobody')); sys.path.insert(0, str(fe / 'tribev2-src'))
    from donoso_signals import vjepa_index
    vidx = vjepa_index(); feats = {}
    for c, ps in preds.items():
        rows = []
        for p in ps:
            key = str(Path(str(p).replace('.tribe.npy', '.mp4')).resolve())
            if key not in vidx: return None
            folder, dd = vidx[key]
            a = np.array(np.memmap(folder / dd['filename'], dtype=dd['dtype'], mode='r', offset=dd['offset'], shape=tuple(dd['shape'])), dtype=np.float32)
            L = a.shape[1]; k = np.unique([int(i * (L - 1)) for i in (0.5, 0.75, 1.0)]).tolist(); k[-1] += 1
            rows.append(np.concatenate([a[:, l1:l2].mean(1) for l1, l2 in zip(k[:-1], k[1:])], axis=1).mean(0))
        feats[c] = np.stack(rows)
    d = next(iter(feats.values())).shape[1]
    Mp = np.random.default_rng(1800).standard_normal((d, 20484)).astype(np.float32) / np.sqrt(d)
    return {c: f @ Mp for c, f in feats.items()}


class Deferred:
    """Stands in for the store while a builder computes: each create is recorded with an id made the way the store
    makes them, then all are written in one go under the store's lock, so a long computation never holds the store
    (a two-by-two's baselines and maps take several seconds; holding the lock froze every other call meanwhile)."""
    def __init__(self): self.ops = []

    def create(self, step, kind, data, id=None, depends_on=()):
        import types, uuid
        id = id or f'{kind}_' + uuid.uuid4().hex[:10]; self.ops.append((kind, data, id, list(depends_on)))
        return types.SimpleNamespace(id=id, data=data)

    def apply(self, store, step):
        for kind, data, id, dep in self.ops: store.create(step, kind, data, id=id, depends_on=dep)
