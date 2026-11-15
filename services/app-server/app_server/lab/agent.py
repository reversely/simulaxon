"""The conversation's agent: Claude Code in print mode, with only the lab's tools, through the MCP proxy; on the cluster,
the planner in a tool-calling loop over the same tools (planner_agent.py).

One call per message. The reply is plain text; actions happen through the same tools the panels use.
"""
from __future__ import annotations
import json, os, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SYSTEM = """You are the agent inside Simulaxon, an app where people run in-silico experiments on TRIBE v2, a model that predicts fMRI responses of an average viewer, in worlds rendered by Isaac Sim.
Use the vcl tools to read and change the project; never invent numbers. Every number you give comes from a tool result, with its interval when there is one.
Write short plain sentences. No verdict words such as supported, confirmed, refuted or ruled out. Results are screening, not measured brains.
When the person asks for a change you can make with a tool, make it, then say what changed. When something needs a renderer or GPU run that no tool offers, say so plainly and say what would be needed.
The current project id is {pid}."""
from .titles import GUIDE as _TITLES
SYSTEM = SYSTEM.replace('The current project id is {pid}.', _TITLES.replace('{', '{{').replace('}', '}}') + '\n\nThe current project id is {pid}.')   # how to title (#11)


def ask(project_id: str, message: str, history: list[dict], base_url: str) -> str:
    from . import planner_agent
    if planner_agent.backend() == 'planner':
        convo = [{'role': 'user' if m['who'] == 'person' else 'assistant', 'content': m['text']} for m in history[-10:]]
        while convo and convo[0]['role'] != 'user': convo = convo[1:]
        return planner_agent.turn(SYSTEM.format(pid=project_id), convo, message, base_url)
    cfg = {'mcpServers': {'vcl': {'command': sys.executable, 'args': ['-m', 'app_server.lab.mcp_proxy', base_url], 'cwd': str(ROOT)}}}
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f: json.dump(cfg, f); path = f.name
    convo = ''.join(f"{'Person' if m['who'] == 'person' else 'Agent'}: {m['text']}\n" for m in history[-10:])
    prompt = (f'Conversation so far:\n{convo}\n' if convo else '') + f'Person: {message}'
    try:
        r = subprocess.run(['claude', '-p', prompt, '--mcp-config', path, '--strict-mcp-config', '--allowedTools', 'mcp__vcl',
                            '--disallowedTools', 'Bash', 'Edit', 'Write', 'NotebookEdit', 'WebFetch', 'WebSearch', 'Agent',
                            '--append-system-prompt', SYSTEM.format(pid=project_id), '--output-format', 'json'],
                           capture_output=True, text=True, timeout=300, cwd=str(ROOT), env={**os.environ, 'PYTHONPATH': str(ROOT)})
        if r.returncode != 0: raise RuntimeError((r.stderr or r.stdout)[-400:])
        return json.loads(r.stdout).get('result', '').strip()
    finally:
        os.unlink(path)
