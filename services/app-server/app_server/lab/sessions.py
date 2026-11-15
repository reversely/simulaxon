"""Chats with the agent: discuss an experiment, link or upload data, set it up together, and let the agent run it; or
give one goal and let it go all the way through.

A chat is one agent conversation, resumed turn after turn, so the agent keeps everything it read and did: a Claude Code
session where Claude Code is installed, or the planner's message history on the cluster (planner_agent.py). Each message
from the person starts a turn, in one of two modes:
- discuss: the agent answers, proposes and sets up only what was agreed, then waits for the person;
- through: the agent sets up and runs everything on its own, turn after turn, until it writes DONE.
In both, when a turn ends while a fetch or a run is under way, the chat waits for it and wakes the agent with what
happened, so results arrive in the chat without anyone asking. Every tool call and reply is broadcast as it happens and
kept in backend/data/sessions/<id>.json, so the page shows the work live and a restart resumes it.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from . import datasets, planner_agent, titles
from .ingest import DATA

DIR = DATA / 'sessions'
ROOT = Path(__file__).resolve().parents[2]
SYSTEM = """You are the agent inside Simulaxon. You set up and run experiments on TRIBE v2, a model that predicts the fMRI response of an average viewer to video, and you compare what it predicts with what a paper reported.
You work through the lab's tools only. The usual path for a replication:
1. paper_fetch the paper, then paper_read its methods and results: the stimuli, the design and timing, the regions, and the reported contrast with where it is reported.
2. Find the stimuli: data the person linked or uploaded (dataset_list, file_list), the paper's data or stimulus links (paper_read with find="available" or "osf" or "github" or "openneuro"), or paper_search and dataset_get for a public set of the same kind. Check the licence and size with dataset_get before fetching; fetch only the files the experiment needs with dataset_fetch.
3. file_list the files, region_search the regions, then experiment_create with the conditions, timing, regions, contrasts and the reported result. Fix whatever it refuses and create again.
4. project_run the project. Runs and fetches continue in the background: when you have started one and have nothing else to do, end your turn with the single word WAITING. You will be woken with what happened.
5. experiment_get the results and report, for each reported result, TRIBE's value with its interval, its rank among the 360 areas, the shuffled-label control, and match or no match.
Measured here about TRIBE: its output has the blood-flow lag removed, so a stimulus's response is read over the seconds it is on screen (the default). One image held 4 s gives faces above objects in FFC (+0.052, above 93% of the 360 areas); eight images flashed 0.5 s each in a 4 s block give nothing or the reverse in those seconds. So hold each image about 1 s or longer, and say so when the paper's timing was faster.
Cosmos (a condition's cosmos option) restyles stimuli toward photoreal video. Measured here: Cosmos over an Isaac render moved the fusiform by +0.085, and one Cosmos seed moves it by 0.026, the size of the effects studied. So give every Cosmos condition at least two seeds, and run the same stimuli without Cosmos as their own condition, so the difference Cosmos makes is measured beside the result. Cosmos takes about 4 min per 4 s clip.
When paper_fetch finds only the abstract (the full text is not openly licensed), say so, work from what the abstract states, mark every design choice the abstract does not give as your assumption, and say that a person can add the PDF for the full methods.
Rules: every number you give comes from a tool result. TRIBE reads video only, cannot tell left from right in the visual field, and has no attention or eye-specific input: when a paper's effect depends on those, say what the closest stimulus-driven version is and run that. No verdict words such as supported, confirmed or refuted. Short plain sentences. Size a first run to finish in about 10 minutes, by experiment_create's minutes_estimate (TRIBE takes about 30 s a clip); run more trials only when the person asks or a first run is too noisy to read. A run you no longer need can be stopped with run_stop."""
SYSTEM += '\n\n' + titles.GUIDE   # how to title projects and experiments (#11)
MODES = {
    'discuss': "This message is for discussion. Answer it, propose, and look things up as needed. Set up an experiment with experiment_create only when the person asks for it or agrees to your proposal, so they can see it; do not start a run (project_run) or a large fetch until they ask. End your turn when you have answered.",
    'through': "Go all the way through on your own: read, fetch, set up, run, and report. When the goal is finished, end your final report with the single word DONE.",
}


def _mcp_config(base_url: str) -> str:
    cfg = {'mcpServers': {'vcl': {'command': sys.executable, 'args': ['-m', 'app_server.lab.mcp_proxy', base_url], 'cwd': str(ROOT)}}}
    f = tempfile.NamedTemporaryFile('w', suffix='.json', delete=False); json.dump(cfg, f); f.close(); return f.name


def _internal(res) -> bool:
    """A tool's own fault (500), as opposed to a refusal of the request (#14)."""
    return isinstance(res, dict) and res.get('error') == 500


def _refused(res) -> bool:
    """A tool result the page marks refused: an error with a value. A success may carry "error": null, such as a fetch's status."""
    return isinstance(res, dict) and bool(res.get('error'))


def _unwrap(body: str):
    """A tool result as the agent saw it: the proxy's JSON, which the MCP layer may wrap once more as a string."""
    try:
        j = json.loads(body)
        while isinstance(j, dict) and isinstance(j.get('result'), str): j = json.loads(j['result'])
        return j.get('result', j) if isinstance(j, dict) else j
    except Exception:
        return None


class Session:
    def __init__(self, d: dict, base_url: str, broadcast, tools):
        self.d = d; self.base = base_url; self.broadcast = broadcast; self.tools = tools; self.stop = threading.Event(); self.inbox: list[dict] = []
        self.thread: threading.Thread | None = None; self.proc = None

    def save(self):
        DIR.mkdir(parents=True, exist_ok=True); (DIR / f"{self.d['id']}.json").write_text(json.dumps(self.d, indent=1, default=str))

    def emit(self, **k):
        self.broadcast({'session': self.d['id'], **k})

    def mine(self) -> tuple[set, set]:
        """The projects and datasets this chat started work on, from its own tool calls, so it never waits on another chat's run."""
        projects, fetches = {self.d.get('project_id')} - {None}, set()
        for t in self.d.get('turns', []):
            for c in t.get('tool_calls', []):
                a = c.get('arguments') or {}
                if c['tool'] in ('project_run', 'experiment_create') and a.get('project_id'): projects.add(a['project_id'])
                if c['tool'] == 'dataset_fetch':
                    try: fetches.add(_unwrap(c.get('result') or '{}').get('dataset_id'))
                    except Exception: pass
        return projects, fetches - {None}

    def pending(self) -> list[str]:
        """Background work this chat is waiting on: its own fetches under way and its own projects running."""
        projects, fetches = self.mine()
        out = [f"fetch of {did}" for did, st in datasets._fetches.items() if st['status'] == 'fetching' and did in fetches]
        out += [f"run of project {p.id}" for p in self.tools.store.list('project') if p.data.get('status') == 'Running' and p.id in projects]
        return out

    def snapshot(self) -> dict:
        return {**{('fetch', k): v['status'] for k, v in datasets._fetches.items()}, **{('run', p.id): p.data.get('status') for p in self.tools.store.list('project')}}

    def finished_report(self, before: dict) -> str:
        """What changed while waiting: fetches that ended and projects whose runs ended, with errors."""
        lines = []
        for did, st in datasets._fetches.items():
            if before.get(('fetch', did)) == 'fetching' and st['status'] != 'fetching':
                lines.append(f"Fetch {did}: {st['status']}, {st['done']} of {st['files']} files" + (f", error: {st['error']}" if st['error'] else ''))
        for p in self.tools.store.list('project'):
            if before.get(('run', p.id)) == 'Running' and p.data.get('status') != 'Running':
                lines.append(f"Run of project {p.id} ({p.data.get('title')}): {'finished' if p.data.get('status') == 'Done' else 'stopped or failed; the project is back to Draft'}")
        return '\n'.join(lines) or 'The background work ended.'

    def _linked(self, call: dict, res):
        """experiment_create made the project this chat now builds: remember it and tell the page."""
        if call['tool'] == 'experiment_create' and isinstance(res, dict) and res.get('project_id'):
            self.d['project_id'] = res['project_id']; call['project_id'] = res['project_id']; self.emit(stage='project', project_id=res['project_id'])

    def turn_planner(self, prompt: str, rec: dict, n: int, t0: float, system: str) -> str:
        """A turn on the planner: the same records and events as a Claude Code turn, so the page cannot tell them apart."""
        def on_tool(name, args):
            call = {'tool': name, 'arguments': args, 'at': round(time.time() - t0, 1)}
            rec['tool_calls'].append(call); self.emit(stage='tool', n=n, **call); self.save()
        def on_result(name, args, res):
            call = rec['tool_calls'][-1]; body = json.dumps(res, default=str)
            call['result'] = body[:600]; call['error'] = _refused(res); call['internal'] = _internal(res)
            self._linked(call, res.get('result') if isinstance(res, dict) else None); self.save()
        def on_text(text):
            rec['text'].append(text); self.emit(stage='text', n=n, text=text)
        try:
            rec['reply'] = planner_agent.turn(system, self.d.setdefault('messages', []), prompt, self.base, on_tool, on_result, on_text, self.stop.is_set)
        except Exception as e:
            rec['reply'] = f'(the agent stopped: {type(e).__name__}: {e})'[:500]
        rec['seconds'] = round(time.time() - t0); rec['ended'] = time.strftime('%H:%M:%S'); self.save()
        self.emit(stage='turn_done', n=n, reply=rec['reply'])
        return rec['reply'] or ''

    def turn(self, prompt: str, source: str) -> str:
        n = len(self.d['turns']) + 1; t0 = time.time(); mode = self.d.get('mode', 'through')
        rec = {'n': n, 'from': source, 'mode': mode, 'prompt': prompt, 'started': time.strftime('%H:%M:%S'), 'tool_calls': [], 'text': [], 'reply': None}
        self.d['turns'].append(rec); self.d['status'] = 'working'; self.save(); self.emit(stage='turn', n=n)
        system = SYSTEM + '\n' + MODES[mode] + (f"\nThe project for this chat, if any: {self.d['project_id']}." if self.d.get('project_id') else '')
        # Each turn runs on the agent this place has now, so a chat begun on the Spark (Claude Code) carries on on the cluster.
        self.d['runtime'] = planner_agent.backend(); self.d['agent'] = planner_agent.label()
        if self.d['runtime'] == 'planner': return self.turn_planner(prompt, rec, n, t0, system)
        cfg = _mcp_config(self.base)
        cmd = ['claude', '-p', prompt, '--mcp-config', cfg, '--strict-mcp-config', '--allowedTools', 'mcp__vcl',
               '--disallowedTools', 'Bash', 'Edit', 'Write', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Agent', 'Read', 'Glob', 'Grep',
               '--append-system-prompt', system, '--output-format', 'stream-json', '--verbose']
        if self.d.get('claude_session'): cmd[1:1] = ['--resume', self.d['claude_session']]
        self.proc = p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=str(ROOT), env={**os.environ, 'PYTHONPATH': str(ROOT)})
        try:
            for line in p.stdout:
                if self.stop.is_set(): p.terminate(); break
                try: ev = json.loads(line)
                except json.JSONDecodeError: continue
                if ev.get('session_id'): self.d['claude_session'] = ev['session_id']
                if ev.get('type') == 'assistant':
                    for c in ev.get('message', {}).get('content', []):
                        if c.get('type') == 'tool_use':
                            call = {'tool': c['name'].replace('mcp__vcl__', ''), 'arguments': (c.get('input') or {}).get('arguments', c.get('input') or {}), 'at': round(time.time() - t0, 1), 'id': c.get('id')}
                            rec['tool_calls'].append(call); self.emit(stage='tool', n=n, **call)
                        elif c.get('type') == 'text' and c.get('text', '').strip():
                            rec['text'].append(c['text']); self.emit(stage='text', n=n, text=c['text'])
                if ev.get('type') == 'user':   # tool results: refusals are kept, so the page shows what the agent had to fix
                    for c in ev.get('message', {}).get('content', []):
                        if isinstance(c, dict) and c.get('type') == 'tool_result' and rec['tool_calls']:
                            body = c.get('content'); body = body[0].get('text', '') if isinstance(body, list) and body else str(body)
                            call = next((x for x in reversed(rec['tool_calls']) if x.get('id') and x['id'] == c.get('tool_use_id')), rec['tool_calls'][-1])   # parallel calls: each result to its own call
                            res = _unwrap(body)
                            call['result'] = body[:600]
                            call['error'] = bool(c.get('is_error')) or _refused(res); call['internal'] = _internal(res)
                            self._linked(call, res)
                if ev.get('type') == 'result':
                    rec['reply'] = ev.get('result', ''); rec['cost_usd'] = ev.get('total_cost_usd')
                self.save()
            p.wait(timeout=60)
        finally:
            os.unlink(cfg)
        if p.returncode not in (0, None) and not rec['reply']: rec['reply'] = f"(the agent stopped: {p.stderr.read()[-400:]})"
        rec['seconds'] = round(time.time() - t0); rec['ended'] = time.strftime('%H:%M:%S'); self.save()
        self.emit(stage='turn_done', n=n, reply=rec['reply'])
        return rec['reply'] or ''

    def run(self, prompt: str, source: str):
        """Turns until the agent waits for the person (discuss), finishes (through), or a limit or a person stops it."""
        d = self.d; t0 = time.time(); idle = 0; used = 0
        try:
            while not self.stop.is_set():
                if used >= d['max_turns']: d['status'] = 'idle'; d['why'] = f"stopped at the turn limit ({d['max_turns']}); send a message to continue"; break
                if time.time() - t0 > d['max_hours'] * 3600: d['status'] = 'idle'; d['why'] = f"stopped at the time limit ({d['max_hours']} h); send a message to continue"; break
                d['next'] = None; d['why'] = None; before = self.snapshot()
                reply = self.turn(prompt, source); used += 1
                if self.stop.is_set(): break
                if self.inbox:   # the person wrote during the turn: that comes next
                    m = self.inbox.pop(0); d['mode'] = m['mode']; prompt, source = m['text'], 'person'; continue
                if self.pending():
                    d['status'] = 'waiting'; d['waiting_for'] = self.pending(); self.save(); self.emit(stage='waiting', waiting_for=d['waiting_for'])
                    while self.pending() and not self.stop.is_set() and not self.inbox: time.sleep(5)
                    if self.stop.is_set(): break
                    if self.inbox and self.pending():
                        m = self.inbox.pop(0); d['mode'] = m['mode']; prompt, source = m['text'], 'person'; continue
                    prompt, source = 'The background work you were waiting for has ended:\n' + self.finished_report(before) + '\nContinue.', 'wake'
                    idle = 0; continue
                if d.get('mode') == 'through' and not reply.strip().endswith('DONE'):
                    idle += 1
                    if idle >= 3: d['status'] = 'idle'; d['why'] = 'three turns without progress or background work'; break
                    prompt, source = 'Nothing is running. Continue toward the goal; if it is finished, give the final report and end with DONE.', 'wake'
                    continue
                d['status'] = 'idle'; break   # the agent has answered, or finished: the chat waits for the person
            if self.stop.is_set(): d['status'] = 'idle'; d['why'] = 'stopped by a person'
        except Exception as e:
            d['status'] = 'failed'; d['why'] = f'{type(e).__name__}: {e}'[:400]
        d['waiting_for'] = None; d['updated'] = time.strftime('%Y-%m-%d %H:%M'); self.save(); self.emit(stage='ended', status=d['status'], why=d.get('why'))

    def say(self, text: str, mode: str, source: str = 'person'):
        """A message from the person: starts a turn now, or comes next if the agent is mid-turn or waiting."""
        if mode not in MODES: raise ValueError(f'mode must be one of {list(MODES)}')
        if self.thread and self.thread.is_alive():
            self.inbox.append({'text': text, 'mode': mode}); return {'id': self.d['id'], 'queued': True}
        self.d['mode'] = mode; self.stop.clear(); self.d['status'] = 'working'; self.d.pop('stop_requested', None); self.save()
        self.thread = threading.Thread(target=self.run, args=(text, source), daemon=True); self.thread.start()
        return {'id': self.d['id'], 'status': 'working'}


