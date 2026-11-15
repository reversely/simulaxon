"""The Experimental section (#25): the robotic empathy programme, held apart from the established experiments.

Its first study is visual-cortex-lab test 18 (feasibility/so101/PLAN.md), run on the Spark on 13 Nov 2026: a simulated
SO-101 choosing among four grasps, with TRIBE v2's prediction of a person watching it as an added input stream, against
the same stream unpaired and against controls. Every number here is read from that run's files at request time
(feasibility/data/so101/grasp/main/results.json and check.json); statements about the result are computed from them.
Each grasp candidate can be played as a recording (#23): its third-person clip (the view TRIBE was given), TRIBE v2's
prediction, the arm's joints over the same 6 s, and the grasp's phases.
"""
from __future__ import annotations
import csv, io, json
from pathlib import Path
import numpy as np

from ..home import HOME

RUN = HOME / 'feasibility' / 'data' / 'so101' / 'grasp' / 'main'
JOINTS = ['shoulder_pan', 'shoulder_lift', 'elbow_flex', 'wrist_flex', 'wrist_roll', 'gripper']   # tracks.npz q columns (so101/kin.py ARM, then the gripper)
PHASES = [(0, 'home'), (1, 'above the object'), (2.5, 'descend'), (3.5, 'close'), (4.5, 'settle')]   # PLAN.md, grasp trial
STREAM_S = 6.0
LABELS = {'P+V': 'Joints and cameras', 'P+V+T paired': '+ TRIBE v2, paired', 'P+V+T swapped': "+ TRIBE v2, another trial's",
          'P+V+T shifted': '+ TRIBE v2, 3 s earlier', 'P+V+R': '+ V-JEPA 2 through a random map (no brain)',
          'P+V+C paired (positive control)': '+ contact sensing, paired', 'P+V+C swapped (positive control)': "+ contact sensing, another trial's",
          'P+V+N "paired" (negative control)': '+ noise, "paired"', 'P+V+N swapped (negative control)': "+ noise, another trial's"}
ROLE = {'P+V': 'ordinary streams', 'P+V+T paired': 'candidate', 'P+V+T swapped': 'unpaired', 'P+V+T shifted': 'unpaired', 'P+V+R': 'same form, no brain',
        'P+V+C paired (positive control)': 'positive control', 'P+V+C swapped (positive control)': 'positive control',
        'P+V+N "paired" (negative control)': 'negative control', 'P+V+N swapped (negative control)': 'negative control'}


def _label(k: str) -> str:
    return ' minus '.join(LABELS.get(p.strip(), p.strip()).lstrip('+ ') for p in k.split(' minus '))


def _cand(trial: str, cand: str) -> Path:
    p = (RUN / trial / cand).resolve()
    if not p.is_relative_to(RUN.resolve()) or not (p / 'outcome.json').exists(): raise ValueError(f'no grasp {trial}/{cand}')
    return p


def examples(n_trials: int = 2) -> list[dict]:
    """Grasps from held-out trials where one candidate held under the gentle shake and another did not, in trial order."""
    out = []
    for t in sorted(p for p in RUN.glob('standard_t*') if p.is_dir()):
        cs = {}
        for c in sorted(t.glob('c*')):
            if (c / 'clip_third.mp4').exists() and (c / 'tribe_third.npy').exists():
                cs[c.name] = json.loads((c / 'outcome.json').read_text())
        held = [k for k, o in cs.items() if o['held']['gentle']]; lost = [k for k, o in cs.items() if not o['held']['gentle']]
        if held and lost:
            for k in (held[0], lost[0]):
                o = cs[k]; out.append({'trial': t.name, 'candidate': k, 'held_gentle': o['held']['gentle'], 'held_firm': o['held']['firm'], 'lifted': o['lifted'],
                                       'object': f"{o['object']['shape']}, {round(o['object']['mass_kg'] * 1000)} g", 'grip_nm': round(o['grip_nm'], 3)})
        if len(out) >= 2 * n_trials: break
    return out


