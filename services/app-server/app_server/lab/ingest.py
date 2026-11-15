"""Load finished runs from feasibility/out into the store as projects, each opened from a template.

Usage: SIMULAXON_HOME=... python -m app_server.lab.ingest [DB_PATH]
Every project names its template and fills the template's blanks. The builders in plans.py do the rest, so a new
project is a new entry in PROJECTS, never new code. Projects whose runs are not finished are created as drafts.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
from ..store import Store
from . import plans, templates, records, worlds
from ..script import parse

from ..home import HOME as ROOT
OUT = ROOT / 'feasibility' / 'out'
DATA = ROOT / 'backend' / 'data'; FILES = DATA / 'files'


def out_url(p):
    if not p: return None
    p = Path(p)
    return '/out/' + str(p.resolve().relative_to(OUT.resolve())) if p.exists() else None


def _pairs(folder: str, items_file: str, a: str, b: str):
    items = json.load(open(OUT / items_file)); by = {(it['pair'], it['kind']): it for it in items}
    units = []
    for i in sorted({it['pair'] for it in items}):
        def side(kind):
            it = by[(i, kind)]; stem = f'p{i:02d}_{kind}'
            return {'label': it['name'].replace('_', ' ').capitalize() if it['name'].islower() else it['name'],
                    'image': OUT / folder / 'renders' / f'{stem}_tribe.png', 'clip': OUT / folder / 'clips' / f'{stem}_on.mp4',
                    'preds': OUT / folder / f'{stem}_preds.npy', 'usd': it['usd'], 'id': f'{folder}/{stem}'}
        units.append({'unit': f'pair {i + 1}', 'a': side(a), 'b': side(b)})
    return units


def _physics():
    rep = json.load(open(OUT / 'physics' / 'report.json')); items = {it['name']: it for it in json.load(open(OUT / 'physics_items.json'))}
    units = []
    for name in rep['items']:
        def side(cond):
            return {'label': items[name]['label'], 'image': OUT / 'physics' / f'{name}_{cond}' / 'frame_045.png',
                    'clip': OUT / 'physics' / 'clips' / f'{name}_{cond}_on.mp4', 'preds': OUT / 'physics' / f'{name}_{cond}_preds.npy',
                    'usd': items[name]['usd'], 'id': name}
        units.append({'unit': items[name]['label'], 'a': side('hovers'), 'b': side('lands')})
    return units, rep


def _loo():
    L = json.load(open(OUT / 'loo_room' / 'objects.json'))
    scene = json.load(open(OUT / 'scenes' / 'scene_d0f849e0e9' / '1df8750bbad9.json')); desc = {o['id']: o.get('description', '') for o in scene['objects']}
    full = {'label': 'Operating room, SAGE-10k 7e07a47a', 'image': OUT / 'loo_room' / 'full_rgb.png', 'clip': OUT / 'loo_room' / 'clips' / 'full_on.mp4',
            'preds': OUT / 'loo_room' / 'full_preds.npy'}
    objs = [{'path': o['path'], 'label': o['label'].replace('_', ' '), 'description': desc.get(o['path'].split('/')[-1], ''),
             'image': OUT / 'loo_room' / f"hide_{o['k']:02d}_rgb.png", 'clip': OUT / 'loo_room' / 'clips' / f"hide_{o['k']:02d}_on.mp4",
             'preds': OUT / 'loo_room' / f"hide_{o['k']:02d}_preds.npy", 'pixels': o['pixels'], 'bbox_px': o['bbox_px']} for o in L['objects']]
    return full, objs, scene


def _screen():
    """Every distinct stimulus already rendered on the counter, from every counter run."""
    seen, items = set(), []
    for folder, f, kinds in (('calib20', 'calib_items.json', ('face', 'object')), ('colourfit20', 'colourfit20_items_abs.json', ('food', 'matched')),
                             ('shape20', 'shape20_items_abs.json', ('food', 'matched'))):
        for u in _pairs(folder, f, *kinds):
            for x in (u['a'], u['b']):
                if x['usd'] in seen: continue
                seen.add(x['usd']); items.append(x)
    return items


PIPE = ['Isaac Sim 6.2', '3 s on screen, then 7 s grey', 'TRIBE v2, video only, bfloat16', 'Destrieux regions']
PROJECTS = [
    {'id': 'faces_vs_vases', 'template': 'check_contrast', 'title': 'Faces against vases',
     'bindings': {'a': 'a face', 'b': 'a vase of the same height', 'region': 'the face regions', 'match_on': 'height and width'},
     'labels': ('Bust', 'Vase'), 'source': lambda: _pairs('calib20', 'calib_items.json', 'face', 'object'),
     'provenance': ['20 SAGE-10k busts and 20 height-matched vases'] + PIPE, 'search': records.search_sage_busts, 'note': 'Positive control: a known effect, to check the pipeline.'},
    {'id': 'food_vs_colour', 'template': 'check_contrast', 'title': 'Food against colour-matched objects',
     'bindings': {'a': 'food', 'b': 'an object of the same colour', 'region': 'the ventral visual regions', 'match_on': 'colour'},
     'labels': ('Food', 'Colour-matched object'), 'source': lambda: _pairs('colourfit20', 'colourfit20_items_abs.json', 'food', 'matched'),
     'provenance': ['20 Palatial foods and 20 colour-matched objects'] + PIPE, 'search': lambda: records.search_palatial_food('colour'), 'note': 'One seed and one camera, fitted to equal size on screen.'},
    {'id': 'food_vs_shape', 'template': 'check_contrast', 'title': 'Food against shape-matched objects',
     'bindings': {'a': 'food', 'b': 'an object of the same shape', 'region': 'the ventral visual regions', 'match_on': 'shape'},
     'labels': ('Food', 'Shape-matched object'), 'source': lambda: _pairs('shape20', 'shape20_items_abs.json', 'food', 'matched'),
     'provenance': ['20 Palatial foods and 20 shape-matched objects'] + PIPE, 'search': lambda: records.search_palatial_food('shape'), 'note': 'One seed and one camera, fitted to equal size on screen.'},
    {'id': 'room_objects', 'template': 'one_object_out', 'title': 'Objects in an operating room',
     'bindings': {'scene': 'an operating room', 'region': 'each region', 'camera': 'corner, eye height', 'n_objects': 16},
     'source': _loo, 'search': records.search_room_objects, 'provenance': ['SAGE-10k room 7e07a47a, 88 objects', 'Isaac Sim 6.2, corner camera', '16 largest objects hidden in turn'] + PIPE[1:],
     'note': 'One camera and one seed, so effects have no interval yet.'},
    {'id': 'screen_v1_lo', 'template': 'select_stimuli', 'title': 'Stimuli that drive early and object regions together or apart',
     'bindings': {'a_region': 'Early visual', 'b_region': 'Lateral occipital', 'a_label': 'early visual cortex', 'b_label': 'the lateral occipital region', 'n_items': 0, 'k': 5}, 'source': _screen,
     'provenance': ['Every stimulus rendered on the counter so far'] + PIPE[1:], 'note': 'Early visual and lateral occipital stand in for V1 and V4, as anatomical regions.'},
    {'id': 'falls', 'template': 'possible_impossible', 'title': 'Falling objects that stop in mid-air',
     'bindings': {'region': 'visual cortex', 'event': 'a falling object stops in mid-air', 'a': 'stops in mid-air', 'b': 'lands',
                  'n_items': 8, 'drop_m': 0.4, 'gap_m': 0.08, 'restitution': 0.35},
     'labels': ('Stops in mid-air', 'Lands'), 'source': _physics, 'run_in_app': True,   # test 13's falls let gravity pull the item through the counter 'search': records.search_physics_items,
     'provenance': ['8 Palatial items, dropped 0.40 m', 'Isaac Sim 6.2, motion from the equations of motion', '3 s of motion, then 7 s grey'] + PIPE[2:],
     'note': 'Both clips share every frame until contact. The hovering item ends 8 cm higher.'},
]


def ready(p) -> bool:
    try:
        if p['template'] == 'select_stimuli': return all(Path(x['preds']).exists() for x in p['source']())
        if p['template'] == 'one_object_out':
            full, objs, _ = p['source'](); return all(Path(x['preds']).exists() for x in [full] + objs)
        src = p['source'](); units = src[0] if isinstance(src, tuple) else src
        return all(Path(u[c]['preds']).exists() for u in units for c in 'ab')
    except FileNotFoundError:
        return False


def build(store: Store, p: dict) -> dict:
    """One project row, written once, then its samples, analyses and results, so nothing it made starts out of date."""
    t = templates.get(p['template']); b = p['bindings']
    step = store.begin('agent', 'project_create', {'template_id': t['id'], 'bindings': b})
    params = [{**x, 'value': templates.fill(x['value'], b)} for x in t['parameters']]
    status = 'Done' if ready(p) else 'Running'
    data = {'title': p['title'], 'question': p.get('question') or templates.fill(t['question'], b), 'question_written': bool(p.get('question')), 'template_id': t['id'], 'bindings': b, 'parameters': params,
            'plan': t['plan'], 'provenance': p['provenance'], 'note': p.get('note', ''), 'status': status, 'created_order': PROJECTS.index(p)}
    if p.get('run_in_app'):   # rendered and read by the app's own runner: a draft with its world, pairs and controls
        units = p['source']()[0]
        assets = {u['a']['id']: {'label': u['a']['label'], 'usd': str(u['a']['usd']), 'image': None} for u in units}
        data.update(status='Draft', run_in_app_built=True, assets=assets, world={'kind': t['world'], 'name': 'Counter, Isaac Sim'}, labels=list(p['labels']),
                    pairs=[[{'item': u['a']['id'], 'outcome': 'hovers'}, {'item': u['a']['id'], 'outcome': 'lands'}] for u in units],
                    script=worlds.script(t['world'], assets, {}))
        store.create(step, 'project', data, id=p['id'])
        for prm in parse(data['script']):
            store.create(step, 'parameter', {**prm.to_dict(), 'project_id': p['id']}, id=f"{p['id']}.{prm.name}", depends_on=[('project', p['id'])])
        return {'project': p['id'], 'status': 'Draft'}
    if status != 'Done':
        store.create(step, 'project', data, id=p['id']); return {'project': p['id'], 'status': status}
    data['search'] = p['search']() if p.get('search') else None
    kind = t['world']
    if t['plan'] == 'selection':
        items = p['source'](); b = {**b, 'n_items': len(items)}
        data.update(bindings=b, question=templates.fill(t['question'], b), parameters=[{**x, 'value': templates.fill(x['value'], b)} for x in t['parameters']],
                    assets={x['id']: {'label': x['label'], 'usd': str(x['usd']), 'image': out_url(x['image'])} for x in items},
                    world={'kind': 'counter', 'name': 'Counter, Isaac Sim'}, hero=out_url(items[0]['image']), counts={'units': len(items), 'clips': len(items)})
        data['script'] = worlds.script('counter', data['assets'], {})
        store.create(step, 'project', data, id=p['id'])
        counts = plans.selection(store, step, p['id'], items, b['a_region'], b['b_region'], int(b['k']), (0, 3), FILES, out_url)
        for prm in parse(data['script']):
            store.create(step, 'parameter', {**prm.to_dict(), 'project_id': p['id']}, id=f"{p['id']}.{prm.name}", depends_on=[('project', p['id'])])
        return {'project': p['id'], 'status': status, **counts}
    if kind == 'stage':
        full, objs, scene = p['source']()
        data['assets'] = {f"/World/Objects/{o['id']}": {'label': o['label'].replace('_', ' ')} for o in scene['objects']}
        data['world'] = {'kind': 'stage', 'name': f"{scene['rooms'][0].get('room_type', 'room').capitalize()}, SAGE-10k", 'usda': str(OUT / 'scenes' / 'scene_d0f849e0e9' / '1df8750bbad9.usda')}
    else:
        src = p['source'](); us = src[0] if isinstance(src, tuple) else src
        data['assets'] = {x['id']: {'label': x['label'], 'usd': str(x['usd']), 'image': out_url(x['image'])} for u in us for x in ([u['a'], u['b']] if kind == 'counter' else [u['a']])}
        data['world'] = {'kind': kind, 'name': 'Counter, Isaac Sim'}
        data['pairs'] = [[{'item': u['a']['id']}, {'item': u['b']['id']}] for u in us] if kind == 'counter' else [[{'item': u['a']['id'], 'outcome': 'hovers'}, {'item': u['b']['id'], 'outcome': 'lands'}] for u in us]
        data['labels'] = list(p['labels'])
    data['script'] = worlds.script(kind, data['assets'], {})
    if t['plan'] == 'leave_one_out':
        full, objs, scene = p['source']()
        data.update(hero=out_url(full['image']), counts={'objects': len(objs), 'clips': len(objs) + 1})
        tested = {o['path'] for o in objs}
        data['scene'] = {'name': scene.get('name', '')[:80], 'room': scene['rooms'][0].get('room_type', ''), 'objects': [
            {'path': f"/World/Objects/{o['id']}", 'label': o['label'].replace('_', ' '), 'collection': o['source']['collection'], 'placed_on': o.get('placed_on', ''),
             'tested': f"/World/Objects/{o['id']}" in tested} for o in scene['objects']]}
        store.create(step, 'project', data, id=p['id'])
        counts = plans.leave_one_out(store, step, p['id'], full, objs, (0, 3), FILES, out_url)
    else:
        src = p['source'](); units = src[0] if isinstance(src, tuple) else src
        data.update(hero=out_url(units[0]['a']['image']), counts={'units': len(units), 'clips': 2 * len(units)})
        store.create(step, 'project', data, id=p['id'])
        counts = plans.matched(store, step, p['id'], units, (0, 3), p['labels'], FILES, out_url)
    for prm in parse(data['script']):
        store.create(step, 'parameter', {**prm.to_dict(), 'project_id': p['id']}, id=f"{p['id']}.{prm.name}", depends_on=[('project', p['id'])])
    return {'project': p['id'], 'status': status, **counts}


def refresh_controls(store, project_id: str):
    """Bring a kept project's controls up to the current scene script: new options and new parameters appear, values stay."""
    cur = store.get('project', project_id); w = cur.data.get('world')
    if not w: return
    assets = {**cur.data.get('assets', {}), **{r.data['asset_id']: r.data for r in store.list('asset') if r.data.get('project_id') == project_id}}
    rows = {r.data['name']: r for r in store.list('parameter') if r.data.get('project_id') == project_id}
    script = worlds.script(w['kind'], assets, {n: r.data['value'] for n, r in rows.items()})
    step = store.begin('app', 'parameter_update', {'project_id': project_id, 'refresh': 'scene script'})
    for prm in parse(script):
        d = {**prm.to_dict(), 'project_id': project_id}
        if prm.name not in rows: store.create(step, 'parameter', d, id=f'{project_id}.{prm.name}', depends_on=[('project', project_id)])
        elif {k: rows[prm.name].data.get(k) for k in ('options', 'range', 'label', 'line')} != {k: d.get(k) for k in ('options', 'range', 'label', 'line')}:
            store.update(step, 'parameter', rows[prm.name].id, {k: d[k] for k in ('options', 'range', 'label', 'line', 'target') if k in d}, rows[prm.name].version, mark_stale=False)
    if cur.data.get('script') != script: store.update(step, 'project', project_id, {'script': script}, store.get('project', project_id).version, mark_stale=False)


