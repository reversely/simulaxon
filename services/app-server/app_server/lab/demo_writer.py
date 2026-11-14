"""The agent writes a paper demo. A seed names only the paper, its link and a template; the agent reads the paper,
looks at the projects and tools that exist, and writes the steps. The result is checked before it is saved, so a demo
never names a project, control, region, view or tool that does not exist, and carries no results of its own.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, tempfile
from pathlib import Path
from . import planner_agent, regions, templates

DATA = Path(__file__).parent / 'demo_data'
SEEDS, WRITTEN = DATA / 'seeds', DATA / 'written'
ROOT = Path(__file__).resolve().parents[2]
VIEWS = ['room', 'samples', 'brain', 'search', 'data', 'findings', 'sources']
TOOLS = ['project_create', 'project_update', 'project_run', 'parameter_set']
READS = ['paired', 'selection', 'per_object']
VERDICT = re.compile(r'\b(supported|confirmed|refuted|ruled out|as predicted)\b', re.I)

FORMAT = """Write the demo as one JSON object, and nothing else, with keys:
  title     a short name for the demo, in plain words, under 8 words
  steps     4 to 8 steps, in the order the paper did them
Each step has:
  title     under 6 words
  flow      one of: build, vary, run, compare, challenge, handoff
  paper     one or two plain sentences: what the paper did at this point. Only what the paper's own page supports. No numbers it reports.
  here      one or two plain sentences: what this app does in its place, and how it differs where it must
  show      {"project": REF, "view": one of %(views)s, "region": optional region name, "unit": optional 0-based index, "condition": optional selection condition}
  read      optional {"project": REF, "kind": one of %(reads)s, "region": region name} or, for selection, {"project": REF, "kind": "selection", "condition": condition id}
  actions   optional list of {"tool": one of %(tools)s, "args": {...}, "as": optional name for a project it creates}
  wait      optional "preview" (after parameter_set) or "run" (after project_run)
  dwell_s   seconds to stay on the step, 6 to 12
