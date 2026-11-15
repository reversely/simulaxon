"""The page names the agent by the planner model that runs it, or "the agent"; never a runtime's name (#40)."""
from app_server.lab import planner_agent
from app_server.config import PLANNER_MODEL


def test_label_names_the_planner_model(monkeypatch):
    monkeypatch.setenv('SIMULAXON_AGENT', 'planner')
    assert planner_agent.label() == f'{PLANNER_MODEL} on the planner'


def test_label_never_names_claude_code(monkeypatch):
    monkeypatch.setenv('SIMULAXON_AGENT', 'claude')
    assert planner_agent.label() == 'the agent'


def test_saved_runtime_names_read_as_the_agent():
    assert planner_agent.shown('Claude Code') == 'the agent'
    assert planner_agent.shown(None) == 'the agent'
    assert planner_agent.shown('nvidia/nemotron-3-super on the planner') == 'nvidia/nemotron-3-super on the planner'
