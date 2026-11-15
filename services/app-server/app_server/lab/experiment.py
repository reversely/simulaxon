"""Experiments set up from data, for any paper: conditions as lists of stimulus files, trial timing, regions, contrasts and
the paper's reported result. A run makes one clip per trial (TRIBE reads a whole clip at once, so trials are never joined,
and every trial has the same length and structure), TRIBE reads each, and every contrast comes back with its baselines
and match or no match against what the paper reported. Nothing here is written for one paper or one dataset.

Every stimulus keeps its origin: a fetched dataset (its source and licence), Isaac Sim (the render it came from), or a
file a person added; a condition can pass its stimuli through Cosmos, and then the origin says so and what it came from.
Samples carry it, so the interface shows where each stimulus came from.
"""
from __future__ import annotations
import fnmatch, hashlib, json, math, re, shutil, subprocess, threading
from pathlib import Path
import numpy as np
from . import datasets, maps, plans, regions
from .ingest import DATA, FILES

CLIPS = FILES / 'experiments' / 'clips'
SIZE = 512   # square frames: TRIBE's video model sees only a centre square, so nothing is cropped away
GREY = '0x808080'
IMAGE, VIDEO = ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.gif', '.webp'), ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg')
TRIBE_S_PER_SECOND = 2.2   # measured 2026-11-14: about 26 s for a 12 s clip, about 65 s for a 30 s clip
CW, CH = 832, 480   # Cosmos Sim-Transfer's trained frame (16:9 bucket); it refuses inputs it would distort by over 3%


def _files_of(cond: dict) -> tuple[list[Path], dict]:
    """A condition's stimulus files and their origin. Files come from a fetched dataset (dataset_id plus patterns relative
    to it), or from paths under the lab's data folder (Isaac Sim renders under files/, or files a person added)."""
    pats = cond.get('files') or []
    if isinstance(pats, str): pats = [pats]
    if cond.get('dataset_id'):
        root = datasets.HERE / cond['dataset_id']
        if not root.exists(): raise ValueError(f"condition {cond.get('name')}: no fetched dataset {cond['dataset_id']}")
        meta = json.loads((root / '_dataset.json').read_text()) if (root / '_dataset.json').exists() else {}
        allf = sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in IMAGE + VIDEO)
        got = [p for p in allf if any(fnmatch.fnmatch(str(p.relative_to(root)), q) for q in pats)]
        origin = ({'kind': 'file', 'label': 'Uploaded', 'dataset_id': cond['dataset_id'], 'title': 'Uploaded in a chat'} if meta.get('repository') == 'upload' else
                  {'kind': 'generated', 'label': 'Made here', 'dataset_id': cond['dataset_id'], 'title': meta.get('title'), 'ref': meta.get('ref'), 'licence': meta.get('licence')} if meta.get('repository') == 'generated' else
                  {'kind': 'dataset', 'label': 'Fetched dataset', 'dataset_id': cond['dataset_id'], 'title': meta.get('title'), 'ref': meta.get('ref'), 'licence': meta.get('licence')})
    else:
        got = []
        for q in pats:
            p = Path(q)
            p = p if p.is_absolute() else DATA / q
            got += sorted(x for x in p.parent.glob(p.name) if x.is_file()) if any(c in p.name for c in '*?[') else ([p] if p.is_file() else [])
        for p in got:
            if not str(p.resolve()).startswith(str(DATA.resolve())): raise ValueError(f'{p} is outside the lab data folder')
        isaac = all('previews' in p.parts or 'runs' in p.parts or 'clips' in p.parts for p in got) and cond.get('origin') == 'isaac'
        origin = {'kind': 'isaac', 'label': 'Rendered in Isaac Sim'} if isaac else {'kind': 'file', 'label': 'File added here'}
    got = [p for p in got if p.suffix.lower() in IMAGE + VIDEO]
    if not got: raise ValueError(f"condition {cond.get('name')}: no image or video matches {pats}")
    if cond.get('cosmos'):   # every stimulus restyled by Cosmos before TRIBE reads it
        cz = cond['cosmos']
        if not cz.get('prompt'): raise ValueError(f"condition {cond.get('name')}: Cosmos needs a prompt describing the scene")
        origin = {'kind': 'cosmos', 'label': 'Cosmos, from ' + {'dataset': 'a dataset', 'isaac': 'Isaac Sim'}.get(origin['kind'], 'an added file'), 'from': origin, 'prompt': cz['prompt'], 'seeds': cz.get('seeds', [0, 1]), 'control': cz.get('control', 'edge')}
    return got, origin