REF is "$p:<project id>" for a project that exists, or "$made:<name>" for one an earlier step created with "as".
parameter_set args: {"project_id": REF, "name": control name, "value": an option or number, or "$option:0" for the first option other than the current one}.
project_create args: {"template_id", "title", "bindings", "from_project_id": REF} copies that project's world and controls.
Bindings are the words that fill the template question's blanks, so they read inside that sentence: lower case, plain phrases, never atlas labels or internal ids. Where the question says "Does {a}", {a} is one thing: "an item chosen for early visual cortex", not "items chosen for ...". Regions in bindings are phrases such as "the early visual cortex"; atlas names belong only in "show" and "read".
project_update args may set "pairs" to "$pairs_first:$p:<project>:<n>" for that project's first n pairs, "$pairs_from:$p:<selection project>:<condition>:<condition>" or "$swap_outcome:$p:<project>:<old>:<new>", and "labels".
Projects that exist are other people's finished studies: a step may change one of their controls only to preview it, with wait "preview", and never runs them.
To run something new, create a project from one that exists with project_create and "as", set its controls, give it at most 8 pairs with project_update, then project_run it with wait "run".
Rules: no verdict words such as supported, confirmed, refuted or ruled out. No results typed in: every number shown comes from "read" at play time.
Use only projects, controls, options, regions and analyses listed below. Prefer steps that change a control live, so the viewer sees Isaac render and TRIBE read.
"""


def inventory(store, template_id: str | None = None) -> dict:
    """What exists: projects with their template, plan, question, controls and analyses; regions; selection conditions.
    For a demo, only the original studies built from its paper's template: never another paper's study, nor a copy an
    earlier demo made."""
    params = {}
    for r in store.list('parameter'):
        params.setdefault(r.data['project_id'], []).append({'name': r.data['name'], 'type': r.data['type'], 'value': r.data['value'],
                                                             'options': r.data.get('options'), 'range': r.data.get('range')})
    kinds = {}
    for a in store.list('analysis'): kinds.setdefault(a.data['project_id'], set()).add(a.data['kind'])
    projects = [{'id': p.id, 'title': p.data['title'], 'template': p.data['template_id'], 'plan': p.data['plan'], 'question': p.data['question'],
                 'status': p.data['status'], 'bindings': p.data.get('bindings', {}), 'note': p.data.get('note', ''), 'controls': [{k: v for k, v in c.items() if v is not None} for c in params.get(p.id, [])
                                                                                           if not (c['type'] == 'asset' and len(c.get('options') or []) > 12)],
                 'analyses': sorted(kinds.get(p.id, []))} for p in store.list('project') if p.data.get('status') in ('Done', 'Draft')
                and (template_id is None or (p.data.get('template_id') == template_id and not p.data.get('forked_from') and p.data.get('world')))]
    return {'projects': projects, 'regions': [r['region'] for r in regions.table()],
            'selection_conditions': ['align_up', 'align_down', 'a_over_b', 'b_over_a'],
            'templates': [{'id': t['id'], 'title': t['title'], 'question': t['question'], 'plan': t['plan'], 'controls': t['controls']} for t in templates.TEMPLATES]}


def check(demo: dict, seed: dict, inv: dict) -> list[str]:
    """Everything a demo names must exist; nothing it says may be a verdict or a typed-in result."""
    problems, made, limited, plan_of = [], set(), set(), {}
    pids = {p['id']: p for p in inv['projects']}; regs = set(inv['regions'])
    if not pids: problems.append(f"no original study uses the template {seed['template']}")
    def ref_ok(v, where):
        if not isinstance(v, str): problems.append(f'{where}: project reference missing'); return None
        if v.startswith('$p:'):
            if v[3:] not in pids: problems.append(f'{where}: {v[3:]} is not one of this paper\'s studies; use only the projects listed')
            return v[3:]
        if v.startswith('$made:'):
            if v[6:] not in made: problems.append(f'{where}: {v} is used before a step creates it')
            return None
        problems.append(f'{where}: {v} is not a project reference')
    steps = demo.get('steps') or []
    if not 3 <= len(steps) <= 9: problems.append(f'{len(steps)} steps; write 4 to 8')
    for i, s in enumerate(steps, 1):
        w = f'step {i}'
        for k in ('title', 'paper', 'here', 'show'):
            if not s.get(k): problems.append(f'{w}: {k} is missing')
        if s.get('flow') not in templates.FLOWS: problems.append(f'{w}: flow {s.get("flow")}')
        for k in ('title', 'paper', 'here'):
            t = str(s.get(k, ''))
            if VERDICT.search(t): problems.append(f'{w}: verdict word in {k}')
            if re.search(r'[+−-]?\d+\.\d+', t): problems.append(f'{w}: a number is typed into {k}; numbers come from read')
            if re.search(r'[·()]', t): problems.append(f'{w}: separator or parenthesis in {k}')
        for a in s.get('actions') or []:
            if a.get('tool') not in TOOLS: problems.append(f'{w}: tool {a.get("tool")}'); continue
            args = a.get('args') or {}
            if a['tool'] == 'parameter_set':
                pid = ref_ok(args.get('project_id'), w)
                if pid and args.get('name') not in [c['name'] for c in pids[pid]['controls']]: problems.append(f'{w}: {pid} has no control {args.get("name")}')
            if a['tool'] == 'project_create':
                if args.get('template_id') not in [t['id'] for t in inv['templates']]: problems.append(f'{w}: no template {args.get("template_id")}')
                else:
                    src = pids.get(str(args.get('from_project_id', ''))[3:], {})
                    have = {**(src.get('bindings') or {} if src.get('template') == args['template_id'] else {}), **(args.get('bindings') or {})}
                    q = next(t['question'] for t in inv['templates'] if t['id'] == args['template_id'])
                    missing = [k for k in re.findall(r'\{(\w+)\}', q) if k not in have]
                    if missing: problems.append(f'{w}: the new project leaves blanks unfilled: {", ".join(missing)}')
                    for k, v in (args.get('bindings') or {}).items():
                        if isinstance(v, str) and any(c.replace('_', x) in v.lower() for c in inv['selection_conditions'] for x in ('_', '-', ' ')):
                            problems.append(f'{w}: blank {k} uses an internal condition name; say what the stimuli do, such as "stimuli that drive both regions"')
                        if isinstance(v, str) and re.search(r'\bDoes \{' + k + r'\}', q) and re.match(r'[a-z-]+s\b', v) and not re.match(r'(a|an|the|one)\b', v):
                            problems.append(f'{w}: blank {k} follows "Does", so it reads as one thing; write "{v}" in the singular, such as "an item chosen for ..."')
                        if isinstance(v, str) and k in re.findall(r'\{(\w+)\}', q) and v[:1].isupper(): problems.append(f'{w}: blank {k} reads inside a sentence; write "{v}" in lower case, as a phrase such as "the superior parietal lobe"')
                    if a.get('as'): plan_of[a['as']] = next(t['plan'] for t in inv['templates'] if t['id'] == args['template_id'])
                if args.get('from_project_id'): ref_ok(args['from_project_id'], w)
                if a.get('as'): made.add(a['as'])
            if a['tool'] in ('project_run', 'project_update'): ref_ok(args.get('project_id'), w)
        sh = s.get('show') or {}
        ref_ok(sh.get('project'), f'{w} show')
        if sh.get('view') not in VIEWS: problems.append(f'{w}: view {sh.get("view")}')
        if sh.get('region') and sh['region'] not in regs: problems.append(f'{w}: no region {sh["region"]}')
        rd = s.get('read')
        if rd:
            pid = ref_ok(rd.get('project'), f'{w} read')
            if rd.get('kind') not in READS: problems.append(f'{w}: read kind {rd.get("kind")}')
            if rd.get('kind') == 'paired' and rd.get('region') not in regs: problems.append(f'{w}: read region {rd.get("region")}')
            if rd.get('kind') == 'selection' and rd.get('condition') not in inv['selection_conditions']: problems.append(f'{w}: condition {rd.get("condition")}')
            if pid and rd.get('kind') not in pids[pid]['analyses']: problems.append(f'{w}: {pid} has no {rd.get("kind")} result')
        if s.get('wait') not in (None, 'preview', 'run'): problems.append(f'{w}: wait {s.get("wait")}')
        acts = s.get('actions') or []
        for a in acts:
            pr = (a.get('args') or {}).get('project_id')
            if a.get('tool') == 'project_run' and not str(pr).startswith('$made:'): problems.append(f'{w}: runs {pr}, an existing study; create a project and run that')
            if a.get('tool') in ('parameter_set', 'project_update') and str(pr).startswith('$p:') and s.get('wait') != 'preview': problems.append(f'{w}: changes {pr} without wait "preview"')
            if a.get('tool') == 'project_run' and str(pr).startswith('$made:'):
                if pr not in limited: problems.append(f'{w}: runs {pr} before a project_update gives it at most 8 pairs')
                if plan_of.get(pr[6:], 'matched') != 'matched': problems.append(f'{w}: {pr} has a {plan_of[pr[6:]]} plan; only matched-pair plans run, so create it from a template whose plan is matched')
                if s.get('wait') != 'run': problems.append(f'{w}: a run step needs wait "run"')
            if a.get('tool') == 'project_update' and str(pr).startswith('$made:'):
                pv = (a.get('args') or {}).get('pairs')
                if isinstance(pv, str) and (pv.startswith('$pairs_from:') or pv.startswith('$swap_outcome:')): limited.add(pr)
                elif isinstance(pv, str) and pv.startswith('$pairs_first:'):
                    try: n = int(pv.rsplit(':', 1)[1])
                    except ValueError: n = 99
                    if n > 8: problems.append(f'{w}: {n} pairs; at most 8')
                    else: limited.add(pr)
    return problems


def write(store, seed_id: str, base_url: str, attempts: int = 5) -> dict:
    """Ask the agent to write the demo for a seed; check it; on problems, give them back and ask again."""
    seed = json.load(open(SEEDS / f'{seed_id}.json')); inv = inventory(store, seed['template'])
    cfg = {'mcpServers': {'vcl': {'command': sys.executable, 'args': ['-m', 'app_server.lab.mcp_proxy', base_url], 'cwd': str(ROOT)}}}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f: json.dump(cfg, f); cfg_path = f.name
    prompt = (f"Write a demo that replays this paper's experiment in this app, in the paper's own order.\n"
              f"Paper: {seed['paper']}\nLink: {seed['url']}\nTemplate to build on: {seed['template']}\n\n"
              + ("Read the paper first with paper_fetch and paper_read, so every 'paper' sentence matches what it did.\n\n" if planner_agent.backend() == 'planner'
                 else "Read the paper's page first with WebFetch, so every 'paper' sentence matches what it did.\n\n")
              + FORMAT % {'views': VIEWS, 'reads': READS, 'tools': TOOLS}
              + "\nWhat exists in the app:\n" + json.dumps(inv, ensure_ascii=False))
    try:
        for n in range(attempts):
            if planner_agent.backend() == 'planner':   # the cluster: the planner, with the lab's tools in place of WebFetch
                text = planner_agent.turn('You write demos for the Simulaxon lab app. Use the tools to read the paper and the app; answer with the JSON only.', [], prompt, base_url)
            else:
                r = subprocess.run(['claude', '-p', prompt, '--mcp-config', cfg_path, '--strict-mcp-config', '--allowedTools', 'mcp__vcl', 'WebFetch',
                                    '--disallowedTools', 'Bash', 'Edit', 'Write', 'NotebookEdit', 'Agent', '--output-format', 'json'],
                                   capture_output=True, text=True, timeout=900, cwd=str(ROOT), env={**os.environ, 'PYTHONPATH': str(ROOT)})
                if r.returncode != 0: raise RuntimeError((r.stderr or r.stdout)[-400:])
                text = json.loads(r.stdout).get('result', '')
            m = re.search(r'\{[\s\S]*\}', text)
            try: demo = json.loads(m.group(0)) if m else {}
            except json.JSONDecodeError as e: demo, probs = {}, [f'not valid JSON: {e}']
            else: probs = check(demo, seed, inv)
            if not probs:
                out = {**seed, 'title': demo['title'], 'steps': demo['steps'], 'written_by': 'agent', 'attempts': n + 1}
                WRITTEN.mkdir(exist_ok=True); json.dump(out, open(WRITTEN / f'{seed_id}.json', 'w'), indent=1, ensure_ascii=False)
                return {'id': seed_id, 'steps': len(demo['steps']), 'attempts': n + 1}
            prompt += "\n\nYour last answer had these problems. Fix every one and answer with the whole JSON again:\n- " + '\n- '.join(probs) + "\n\nYour last answer:\n" + (m.group(0) if m else text)[:12000]
        raise RuntimeError('still has problems after %d attempts: %s' % (attempts, '; '.join(probs[:8])))
    finally:
        os.unlink(cfg_path)
