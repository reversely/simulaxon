"""Seeded examples: classic experiments the field already knows, each shown by its real stimulus playing, each linked to the project it ran in here, or to a
goal the agent can start from. What each says about its own run is read from that project, never written here.
Each has a kind, which the start sheet groups them by: "replication" (a published result rerun on the model),
"fine_tuning" (fitting the model to measured fMRI) or "new" (a question no paper has run).

The owner (2026-11-14): seed the examples with experiments of real significance in the field, such as those raised in
the conversation, because everyone in the field already understands them.
"""
from __future__ import annotations
import json
from pathlib import Path
from .ingest import FILES, ROOT

EXAMPLES = [
    {'id': 'rivalry', 'kind': 'replication', 'title': 'Face and house binocular rivalry', 'what': 'What you see switches between the two, every few seconds.',
     'source': 'Tong, Nakayama, Vaughan and Kanwisher, 1998', 'doi': '10.1016/S0896-6273(00)80592-9',
     'media': ['examples/rivalry.mp4'], 'project_title': 'Face and house binocular rivalry in one stream (after Tong et al., 1998)',
     'goal': 'Replicate the binocular rivalry result of Tong, Nakayama, Vaughan and Kanwisher 1998 (doi 10.1016/S0896-6273(00)80592-9) with faces and houses, as far as a model with one picture stream allows.'},
    {'id': 'flash', 'kind': 'replication', 'title': 'Periodic full-field flash', 'what': 'Follow a simple flash of light through the visual areas.',
     'source': 'Logothetis and others, 2001: electrodes and fMRI at once', 'doi': '10.1038/35084005',
     'media': ['examples/flash.mp4'], 'project_title': 'Periodic full-field flash stimulation at 0.25 Hz (after Logothetis et al., 2001)',
     'goal': 'Show a full-field flash every few seconds and follow its response through the visual areas, after Logothetis and others 2001 (doi 10.1038/35084005).'},
    {'id': 'faces', 'kind': 'replication', 'title': 'Face versus object selectivity', 'what': 'An area on the underside of the brain responds most to faces.',
     'source': 'Kanwisher, McDermott and Chun, 1997', 'doi': '10.1523/JNEUROSCI.17-11-04302.1997',
     'media': ['examples/faces_objects.mp4'], 'project_title': 'Face versus object selectivity in the fusiform face area (Kanwisher et al., 1997)',
     'goal': 'Replicate the main result of Kanwisher, McDermott and Chun 1997 (doi 10.1523/JNEUROSCI.17-11-04302.1997) with public stimuli.'},
    {'id': 'humanoid', 'kind': 'replication', 'retired': 'its human is a bare SMPL-X mesh (owner, 15 Nov 2026)', 'title': 'Appearance and motion congruence of a humanoid', 'what': "How a humanoid's look and motion register in the area that reads actions.",
     'source': 'Saygin and others, 2012', 'doi': '10.1093/scan/nsr025',
     'media': ['examples/humanoid.mp4'], 'project_title': 'Appearance and motion congruence of a humanoid robot (after Saygin et al., 2012)',
     'goal': 'Replicate Saygin and others 2012 (doi 10.1093/scan/nsr025): a body whose look and motion disagree, with the G1 and a human body in a scanned room.'},
    {'id': 'fit_person', 'kind': 'fine_tuning', 'title': 'Subject-specific encoding-model fitting', 'what': "How many of one person's scans it takes to predict their brain.",
     'source': "d'Ascoli and others, 2026, the model's own paper", 'doi': '10.48550/arXiv.2605.04326',
     'media': ['examples/action_clips.mp4'], 'project_title': None, 'result_file': 'feasibility/data/had/personalize.json', 'dataset_id': 'openneuro_ds004488',
     'goal': "Fit the brain model to one person of the Human Action Dataset from their own scans, and compare with the released model and a fit to everyone else."},
    {'id': 'photoreal', 'kind': 'new', 'title': 'Simulated versus photoreal renders', 'what': 'Does the brain respond the same once a render looks real?',
     'source': 'No classic paper yet', 'doi': None,
     'media': ['examples/photoreal.mp4'], 'project_title': 'Simulated versus Cosmos-restyled renders of a humanoid in an EgoBody scene',
     'goal': 'Compare Isaac Sim renders with their Cosmos versions in TRIBE, with at least two Cosmos seeds and the renders as their own condition.'},
]