_live: dict[str, Session] = {}


def _load(sid: str, tools, broadcast, base_url) -> Session:
    if sid not in _live:
        d = json.loads((DIR / f'{sid}.json').read_text()); d.setdefault('mode', 'through')
        _live[sid] = Session(d, base_url, broadcast, tools)
    return _live[sid]


def start(tools, broadcast, base_url: str, text: str, mode: str = 'discuss', project_id: str | None = None, max_turns: int = 40, max_hours: float = 8) -> dict:
    """A new chat, started with the person's first message."""
    sid = 'session_' + uuid.uuid4().hex[:8]
    d = {'id': sid, 'goal': text, 'project_id': project_id, 'mode': mode, 'status': 'working', 'turns': [], 'max_turns': max_turns, 'max_hours': max_hours,
         'started': time.strftime('%Y-%m-%d %H:%M'), 'runtime': planner_agent.backend(), 'agent': planner_agent.label(), 'claude_session': None}
    s = Session(d, base_url, broadcast, tools); s.save(); _live[sid] = s
    return s.say(text if mode == 'discuss' else f'Goal: {text}', mode, 'person')


def message(tools, broadcast, base_url: str, sid: str, text: str, mode: str = 'discuss') -> dict:
    return _load(sid, tools, broadcast, base_url).say(text, mode)


