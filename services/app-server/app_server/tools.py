"""Tool layer (design spec §3.5, implementation spec §7).

One registry. Every tool is named {resource}_{verb}. Panels and the agent call the same tools.
Project tools write a step through the store. Display tools write only the caller's session display
and never create a step. Actions only a person can take refuse with needs_person when the actor is an agent.
"""
from __future__ import annotations
import random, threading
from dataclasses import dataclass
from typing import Callable
from .store import Store
from .script import parse, ScriptError

VERBS = {'list', 'get', 'search', 'create', 'update', 'delete', 'run', 'cancel', 'undo', 'query', 'post', 'fetch', 'read'}
PAGES = {'scene', 'samples', 'neural', 'search', 'data', 'findings', 'sources'}
VIEWS = {'lateral', 'ventral', 'medial', 'posterior'}
LAYERS = {'full', 'background', 'object', 'mask', 'depth'}


class NeedsPerson(Exception):
    pass


@dataclass
class Tool:
    name: str
    resource: str
    verb: str
    fn: Callable
    writes_project: bool
    person_only: bool = False


class Tools:
    def __init__(self, store: Store):
        self.store = store; self.registry: dict[str, Tool] = {}; self.displays: dict[str, dict] = {}; self.lock = threading.RLock()
        self._register_all()

    def tool(self, resource: str, verb: str, writes_project: bool = True, person_only: bool = False):
        assert verb in VERBS, verb
        def deco(fn):
            name = f'{resource}_{verb}'; self.registry[name] = Tool(name, resource, verb, fn, writes_project, person_only); return fn
        return deco

    def call(self, name: str, actor: str, **args):
        with self.lock:   # one writer at a time: panels, the agent and background previews share one store
            return self._call(name, actor, **args)

    def _call(self, name: str, actor: str, **args):
        t = self.registry[name]
        if t.person_only and actor != 'person':
            raise NeedsPerson(f'{name} needs a person')
        if t.writes_project and t.verb not in ('get', 'list', 'search', 'query'):
            step = self.store.begin(actor, name, args)
            try:
                return t.fn(step=step, actor=actor, **args)
            except Exception:
                self.store.discard(step)   # a refused or failed call leaves no step and no half-written rows
                raise
        return t.fn(actor=actor, **args)

    def _register_all(self):
        s = self.store

        @self.tool('project', 'create')
        def project_create(step, actor, question):
            return s.create(step, 'project', {'question': question})

        @self.tool('project', 'get')
        def project_get(actor, project_id):
            return s.get('project', project_id)

        @self.tool('parameter', 'create')
        def parameter_create(step, actor, project_id, script):
            """Parse a scene script and create one parameter row per declared parameter."""
            rows = []
            for p in parse(script):
                rows.append(s.create(step, 'parameter', {**p.to_dict(), 'project_id': project_id}, id=f'{project_id}.{p.name}', depends_on=[('project', project_id)]))
            return rows

        @self.tool('parameter', 'list')
        def parameter_list(actor, project_id):
            return [r for r in s.list('parameter') if r.data.get('project_id') == project_id]

        @self.tool('parameter', 'update')
        def parameter_update(step, actor, parameter_id, expect_version, value=None, role=None, range=None):
            cur = s.get('parameter', parameter_id); d = dict(cur.data)
            if value is not None: d['value'] = value
            if role is not None: d['role'] = role
            if range is not None: d['range'] = tuple(range)
            src = _as_script(d)
            parse(src)  # same validation as the scene script
            return s.update(step, 'parameter', parameter_id, {k: d[k] for k in ('value', 'role', 'range') if k in d}, expect_version)

        @self.tool('sample', 'create')
        def sample_create(step, actor, project_id, plan, count, seed):
            """plan: 'grid' over manipulated asset sets is out of scope here; 'random' draws every randomized parameter."""
            params = [r for r in s.list('parameter') if r.data.get('project_id') == project_id]
            rng = random.Random(seed); out = []
            for i in range(count):
                vals = {}
                for r in params:
                    p = r.data
                    if p.get('role') == 'randomized' and p.get('range'):
                        lo, hi = p['range']
                        vals[p['name']] = round(lo * (hi / lo) ** rng.random(), 4) if p.get('sampler') == 'log_uniform' else round(rng.uniform(lo, hi), 4)
                    else:
                        vals[p['name']] = p['value']
                out.append(s.create(step, 'sample', {'project_id': project_id, 'values': vals, 'seed': seed, 'index': i},
                                    depends_on=[('parameter', r.id) for r in params]))
            return out

        @self.tool('source', 'update', person_only=True)
        def source_update(step, actor, source_id, accept_terms: bool):
            return s.create(step, 'source_access', {'source_id': source_id, 'accepted': accept_terms})

        @self.tool('source', 'search', writes_project=False)
        def source_search(actor, source_id, filters, name_field='name'):
            """Run filters over a source index. Returns each step's count and removed rows with reasons."""
            from .search import load_source, run
            return run(load_source(source_id), filters, name_field)

        # ---------- scenes: every generation method lands as one scene row plus one row per object ----------
        from .scene import scene_tools as _st

        @self.tool('record', 'create')
        def record_create(step, actor, file_path, collection='Your files', up_axis='auto', units='auto'):
            """Import a file into your files: a mesh (GLB, glTF, OBJ, PLY, STL) is converted to USD; USD is kept.
            Returns the record with what was normalised (axis, units, origin) so the person can check it."""
            return s.create(step, 'record', _st.import_file(file_path, collection, up_axis, units))

        @self.tool('scene', 'create')
        def scene_create(step, actor, project_id, method, settings: dict | None = None):
            """method: empty, sage_layout (settings: folder), record (settings: record_id, surface_height_m).
            Creates the scene row and one object row per imported object, each addressed by its USD path."""
            scene = _st.build(method, settings or {}, s)
            row = s.create(step, 'scene', {'project_id': project_id, 'method': method, 'scene': _st.to_dict(scene)}, depends_on=[('project', project_id)])
            objs = [s.create(step, 'object', _st.object_row(row.id, o), id=_st.object_path(row.id, o.id), depends_on=[('scene', row.id)]) for o in scene.objects]
            return {'scene': row, 'objects': objs, 'skipped': scene.skipped}

        @self.tool('scene', 'get', writes_project=False)
        def scene_get(actor, scene_id, compose: bool = False):
            """The scene with its current objects. compose=True writes the USD stage and returns its path."""
            return _st.current(s, scene_id, compose)

        @self.tool('object', 'list', writes_project=False)
        def object_list(actor, scene_id):
            return [r for r in s.list('object') if r.data.get('scene_id') == scene_id]

        @self.tool('object', 'get', writes_project=False)
        def object_get(actor, path):
            return s.get('object', path)

        @self.tool('object', 'create')
        def object_create(step, actor, scene_id, record_id, position_m, rotation_deg=(0.0, 0.0, 0.0), label=None, role='context', placed_on=None):
            """Place a record from any source into the scene."""
            data = _st.object_from_record(s, scene_id, record_id, list(position_m), list(rotation_deg), label, role, placed_on)
            return s.create(step, 'object', data, id=data['path'], depends_on=[('scene', scene_id), ('record', record_id)])

        @self.tool('object', 'update')
        def object_update(step, actor, path, expect_version, position_m=None, rotation_deg=None, size_m=None, role=None):
            if role is not None and role not in _st.ROLES: raise ValueError(f'role must be one of {sorted(_st.ROLES)}')
            ch = {k: (list(v) if isinstance(v, (list, tuple)) else v) for k, v in
                  {'position_m': position_m, 'rotation_deg': rotation_deg, 'size_m': size_m, 'role': role}.items() if v is not None}
            return s.update(step, 'object', path, ch, expect_version)

        @self.tool('object', 'delete')
        def object_delete(step, actor, path, expect_version):
            return s.delete(step, 'object', path, expect_version)

        @self.tool('analysis', 'create')
        def analysis_create(step, actor, project_id, kind, inputs: dict, prediction: dict | None = None):
            """An analysis of a known kind over named inputs. A prediction, if any, is saved before it runs."""
            from .analysis import KINDS
            if kind not in KINDS: raise ValueError(f'kind must be one of {sorted(KINDS)}')
            return s.create(step, 'analysis', {'project_id': project_id, 'kind': kind, 'inputs': inputs, 'prediction': prediction}, depends_on=[('project', project_id)])

        @self.tool('analysis', 'run')
        def analysis_run(step, actor, analysis_id, data: dict):
            """Run an analysis on arrays supplied by name. Stores a result row that depends on the analysis."""
            from .analysis import KINDS
            a = s.get('analysis', analysis_id).data
            res = KINDS[a['kind']](**data)
            if a.get('prediction'): res['prediction'] = a['prediction']
            return s.create(step, 'result', {'analysis_id': analysis_id, **res}, depends_on=[('analysis', analysis_id)])

        @self.tool('step', 'list', writes_project=False)
        def step_list(actor, limit: int | None = None):
            """Every step, oldest first; with limit, only the latest ones."""
            st = s.steps()
            return st[-limit:] if limit else st

        @self.tool('step', 'undo', writes_project=False)
        def step_undo(actor, step_id):
            return s.undo(step_id, actor)

        @self.tool('display', 'get', writes_project=False)
        def display_get(actor, session_id):
            return self.displays.get(session_id, {'page': 'scene'})

        @self.tool('display', 'update', writes_project=False)
        def display_update(actor, session_id, changes: dict):
            d = dict(self.displays.get(session_id, {'page': 'scene'}))
            if 'page' in changes and changes['page'] not in PAGES: raise ValueError(f'page must be one of {sorted(PAGES)}')
            nm = changes.get('neural', {})
            if 'view' in nm and nm['view'] not in VIEWS: raise ValueError(f'view must be one of {sorted(VIEWS)}')
            sc = changes.get('scene', {})
            if 'layer' in sc and sc['layer'] not in LAYERS: raise ValueError(f'layer must be one of {sorted(LAYERS)}')
            for k, v in changes.items():
                d[k] = {**d.get(k, {}), **v} if isinstance(v, dict) else v
            self.displays[session_id] = d
            return d


def _as_script(d: dict) -> str:
    """Rebuild one declaration so a single parameter is validated by the same parser as the script."""
    args = [repr(d['value'])] + [f'{k}={d[k]!r}' for k in ('unit', 'range', 'sampler', 'role', 'target', 'options', 'steps') if d.get(k) is not None]
    return f"{d['name']} = {d['type']}({', '.join(args)})"
