"""Paper demos: a published experiment replayed in the app, step by step, in the paper's own order.

The engine is generic; each demo is a data file in demo_data/ (one per paper).
A demo is data. Each step says what the paper did, what the app does in its place, the tool calls that do it (made by
the agent through the same registry the panels use), what the screen shows, and which live result to read. Numbers in
the narration always come from tool results at play time, never from this file. References:
  $p:<id>            an existing project
  $made:<name>       a project made by an earlier step of this demo (found again by title on a replay)
  $pairs_from:<project>:<condition>:<condition>   pairs of the stimuli a selection kept under two conditions
  $option:<n>        for a control, the n-th of its options other than its current value, so every play makes a real change
"""
from __future__ import annotations
import copy
import json, threading, time
from pathlib import Path

DATA = Path(__file__).parent / 'demo_data'


def load() -> list[dict]:
    """Every demo the agent has written from a seed (demo_data/written/<id>.json). A seed names only a paper, its link and
    a template; nothing here or in the seeds names a step."""
    return [json.load(open(f)) for f in sorted((DATA / 'written').glob('*.json')) if not f.name.endswith('.hand.json')]


def seeds() -> list[dict]:
    return [json.load(open(f)) for f in sorted((DATA / 'seeds').glob('*.json'))]


DEMOS = load()


def get(demo_id: str) -> dict:
    for d in load():   # read fresh, so an edited or added demo file plays without a restart
        if d['id'] == demo_id: return d
    from ..store import Missing
    raise Missing(f"no demo {demo_id}")


