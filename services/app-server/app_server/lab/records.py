"""What each project's search and sources were, recomputed from the real indexes so every count is real.

search_* functions return {reading, steps: [{label, query, kept, removed, removed_rows: [{name, reason}]}], picked: [...]}.
Steps are the same shape source_search returns, so the Search view draws any of them.
"""
from __future__ import annotations
import json, re
from pathlib import Path
import numpy as np

from ..home import HOME as ROOT
FE = ROOT / 'feasibility'; IDX = FE / 'indexes'; OUT = FE / 'out'


def _step(label, query, before, after, why=lambda r: ''):
    keep = {id(r) for r in after}; gone = [r for r in before if id(r) not in keep]
    return {'label': label, 'query': query, 'kept': len(after), 'removed': len(gone),
            'removed_rows': [{'name': r.get('label') or r.get('type') or r.get('name'), 'reason': why(r)} for r in gone[:40]]}


def search_palatial_food(match: str) -> dict:
    s = json.load(open(IDX / 'palatial' / 'search_food.json'))
    steps = [{'label': x['step'], 'query': x['query'], 'kept': x['kept'], 'removed': x['removed'],
              'removed_rows': [{'name': r.get('name'), 'reason': r.get('reason', '')} for r in x.get('removed_rows', [])[:40]]} for x in s['steps']]
    return {'reading': f'Food is any Palatial asset labelled food, fruit or vegetable whose image looks like food, under 30 cm, without printed text. Each food is paired with the non-food nearest in {match}.',
            'source': 'Palatial NV asset library, 1,013 assets', 'steps': steps,
            'pairs_note': f"{s['pair_count']} pairs from a non-food pool of {s.get('non_food_pool') if isinstance(s.get('non_food_pool'), int) else len(s.get('non_food_pool') or [])}; the 20 closest were run."}


def search_sage_busts() -> dict:
    rows = [json.loads(l) for l in open(IDX / 'sage10k' / 'scenes_v2.jsonl')]
    rows = [r for r in rows if 'error' not in r]
    objs = [o for r in rows for o in r['objects'] if o.get('source_id') and o.get('height_m')]
    busts = [o for o in objs if o['type'] in ('bust', 'romanbust')]
    sized = [o for o in busts if 0.3 <= o['height_m'] <= 0.7]
    seen, uniq = set(), []
    for o in sized:
        if o['source_id'] not in seen: uniq.append(o); seen.add(o['source_id'])
    noface = re.compile(r'face|head|figure|bust|statue|portrait|person|man\b|woman', re.I)
    vases = [o for o in objs if o['type'] in ('vase', 'urn', 'floorvase', 'vase1', 'vase2')]
    vclean = [o for o in vases if not noface.search(o.get('description') or '')]
    vsized = [o for o in vclean if 0.2 <= o['height_m'] <= 0.8]
    steps = [_step('Objects in SAGE-10k scenes with a size', 'all placed objects with a mesh and height', objs, objs),
             _step('Busts', "type in {bust, romanbust}", objs, busts, lambda r: r['type']),
             _step('0.3 to 0.7 m tall', 'height_m between 0.3 and 0.7', busts, sized, lambda r: f"{r['height_m']:.2f} m"),
             _step('One per mesh', 'distinct source_id', sized, uniq, lambda r: 'same mesh as an earlier bust'),
             _step('First 20', 'first 20 in index order', uniq, uniq[:20], lambda r: 'beyond 20'),
             _step('Vases and urns to match', "type in {vase, urn, floorvase}", objs, vases, lambda r: r['type']),
             _step('No face in the description', 'description has no face, head, figure, bust or person', vases, vclean, lambda r: (r.get('description') or '')[:60]),
             _step('0.2 to 0.8 m tall', 'height_m between 0.2 and 0.8', vclean, vsized, lambda r: f"{r['height_m']:.2f} m")]
    return {'reading': 'A face is a sculpted bust from SAGE-10k. Each bust is paired with the vase or urn nearest in height and width whose description mentions no face.',
            'source': 'SAGE-10k objects, read by range request', 'steps': steps, 'pairs_note': 'Nearest vase in height plus width, each vase used once.'}