def resume_all(tools, broadcast, base_url: str):
    """At start-up: chats cut off mid-turn or while waiting continue in the same conversation."""
    for f in DIR.glob('session_*.json') if DIR.exists() else []:
        d = json.loads(f.read_text())
        if d.get('status') in ('working', 'waiting') and not d.get('stop_requested'):
            s = _load(d['id'], tools, broadcast, base_url)
            s.say('The lab restarted while you were working. Runs that were going resume on their own from the clips already read, so leave them running: do not stop or restart them. Check where things stand and continue.', d.get('mode', 'through'), 'wake')


def get(sid: str) -> dict:
    d = json.loads((DIR / f'{sid}.json').read_text())
    return d | {'agent': planner_agent.shown(d.get('agent'))}


def listing(project_id: str | None = None) -> list[dict]:
    out = []
    for f in sorted(DIR.glob('session_*.json'), key=lambda p: p.stat().st_mtime, reverse=True) if DIR.exists() else []:
        d = json.loads(f.read_text())
        if project_id and d.get('project_id') != project_id: continue
        out.append({k: d.get(k) for k in ('id', 'goal', 'project_id', 'mode', 'status', 'why', 'started', 'updated', 'waiting_for')} | {'agent': planner_agent.shown(d.get('agent')),
            'turns': len(d['turns']), 'tool_calls': sum(len(t['tool_calls']) for t in d['turns']), 'errors': sum(sum(1 for c in t['tool_calls'] if c.get('error') and not c.get('internal')) for t in d['turns']),
            'internal_errors': sum(sum(1 for c in t['tool_calls'] if c.get('internal')) for t in d['turns'])})
    return out