class Player:
    """Plays one demo at a time. Every action is a tool call by the agent; every number read at play time."""

    def __init__(self, tools, broadcast):
        self.tools, self.broadcast = tools, broadcast
        self.state = {'demo': None, 'step': 0, 'status': 'idle', 'made': {}, 'narration': [], 'show': None, 'error': None}
        self.go = threading.Event(); self.skip = threading.Event(); self.stop_flag = False; self.thread = None
        self.waiting = {'run': set(), 'preview': set()}; self.borrowed = {}

    # ---------- references ----------
    def ref(self, v):
        if isinstance(v, str):
            if v.startswith('$p:'): return v[3:]
            if v.startswith('$made:'): return self.state['made'].get(v[6:])
            if v.startswith('$pairs_from:'):   # $pairs_from:$p:<project>:<condition>:<condition>
                _, _, src, c1, c2 = v.split(':')
                res = self.result(src, 'selection')
                return [[{'item': x}, {'item': y}] for x, y in zip(res['conditions'][c1]['ids'], res['conditions'][c2]['ids'])]
            if v.startswith('$pairs_first:'):   # $pairs_first:$p:<project>:<n>
                _, _, src, n = v.split(':')
                return copy.deepcopy(self.tools.store.get('project', src).data['pairs'][:int(n)])
            if v.startswith('$swap_outcome:'):
                _, _, src, old, new = v.split(':')
                P = self.tools.store.get('project', src).data
                return [[{**c, **({'outcome': new} if c.get('outcome') == old else {})} for c in pair] for pair in P['pairs']]
            return v
        if isinstance(v, dict): return {k: self.ref(x) for k, x in v.items()}
        if isinstance(v, list): return [self.ref(x) for x in v]
        return v

    def result(self, project_id, kind):
        for a in self.tools.call('analysis_list', 'agent', project_id=project_id):
            if a['analysis'].data['kind'] == kind and a['result']: return a['result'].data
        return None

    def reading(self, read):
        pid = self.ref(read['project']); r = self.result(pid, read['kind']) if pid else None
        if not r: return None
        if read['kind'] == 'paired':
            x = next(x for x in r['regions'] if x['region'] == read['region'])
            return {'region': x['region'], 'value': x['value'], 'interval_95': x['interval_95'], 'n': x['n'], 'units_positive': x['units_positive']}
        if read['kind'] == 'selection':
            c = r['conditions'][read['condition']]
            return {'condition': c['name'], 'score': c['score'], 'random_95': c['random_95'], 'share_random_at_least': c['share_random_at_least'],
                    'mean_a': c['mean_a'], 'mean_b': c['mean_b'], 'k': r['k'], 'n': r['n']}
        return None

    # ---------- control ----------
    def emit(self, **k):
        if 'error' in k: self.state['error'] = k['error']
        self.broadcast({'demo': self.state['demo'], **{x: self.state[x] for x in ('step', 'status', 'show')}, **k})

    def start(self, demo_id):
        self.stop()
        d = get(demo_id); self.stop_flag = False
        self.state = {'demo': demo_id, 'step': 0, 'status': 'playing', 'made': {}, 'narration': [], 'show': None, 'error': None}
        self.go.set(); self.thread = threading.Thread(target=self.play, args=(d,), daemon=True); self.thread.start()
        threading.Thread(target=self.prepare, args=(d,), daemon=True).start()
        return self.snapshot()

    def target(self, args):
        """The value a parameter_set action will set, worked out the same way play() does."""
        prm = self.tools.store.get('parameter', f"{args['project_id']}.{args['name']}")
        if prm is None: return None, None
        val = args['value']
        if isinstance(val, str) and val.startswith('$option:'):
            opts = [o for o in prm.data['options'] if o != prm.data['value']]; val = opts[int(val[8:]) % len(opts)]
        return prm, val

    def prepare_all(self):
        """At start-up: prepare every demo's live steps, so the first play does not wait on the GPU."""
        for d in load():
            try: self.prepare(d)
            except Exception as e: print(f'demo {d.get("id")} not prepared: {e}', flush=True)   # one stale demo never stops the server

    def prepare(self, d):
        """Render every live step of the demo ahead, in the background, so the step finds its result ready: previews on
        projects that exist, and every clip of a run on a project the demo will make, worked out the way runner.start does."""
        from . import preview
        made = {}   # name -> {'src', 'values', 'pairs'}, simulated without creating anything
        for s in d['steps']:
            for a in s.get('actions', []):
                if self.stop_flag: return
                args = a['args']; pid = args.get('project_id', '')
                if a['tool'] == 'project_create' and a.get('as') and str(args.get('from_project_id', '')).startswith('$p:'):
                    src = args['from_project_id'][3:]; S = self.tools.store.get('project', src)
                    if S: made[a['as']] = {'src': src, 'values': {r.data['name']: r.data['value'] for r in self.tools.store.list('parameter') if r.data.get('project_id') == src}, 'pairs': S.data.get('pairs')}
                elif str(pid).startswith('$made:') and pid[6:] in made:
                    m = made[pid[6:]]
                    if a['tool'] == 'parameter_set':
                        prm, val = self.target({**args, 'project_id': m['src']})
                        if prm is not None:
                            m['values'][args['name']] = val
                            preview.start(self.tools, self.broadcast, m['src'], 'agent', values=dict(m['values']), source='Prepared for the demo')
                    elif a['tool'] == 'project_update' and 'pairs' in args:
                        try: m['pairs'] = self.ref(args['pairs'])
                        except Exception: m['pairs'] = None
                    elif a['tool'] == 'project_run' and m['pairs']: self.prepare_run(m)
                elif a['tool'] == 'parameter_set' and str(pid).startswith('$p:'):
                    a2 = self.ref(args); prm, val = self.target(a2)
                    if prm is not None and prm.data['value'] != val:
                        preview.start(self.tools, self.broadcast, a2['project_id'], 'agent', values={a2['name']: val}, source='Prepared for the demo')

    def prepare_run(self, m):
        """Every clip a demo run will need, rendered ahead in the batch lane under the key the run will use."""
        import hashlib, json as _j
        from . import worlds
        from .ingest import FILES
        from .preview import render_and_read, REVISION, _label
        S = self.tools.store.get('project', m['src']).data; w = S.get('world'); assets = self.tools.all_assets(m['src'])
        def go():
            for a, b in m['pairs']:
                for change in (a, b):
                    if self.stop_flag: return
                    change = change if isinstance(change, dict) else {'item': change}
                    vals = {**m['values'], **change}; inputs = worlds.job(w['kind'], vals, assets, w)
                    key = hashlib.sha1(_j.dumps([REVISION, inputs], sort_keys=True).encode()).hexdigest()[:14]
                    try: render_and_read(inputs, FILES / 'runs' / 'clips', key, 'batch', ctx={'project': m['src'], 'title': S.get('title'), 'label': _label(vals, assets), 'source': 'Prepared for the demo', 'actor': 'agent'})
                    except Exception: pass
        threading.Thread(target=go, daemon=True).start()

    def control(self, action):
        if action == 'pause': self.go.clear(); self.state['status'] = 'paused'
        elif action == 'resume': self.go.set(); self.state['status'] = 'playing'
        elif action == 'next': self.skip.set(); self.go.set(); self.state['status'] = 'playing'
        elif action == 'stop': self.stop()
        else: raise ValueError('action must be pause, resume, next or stop')
        self.emit(); return self.snapshot()

    def stop(self):
        self.stop_flag = True; self.go.set(); self.skip.set()
        if self.thread and self.thread.is_alive(): self.thread.join(timeout=5)
        self.skip.clear(); self.state['status'] = 'idle'

    def snapshot(self):
        d = get(self.state['demo']) if self.state['demo'] else None
        return {**self.state, 'title': d and d['title'], 'paper': d and d['paper'], 'url': d and d['url'],
                'steps': d and [{'title': s['title'], 'flow': s['flow']} for s in d['steps']]}

    def notify(self, kind, project_id):   # called from the event stream: a run or preview finished
        self.waiting[kind].discard(project_id)

    def pause_point(self, seconds):
        t = time.time()
        while time.time() - t < seconds:
            if self.stop_flag: raise StopIteration
            if self.skip.is_set(): self.skip.clear(); return
            self.go.wait(); time.sleep(0.2)

    def play(self, d):
        try:
            for k, s in enumerate(d['steps']):
                if self.stop_flag: return
                self.state['step'] = k; self.state['status'] = 'playing'
                for a in s.get('actions', []):
                    args = self.ref(a['args'])
                    if a['tool'] == 'project_create' and args.get('from_project_id'):   # copy the study as it was, not mid-preview
                        self.give_back(only=args['from_project_id'])
                    if a.get('as') and a['tool'] == 'project_create':
                        args['made_by'] = f"demo {d['id']}"   # only this demo's own projects are reused; a study with the same title is never touched
                        found = [p for p in self.tools.store.list('project') if p.data.get('title') == args['title'] and p.data.get('made_by') == args['made_by']]
                        if found: self.state['made'][a['as']] = found[0].id; continue   # replay: reuse the earlier run, never redo it
                    if a['tool'] == 'project_run':
                        P = self.tools.store.get('project', args['project_id'])
                        if P.data.get('status') in ('Done', 'Running'):
                            if P.data['status'] == 'Running': self.waiting['run'].add(args['project_id'])
                            continue
                        self.waiting['run'].add(args['project_id'])
                    if a['tool'] == 'parameter_set':
                        prm, val = self.target(args)
                        if prm.data['value'] == val: continue
                        if prm.data['project_id'] not in self.state['made'].values(): self.borrowed.setdefault(prm.id, prm.data['value'])   # put back when the demo ends
                        self.waiting['preview'].add(args['project_id'])
                        self.tools.call('parameter_update', 'agent', parameter_id=prm.id, expect_version=prm.version, value=val); continue
                    if a['tool'] == 'project_update':
                        args['expect_version'] = self.tools.store.get('project', args['project_id']).version
                    out = self.tools.call(a['tool'], 'agent', **args)
                    if a.get('as'): self.state['made'][a['as']] = out.id
                show = self.ref(s.get('show', {})); self.state['show'] = show
                self.emit(narration={'title': s['title'], 'paper': s['paper'], 'here': s['here']})
                if s.get('wait'):
                    self.state['status'] = 'waiting'; self.emit()
                    pid = show.get('project')
                    while pid in self.waiting[s['wait']]:
                        if self.stop_flag: return
                        if self.skip.is_set(): break
                        time.sleep(0.5)
                    self.state['status'] = 'playing'
                reading = self.reading(self.ref(s['read'])) if s.get('read') else None
                self.emit(narration={'title': s['title'], 'paper': s['paper'], 'here': s['here'], 'reading': reading, 'read': self.ref(s.get('read'))})
                self.pause_point(s.get('dwell_s', 8))
            self.state['status'] = 'done'; self.emit()
            self.prepare(d)   # the next play's live steps start rendering now, so they are ready when it comes
        except StopIteration:
            self.state['status'] = 'idle'
        except Exception as e:   # a failed step is shown, never swallowed
            self.state['status'] = 'failed'; self.emit(error=f"{type(e).__name__}: {e}"[:300])
        finally:
            self.give_back()

    def give_back(self, only=None):
        """A demo previews controls on studies that exist; when it ends or stops, each control goes back to its value."""
        for pid, v in list(self.borrowed.items()):
            if only and not pid.startswith(only + '.'): continue
            prm = self.tools.store.get('parameter', pid)
            if prm is not None and prm.data['value'] != v:
                try: self.tools.call('parameter_update', 'app', parameter_id=pid, expect_version=prm.version, value=v)
                except Exception: pass
            self.borrowed.pop(pid, None)
