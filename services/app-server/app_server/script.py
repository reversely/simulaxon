"""Scene script parser (implementation spec §5).

A scene script is a Python file. Parameters are top-level assignments whose value is a call to one
of a fixed set of constructors with literal arguments. Everything else is ordinary code that the
renderer runs. Parsing never executes the file, so the parameter list is deterministic and safe.

    item       = asset("palatial/D00002", role="manipulated", domain=search("palatial", "food"))
    distance_m = number(0.62, unit="m", range=(0.3, 3.0), sampler="log_uniform", role="randomized",
                        target="camera.distance_to(item)")
"""
from __future__ import annotations
import ast
from dataclasses import dataclass, field, asdict
from typing import Any

TYPES = {'number', 'angle', 'asset', 'colour', 'choice', 'prompt', 'pose', 'world'}
ROLES = {'manipulated', 'randomized', 'fixed', 'measured', 'matched', 'split'}
SAMPLERS = {'fixed', 'uniform', 'log_uniform', 'normal', 'choice', 'sequence', 'grid'}
KNOWN_KEYS = {'unit', 'range', 'sampler', 'role', 'target', 'domain', 'options', 'steps', 'label'}


class ScriptError(ValueError):
    def __init__(self, line: int, message: str):
        super().__init__(f'line {line}: {message}'); self.line = line; self.message = message


@dataclass
class Parameter:
    name: str
    type: str
    value: Any
    role: str = 'fixed'
    unit: str | None = None
    range: tuple | None = None
    sampler: str = 'fixed'
    target: str | None = None
    domain: Any = None
    options: list | None = None
    steps: int | None = None
    label: str | None = None
    line: int = 0

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _literal(node: ast.AST, line: int) -> Any:
    """Literal values, plus nested known calls such as search(...) kept as {'call': name, 'args': [...]}."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        return {'call': node.func.id, 'args': [_literal(a, line) for a in node.args],
                'kwargs': {k.arg: _literal(k.value, line) for k in node.keywords}}
    try:
        return ast.literal_eval(node)
    except Exception:
        raise ScriptError(line, 'parameter arguments must be literals, such as numbers, strings, tuples or lists')


def parse(source: str) -> list[Parameter]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ScriptError(e.lineno or 0, f'syntax error: {e.msg}')
    params: list[Parameter] = []; seen: set[str] = set()
    for node in tree.body:
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)):
            continue
        kind = node.value.func.id
        if kind not in TYPES:
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            raise ScriptError(node.lineno, 'a parameter must be assigned to a single name')
        name = node.targets[0].id
        if name in seen:
            raise ScriptError(node.lineno, f'parameter "{name}" is declared twice')
        seen.add(name)
        call = node.value
        if not call.args:
            raise ScriptError(node.lineno, f'{kind}() needs a current value as its first argument')
        kw = {k.arg: _literal(k.value, node.lineno) for k in call.keywords}
        unknown = set(kw) - KNOWN_KEYS
        if unknown:
            raise ScriptError(node.lineno, f'unknown setting {sorted(unknown)} on "{name}"')
        p = Parameter(name=name, type=kind, value=_literal(call.args[0], node.lineno), line=node.lineno,
                      **{k: (tuple(v) if k == 'range' and isinstance(v, list) else v) for k, v in kw.items()})
        _validate(p)
        params.append(p)
    return params


def _validate(p: Parameter) -> None:
    if p.role not in ROLES:
        raise ScriptError(p.line, f'role "{p.role}" is not one of {sorted(ROLES)}')
    if p.sampler not in SAMPLERS:
        raise ScriptError(p.line, f'sampler "{p.sampler}" is not one of {sorted(SAMPLERS)}')
    if p.type in ('number', 'angle'):
        if not isinstance(p.value, (int, float)):
            raise ScriptError(p.line, f'"{p.name}" must start with a number')
        if p.range is not None:
            lo, hi = p.range
            if not lo <= p.value <= hi:
                raise ScriptError(p.line, f'"{p.name}" = {p.value} is outside its range {lo} to {hi}')
            if p.sampler == 'log_uniform' and lo <= 0:
                raise ScriptError(p.line, f'"{p.name}" uses log_uniform, so its range must be above 0')
        if p.type == 'angle' and p.unit is None:
            p.unit = 'deg'
    if p.role == 'randomized' and p.sampler == 'fixed':
        raise ScriptError(p.line, f'"{p.name}" is randomized but has no sampler')
    if p.sampler in ('uniform', 'log_uniform', 'normal') and p.range is None:
        raise ScriptError(p.line, f'"{p.name}" uses {p.sampler}, so it needs a range')
    if p.type == 'choice' and not p.options:
        raise ScriptError(p.line, f'"{p.name}" is a choice, so it needs options')


def resolve_targets(params: list[Parameter], known: set[str]) -> list[str]:
    """Return problems for targets that are not known scene attributes, camera relations or connector settings."""
    problems = []
    for p in params:
        if p.target is None:
            continue
        if p.target.startswith('connector:'):
            if p.target not in known:
                problems.append(f'line {p.line}: "{p.name}" targets {p.target}, which no connector in the pipeline declares')
        elif p.target.split('(')[0] not in known:
            problems.append(f'line {p.line}: "{p.name}" targets {p.target}, which is not in the scene')
    return problems
