"""Versioned store (implementation spec §2).

Every object is a row of (kind, id, version, data). Rows are never edited in place: an update writes
version n+1, compare-and-set on the version the caller last saw. Every write belongs to a step.
Undo restores, for each object the step touched, the version it had before the step, as a new
version, and marks everything that depends on those objects out of date.
"""
from __future__ import annotations
import functools, json, threading, time, uuid
from dataclasses import dataclass
import duckdb



class Missing(ValueError, KeyError):
    """A row, step, template or demo the caller named that isn't there: the caller's mistake, refused with 422 (#14)."""
    def __str__(self): return str(self.args[0]) if self.args else 'not found'

class Conflict(Exception):
    """The object changed since the caller read it."""


@dataclass
class Row:
    kind: str
    id: str
    version: int
    data: dict
    step_id: str
    deleted: bool = False


def _locked(fn):
    """One DuckDB connection serves the panels, the agent, previews, runs and demos; every call takes the store's lock."""
    @functools.wraps(fn)
    def run(self, *a, **k):
        with self._lock: return fn(self, *a, **k)
    return run


class Store:
    def __init__(self, path: str = ':memory:'):
        self._lock = threading.RLock()
        self.db = duckdb.connect(path)
        self.db.execute('''create table if not exists rows (kind varchar, id varchar, version integer, data json, step_id varchar,
                           deleted boolean, ts double, primary key (kind, id, version))''')
        self.db.execute('''create table if not exists steps (step_id varchar primary key, actor varchar, tool varchar, args json,
                           code varchar, ts double, undoes varchar)''')
        self.db.execute('''create table if not exists touched (step_id varchar, kind varchar, id varchar, before_version integer, after_version integer)''')
        self.db.execute('''create table if not exists deps (kind varchar, id varchar, on_kind varchar, on_id varchar)''')
        self.db.execute('''create table if not exists stale (kind varchar, id varchar, because_step varchar)''')

    # ---------- steps ----------
    @_locked
    def begin(self, actor: str, tool: str, args: dict, code: str = '', undoes: str | None = None) -> str:
        sid = 'step_' + uuid.uuid4().hex[:12]
        self.db.execute('insert into steps values (?, ?, ?, ?, ?, ?, ?)', [sid, actor, tool, json.dumps(args), code, time.time(), undoes])
        return sid

    # ---------- reads ----------
    @_locked
    def get(self, kind: str, id: str) -> Row | None:
        r = self.db.execute('select kind, id, version, data, step_id, deleted from rows where kind=? and id=? order by version desc limit 1', [kind, id]).fetchone()
        if not r or r[5]: return None
        return Row(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5])

    @_locked
    def version_of(self, kind: str, id: str, version: int) -> Row | None:
        r = self.db.execute('select kind, id, version, data, step_id, deleted from rows where kind=? and id=? and version=?', [kind, id, version]).fetchone()
        return Row(r[0], r[1], r[2], json.loads(r[3]), r[4], r[5]) if r else None

    @_locked
    def list(self, kind: str) -> list[Row]:
        q = '''select kind, id, version, data, step_id, deleted from rows r where kind=? and version = (select max(version) from rows where kind=r.kind and id=r.id)'''
        return [Row(a, b, c, json.loads(d), e, f) for a, b, c, d, e, f in self.db.execute(q, [kind]).fetchall() if not f]

    @_locked
    def is_stale(self, kind: str, id: str) -> bool:
        return bool(self.db.execute('select 1 from stale where kind=? and id=?', [kind, id]).fetchone())

    # ---------- writes ----------
    @_locked
    def _write(self, step_id: str, kind: str, id: str, data: dict, expect_version: int | None, deleted=False, mark_stale=True) -> Row:
        cur = self.db.execute('select max(version) from rows where kind=? and id=?', [kind, id]).fetchone()[0]
        if expect_version is not None and cur != expect_version:
            raise Conflict(f'{kind} {id} is at version {cur}, not {expect_version}')
        v = (cur or 0) + 1
        self.db.execute('insert into rows values (?, ?, ?, ?, ?, ?, ?)', [kind, id, v, json.dumps(data), step_id, deleted, time.time()])
        self.db.execute('insert into touched values (?, ?, ?, ?, ?)', [step_id, kind, id, cur or 0, v])
        self.db.execute('delete from stale where kind=? and id=?', [kind, id])
        if mark_stale: self._mark_dependents_stale(kind, id, step_id)
        return Row(kind, id, v, data, step_id, deleted)

    @_locked
    def create(self, step_id: str, kind: str, data: dict, id: str | None = None, depends_on: list[tuple[str, str]] = ()) -> Row:
        id = id or f'{kind}_' + uuid.uuid4().hex[:10]
        if self.get(kind, id): raise Conflict(f'{kind} {id} already exists')
        row = self._write(step_id, kind, id, data, None)
        for k, i in depends_on: self.db.execute('insert into deps values (?, ?, ?, ?)', [kind, id, k, i])
        return row

    @_locked
    def update(self, step_id: str, kind: str, id: str, changes: dict, expect_version: int, mark_stale: bool = True) -> Row:
        """mark_stale=False for metadata, such as a status or a title, that nothing computed from the row depends on."""
        cur = self.get(kind, id)
        if cur is None: raise Missing(f'no {kind} {id}')
        return self._write(step_id, kind, id, {**cur.data, **changes}, expect_version, mark_stale=mark_stale)

    @_locked
    def delete(self, step_id: str, kind: str, id: str, expect_version: int) -> Row:
        cur = self.get(kind, id)
        if cur is None: raise Missing(f'no {kind} {id}')
        return self._write(step_id, kind, id, cur.data, expect_version, deleted=True)

    @_locked
    def _mark_dependents_stale(self, kind: str, id: str, step_id: str) -> None:
        frontier, seen = [(kind, id)], set()
        while frontier:
            k, i = frontier.pop()
            for dk, di in self.db.execute('select kind, id from deps where on_kind=? and on_id=?', [k, i]).fetchall():
                if (dk, di) in seen: continue
                seen.add((dk, di)); frontier.append((dk, di))
                if not self.is_stale(dk, di): self.db.execute('insert into stale values (?, ?, ?)', [dk, di, step_id])

    # ---------- undo ----------
    @_locked
    def undo(self, step_id: str, actor: str) -> str:
        """Put every row the step wrote back as it was before the step, all or nothing.

        A step can write the same row more than once (create a project, then update it), so each row's writes collapse
        to its version before the step's first write and after its last. Every row is checked before any is written:
        if one changed after the step, nothing is undone."""
        touched = self.db.execute('select kind, id, min(before_version), max(after_version) from touched where step_id=? group by kind, id', [step_id]).fetchall()
        if not touched: raise Missing(f'step {step_id} changed nothing')
        for kind, id, before, after in touched:
            latest = self.db.execute('select max(version) from rows where kind=? and id=?', [kind, id]).fetchone()[0]
            if latest != after:
                raise Conflict(f'{kind} {id} changed after step {step_id}; undo the later steps first')
        u = self.begin(actor, 'step_undo', {'step_id': step_id}, undoes=step_id)
        try:
            for kind, id, before, after in touched:
                if before == 0:
                    cur = self.get(kind, id); self._write(u, kind, id, cur.data if cur else {}, after, deleted=True)
                else:
                    old = self.version_of(kind, id, before); self._write(u, kind, id, old.data, after, deleted=old.deleted)
        except Exception:
            self.discard(u); raise
        return u

    @_locked
    def discard(self, step_id: str) -> None:
        """Remove a step that failed partway, with every row version, dependency and stale mark it wrote, so a tool that
        raises leaves the store as it was. Only that step's own writes go; other steps are untouched."""
        made = self.db.execute('select kind, id from touched where step_id=? and before_version=0', [step_id]).fetchall()
        self.db.execute('delete from rows where step_id=?', [step_id])
        self.db.execute('delete from touched where step_id=?', [step_id])
        self.db.execute('delete from stale where because_step=?', [step_id])
        for kind, id in made:   # dependencies of rows the step created, which no longer exist
            if not self.db.execute('select 1 from rows where kind=? and id=?', [kind, id]).fetchone():
                self.db.execute('delete from deps where kind=? and id=?', [kind, id])
        self.db.execute('delete from steps where step_id=?', [step_id])

    @_locked
    def steps_for(self, project_id: str) -> list[dict]:
        """The steps that wrote this project's rows: the project itself, or any row whose project_id is this project (#21)."""
        cols = ['step_id', 'actor', 'tool', 'args', 'code', 'ts', 'undoes']
        q = '''select distinct s.step_id, s.actor, s.tool, s.args, s.code, s.ts, s.undoes from steps s join touched t on t.step_id = s.step_id
               join rows r on r.kind = t.kind and r.id = t.id and r.version = t.after_version
               where (t.kind = 'project' and t.id = ?) or json_extract_string(r.data, '$.project_id') = ? order by s.ts'''
        return [dict(zip(cols, r)) for r in self.db.execute(q, [project_id, project_id]).fetchall()]

    @_locked
    def steps(self) -> list[dict]:
        cols = ['step_id', 'actor', 'tool', 'args', 'code', 'ts', 'undoes']
        return [dict(zip(cols, r)) for r in self.db.execute('select * from steps order by ts').fetchall()]
