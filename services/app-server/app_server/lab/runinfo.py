"""What a run records about how it was made (#19): when it started and ended, who started it, the code it ran, the
renderer revision and the version of every connector it used. Saved on the project with status Done, and read by
run_get, the record behind the results dashboard and its exports.

The owner (2026-11-14): "no run generation look, no export possibilities or tabulated data makes it look hardcoded &
unprofessional. yes, the result should be a dashboard"
"""
from __future__ import annotations
import subprocess, time
from pathlib import Path

from . import preview


def _code() -> str:
    """The commit the server's code came from, read once at import, so it names the code that is running."""
    try:
        here = Path(__file__).resolve().parent
        sha = subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=here, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', '.'], cwd=here, capture_output=True, text=True, timeout=5).stdout.strip()
        return (sha + (' with local changes' if dirty else '')) if sha else 'unknown'
    except Exception:
        return 'unknown'


CODE = _code()
VERSIONS = {name: version for name, _role, version in preview.CONNECTORS}
ROLES = {name: role for name, role, _version in preview.CONNECTORS}


def renderer_for(kind: str) -> str:
    """The connector that renders a world of this kind (as preview.render_and_read sends it)."""
    return 'isaac_body' if kind == 'body' else 'isaac_stage' if kind == 'stage' else 'isaac_counter'


def start(actor: str) -> dict:
    return {'started_at': round(time.time(), 1), 'started_by': actor, 'code': CODE}


def finish(info: dict, connectors: set[str], renderer_revisions: set[str] | None = None) -> dict:
    """The record a finished run saves: its start, its end, and the connectors and renderer revisions it used."""
    return {**info, 'finished_at': round(time.time(), 1),
            'connectors': [{'name': c, 'role': ROLES.get(c, ''), 'version': VERSIONS.get(c, 'unknown')} for c in sorted(connectors)],
            'renderer_revisions': sorted(renderer_revisions or ()), 'scene_worker': preview.REVISION}