def _defaults(t: dict) -> dict:
    t = {'design': 'block', 'item_s': 1.0, 'gap_s': 0.0, 'items_per_trial': 1, 'trials_per_condition': 10, 'rest_s': 6.0, 'seed': 0, **(t or {})}
    if t['design'] == 'event': t['items_per_trial'] = 1
    on = t['items_per_trial'] * (t['item_s'] + t['gap_s'])
    t['on_s'] = round(on, 3); t['clip_s'] = round(on + t['rest_s'], 3)
    t.setdefault('read_s', [0, max(1, math.ceil(on))])   # the seconds on screen: TRIBE's output has the blood-flow lag removed (feasibility test 3b; held faces against objects, 2026-11-14)
    return t


def plan(spec: dict) -> dict:
    """Check an experiment and lay out its trials: every condition's files, every trial's items, the regions and the
    contrasts resolved. Raises with the reason when anything is missing or unequal."""
    conds = spec.get('conditions') or []
    if len(conds) < 2: raise ValueError('an experiment needs at least two conditions')
    names = [c['name'] for c in conds]
    if len(set(names)) != len(names): raise ValueError('condition names must differ')
    t = _defaults(spec.get('trial')); rng = np.random.default_rng(t['seed']); trials = []; shared = None
    for c in conds:
        fs, origin = _files_of(c)
        need = t['items_per_trial'] * t['trials_per_condition']
        if t.get('paired'):   # the same source items, in the same order, in every condition: trial k is compared with trial k
            fnames = [str(p.relative_to(p.parents[1])) for p in fs]
            if shared is None: shared = fnames; order = list(rng.permutation(len(fs))); pidx = (order * math.ceil(need / len(fs)))[:need]
            elif fnames != shared: raise ValueError(f"paired conditions need the same stimulus files; {c['name']} differs from {conds[0]['name']}")
            idx = pidx
        else:
            order = list(rng.permutation(len(fs))); idx = (order * math.ceil(need / len(fs)))[:need]   # each file before any repeats
        for k in range(t['trials_per_condition']):
            items = [str(fs[i]) for i in idx[k * t['items_per_trial']:(k + 1) * t['items_per_trial']]]
            if origin['kind'] == 'cosmos':   # seeds alternate across trials, so seed spread shows within the condition
                items = [{'src': x, 'prompt': origin['prompt'], 'seed': origin['seeds'][k % len(origin['seeds'])], 'control': origin['control']} for x in items]
            trials.append({'condition': c['name'], 'index': k, 'items': items, 'origin': origin, 'files_available': len(fs)})
    regs = spec.get('regions') or []
    if not regs: raise ValueError('name at least one region (region_search lists them)')
    for r in regs: regions.mask_for(r if isinstance(r, str) else r['areas'])
    cts = spec.get('contrasts') or [{'name': f'{names[0]} against {names[1]}', 'weights': {names[0]: 1, names[1]: -1}}]
    for ct in cts:
        bad = [k for k in ct['weights'] if k not in names]
        if bad: raise ValueError(f"contrast {ct['name']}: no condition {bad}")
        if abs(sum(ct['weights'].values())) > 1e-9: raise ValueError(f"contrast {ct['name']}: weights must sum to zero")
    groups = {_region_name(r) for r in regs}
    reported = []
    for rp in spec.get('reported') or []:
        if rp.get('contrast') not in [c['name'] for c in cts]: raise ValueError(f"reported result names no contrast here: {rp.get('contrast')}")
        name = _region_name(rp['region']) if isinstance(rp.get('region'), (str, dict)) else None
        if name is None: raise ValueError('a reported result needs a region: a name from regions, or an atlas name')
        if name not in groups: regions.mask_for(name)   # a region of this experiment, such as a group it defines, or any atlas name
        reported.append({**rp, 'region': name})
    return {'trial': t, 'trials': trials, 'contrasts': cts, 'regions': regs, 'reported': reported,
            'clips': len(trials), 'cosmos_clips': len(cz := {json.dumps(x, sort_keys=True) for tr in trials for x in tr['items'] if isinstance(x, dict)}),
            'minutes_estimate': round(len(trials) * (TRIBE_S_PER_SECOND * t['clip_s'] + 3) / 60 + (len(cz) * 4 * max(0.5, t['item_s'] / 4) + 2 if cz else 0), 1)}   # Cosmos: about 4 min per 4 s clip, 2 min to load


