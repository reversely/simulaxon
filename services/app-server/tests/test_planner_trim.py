"""What the planner sees of a long chat: the person's latest message always, tool results never apart from their call,
and never more than the character budget."""
import json
from app_server.lab.planner_agent import _trim


def round_(i, calls, body='x'):
    return [{'role': 'assistant', 'content': None, 'tool_calls': [{'id': f'c{i}_{k}'} for k in range(calls)]}] + \
           [{'role': 'tool', 'tool_call_id': f'c{i}_{k}', 'content': body} for k in range(calls)]


def paired(h):
    """Every tool message follows an assistant message that called it."""
    called = set()
    for m in h:
        if m['role'] == 'assistant': called = {c['id'] for c in m.get('tool_calls') or []}
        if m['role'] == 'tool' and m['tool_call_id'] not in called: return False
    return True


def test_a_long_turn_keeps_the_persons_message():
    h = [{'role': 'user', 'content': 'replicate this paper'}] + [m for i in range(24) for m in round_(i, 3)]   # 97 messages
    t = _trim(h)
    assert t[0] == h[0] and t[1]['role'] == 'assistant' and t[-1] == h[-1] and len(t) <= 80 and paired(t)


def test_large_results_stay_within_the_budget():
    h = [{'role': 'user', 'content': 'read the paper'}] + [m for i in range(12) for m in round_(i, 2, 'y' * 20000)]
    t = _trim(h, budget=140_000)
    assert t[0] == h[0] and sum(len(json.dumps(m)) for m in t) <= 140_000 and paired(t) and t[-1] == h[-1]


def test_earlier_turns_come_whole_from_a_persons_message():
    h = [{'role': 'user', 'content': 'first'}] + round_(0, 1) + [{'role': 'assistant', 'content': 'done'},
         {'role': 'user', 'content': 'second'}] + round_(1, 1)
    t = _trim(h)
    assert t == h
    t = _trim(h, keep=4)   # room for the second turn only
    assert t[0]['content'] == 'second' and paired(t)


def test_an_empty_history_sends_nothing():
    assert _trim([]) == []
