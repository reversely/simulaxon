"""The agent on the cluster: Nemotron through the planner's OpenAI-compatible API, calling the lab's tools.

Where Claude Code is installed (the Spark), a turn is `claude -p` with the lab's tools through the MCP proxy. The
cluster has no Claude Code; the planner serves the model (fuzzball/simulaxon.fz). There a turn is a tool-calling loop:
each tool call the model makes goes to POST /tools/{name} as actor "agent", exactly as the MCP proxy forwards it, and
its result goes back to the model, until the model answers without calling a tool.

SIMULAXON_AGENT picks the runtime: "planner" or "claude". By default it is the planner when PLANNER_URL is set or
Claude Code is not installed.
"""
from __future__ import annotations
import json, os, shutil, urllib.error, urllib.request
from ..config import PLANNER_MODEL, PLANNER_URL

ROUNDS = 24          # tool rounds in one turn before the agent must answer
RESULT_CHARS = 20000  # a tool result as the model sees it; the page keeps its own shorter copy


def backend() -> str:
    v = os.environ.get('SIMULAXON_AGENT')
    if v: return v
    return 'planner' if os.environ.get('PLANNER_URL') or not shutil.which('claude') else 'claude'


def label() -> str:
    """The agent's name as the page shows it."""
    return f'{PLANNER_MODEL} on the planner' if backend() == 'planner' else 'Claude Code'


def call_tool(base: str, name: str, args: dict):
    """One tool through the app's HTTP surface as the agent; refusals come back as {error, detail} for the model to fix."""
    req = urllib.request.Request(f'{base}/tools/{name}', method='POST', data=json.dumps(args).encode(),
                                 headers={'Content-Type': 'application/json', 'X-Actor': 'agent'})
    try:
        with urllib.request.urlopen(req, timeout=600) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: detail = json.loads(e.read() or b'{}').get('detail')
        except ValueError: detail = None
        return {'error': e.code, 'detail': detail}


def tools(base: str) -> list[dict]:
    """Every tool the agent may call, in the OpenAI function format: the same names, docs and argument lists the MCP
    proxy offers Claude Code. Person-only tools are left out, since the server refuses them to the agent."""
    with urllib.request.urlopen(f'{base}/tools', timeout=60) as r: listed = json.loads(r.read())
    out = []
    for t in listed:
        if t.get('person_only'): continue
        desc = f"{(t.get('doc') or t['name']).strip()} Arguments: {t.get('arguments') or 'none'}."
        if t['name'] == 'parameter_update':
            desc += ' To change a parameter, read its current version with parameter_list first and pass it as expect_version.'
        out.append({'type': 'function', 'function': {'name': t['name'], 'description': desc[:1500],
                                                     'parameters': {'type': 'object', 'additionalProperties': True}}})
    return out


def chat(messages: list[dict], tool_list: list[dict]) -> dict:
    body = {'model': PLANNER_MODEL, 'messages': messages, 'tools': tool_list, 'tool_choice': 'auto', 'temperature': 0.2}
    req = urllib.request.Request(PLANNER_URL + '/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=600) as r: return json.loads(r.read())['choices'][0]['message']
    except OSError as e:
        raise RuntimeError(f'the planner is unreachable at {PLANNER_URL}: {e}') from e


HISTORY_CHARS = 140_000   # history sent per request. vLLM serves 65,536 tokens (fuzzball/simulaxon.fz); the system prompt and
                          # 59 tool definitions take about 21,000 characters (about 5,300 tokens, measured 2026-11-14). At a
                          # cautious 3 characters per token for JSON, this is about 47,000 tokens, which leaves room to answer.


def _trim(history: list[dict], keep: int = 80, budget: int = HISTORY_CHARS) -> list[dict]:
    """The messages the model sees: always the person's latest message, then as much of the newest context as fits in
    keep messages and budget characters. Every tool result stays with the assistant message that called it.

    Within the current turn: the person's message, then its newest rounds. Before it: earlier turns, whole from a
    person's message on, while they fit."""
    size = lambda m: len(json.dumps(m, default=str))
    last = max((i for i, m in enumerate(history) if m.get('role') == 'user'), default=None)
    if last is None: return []
    prompt, turn = history[last], history[last + 1:]
    room_n, room_c = keep - 1, budget - size(prompt)
    kept: list[dict] = []
    for m in reversed(turn):   # the current turn's newest messages first
        if len(kept) >= room_n or size(m) > room_c: break
        kept.insert(0, m); room_n -= 1; room_c -= size(m)
    if len(kept) < len(turn):   # the turn was cut: start at an assistant message, so no tool result lacks its call
        while kept and kept[0].get('role') != 'assistant': kept.pop(0)
        if not kept and turn: kept = turn[-1:] if turn[-1].get('role') == 'assistant' else []   # never lose the latest round entirely
        return [prompt] + kept
    earlier, before = history[:last], []
    for m in reversed(earlier):   # earlier turns, newest first, while they fit
        if room_n <= 0 or size(m) > room_c: break
        before.insert(0, m); room_n -= 1; room_c -= size(m)
    while before and before[0].get('role') != 'user': before.pop(0)
    return before + [prompt] + kept


def turn(system: str, history: list[dict], prompt: str, base: str, on_tool=None, on_result=None, on_text=None, stop=None) -> str:
    """One turn: the person's (or a wake-up's) prompt, then model and tool rounds until the model answers.

    history holds the conversation as OpenAI messages and is extended in place, so the caller can keep it across turns.
    on_tool(name, args) is called before each tool runs, on_result(name, args, result) after, on_text(text) for text the
    model writes alongside its tool calls. stop(), when given and true, ends the turn between rounds."""
    history.append({'role': 'user', 'content': prompt})
    offered = tools(base)
    for _ in range(ROUNDS):
        if stop and stop(): return ''
        msg = chat([{'role': 'system', 'content': system}] + _trim(history), offered)
        history.append({k: v for k, v in msg.items() if k in ('role', 'content', 'tool_calls')})
        calls = msg.get('tool_calls') or []
        if not calls: return (msg.get('content') or '').strip()
        if (msg.get('content') or '').strip() and on_text: on_text(msg['content'].strip())
        for c in calls:
            name = c['function']['name']
            try: args = json.loads(c['function'].get('arguments') or '{}')
            except json.JSONDecodeError: args = {}
            if not isinstance(args, dict): args = {}
            if isinstance(args.get('arguments'), dict) and len(args) == 1: args = args['arguments']   # the MCP proxy's wrapping, if the model copies it
            if on_tool: on_tool(name, args)
            res = call_tool(base, name, args)
            if on_result: on_result(name, args, res)
            history.append({'role': 'tool', 'tool_call_id': c.get('id', name), 'content': json.dumps(res, default=str)[:RESULT_CHARS]})
    return f'I stopped after {ROUNDS} rounds of tool calls without an answer.'