def _region_name(r) -> str:
    return r if isinstance(r, str) else r['name']


def _region_mask(r) -> np.ndarray:
    return regions.mask_for(r if isinstance(r, str) else r['areas'])


def _segment(src: str | None, seconds: float) -> Path:
    """One stretch of a trial as a normalised clip: an image held, a video's first seconds, or grey. Cached by content."""
    key = hashlib.sha1(json.dumps([src, seconds, SIZE, src and Path(src).stat().st_mtime_ns]).encode()).hexdigest()[:16]
    out = CLIPS / 'segments' / f'{key}.mp4'
    if out.exists(): return out
    out.parent.mkdir(parents=True, exist_ok=True)
    fit = f'scale={SIZE}:{SIZE}:force_original_aspect_ratio=decrease,pad={SIZE}:{SIZE}:(ow-iw)/2:(oh-ih)/2:color={GREY},format=yuv420p,fps=30'
    if src is None: cmd = ['-f', 'lavfi', '-i', f'color=c={GREY}:s={SIZE}x{SIZE}:r=30:d={seconds}']
    elif Path(src).suffix.lower() in IMAGE: cmd = ['-loop', '1', '-t', str(seconds), '-i', src]
    else: cmd = ['-t', str(seconds), '-i', src]
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *cmd, '-vf', fit, '-t', str(seconds), '-an', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', str(out)], check=True)
    return out


def make_clip(items: list[str], t: dict) -> tuple[Path, Path]:
    """A trial's clip (items in order with gaps, then rest, all on grey) and a still of its first item."""
    key = hashlib.sha1(json.dumps([items, t['item_s'], t['gap_s'], t['rest_s'], SIZE]).encode()).hexdigest()[:16]
    clip, still = CLIPS / f'{key}.mp4', CLIPS / f'{key}.png'
    if not clip.exists():
        segs = []
        for it in items:
            segs.append(_segment(it, t['item_s']))
            if t['gap_s']: segs.append(_segment(None, t['gap_s']))
        segs.append(_segment(None, t['rest_s']))
        lst = clip.with_suffix('.txt'); lst.write_text(''.join(f"file '{s}'\n" for s in segs))
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lst), '-c', 'copy', str(clip)], check=True); lst.unlink()
    if not still.exists():
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-ss', str(min(0.5, t['item_s'] / 2)), '-i', str(clip), '-frames:v', '1', str(still)], check=True)
    return clip, still


def _src(item) -> str:
    return item['src'] if isinstance(item, dict) else item


def cosmos_item(item: dict, item_s: float, wait) -> str:
    """A stimulus restyled by Cosmos: the source as a 30 fps 16:9 clip (an image is held), then Cosmos with the prompt, seed
    and control. Cached by content, so a rerun or another condition with the same item reuses it."""
    src = Path(item['src']); n = max(5, min(301, int(item_s * 30) // 4 * 4 + 1))   # Cosmos takes 4k + 1 frames; up to 10 s, so a 9 s body-study clip goes through whole (#17)
    key = hashlib.sha1(json.dumps([str(src), src.stat().st_mtime_ns, item['prompt'], item['seed'], item['control'], n]).encode()).hexdigest()[:16]
    out_dir = CLIPS / 'cosmos'; done = out_dir / key / 'vision.mp4'
    if done.exists(): return str(done)
    out_dir.mkdir(parents=True, exist_ok=True); norm = out_dir / f'{key}_source.mp4'
    fit = f'scale={CW}:{CH}:force_original_aspect_ratio=decrease,pad={CW}:{CH}:(ow-iw)/2:(oh-ih)/2:color=0x808080,fps=30,format=yuv420p'
    inp = ['-loop', '1', '-t', str(n / 30 + 0.1), '-i', str(src)] if src.suffix.lower() in IMAGE else ['-i', str(src)]
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *inp, '-vf', fit, '-frames:v', str(n), '-an', '-c:v', 'libx264', '-crf', '16', str(norm)], check=True)
    from . import preview
    j = preview.queue().submit('cosmos_sim_transfer', {'controls': {'rgb': str(norm)}, 'prompt': item['prompt'], 'out_dir': str(out_dir), 'name': key},
                               {'control': item['control'], 'seed': int(item['seed']), 'frames': n, 'fps': 30}, lane='batch')
    wait(j)
    if j.status != 'done': raise RuntimeError(j.error or 'Cosmos failed')
    w, h = _size(src); s = min(CW / w, CH / h); cw, ch = int(w * s) // 2 * 2, int(h * s) // 2 * 2
    if (cw, ch) == (CW, CH): return j.outputs['clip']
    crop = out_dir / key / 'vision_crop.mp4'   # back to the source's own shape: the padding Cosmos filled is not the stimulus
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-i', j.outputs['clip'], '-vf', f'crop={cw}:{ch}:{(CW - cw) // 2}:{(CH - ch) // 2}', '-an', '-c:v', 'libx264', '-crf', '16', str(crop)], check=True)
    return str(crop)


def _size(p: Path) -> tuple[int, int]:
    """Width and height of a video or image: ffprobe where it is installed, else read from ffmpeg's description of the
    input (the cluster's app server has only the static ffmpeg from the TRIBE environment)."""
    if shutil.which('ffprobe'):
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', str(p)], capture_output=True, text=True).stdout.strip().split(',')
        return int(r[0]), int(r[1])
    info = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(p)], capture_output=True, text=True).stderr
    m = re.search(r'Video: [^\n]*?(\d{2,5})x(\d{2,5})', info)
    if not m: raise RuntimeError(f'no video stream in {p}')
    return int(m.group(1)), int(m.group(2))