def stop(sid: str) -> dict:
    s = _live.get(sid)
    f = DIR / f'{sid}.json'
    if f.exists():   # saved at once, so a restart before the turn ends never resumes a chat a person stopped
        d = json.loads(f.read_text()); d['stop_requested'] = True; f.write_text(json.dumps(d, indent=1))
        if s: s.d['stop_requested'] = True
    if s:
        s.stop.set(); s.inbox.clear()
        if s.proc and s.proc.poll() is None: s.proc.terminate()   # Claude Code; a planner turn checks stop between rounds
    return {'id': sid, 'stopping': bool(s)}


def upload(name: str, data: bytes, dataset_id: str | None = None) -> dict:
    """upload_file for a body already in memory."""
    tmp = Path(tempfile.mkdtemp()) / Path(name).name; tmp.write_bytes(data)
    return upload_file(name, tmp, dataset_id)


def upload_file(name: str, src: Path, dataset_id: str | None = None) -> dict:
    """Files a person adds in a chat become a dataset of their own, labelled as uploaded; archives are unpacked. src is
    the received file, moved into the dataset, so a large upload is never held in memory."""
    import shutil
    did = dataset_id or 'upload_' + uuid.uuid4().hex[:8]
    root = datasets.dataset_dir(did); root.mkdir(parents=True, exist_ok=True)   # refuses an ID such as ../ that leaves the datasets
    parts = [p for p in Path(name).parts if p not in ('', '.', '..', '/') and not p.startswith('.')]   # a folder import keeps its subfolders (#22)
    if not parts: raise ValueError(f'not a file name: {name!r}')
    safe = Path(*parts).as_posix(); (root / safe).parent.mkdir(parents=True, exist_ok=True); shutil.move(str(src), root / safe); size = (root / safe).stat().st_size
    if datasets.kind_of(safe) == 'archive':
        try: datasets._unpack(root / safe)
        except ValueError: (root / safe).unlink(); raise   # refused as too large to unpack: nothing of it stays
    meta_f = root / '_dataset.json'
    meta = json.loads(meta_f.read_text()) if meta_f.exists() else {'id': did, 'ref': 'upload', 'repository': 'upload', 'key': did, 'title': 'Uploaded in a chat', 'licence': None,
                                                                   'fetched_at': time.strftime('%Y-%m-%d %H:%M'), 'files': []}
    meta['files'] = sorted(set(meta['files'] + [safe])); meta_f.write_text(json.dumps(meta, indent=1))
    return {'dataset_id': did, 'file': safe, 'kind': datasets.kind_of(safe), 'megabytes': round(size / 1e6, 3)}