def search_room_objects() -> dict:
    L = json.load(open(OUT / 'loo_room' / 'objects.json')); m = np.load(OUT / 'loo_room' / 'full_objects.npy')
    order = L['order']; px = {p: int((m == i + 1).sum()) for i, p in enumerate(order)}
    sc = json.load(open(OUT / 'scenes' / 'scene_d0f849e0e9' / '1df8750bbad9.json')); lab = {o['id']: o['label'] for o in sc['objects']}
    allo = [{'label': lab.get(p.split('/')[-1], p.split('/')[-1]).replace('_', ' '), 'path': p, 'px': px[p]} for p in order]
    vis = [o for o in allo if o['px'] > 0]; top = sorted(vis, key=lambda o: -o['px'])[:len(L['objects'])]
    return {'reading': 'Every object in the room is a candidate. The ones that cover the most of the frame are tested first.',
            'source': 'SAGE-10k room 7e07a47a', 'steps': [
                _step('Objects in the room', 'all objects', allo, allo),
                _step('Visible from the camera', 'pixels in the object mask > 0', allo, vis, lambda r: 'not in view'),
                _step(f'{len(top)} largest in the frame', 'sorted by pixels', vis, top, lambda r: f"{r['px']:,} pixels")]}


def search_physics_items() -> dict:
    items = json.load(open(OUT / 'physics_items.json')); s = json.load(open(OUT / 'colourfit20_items_abs.json'))
    pool = [{'label': x['name']} for x in s]; pick = [p for p in pool if p['label'] in {i['label'] for i in items}]
    return {'reading': 'Items with varied shapes and sizes, chosen from the colour-matched set already rendered.', 'source': 'Palatial, colour-matched set',
            'steps': [_step('Items already rendered', 'colour-matched set', pool, pool), _step('Picked by hand', 'varied shape and size', pool, pick, lambda r: 'not picked')]}


def _du(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob('*') if f.is_file()) if p.exists() else 0


def sources() -> list[dict]:
    hub = Path.home() / '.cache' / 'huggingface' / 'hub'
    def model(repo): return (hub / ('models--' + repo.replace('/', '--'))).exists()
    out = [
        {'name': 'Palatial NV asset library', 'kind': 'Assets', 'count': '1,013 assets', 'licence': 'CC BY 4.0', 'where': 'feasibility/indexes/palatial', 'ready': (IDX / 'palatial/catalog.parquet').exists(), 'needs_person': ''},
        {'name': 'SimReady assets', 'kind': 'Assets', 'count': '2,677 packages', 'licence': 'CC BY 4.0', 'where': 'feasibility/indexes/simready', 'ready': (IDX / 'simready/records.parquet').exists(), 'needs_person': ''},
        {'name': 'SAGE-10k', 'kind': 'Scenes', 'count': '10,000 scenes, 853,428 objects', 'licence': 'Apache 2.0', 'where': 'feasibility/indexes/sage10k', 'ready': (IDX / 'sage10k/scenes.parquet').exists(), 'needs_person': ''},
        {'name': 'NSD', 'kind': 'Measured fMRI', 'count': '8 people, 73,000 photos', 'licence': 'Data agreement', 'where': 'Not downloaded', 'ready': False, 'needs_person': 'Sign the NSD data agreement'},
        {'name': 'TRIBE v2', 'kind': 'Brain model', 'count': 'fsaverage5, 20,484 vertices', 'licence': 'CC BY-NC 4.0', 'where': 'Hugging Face cache', 'ready': model('facebook/tribev2'), 'needs_person': ''},
        {'name': 'V-JEPA 2', 'kind': 'Video encoder for TRIBE', 'count': 'ViT-g, bfloat16', 'licence': 'Open', 'where': 'Hugging Face cache', 'ready': model('facebook/vjepa2-vitg-fpc64-256'), 'needs_person': ''},
        {'name': 'Isaac Sim 6.2', 'kind': 'Renderer', 'count': 'Headless, masks per object', 'licence': 'NVIDIA licence', 'where': 'feasibility/isaac/.venv', 'ready': (FE / 'isaac/.venv').exists(), 'needs_person': ''},
        {'name': 'Cosmos3 Nano Sim-Transfer', 'kind': 'World model', 'count': 'About 4 min per 4 s clip here', 'licence': 'NVIDIA open model', 'where': 'Hugging Face cache', 'ready': model('nvidia/Cosmos3-Nano-Sim-Transfer'), 'needs_person': ''},
        {'name': 'SigLIP so400m', 'kind': 'Image embeddings for search', 'count': '3,562 images embedded', 'licence': 'Apache 2.0', 'where': 'Hugging Face cache', 'ready': model('google/siglip-so400m-patch14-384'), 'needs_person': ''},
        {'name': 'BERG encoders', 'kind': 'Other brain models', 'count': '23 encoders', 'licence': 'Not checked', 'where': 'Not installed', 'ready': False, 'needs_person': 'Read BERG terms and the NSD agreement'},
    ]
    return out