def _boot_diff(groups: dict[str, np.ndarray], w: dict, rng, n=4000) -> list[float]:
    """95% interval of a weighted sum of condition means, resampling trials within each condition."""
    sims = np.zeros(n)
    for c, wt in w.items():
        v = groups[c]; sims += wt * v[rng.integers(0, len(v), (n, len(v)))].mean(1)
    return [round(float(x), 4) for x in np.percentile(sims, [2.5, 97.5])]


def analyse(trials: list[dict], P: dict, out_url) -> dict:
    """Every contrast in every region with its baselines, then match or no match against the reported result."""
    t = P['trial']; a, b = t['read_s']; rng = np.random.default_rng(0)
    on = {i: np.load(x['preds'])[a:b].mean(0) for i, x in enumerate(trials)}
    stats = {i: plans._clip_stats(x['clip']) for i, x in enumerate(trials)}   # motion energy, brightness
    names = list(dict.fromkeys(x['condition'] for x in trials))
    idx = {c: [i for i, x in enumerate(trials) if x['condition'] == c] for c in names}
    vj = plans._vjepa_random_map({c: [trials[i]['preds'] for i in idx[c]] for c in names})
    areas = regions.hcp_areas(); whole = np.ones(20484, bool)
    out = []
    for ct in P['contrasts']:
        w = ct['weights']; used = [c for c in w]
        D = sum(wt * np.mean([on[i] for i in idx[c]], 0) for c, wt in w.items())   # the contrast map, per vertex
        area_vals = np.array([D[m].mean() for m in areas])
        pool = [i for c in used for i in idx[c]]; sizes = [len(idx[c]) for c in used]
        paired = bool(t.get('paired')) and len(used) == 2 and sorted(w.values()) == [-1, 1]
        def region_row(name, m):
            if paired:   # trial k of one condition against trial k of the other: the same source item
                a, b = sorted(used, key=lambda c: -w[c]); v = np.array([on[i][m].mean() for i in idx[a]]) - np.array([on[i][m].mean() for i in idx[b]])
                flips = np.array([(v * rng.choice([-1, 1], len(v))).mean() for _ in range(2000)])
                return {'region': name, 'value': round(float(v.mean()), 4), 'interval_95': [round(float(x), 4) for x in np.percentile(v[rng.integers(0, len(v), (4000, len(v)))].mean(1), [2.5, 97.5])],
                        'n': len(v), 'units_positive': int((v > 0).sum()), 'per_unit': [round(float(x), 4) for x in v], 'area_rank_pct': round(float((area_vals < m_val(D, m)).mean() * 100), 1),
                        'shuffled_labels_95': [round(float(x), 4) for x in np.percentile(flips, [2.5, 97.5])], 'shuffled_at_least_as_far': round(float((np.abs(flips) >= abs(v.mean())).mean()), 4),
                        'vjepa_random_map': round(float(sum(wt * vj[c][:, m].mean(1).mean() for c, wt in w.items())), 4) if vj else None}
            g = {c: np.array([on[i][m].mean() for i in idx[c]]) for c in used}
            val = float(sum(wt * g[c].mean() for c, wt in w.items()))
            vals = np.array([on[i][m].mean() for i in pool]); null = []
            for _ in range(2000):   # condition labels shuffled among the same trials: the contrast this design gives by chance
                p = rng.permutation(len(pool)); k = 0; s = 0.0
                for c, n in zip(used, sizes): s += w[c] * vals[p[k:k + n]].mean(); k += n
                null.append(s)
            null = np.array(null)
            return {'region': name, 'value': round(val, 4), 'interval_95': _boot_diff(g, w, rng), 'n': {c: len(idx[c]) for c in used},
                    'units_positive': None, 'area_rank_pct': round(float((area_vals < m_val(D, m)).mean() * 100), 1),
                    'shuffled_labels_95': [round(float(x), 4) for x in np.percentile(null, [2.5, 97.5])],
                    'shuffled_at_least_as_far': round(float((np.abs(null) >= abs(val)).mean()), 4),
                    'vjepa_random_map': round(float(sum(wt * vj[c][:, m].mean(1).mean() for c, wt in w.items())), 4) if vj else None}
        rows = [region_row(_region_name(r), _region_mask(r)) for r in P['regions']]
        def low(j, label, units):
            g = {c: np.array([stats[i][j] for i in idx[c]]) for c in used}
            return {'name': label, 'value': round(float(sum(wt * g[c].mean() for c, wt in w.items())), 4), 'interval_95': _boot_diff(g, w, rng), 'units': units, 'units_positive': None, 'n': len(pool)}
        whole_row = region_row('Whole cortex', whole)
        baselines = [{'name': 'Whole cortex', 'value': whole_row['value'], 'interval_95': whole_row['interval_95'], 'units': 'TRIBE units', 'units_positive': None, 'n': len(pool)},
                     low(0, 'Motion energy of the clips', 'grey levels per frame'), low(1, 'Brightness of the clips', 'grey levels')]
        reported = []
        for rp in P['reported']:
            if rp['contrast'] != ct['name']: continue
            row = next((r for r in rows if r['region'] == rp['region']), None) or region_row(rp['region'], regions.mask_for(rp['region']))   # a group this experiment defines is one of its rows
            want = 1 if rp.get('direction', 'higher') in ('higher', '+', 'positive', 'increase') else -1
            lo, hi = row['interval_95']; sign = 1 if lo > 0 else -1 if hi < 0 else 0
            verdict = 'match' if sign == want else ('no match: interval includes zero' if sign == 0 else 'no match: opposite direction')
            reported.append({**rp, 'tribe_value': row['value'], 'tribe_interval_95': row['interval_95'], 'area_rank_pct': row['area_rank_pct'],
                             'shuffled_labels_95': row['shuffled_labels_95'], 'result': verdict})
        mp = maps.render(D, 'contrast', FILES)
        out.append({'contrast': ct['name'], 'weights': w, 'regions': rows, 'baselines': baselines, 'reported': reported, 'map': mp,
                    'read_s': [a, b], 'vjepa_note': None if vj else 'V-JEPA 2 features for these clips are not in the cache, so the features-only baseline is missing'})
    return {'contrasts': out}


