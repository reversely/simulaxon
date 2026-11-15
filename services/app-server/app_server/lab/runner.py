"""Run a whole project: every sample of its plan through Isaac and TRIBE, then its analyses. The same path as a live
preview (preview.render_and_read), so a run and a preview of the same values give the same numbers.

Matched plans run each pair as two sets of parameter changes, such as {"item": a} against {"item": b}, or
{"item": x, "outcome": "hovers"} against {"item": x, "outcome": "lands"}; every other parameter keeps its current value.
Factorial plans run every unit in every cell of the template's factors, such as {"moment": m, "body": "g1", "motion":
"robotic"}, then the template's contrasts. Progress is broadcast as
{"run": project_id, "done": k, "total": n}; the project goes Running, then Done with its samples and analyses.
"""
from __future__ import annotations
import hashlib, json, threading
from pathlib import Path
from . import plans, worlds
from .ingest import FILES
from .preview import render_and_read, REVISION, _label


SHUTTING_DOWN = threading.Event()
STOP: set[str] = set()   # projects whose run a person or the agent stopped (run_stop); each run checks between clips


def start(tools, broadcast, project_id: str, actor: str):
    s = tools.store; P = s.get('project', project_id)
    d = P.data; w = d.get('world'); pairs = d.get('pairs')
    if d.get('plan') == 'factorial': return _factorial(tools, broadcast, project_id, actor)
    if d.get('plan') == 'experiment':   # set up from data by experiment_create: any paper, any stimuli
        from . import experiment
        return experiment.run(tools, broadcast, project_id, actor)
    if not w or not pairs: raise ValueError('This project has no world or no pairs to run yet')
    if d.get('plan') != 'matched': raise ValueError('Only matched plans run from the app so far')
    params = {r.data['name']: r.data['value'] for r in s.list('parameter') if r.data.get('project_id') == project_id}
    assets = tools.all_assets(project_id); labels = tuple(d.get('labels') or ('First', 'Second'))
    tools.call('project_update', actor, project_id=project_id, expect_version=P.version, status='Running')
    out = FILES / 'runs' / 'clips'   # shared by content key, so a clip rendered ahead for a demo, or by another run, is reused

    def go():
        ev = lambda **k: broadcast({'run': project_id, **k})
        try:
            units, total, k = [], 2 * len(pairs), 0
            for i, (a, b) in enumerate(pairs):
                side = {}
                for cond, change in (('a', a), ('b', b)):
                    change = change if isinstance(change, dict) else {'item': change}   # older projects stored bare asset ids
                    vals = {**params, **change}; aid = change.get('item', '')
                    inputs = worlds.job(w['kind'], vals, assets, w)
                    key = hashlib.sha1(json.dumps([REVISION, inputs], sort_keys=True).encode()).hexdigest()[:14]
                    res = render_and_read(inputs, out, key, 'batch', ctx={'project': project_id, 'title': d.get('title'), 'label': _label(vals, assets), 'source': f'Run, {k + 1} of {total}', 'actor': actor}); k += 1; ev(done=k, total=total, image=f'/files/runs/clips/{key}.png')
                    side[cond] = {'label': assets.get(aid, {}).get('label', aid), 'image': Path(res['rgb']), 'clip': Path(res['clip_on']), 'preds': Path(res['preds'])}
                units.append({'unit': f'pair {i + 1}', **side})
            url = lambda p: '/files/' + str(Path(p).resolve().relative_to(FILES.resolve())) if p else None
            with tools.lock:
                step = s.begin(actor, 'project_run', {'project_id': project_id})
                plans.matched(s, step, project_id, units, (0, 3), labels, FILES, url)
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Done',
                       counts={'units': len(units), 'clips': total}, run_values=params)
            ev(stage='done')
        except Exception as e:
            if SHUTTING_DOWN.is_set(): return   # the server is stopping, not the run failing; start-up resumes it
            import traceback; print(f'run {project_id} failed:', flush=True); traceback.print_exc()
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Draft')
            ev(stage='failed', error=str(e)[-300:])
    threading.Thread(target=go, daemon=True).start()
    return {'queued': True, 'clips': 2 * len(pairs)}


def _factorial(tools, broadcast, project_id: str, actor: str):
    """Every unit (a world asset, such as a moment) in every cell of the template's factors, then its contrasts."""
    from . import templates
    s = tools.store; P = s.get('project', project_id); d = P.data; w = d.get('world'); units = d.get('units')
    if not w or not units: raise ValueError('This project has no world or no units to run yet')
    t = templates.get(d['template_id']); cells = t['cells']; unit_param = t['unit_parameter']
    params = {r.data['name']: r.data['value'] for r in s.list('parameter') if r.data.get('project_id') == project_id}
    assets = tools.all_assets(project_id); total = len(units) * len(cells)
    tools.call('project_update', actor, project_id=project_id, expect_version=P.version, status='Running')
    out = FILES / 'runs' / 'clips'

    def go():
        ev = lambda **k: broadcast({'run': project_id, **k})
        try:
            done, rows = 0, []
            for u in units:
                cl = {}
                for c in cells:
                    vals = {**params, unit_param: u, **c['values']}
                    inputs = worlds.job(w['kind'], vals, assets, w)
                    key = hashlib.sha1(json.dumps([REVISION, inputs], sort_keys=True).encode()).hexdigest()[:14]
                    res = render_and_read(inputs, out, key, 'batch', ctx={'project': project_id, 'title': d.get('title'), 'label': _label(vals, assets),
                                                                         'source': f'Run, {done + 1} of {total}', 'actor': actor})
                    done += 1; ev(done=done, total=total)
                    cl[c['id']] = {'label': _label(vals, assets), 'image': Path(res['rgb']), 'clip': Path(res['clip_on']), 'preds': Path(res['preds'])}
                rows.append({'unit': assets.get(u, {}).get('label', u), 'cells': cl})
            url = lambda p: '/files/' + str(Path(p).resolve().relative_to(FILES.resolve())) if p else None
            ev(stage='comparing')   # the contrasts, baselines and maps take several seconds: the page says so
            rec = plans.Deferred()   # computed without the store's lock; only the writes take it
            plans.factorial(rec, None, project_id, rows, tuple(t['window_s']), cells, t['contrasts'], FILES, url)
            with tools.lock:
                step = s.begin(actor, 'project_run', {'project_id': project_id})
                rec.apply(s, step)
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Done',
                       counts={'units': len(rows), 'clips': total}, run_values=params)
            ev(stage='done')
        except Exception as e:
            if SHUTTING_DOWN.is_set(): return
            import traceback; print(f'run {project_id} failed:', flush=True); traceback.print_exc()
            cur = s.get('project', project_id)
            tools.call('project_update', actor, project_id=project_id, expect_version=cur.version, status='Draft')
            ev(stage='failed', error=str(e)[-300:])
    threading.Thread(target=go, daemon=True).start()
    return {'queued': True, 'clips': total}