ASSUMPTIONS = [
    # Each applies to some kinds of world. Evidence that a project in the store measured is read from it at request time.
    {'text': 'The pipeline detects a known effect', 'worlds': ['counter', 'stage', 'fall'], 'status': 'Untested',
     'evidence': 'Run a positive control from the Check a contrast template', 'from_note': 'Positive control'},
    {'text': 'Asset labels are correct', 'worlds': ['counter', 'fall'], 'status': 'Tested',
     'evidence': '15 of 1,013 Palatial labels flagged by image embedding; flagged items removed or reviewed'},
    {'text': 'Objects are the same size on screen across conditions', 'worlds': ['counter'], 'status': 'Tested',
     'evidence': 'The camera is framed to each object; a fixed camera gave a smaller effect'},
    {'text': 'Every hidden object covers a comparable share of the frame', 'worlds': ['stage'], 'status': 'Untested',
     'evidence': 'Effects and share of the frame correlate across objects; compare against size before reading an object'},
    {'text': 'Motion is matched across conditions', 'worlds': ['fall'], 'status': 'Untested',
     'evidence': 'Use the matched-motion outcome as a control'},
    {'text': 'One average viewer stands in for people', 'worlds': ['counter', 'stage', 'fall'], 'status': 'Known limit',
     'evidence': 'Meta reports r about 0.07 to 0.09 against one unseen person on video'},
    {'text': 'TRIBE responds to renders as it does to film', 'worlds': ['counter', 'stage', 'fall'], 'status': 'Untested',
     'evidence': 'A Cosmos restyle moved predicted responses more than any category effect here'},
    {'text': 'Anatomical regions stand in for functional ones', 'worlds': ['counter', 'stage', 'fall'], 'status': 'Untested',
     'evidence': 'Functional regions need measured data, such as the Natural Scenes Dataset'},
]


def assumptions(store, project_id: str) -> list[dict]:
    """The assumptions that apply to this project's world, with evidence read live from any project that tested one."""
    P = store.get('project', project_id); kind = (P.data.get('world') or {}).get('kind') if P else None
    out = []
    for a in ASSUMPTIONS:
        if kind and kind not in a['worlds']: continue
        row = {k: a[k] for k in ('text', 'status', 'evidence')}
        if a.get('from_note'):   # a project marked as this check, with a result: its own numbers, its own title
            for p in store.list('project'):
                if a['from_note'] in (p.data.get('note') or ''):
                    res = [r.data for r in store.list('result') if r.data.get('project_id') == p.id and r.data.get('regions') and 'interval_95' in r.data['regions'][0]]
                    if res:
                        top = res[0]['regions'][0]
                        row.update(status='Tested', evidence=f"{p.data['title']}: {top['region']} {top['value']:+.3f}, interval {top['interval_95'][0]:+.3f} to {top['interval_95'][1]:+.3f}")
                        break
        out.append(row)
    return out


NAMES = {'isaac': 'Isaac Sim', 'cosmos': 'Cosmos 3 Nano', 'tribe': 'TRIBE v2', 'vjepa': 'V-JEPA 2'}


def _remote_state() -> tuple[str, str]:
    """Rendering and brain prediction where render-score runs them (the cluster's video workstation): the jobs this app has
    in flight there, by model, or "Not running" when render-score cannot be found."""
    from . import preview
    from ..config import render_score_url
    try: render_score_url()
    except Exception: return 'Not running', 'Not running'
    q = preview._q
    live = [j for j in (q.jobs.values() if q else []) if j.status in ('queued', 'running')]
    def say(prefixes):
        js = [j for j in live if j.connector_id.split('_')[0] in prefixes]
        if not js: return 'Idle'
        names = list(dict.fromkeys(NAMES[j.connector_id.split('_')[0]] for j in js))
        n = sum(j.status == 'running' for j in js)
        return f"{', '.join(names)}: {n} running" + (f', {len(js) - n} waiting' if len(js) > n else '')
    return say(('isaac', 'cosmos')), say(('tribe', 'vjepa'))


