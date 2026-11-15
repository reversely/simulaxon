"""Lab tools on the one registry: templates, projects, samples, analyses with results, brain maps and regions.

Panels and the agent call the same tools. Project tools write steps; reads never do.
"""
from __future__ import annotations
import copy
from pathlib import Path
import numpy as np
from . import templates, regions, maps, records, titles
from .ingest import FILES


def slider_step(lo: float, hi: float) -> float:
    """Sliders move in twenty steps across their range, so nearby values are few and can be rendered ahead."""
    return round((hi - lo) / 20, 6)


def register(tools, broadcast=lambda m: None):
    s = tools.store
    from . import preview, demos
    raw = broadcast
    def broadcast(msg: dict):   # every event also tells a playing demo that what it waits for has finished
        if msg.get('preview') and msg.get('stage') in ('done', 'failed'): player.notify('preview', msg['preview'])
        if msg.get('run') and msg.get('stage') in ('done', 'failed'): player.notify('run', msg['run'])
        if msg.get('run'):   # kept, so a page opened mid-run shows where the run is instead of waiting for the next event
            cur = progress.get(msg['run'], {})
            if cur.get('stage') == 'failed' and 'done' in msg: cur = {}   # a new run of a project that failed or was stopped: its old outcome goes
            progress[msg['run']] = {**cur, **{k: msg[k] for k in ('done', 'total', 'stage') if k in msg}}
            if msg.get('stage') == 'done': progress.pop(msg['run'], None)
            if msg.get('stage') == 'failed': progress[msg['run']] = {'stage': 'failed', 'error': msg.get('error', '')}   # kept until it runs again
        raw(msg)
    progress: dict[str, dict] = {}
    player = demos.Player(tools, broadcast)
    tools.lab_broadcast = broadcast; tools.demo_player = player
    preview.on_job = lambda m: raw({'job': m})

    @tools.tool('demo', 'list', writes_project=False)
    def demo_list(actor):
        """Paper demos: every seed, and for each one the agent has written, the steps it takes here."""
        written = {d['id']: d for d in demos.load()}
        import json as _json, re as _re
        def gone(d):   # projects a written demo names that no longer exist: it has to be written again
            refs = set(_re.findall(r'"\$p:([A-Za-z0-9_]+)"', _json.dumps(d)))
            return sorted(r for r in refs if s.get('project', r) is None)
        return [{'id': sd['id'], 'paper': sd['paper'], 'url': sd['url'], 'template': sd['template'], 'written': sd['id'] in written,
                 'missing_projects': gone(written[sd['id']]) if sd['id'] in written else [],
                 'writing': sd['id'] in writing, 'title': written.get(sd['id'], {}).get('title'),
                 'steps': [{'title': x['title'], 'flow': x['flow'], 'paper': x['paper'], 'here': x['here']} for x in written.get(sd['id'], {}).get('steps', [])]}
                for sd in demos.seeds()]

    writing: set[str] = set()

    @tools.tool('demo', 'create', writes_project=False)
    def demo_create(actor, seed_id):
        """The agent reads the seed's paper, looks at the projects and tools here, and writes the demo's steps. Every name it
        uses is checked against what exists; problems go back to it until none are left. Runs in the background."""
        import threading
        from . import demo_writer
        if seed_id in writing: return {'writing': True}
        writing.add(seed_id); broadcast({'demo_writing': seed_id, 'stage': 'writing'})
        def go():
            try:
                out = demo_writer.write(s, seed_id, f'http://127.0.0.1:{tools.port}'); broadcast({'demo_writing': seed_id, 'stage': 'done', **out})
                player.prepare(demos.get(seed_id))
            except Exception as e:
                print(f'demo {seed_id} not written: {e}', flush=True)
                broadcast({'demo_writing': seed_id, 'stage': 'failed', 'error': str(e)[-300:]})
            finally:
                writing.discard(seed_id)
        threading.Thread(target=go, daemon=True).start()
        return {'writing': True}

    @tools.tool('demo', 'run', writes_project=False)
    def demo_run(actor, demo_id):
        """Start playing a paper demo. Every step's actions are tool calls by the agent; it waits for live renders and runs."""
        return player.start(demo_id)

    @tools.tool('demo', 'update', writes_project=False)
    def demo_update(actor, action):
        """Control the playing demo. action: pause, resume, next or stop."""
        return player.control(action)

    @tools.tool('demo', 'get', writes_project=False)
    def demo_get(actor):
        return player.snapshot()

    @tools.tool('preview', 'create')
    def preview_create(step, actor, project_id, key, values, inputs, image, clip, readout, map, mask_labels):
        """Record one live preview: the values, the render, and TRIBE's readout and map. Written by the preview runner."""
        return s.create(step, 'preview', {'project_id': project_id, 'key': key, 'values': values, 'inputs': inputs, 'image': image, 'clip': clip,
                                          'readout': readout, 'map': map, 'mask_labels': mask_labels}, id=f'preview_{key}', depends_on=[('project', project_id)])

    @tools.tool('preview', 'list', writes_project=False)
    def preview_list(actor, project_id):
        return [r for r in s.list('preview') if r.data.get('project_id') == project_id]

    @tools.tool('preview', 'search', writes_project=False)
    def preview_search(actor, project_id):
        """Render, in the background, every option of the project's choice controls that has not been rendered, one change
        at a time from the current values, so picking any option answers from cache. Your own previews always go first."""
        params = [r.data for r in s.list('parameter') if r.data.get('project_id') == project_id]
        n = 0
        for prm in params:
            if prm['type'] == 'choice':
                for o in prm.get('options') or []:
                    if o != prm['value']:
                        preview.start(tools, broadcast, project_id, 'app', values={prm['name']: o}, source='Prepared for this room', lane='ahead'); n += 1
            elif prm['type'] in ('number', 'angle') and prm.get('range') and prm.get('role') != 'measured':
                lo, hi = prm['range']; step = slider_step(lo, hi)
                for v in (prm['value'] - step, prm['value'] + step):   # the slider's grid runs through the current value: one step either side
                    v = round(v, 6)
                    if lo <= v <= hi: preview.start(tools, broadcast, project_id, 'app', values={prm['name']: v}, source='Prepared for this room', lane='ahead'); n += 1
        return {'options': n}

    @tools.tool('preview', 'run', writes_project=False)
    def preview_run(actor, project_id):
        """Render the project's current parameter values in Isaac and read them with TRIBE. Returns at once; the room updates when done."""
        return preview.start(tools, broadcast, project_id, actor)

    base_update = tools.registry['parameter_update'].fn
    def parameter_update(step, actor, parameter_id, expect_version, value=None, role=None, range=None):
        """Change a scene parameter. The room re-renders those exact values, and TRIBE reads them, in the fast lane."""
        cur = s.get('parameter', parameter_id).data
        if value is not None and cur.get('options') and value not in cur['options']:
            raise ValueError(f'{cur["name"]} must be one of its options')
        row = base_update(step=step, actor=actor, parameter_id=parameter_id, expect_version=expect_version, value=value, role=role, range=range)
        preview.start(tools, broadcast, row.data['project_id'], actor)
        if row.data['type'] in ('number', 'angle') and row.data.get('range'):   # the next nudge either way renders in the background now
            lo, hi = row.data['range']; st = slider_step(lo, hi)
            for v in (row.data['value'] - st, row.data['value'] + st):
                if lo <= round(v, 6) <= hi: preview.start(tools, broadcast, row.data['project_id'], 'app', values={row.data['name']: round(v, 6)}, source='Prepared for the next nudge', lane='ahead')
        return row
    tools.registry['parameter_update'].fn = parameter_update

    def all_assets(project_id):
        P = s.get('project', project_id)
        if P is None: return {}   # undone or removed
        return {**P.data.get('assets', {}), **{r.data['asset_id']: r.data for r in s.list('asset') if r.data.get('project_id') == project_id}}
    tools.all_assets = all_assets

    def of(kind, project_id):
        return sorted((r for r in s.list(kind) if r.data.get('project_id') == project_id), key=lambda r: r.data.get('index', 0))

    @tools.tool('template', 'list', writes_project=False)
    def template_list(actor):
        """Every template: question with blanks, sampling plan, parameters with roles, analyses, controls, hand-off, walkthrough."""
        used = {}
        for p in s.list('project'):   # a project made from a question alone has no template
            if p.data.get('template_id'): used[p.data['template_id']] = used.get(p.data['template_id'], 0) + 1
        return [{**t, 'walkthrough': [{'flow': f, 'flow_name': templates.FLOWS[f], 'text': x} for f, x in t['walkthrough']],
                 'projects': used.get(t['id'], 0)} for t in templates.TEMPLATES]

    @tools.tool('project', 'list', writes_project=False)
    def project_list(actor):
        return sorted(s.list('project'), key=lambda r: r.data.get('created_order', 0))

    @tools.tool('project', 'create')
    def project_create_from(step, actor, question=None, template_id=None, title=None, bindings: dict | None = None, from_project_id: str | None = None, made_by: str | None = None):
        """A new draft project from a template, or a fork of an existing project. Blanks are filled from bindings.
        With only a question, a bare project as before."""
        if template_id is None: return s.create(step, 'project', {'question': question})
        t = templates.get(template_id)
        src = s.get('project', from_project_id).data if from_project_id else {}
        b = {**t.get('defaults', {}), **(src.get('bindings') or {} if src.get('template_id') == template_id else {}), **(bindings or {})}   # template defaults, then a fork's blanks, then the given ones
        params = [{**x, 'value': templates.fill(x['value'], b)} for x in t['parameters']]
        keep = {k: copy.deepcopy(src[k]) for k in ('provenance', 'world', 'assets', 'script', 'pairs', 'labels', 'search') if k in src}
        row = s.create(step, 'project', {'provenance': [], **keep, 'title': title, 'question': templates.fill(t['question'], b), 'template_id': t['id'], 'bindings': b,
                                         'parameters': params, 'plan': t['plan'], 'status': 'Draft', 'forked_from': from_project_id, 'note': '', 'made_by': made_by,
                                         'created_order': len(s.list('project'))})
        if not from_project_id and t['world'] == 'body':   # a world that builds itself from data: EgoBody moments by the template's search
            from . import worlds
            from ..script import parse
            bw = worlds.body_world(int(b.get('n_moments', 6)), float(b.get('keyframe_s', 0.5)))
            row = s.update(step, 'project', row.id, {**row.data, **bw, 'provenance': ['EgoBody: first-person recordings, both bodies tracked, rooms scanned',
                                                                                     'Isaac Sim 6.2: the scanned room, a human body or the G1, from the partner\'s eye',
                                                                                     '9 s per clip, 30 fps', 'TRIBE v2 on video, seconds 1 to 9']}, row.version)
            for prm in parse(bw['script']):
                s.create(step, 'parameter', {**prm.to_dict(), 'project_id': row.id}, id=f"{row.id}.{prm.name}", depends_on=[('project', row.id)])
        if from_project_id:   # the fork starts from the same world: its scene parameters at their current values, and added assets
            for r in [r for r in s.list('parameter') if r.data.get('project_id') == from_project_id]:
                s.create(step, 'parameter', {**r.data, 'project_id': row.id}, id=f"{row.id}.{r.data['name']}", depends_on=[('project', row.id)])
            for r in [r for r in s.list('asset') if r.data.get('project_id') == from_project_id]:
                s.create(step, 'asset', {**r.data, 'project_id': row.id}, id=f"{row.id}:{r.data['asset_id']}", depends_on=[('project', row.id)])
        return row

    @tools.tool('project', 'delete')
    def project_delete(step, actor, project_id, expect_version):
        """Delete a project. Like every change, it is a step that undo can reverse."""
        return s.delete(step, 'project', project_id, expect_version)

    @tools.tool('project', 'update')
    def project_update(step, actor, project_id, expect_version, title=None, bindings: dict | None = None, status=None, counts=None,
                       run_values=None, pairs=None, labels=None):
        """Change a project's title or blanks, or its run bookkeeping: status, counts, pairs to run and condition labels.
        Only a change to the blanks marks results out of date; the rest is metadata."""
        cur = s.get('project', project_id); d = {}
        for k, v in (('title', title), ('status', status), ('counts', counts), ('run_values', run_values), ('pairs', pairs), ('labels', labels)):
            if v is not None: d[k] = v
        if status is not None and status not in ('Draft', 'Running', 'Done'): raise ValueError('status must be Draft, Running or Done')
        if bindings is not None:
            t = templates.get(cur.data['template_id']); b = {**cur.data['bindings'], **bindings}
            d.update({'bindings': b, 'question': templates.fill(t['question'], b),
                      'parameters': [{**x, 'value': templates.fill(x['value'], b)} for x in t['parameters']]})
        return s.update(step, 'project', project_id, d, expect_version, mark_stale=bindings is not None)

    @tools.tool('project', 'run', writes_project=False)
    def project_run(actor, project_id):
        """Run every sample of the project's plan through Isaac and TRIBE, then its analyses. Returns at once; progress is broadcast."""
        from . import runner
        return runner.start(tools, broadcast, project_id, actor)

    @tools.tool('sample', 'list', writes_project=False)
    def sample_list(actor, project_id):
        return of('sample', project_id)

    @tools.tool('analysis', 'list', writes_project=False)
    def analysis_list(actor, project_id):
        """Every analysis of a project with its result, or no result when it has not run."""
        res = {r.data['analysis_id']: r for r in s.list('result') if r.data.get('project_id') == project_id}
        return [{'analysis': a, 'result': res.get(a.id), 'stale': s.is_stale('result', res[a.id].id) if a.id in res else False}
                for a in of('analysis', project_id)]

    @tools.tool('neural_map', 'get', writes_project=False)
    def neural_map_get(actor, map_id):
        return s.get('neural_map', map_id)

    @tools.tool('neural_map', 'create')
    def neural_map_create(step, actor, sample_id):
        """The brain map of one sample, over the seconds it is on screen. Cached by content."""
        smp = s.get('sample', sample_id).data
        existing = [r for r in s.list('neural_map') if r.data.get('sample_id') == sample_id]
        if existing: return existing[0]
        v = np.load(smp['preds'])[0:3].mean(0)
        mp = maps.render(v, 'single', FILES)
        return s.create(step, 'neural_map', {'project_id': smp['project_id'], 'sample_id': sample_id, 'title': smp['label'], 'kind': 'single', **mp},
                        depends_on=[('sample', sample_id)])

    @tools.tool('record', 'search', writes_project=False)
    def record_search(actor, q: str, source_id: str = 'palatial', limit: int = 24):
        """Search a library by name. Each row says whether its files are already on this machine."""
        import pandas as pd
        from .ingest import ROOT
        IX = ROOT / 'feasibility' / 'indexes' / 'palatial'; A = ROOT / 'feasibility' / 'assets' / 'palatial'
        d = pd.read_parquet(IX / 'catalog.parquet')
        text = (d['name'].fillna('') + ' ' + d['display_name'].fillna('') + ' ' + d['class_label'].fillna('') + ' ' + d['catalog_id'].str.replace('_', ' ')).str.lower()
        for w in q.lower().split(): text, d = text[text.str.contains(w, regex=False)], d[text.str.contains(w, regex=False)]   # every word must appear
        d = d.head(limit)
        return [{'id': r.catalog_id, 'name': r.name, 'label': r.class_label, 'size_m': round(max(r.bounds_x_m, r.bounds_y_m, r.bounds_z_m), 3),
                 'image': f'/index/palatial/previews/{r.render_image_path}' if (IX / 'previews' / str(r.render_image_path)).exists() else None,
                 'local': (A / r.usd_path).exists()} for r in d.itertuples()]

    @tools.tool('asset', 'create')
    def asset_create(step, actor, project_id: str, source_id: str, record_id: str | None = None, file_path: str | None = None, parameter: str = 'item'):
        """Add an asset to a project's world and make it the current value of an asset parameter, so the room renders it.
        source_id: palatial (a library record, downloaded if needed) or file (a file you uploaded; meshes become USD)."""
        from .ingest import ROOT
        P = s.get('project', project_id); prm = s.get('parameter', f'{project_id}.{parameter}')
        if prm is None or prm.data['type'] != 'asset': raise ValueError(f'{parameter} is not an asset parameter of this project')
        if source_id == 'palatial':
            import pandas as pd
            r = pd.read_parquet(ROOT / 'feasibility/indexes/palatial/catalog.parquet').set_index('catalog_id').loc[record_id]
            A = ROOT / 'feasibility' / 'assets' / 'palatial'; usd = A / r.usd_path
            if not usd.exists():
                from huggingface_hub import snapshot_download
                snapshot_download('PalatialSim/palatial-nv-asset-library', repo_type='dataset', revision=r.source_revision,
                                  allow_patterns=[str(Path(r.usd_path).parent) + '/*'], local_dir=str(A))
            aid, entry = record_id, {'label': r['name'], 'usd': str(usd), 'image': f'/index/palatial/previews/{r.render_image_path}', 'source': 'Palatial'}
        elif source_id == 'file':
            from ..scene import scene_tools as st
            rec = st.import_file(file_path, 'Your files', 'auto', 'auto'); fp = Path(file_path)
            aid, entry = f'file_{fp.stem}', {'label': fp.stem, 'usd': rec['asset']['path'], 'image': None, 'source': 'Your files', 'import_report': rec['import_report']}
        else:
            raise ValueError('source_id must be palatial or file')
        if not s.get('asset', f'{project_id}:{aid}'):   # a row of its own, so adding to the world never marks results out of date
            s.create(step, 'asset', {'project_id': project_id, 'asset_id': aid, **entry}, id=f'{project_id}:{aid}', depends_on=[('project', project_id)])
        opts = list(prm.data.get('options') or []); opts = opts if aid in opts else opts + [aid]
        row = s.update(step, 'parameter', prm.id, {'options': opts, 'value': aid}, prm.version)
        preview.start(tools, broadcast, project_id, actor)
        return row

    @tools.tool('asset', 'list', writes_project=False)
    def asset_list(actor, project_id):
        """Every asset the project's world can use: from its runs, and added since."""
        return all_assets(project_id)

    @tools.tool('source', 'list', writes_project=False)
    def source_list(actor):
        """Libraries, scene sets, models and simulators: where each is, its licence, and what needs a person."""
        return records.sources()

    @tools.tool('assumption', 'list', writes_project=False)
    def assumption_list(actor, project_id: str | None = None):
        """The assumptions behind a project's numbers, for its kind of world, with evidence read from the store."""
        return records.assumptions(s, project_id) if project_id else [{k: a[k] for k in ('text', 'status', 'evidence')} for a in records.ASSUMPTIONS]

    @tools.tool('machine', 'get', writes_project=False)
    def machine_get(actor):
        """What the agent, the world node and the brain node are doing now, read from running processes, and whether this
        place has a dashboard: /dashboard finds Grafana through the Fuzzball CLI, so a place without it (the Spark) has none."""
        import shutil
        from ..config import FUZZBALL
        return {**records.machine(), 'dashboard': bool(shutil.which(FUZZBALL))}

    @tools.tool('roi', 'list', writes_project=False)
    def roi_list(actor):
        return regions.table()

    # ---------- papers, datasets, regions and experiments: what the agent needs to set up a replication it has never seen ----------
    from . import papers, datasets as dsets, experiment

    @tools.tool('course', 'get', writes_project=False)
    def course_get(actor, project_id, region):
        """A region's response second by second, the mean over each condition's samples, from the saved predictions:
        {seconds, conditions: [{name, values, n}]}. Region: a name from region_search, or a list of names for a group."""
        import numpy as np
        m = regions.mask_for(region); by: dict[str, list] = {}
        for r in of('sample', project_id):
            pr = r.data.get('preds')
            if not pr: continue
            try: v = np.load(pr)
            except Exception: continue
            by.setdefault(r.data.get('condition', ''), []).append(v[:, m].mean(1))
        if not by: raise ValueError('no saved predictions for this project')
        secs = min(len(x) for xs in by.values() for x in xs)
        return {'region': region, 'seconds': secs, 'conditions': [{'name': c, 'n': len(xs), 'values': [round(float(x), 4) for x in np.mean([x[:secs] for x in xs], 0)]} for c, xs in by.items()]}

    @tools.tool('example', 'list', writes_project=False)
    def example_list(actor):
        """Seeded examples: classic experiments, each with its paper, a picture, what has run here, and the project or goal to start from."""
        from . import examples
        return examples.listing(s)

    @tools.tool('run', 'stop', writes_project=False)
    def run_stop(actor, project_id):
        """Stop an experiment's run after the clip under way. Clips already read stay cached, so running it again picks up
        where it stopped. The project goes back to Draft."""
        from . import runner
        P = s.get('project', project_id).data
        if P.get('status') != 'Running' or project_id not in runner.LIVE: return {'stopped': False, 'why': f"the project is {P.get('status')}, with no run going in this server"}
        runner.STOP[runner.LIVE[project_id]] = 'the agent' if actor == 'agent' else 'a person'
        return {'stopped': True, 'note': 'it stops after the clip under way'}

    @tools.tool('run', 'list', writes_project=False)
    def run_list(actor):
        """Runs under way, by project: clips done, total and stage."""
        return progress

    @tools.tool('paper', 'search', writes_project=False)
    def paper_search(actor, query):
        """Published works matching the words (OpenAlex): title, authors, year, venue, DOI, whether full text is open, citations."""
        return papers.search(query)

    @tools.tool('paper', 'fetch')
    def paper_fetch(step, actor, ref):
        """Fetch a paper's full text by DOI, PMCID, PMID or arXiv id (or a PDF a person added: its path). Returns its parts,
        each with a heading and length, to read with paper_read. Only openly available full text is fetched."""
        p = papers.fetch(ref); o = papers.outline(p)
        if not s.get('paper', p['id']): s.create(step, 'paper', {k: v for k, v in o.items() if k != 'parts'} | {'parts': len(o['parts'])}, id=p['id'])
        return o

    @tools.tool('paper', 'read', writes_project=False)
    def paper_read(actor, paper_id, part: int | None = None, find: str | None = None, offset: int = 0):
        """Read a fetched paper: one part from offset (about 6,000 characters at a time; next_offset continues it), or with
        find, every passage containing all the words, such as find="stimuli presented" or find="Figure 3"."""
        return papers.read(paper_id, part, find, offset)

    @tools.tool('dataset', 'get', writes_project=False)
    def dataset_get(actor, ref, pattern: str | None = None):
        """A repository's files before fetching anything: totals by kind (image, video, audio, brain data ...), the licence,
        and the files matching pattern (glob, such as "stimuli/*/*.jpg"). ref: openneuro:ds000117, osf:abcd3, zenodo:123456,
        figshare:123456, github:owner/repo, hf:owner/name, or a URL."""
        return dsets.summary(dsets.listing(ref), pattern)

    @tools.tool('dataset', 'fetch', writes_project=False)
    def dataset_fetch(actor, ref, include: list[str], max_gb: float = 5.0):
        """Fetch the files matching any include pattern into this machine, in the background. Refuses over max_gb or when
        the disk would drop below its floor. Returns at once; dataset_list shows progress; archives are unpacked."""
        return dsets.fetch(ref, include, max_gb, on_event=broadcast)

    @tools.tool('dataset', 'list', writes_project=False)
    def dataset_list(actor):
        """Datasets on this machine, and fetches under way: source, licence, files and size."""
        return dsets.here()

    @tools.tool('file', 'list', writes_project=False)
    def file_list(actor, dataset_id, pattern: str = '*'):
        """Files of a fetched dataset matching pattern, with kind and size (images with pixels), and counts by kind."""
        return dsets.files(dataset_id, pattern)

    @tools.tool('region', 'search', writes_project=False)
    def region_search(actor, query: str = ''):
        """Regions an experiment can name: TRIBE's HCP-MMP1 areas by code (FFC, PPA, V1, MT ...; L_ or R_ for one hemisphere),
        Destrieux labels, and the named groups. Empty query: the groups and all HCP codes."""
        return regions.search(query)

    @tools.tool('experiment', 'create')
    def experiment_create(step, actor, title, question, conditions: list[dict], regions: list, contrasts: list[dict] | None = None,
                          trial: dict | None = None, reported: list[dict] | None = None, paper_id: str | None = None, project_id: str | None = None):
        """Set up an experiment as a project, or replace a draft project's experiment. Checks everything and returns the trials it will run.
        conditions: [{name, dataset_id, files: [glob patterns relative to the dataset]}] (or files: paths under the lab's data folder,
          with origin "isaac" for Isaac Sim renders). Every stimulus keeps where it came from.
          Add cosmos: {prompt, seeds: [0, 1], control: edge} to a condition to restyle each stimulus with Cosmos before TRIBE reads it
          (about 4 min per 4 s clip; a held image becomes a short clip first). Its origin then reads "Cosmos, from ...".
        regions: names from region_search, or {name, areas: [names]} for a group.
        contrasts: [{name, weights: {condition: weight}}], weights summing to zero; default first condition against second.
        trial: {design: block or event, item_s, gap_s, items_per_trial, trials_per_condition, rest_s, read_s: [first, last] seconds of
          TRIBE's output to average (second 0 is onset; default the seconds on screen, since TRIBE's output has the blood-flow lag removed), seed,
          paired: true to give every condition the same source items in the same order, compared trial by trial (such as a clip against its Cosmos version)}.
          One clip per trial; every trial has the same length.
        reported: the paper's result to compare against: [{contrast, region, direction: higher or lower, where: "Figure 2", quote}];
          region is a name from regions, including a group defined there, or an atlas name.
        Run it with project_run; progress is broadcast; results come back as analyses with baselines and match or no match."""
        regs = regions   # the argument, not the module: this function never needs the module
        spec = {'conditions': conditions, 'regions': regs, 'contrasts': contrasts, 'trial': trial, 'reported': reported, 'paper_id': paper_id}
        P = experiment.plan(spec)
        origins = sorted({tr['origin']['label'] for tr in P['trials']})
        prov = [' and '.join(origins), f"{P['clips']} trials, one {P['trial']['clip_s']:g} s clip each", f"TRIBE v2, video only, seconds {P['trial']['read_s'][0]} to {P['trial']['read_s'][1]}",
                ', '.join(_name(r) for r in regs)]
        per = {}
        for tr in P['trials']: per.setdefault(tr['condition'], {'files_available': tr['files_available'], 'origin': tr['origin'], 'trials': 0}); per[tr['condition']]['trials'] += 1
        paper = s.get('paper', paper_id).data if paper_id and s.get('paper', paper_id) else None
        setup = {'conditions': [{'name': c, **v} for c, v in per.items()], 'trial': P['trial'], 'clips': P['clips'], 'minutes_estimate': P['minutes_estimate'],
                 'contrasts': P['contrasts'], 'regions': [_name(r) for r in regs], 'reported': P['reported']}
        data = {'title': title, 'question': question, 'template_id': None, 'plan': 'experiment', 'status': 'Draft', 'experiment': spec, 'paper_id': paper_id,
                'paper': paper, 'setup': setup, 'provenance': prov, 'made_by': actor, 'bindings': {}, 'parameters': []}
        if project_id:
            cur = s.get('project', project_id)
            if cur.data.get('status') == 'Running': raise ValueError('this project is running')
            row = s.update(step, 'project', project_id, data, cur.version)
        else:
            row = s.create(step, 'project', {**data, 'created_order': len(s.list('project'))})
        return {'project_id': row.id, 'conditions': per, 'trial': P['trial'], 'clips': P['clips'], 'minutes_estimate': P['minutes_estimate'],
                'contrasts': P['contrasts'], 'regions': regs, 'reported': P['reported'], 'example_trial': P['trials'][0]['items'][:4]}

    def _name(r): return r if isinstance(r, str) else r['name']

    @tools.tool('experiment', 'get', writes_project=False)
    def experiment_get(actor, project_id):
        """An experiment's set-up, status and, when done, every contrast with its baselines and match or no match."""
        P = s.get('project', project_id).data
        res = [{'contrast': a['analysis'].data.get('title'), 'regions': a['result'].data.get('regions'), 'baselines': a['result'].data.get('baselines'),
                'reported': a['result'].data.get('reported'), 'note': a['result'].data.get('vjepa_note')}
               for a in analysis_list(actor, project_id) if a['result']]
        return {'title': P.get('title'), 'question': P.get('question'), 'status': P.get('status'), 'experiment': P.get('experiment'), 'results': res}

    for fn in (project_create_from, project_update, experiment_create):   # the title argument says how to title (#11)
        fn.__doc__ = (fn.__doc__ or '').rstrip() + f'\n        title: {titles.ARG}.'
