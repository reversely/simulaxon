"""Seeded examples: classic experiments the field already knows, each shown by its real stimulus playing, each linked to the project it ran in here, or to a
goal the agent can start from. What each says about its own run is read from that project, never written here.

The owner (2026-11-14): seed the examples with experiments of real significance in the field, such as those raised in
the conversation, because everyone in the field already understands them.
"""
from __future__ import annotations
import json
from pathlib import Path
from .ingest import FILES, ROOT

EXAMPLES = [
    {'id': 'rivalry', 'title': 'A face to one eye, a house to the other', 'what': 'What you see switches between the two, every few seconds.',
     'source': 'Tong, Nakayama, Vaughan and Kanwisher, 1998', 'doi': '10.1016/S0896-6273(00)80592-9',
     'media': ['examples/rivalry.mp4'], 'project_title': 'A face to one eye, a house to the other',
     'goal': 'Replicate the binocular rivalry result of Tong, Nakayama, Vaughan and Kanwisher 1998 (doi 10.1016/S0896-6273(00)80592-9) with faces and houses, as far as a model with one picture stream allows.'},
    {'id': 'flash', 'title': 'A flash every 4 seconds', 'what': 'Follow a simple flash of light through the visual areas.',
     'source': 'Logothetis and others, 2001: electrodes and fMRI at once', 'doi': '10.1038/35084005',
     'media': ['examples/flash.mp4'], 'project_title': 'A flash every 4 seconds',
     'goal': 'Show a full-field flash every few seconds and follow its response through the visual areas, after Logothetis and others 2001 (doi 10.1038/35084005).'},
    {'id': 'faces', 'title': 'Faces against objects', 'what': 'An area on the underside of the brain responds most to faces.',
     'source': 'Kanwisher, McDermott and Chun, 1997', 'doi': '10.1523/JNEUROSCI.17-11-04302.1997',
     'media': ['examples/faces_objects.mp4'], 'project_title': 'Kanwisher 1997 FFA: faces vs objects',
     'goal': 'Replicate the main result of Kanwisher, McDermott and Chun 1997 (doi 10.1523/JNEUROSCI.17-11-04302.1997) with public stimuli.'},
    {'id': 'humanoid', 'title': 'A robot that moves like a person', 'what': "How a humanoid's look and motion register in the area that reads actions.",
     'source': 'Saygin and others, 2012', 'doi': '10.1093/scan/nsr025',
     'media': ['examples/humanoid.mp4'], 'project_title': 'Humanoid look against motion',
     'goal': 'Replicate Saygin and others 2012 (doi 10.1093/scan/nsr025): a body whose look and motion disagree, with the G1 and a human body in a scanned room.'},
    {'id': 'fit_person', 'title': 'Fit the model to one person', 'what': "How many of one person's scans it takes to predict their brain.",
     'source': "d'Ascoli and others, 2026, the model's own paper", 'doi': '10.48550/arXiv.2605.04326',
     'media': ['examples/action_clips.mp4'], 'project_title': None, 'result_file': 'feasibility/data/had/personalize.json',
     'goal': "Fit the brain model to one person of the Human Action Dataset from their own scans, and compare with the released model and a fit to everyone else."},
    {'id': 'photoreal', 'title': 'Simulated against photoreal', 'what': 'Does the brain respond the same once a render looks real?',
     'source': 'No classic paper yet', 'doi': None,
     'media': ['examples/photoreal.mp4'], 'project_title': 'The G1 in the EgoBody room, Isaac Sim against Cosmos',
     'goal': 'Compare Isaac Sim renders with their Cosmos versions in TRIBE, with at least two Cosmos seeds and the renders as their own condition.'},
]


def listing(store) -> list[dict]:
    """Every example with what has run here, read from its project or its result file."""
    by_title = {p.data.get('title'): p for p in store.list('project')}
    out = []
    for e in EXAMPLES:
        p = by_title.get(e['project_title']) if e['project_title'] else None
        here, project_id = None, None
        if p is not None:
            project_id = p.id; d = p.data; clips = (d.get('counts') or {}).get('clips')
            here = (f'{clips} clips run here' if clips else 'Set up here') if d.get('status') == 'Done' else f"{d.get('status')} here"
        elif e.get('result_file') and (ROOT / e['result_file']).exists():
            r = json.loads((ROOT / e['result_file']).read_text()); s = r['summary']
            here = f"Fitted here for {r['people']} people: r {s['released']['mean']:.2f} as released, {s['person']['mean']:.2f} fitted"
        out.append({k: e[k] for k in ('id', 'title', 'what', 'source', 'doi', 'goal')} | {'media': ['/files/' + i for i in e['media'] if (FILES / i).exists()],
                                                                                          'project_id': project_id, 'here': here or 'Not run yet'})
    return out