def m_val(D, m) -> float:
    return float(D[m].mean())


def run(tools, broadcast, project_id: str, actor: str) -> dict:
    """Make every trial's clip, read each with TRIBE through the lab's queue, then analyse. Returns at once."""
    from . import preview, runner
    s = tools.store; Prow = s.get('project', project_id); spec = Prow.data.get('experiment')
    if not spec: raise ValueError('this project has no experiment; set one up with experiment_create')
    P = plan(spec); total = len(P['trials'])
    tools.call('project_update', actor, project_id=project_id, expect_version=Prow.version, status='Running')
    import uuid
    token = uuid.uuid4().hex; runner.LIVE[project_id] = token
    from . import runinfo
    info = runinfo.start(actor)   # how the run was made, saved with its results (#19)
    used = {'tribe_v2'} | ({'cosmos_sim_transfer'} if any(isinstance(x, dict) for tr in P['trials'] for x in tr['items']) else set())

    def go():
        ev = lambda **k: broadcast({'run': project_id, **k})
        try:
            done = []
            for k, tr in enumerate(P['trials']):
                if any(isinstance(x, dict) for x in tr['items']):   # Cosmos first: the restyled clips stand in for their sources
                    ev(stage='cosmos', done=k, total=total)
                    tr = {**tr, 'sources': [_src(x) for x in tr['items']], 'items': [cosmos_item(x, P['trial']['item_s'], lambda j: j.done.wait(7200)) if isinstance(x, dict) else x for x in tr['items']]}
                clip, still = make_clip(tr['items'], P['trial'])
                pred = clip.with_suffix('.tribe.npy')
                if not pred.exists():
                    j = preview.queue().submit('tribe_v2', {'clip': str(clip)}, {'on_s': P['trial']['read_s']}, lane='batch'); j.done.wait(3600)
                    if j.status != 'done': raise RuntimeError(j.error or 'TRIBE failed')
                done.append({**tr, 'clip': str(clip), 'still': str(still), 'preds': str(pred)})
                o = np.load(pred)[P['trial']['read_s'][0]:P['trial']['read_s'][1]].mean(0)   # as the saved sample reads it, so the live table and the record agree (#20)
                ev(done=k + 1, total=total, image=out_url(still), trial={'index': k, 'unit': f"{tr['condition']}, trial {tr['index'] + 1}", 'condition': tr['condition'],
                                                                       'label': f"{tr['condition']}, trial {tr['index'] + 1}", 'image': out_url(still), 'clip': out_url(clip),
                                                                       'readout': {_region_name(r): round(float(o[_region_mask(r)].mean()), 4) for r in P['regions']}})
                if runner.SHUTTING_DOWN.is_set(): return
                if token in runner.STOP: raise RuntimeError(f"Stopped by {runner.STOP[token]} after {k + 1} of {total} clips; running it again picks up from there")
            ev(stage='comparing')
            res = analyse(done, P, out_url)
            rec = plans.Deferred()
            for i, tr in enumerate(done):
                o = np.load(tr['preds'])[P['trial']['read_s'][0]:P['trial']['read_s'][1]].mean(0)
                rec.create(None, 'sample', {'project_id': project_id, 'index': i, 'unit': f"{tr['condition']}, trial {tr['index'] + 1}", 'condition': tr['condition'],
                                            'label': f"{tr['condition']}, trial {tr['index'] + 1}", 'image': out_url(tr['still']), 'clip': out_url(tr['clip']), 'preds': tr['preds'],
                                            'origin': tr['origin'], 'items': [Path(x).name for x in tr.get('sources', tr['items'])], 'sources': tr.get('sources'),
                                            'readout': {_region_name(r): round(float(o[_region_mask(r)].mean()), 4) for r in P['regions']}}, depends_on=[('project', project_id)])
            for c in res['contrasts']:
                nm = rec.create(None, 'neural_map', {'project_id': project_id, 'title': c['contrast'], 'kind': 'contrast', **c['map']}, depends_on=[('project', project_id)])
                an = rec.create(None, 'analysis', {'project_id': project_id, 'kind': 'paired', 'title': c['contrast'], 'window_s': c['read_s'], 'weights': c['weights'],
                                                   'units': f"TRIBE units, mean of seconds {c['read_s'][0]} to {c['read_s'][1]}", 'design': 'unpaired trials'}, depends_on=[('project', project_id)])
                rec.create(None, 'result', {'analysis_id': an.id, 'project_id': project_id, 'regions': c['regions'], 'map_id': nm.id, 'baselines': c['baselines'],
                                            'reported': c['reported'], 'vjepa_note': c['vjepa_note'],
                                            'baselines_note': 'Each region also carries its rank among the 360 HCP areas TRIBE reports, the same contrast with condition labels shuffled, and V-JEPA 2 features through a fixed random cortex map'},
                           depends_on=[('analysis', an.id)])
            with tools.lock:
                step = s.begin(actor, 'project_run', {'project_id': project_id})
                for kind in ('result', 'analysis', 'neural_map', 'sample'):   # a run replaces the project's earlier results, in the same step, so undo brings them back (#12)
                    for row in s.list(kind):
                        if row.data.get('project_id') == project_id: s.delete(step, kind, row.id, row.version)
                rec.apply(s, step)
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Done', counts={'units': total, 'clips': total},
                       run_info=runinfo.finish(info, used))
            ev(stage='done')
        except Exception as e:
            if runner.SHUTTING_DOWN.is_set(): return
            import traceback; traceback.print_exc()
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Draft')
            ev(stage='failed', error=str(e)[-300:])
    def run_once():
        try: go()
        finally:   # the run is over, however it ended: its token and any stop request for it go
            if runner.LIVE.get(project_id) == token: runner.LIVE.pop(project_id, None)
            runner.STOP.pop(token, None)
    threading.Thread(target=run_once, daemon=True).start()
    return {'queued': True, 'clips': total, 'minutes_estimate': P['minutes_estimate']}


def out_url(p) -> str | None:
    return '/files/' + str(Path(p).resolve().relative_to(FILES.resolve())) if p else None