def main(db: str):
    FILES.mkdir(parents=True, exist_ok=True)
    store = Store(str(Path(db)))   # never wiped: projects made in the app stay
    for p in PROJECTS:
        cur = store.get('project', p['id'])
        if cur and p.get('run_in_app') and not cur.data.get('run_in_app_built'):   # replace the earlier, invalid build once
            store.db.execute("delete from rows where id = ? or id like ? or json_extract_string(data, '$.project_id') = ?", [p['id'], p['id'] + '.%', p['id']])
            cur = None
        if cur and cur.data.get('status') in ('Done', 'Running') and p.get('run_in_app'): print({'project': p['id'], 'status': 'kept'}); continue
        if cur and cur.data.get('status') == 'Done':
            pr = cur.data.get('pairs') or []
            if pr and isinstance(pr[0][0], str):   # older projects stored pairs as bare ids: make them sets of parameter changes
                kind = cur.data.get('world', {}).get('kind')
                new = [[{'item': a, 'outcome': 'hovers'}, {'item': b, 'outcome': 'lands'}] if kind == 'fall' else [{'item': a}, {'item': b}] for a, b in pr]
                step = store.begin('app', 'project_update', {'project_id': p['id'], 'pairs': 'migrated'})
                store.update(step, 'project', p['id'], {'pairs': new}, cur.version, mark_stale=False)
            refresh_controls(store, p['id'])
            cur = store.get('project', p['id']); t = templates.get(p['template']); b = {**cur.data.get('bindings', {}), **{k: v for k, v in p['bindings'].items() if k not in cur.data.get('bindings', {})}}
            q = p.get('question') or templates.fill(t['question'], b)   # a written question (#24) over the template's fill
            if q != cur.data.get('question') and not cur.data.get('question_written'):   # never replaces a question someone wrote
                step = store.begin('app', 'project_update', {'project_id': p['id'], 'question': 'template wording'})
                store.update(step, 'project', p['id'], {'bindings': b, 'question': q}, cur.version, mark_stale=False)
            print({'project': p['id'], 'status': 'kept'}); continue
        if cur:   # a starting project whose runs were not finished: rebuild it
            store.db.execute("delete from rows where id = ? or id like ?", [p['id'], p['id'] + '.%'])
        print(build(store, p), flush=True)
    store.db.close()


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else str(DATA / 'lab_main.duckdb'))