def machine() -> dict:
    import subprocess
    from . import preview
    from .planner_agent import label
    if preview.remote():   # the workers run in render-score, on another machine: ask the queue, not this machine's processes
        world, brain = _remote_state()
        return {'agent': label(), 'world_node': world, 'brain_node': brain}
    try: ps = subprocess.run(['ps', '-eo', 'args'], capture_output=True, text=True).stdout.splitlines()
    except OSError: ps = []   # an image without ps (python:3.12-slim on the cluster): no local workers to report
    jobs = []
    for line in ps:
        if 'isaac/.venv' in line and '.py' in line: jobs.append(('World node', 'Isaac Sim: ' + Path(line.split()[1]).stem.replace('_', ' ')))
        elif re.search(r'test\d+\w*\.py|tribe_worker\.py', line) and '.venv/bin/python' in line: jobs.append(('Brain node', 'TRIBE: ' + Path(line.split()[1]).stem.replace('_', ' ')))
    jobs = list(dict.fromkeys(jobs))
    world = next((j for n, j in jobs if n == 'World node'), None); brain = next((j for n, j in jobs if n == 'Brain node'), None)
    return {'agent': label(), 'world_node': world or 'Idle', 'brain_node': brain or 'Idle'}


def search_egobody_moments(n: int = 6) -> dict:
    """The body world's search: from EgoBody's decision points to the n moments with the most upper-body motion, by
    the rule in feasibility/observer/motion_lib.py (the same one observer/motions.py uses). Every count from the files."""
    import os, sys, glob
    cache = ROOT / 'backend' / 'data' / 'files' / 'search' / f'egobody_moments_{n}.json'
    if cache.exists(): return json.load(open(cache))
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'studies' / 'observer')); from motion_lib import pick_moments, WORK, ROOT as EGO   # Simulaxon's own study code
    E = np.load(os.path.join(WORK, 'episodes.npz'), allow_pickle=True); recs = sorted(set(E['rec']))
    def usable(r):
        sc = str(np.load(os.path.join(WORK, 'cams', r + '.npz'), allow_pickle=True)['scene'])
        return (os.path.exists(os.path.join(EGO, 'scene_mesh', sc, sc + '.obj')) and bool(glob.glob(f'{EGO}/smplx_camera_wearer_*/{r}/body_idx_*/results'))
                and bool(glob.glob(f'{EGO}/smplx_interactee_*/{r}/body_idx_*/results')))
    ok = {r for r in recs if usable(r)}
    P = pick_moments(n)
    lab = lambda r, k: f"{r.replace('recording_', '').replace('_', ' ')}, moment {k}"
    all_m = [{'name': lab(r, int(k)), 'rec': r, 'k': int(k)} for r, k in zip(E['rec'], E['k'])]
    s1 = [m for m in all_m if m['rec'] in ok]
    fitted = {(x[0], x[2]) for x in P['with_fits']}; s2 = [m for m in s1 if (m['rec'], m['k']) in fitted]
    bestset = {(x[0], x[2]) for x in P['best_per_recording']}; s3 = [m for m in s2 if (m['rec'], m['k']) in bestset]
    pickset = {(x[0], x[2]) for x in P['picked']}; s4 = [m for m in s3 if (m['rec'], m['k']) in pickset]
    speed = {(x[0], x[2]): x[1] for x in P['with_fits']}
    steps = [{'label': 'Moments of real social interaction', 'query': "moments in EgoBody's recordings", 'kept': len(all_m), 'removed': 0, 'removed_rows': []},
             _step('In a scanned room, both bodies tracked', 'room scan, both bodies tracked', all_m, s1, lambda r: 'no scan or no body tracking'),
             _step('Body tracked in at least 100 of 271 frames', "the wearer's body over the moment's 9 s", s1, s2, lambda r: 'body tracked in too few frames'),
             _step('The moment that moves most, per recording', 'median angular speed of the 13 upper-body joints', s2, s3,
                   lambda r: f"{speed[(r['rec'], r['k'])]:.2f} rad/s, below its recording's best"),
             _step(f'The {n} recordings whose best moment moves most', 'sorted by that speed', s3, s4, lambda r: f"{speed[(r['rec'], r['k'])]:.2f} rad/s")]
    out = {'reading': f'A moment is 9 s of a real recorded conversation. Each recording gives the moment where the wearer moves most, and the {n} that move most are kept.',
           'source': 'EgoBody, ETH Zurich: first-person recordings of two people talking, both bodies tracked, rooms scanned',
           'steps': steps,
           'picked': [{'id': f"{r}#{k}", 'rec': r, 'k': k, 'label': f'Moment {i + 1}', 'source': lab(r, k), 'speed_rad_s': round(sp, 3)}   # plain names on screen; the recording stays in the data
                      for i, (r, sp, k, t, nf) in enumerate(P['picked'])]}
    cache.parent.mkdir(parents=True, exist_ok=True); json.dump(out, open(cache, 'w'), indent=1)
    return out