def study() -> dict:
    """The study, its run's results as tables, and computed statements. Raises if the run's files are not on this machine."""
    r = json.loads((RUN / 'results.json').read_text()); c = json.loads((RUN / 'check.json').read_text())
    shakes = {}
    for shake, b in r['by_shake'].items():
        s = b['splits']['standard']; base = s['random_candidate']
        rows = [{'stream': k, 'label': LABELS.get(k, k), 'role': ROLE.get(k, ''), 'held': v, 'auc': s['auc'].get(k)} for k, v in s['held_when_choosing'].items()]
        diffs = [{'contrast': k, 'label': _label(k), 'held': d['held'], 'ci95': d['ci95']} for k, d in s['differences'].items()]
        shakes[shake] = {'trials': s['trials'], 'random_candidate': base, 'oracle': s['oracle'], 'rows': rows, 'differences': diffs,
                         'all_below_random': all(x['held'] < base for x in rows), 'held_range': [min(x['held'] for x in rows), max(x['held'] for x in rows)],
                         'auc_range': [min(x['auc'] for x in rows if x['auc'] is not None), max(x['auc'] for x in rows if x['auc'] is not None)]}
    gates = [{'gate': k, 'result': v} for k, v in sorted({**c.get('gates', {}), **r.get('gates', {})}.items())]
    return {'id': 'robot_observer_grasp', 'experimental': True,
            'title': 'Grasp selection by a simulated SO-101 arm with the predicted cortical response of a human observer as an added input stream',
            'question': "Does a simulated robot pick grasps that hold more often when it also has TRIBE v2's prediction of a person watching it, than with the same stream unpaired?",
            'programme': 'Robotic empathy: which measured or predicted human reactions to a robot can serve as a signal for its behaviour, and beyond what its own inputs carry.',
            'design': [
                ['Robot', 'SO-101 (official URDF), Isaac Sim 6.2, PhysX CPU at 240 Hz, a fresh process per grasp'],
                ['Task', 'Four candidate grasps per object (height, offset, roll, grip torque); each is executed, lifted 15 cm and shaken gently and firmly; it holds if the object stays between both jaws'],
                ['Choice', 'A model trained on 120 trials predicts which candidate holds from the streams of the first 6 s; the robot takes the highest'],
                ['Streams', "Joints and the arm's two cameras (V-JEPA 2 features); TRIBE v2 on the third-person view, 360 HCP-MMP1 areas, last 2 s"],
                ['Unpaired and controls', "TRIBE v2 from another trial, or 3 s earlier; V-JEPA 2 through a random map to the cortex (no brain); contact sensing (positive control, known to carry holding); noise (negative control)"],
                ['Test', f"{shakes['gentle']['trials']} held-out trials in standard scenes; differences by paired bootstrap over trials, 95% intervals"]],
            'run': {'when': '13 Nov 2026, on the Spark', 'candidates': c['candidates_run'], 'lifted': c['lifted'], 'held_gentle': c['held_gentle'], 'held_firm': c['held_firm'],
                    'joint_stream_only_auc': c.get('joint_stream_only_auc'), 'repeats_identical': f"{sum(1 for x in c.get('repeat', []) if x.get('labels_identical'))} of {len(c.get('repeat', []))}"},
            'shakes': shakes, 'gates': gates,
            'scope': "It can say whether, in this simulation, the predicted response of a person watching let the robot choose grasps that hold more often than the same stream unpaired. It cannot say anything about human brains, real cameras or the real arm's physics.",
            'source': 'visual-cortex-lab feasibility/so101/PLAN.md, test 18', 'examples': examples()}


def manifest(trial: str, cand: str) -> dict:
    """One grasp candidate as a recording (#23)."""
    p = _cand(trial, cand); o = json.loads((p / 'outcome.json').read_text())
    return {'format': 'simulaxon.recording', 'version': 1, 'duration_s': STREAM_S,
            'title': f"{trial} {cand}: {o['object']['shape']}, {'held' if o['held']['gentle'] else 'did not hold'} under the gentle shake",
            'streams': [{'name': 'third-person view', 'kind': 'video', 'file': 'clip_third.mp4'},
                        {'name': 'tribe', 'kind': 'tribe', 'file': 'tribe_third.npy', 'rate_hz': 1, 'space': 'fsaverage5', 'model': 'TRIBE v2'},
                        {'name': 'joints', 'kind': 'table', 'file': 'joints.csv', 'time_column': 't', 'units': 'rad'},
                        {'name': 'phases', 'kind': 'events', 'file': 'phases.csv', 'time_column': 't', 'label_column': 'label'}],
            'source': {'study': 'robot_observer_grasp', 'trial': trial, 'candidate': cand}}


def file(trial: str, cand: str, name: str) -> tuple[bytes | Path, str]:
    """A file of a grasp's recording: the stored clip or predictions, or the joints and phases as CSV."""
    p = _cand(trial, cand)
    if name == 'recording.json': return json.dumps(manifest(trial, cand)).encode(), 'application/json'
    if name in ('clip_third.mp4', 'tribe_third.npy'): return p / name, 'video/mp4' if name.endswith('.mp4') else 'application/octet-stream'
    if name == 'joints.csv':
        z = np.load(p / 'tracks.npz'); keep = z['t'] <= STREAM_S + 1e-9; s = io.StringIO(); w = csv.writer(s); w.writerow(['t'] + JOINTS)
        for t, q in list(zip(z['t'][keep], z['q'][keep]))[::6]: w.writerow([f'{t:.3f}'] + [f'{x:.4f}' for x in q])   # 60 Hz to 10 Hz
        return s.getvalue().encode(), 'text/csv'
    if name == 'phases.csv':
        return ('t,label\n' + ''.join(f'{t},{l}\n' for t, l in PHASES)).encode(), 'text/csv'
    raise ValueError(f'no file {name}')