def listing(store) -> list[dict]:
    """Every example with what has run here, read from its project or its result file."""
    by_title = {p.data.get('title'): p for p in store.list('project')}
    out = []
    for e in EXAMPLES:
        if e.get('retired'): continue   # taken out of the app; the entry stays for its history
        p = by_title.get(e['project_title']) if e['project_title'] else None
        here, project_id = None, None
        if p is not None:
            project_id = p.id; d = p.data; clips = (d.get('counts') or {}).get('clips')
            here = (f'{clips} clips run here' if clips else 'Set up here') if d.get('status') == 'Done' else f"{d.get('status')} here"
        elif e.get('result_file') and (ROOT / e['result_file']).exists():
            r = json.loads((ROOT / e['result_file']).read_text()); s = r['summary']
            here = f"Fitted here for {r['people']} people: r {s['released']['mean']:.2f} as released, {s['person']['mean']:.2f} fitted"
        out.append({k: e[k] for k in ('id', 'kind', 'title', 'what', 'source', 'doi', 'goal')} | {'dataset_id': e.get('dataset_id'), 'media': ['/files/' + i for i in e['media'] if (FILES / i).exists()],
                                                                                          'project_id': project_id, 'here': here or 'Not run yet',
                                                                                          'brain': _brain(store, project_id) if project_id else _adapter_brain(store, e.get('dataset_id'))})
    return out


_SCORES: dict[str, float] = {}


def _colour(rel: str) -> float:
    """How much of a rendered map is coloured, not grey surface: the mean saturation of its visible pixels. Cached."""
    if rel not in _SCORES:
        try:
            from PIL import Image
            import numpy as np
            a = np.asarray(Image.open(FILES / rel).convert('RGBA'), np.float32)
            seen = a[..., 3] > 0; rgb = a[..., :3][seen]
            _SCORES[rel] = float((rgb.max(1) - rgb.min(1)).mean()) if len(rgb) else 0.0
        except OSError:
            _SCORES[rel] = -1.0
    return _SCORES[rel]


def _shown(views: dict, title: str) -> dict | None:
    """A map as an example card shows it: the view with the most response in colour, and what the map is."""
    have = {v: rel for v, rel in (views or {}).items() if (FILES / rel).exists()}
    if not have: return None
    v = max(have, key=lambda k: _colour(have[k]))
    return {'image': '/files/' + have[v], 'view': v, 'title': title}


def _brain(store, project_id: str) -> dict | None:
    """The brain's predicted response beside the stimulus on an example's card: the project's first contrast map."""
    maps = {m.id: m.data for m in store.list('neural_map') if m.data.get('project_id') == project_id}
    titles = {a.id: a.data.get('title') for a in store.list('analysis') if a.data.get('project_id') == project_id}
    P = store.get('project', project_id); first = [c.get('name') for c in (((P.data if P else {}).get('experiment') or {}).get('contrasts') or []) if isinstance(c, dict)]
    rank = lambda r: (first.index(t) if (t := titles.get(r.data.get('analysis_id'))) in first else len(first), str(t))   # the set-up's first contrast leads
    for r in sorted(store.list('result'), key=rank):
        m = maps.get(r.data.get('map_id'))
        if r.data.get('project_id') == project_id and m:
            return _shown(m.get('views'), titles.get(r.data.get('analysis_id')) or m.get('title') or 'Contrast')
    return None


def _adapter_brain(store, dataset_id: str | None) -> dict | None:
    """For an example with no project, the newest adapter fitted on its dataset: where it predicts measured fMRI better than TRIBE v2."""
    rows = sorted((a for a in store.list('adapter') if dataset_id and a.data.get('dataset_id') == dataset_id), key=lambda a: a.id, reverse=True)
    if not rows: return None
    from . import adapter, maps
    a = rows[0].data
    gain = adapter.area_map([{**x, 'gain': x['adapter_r'] - x['tribe_v2_r']} for x in a['areas']], 'gain')
    return _shown(maps.render(gain, 'contrast', FILES)['views'], f"{a['name']}: adapter minus TRIBE v2, r per area")
