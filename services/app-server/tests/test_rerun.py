"""A run replaces its project's earlier results in one step, and undoing that step brings them back (#12)."""
import unittest
from app_server.store import Store


class Rerun(unittest.TestCase):
    def test_replace_then_undo(self):
        s = Store(); st = s.begin('agent', 'project_run', {})
        p = s.create(st, 'project', {'title': 'x'}); old = s.create(st, 'analysis', {'project_id': p.id, 'n': 1})
        st2 = s.begin('agent', 'project_run', {})
        for row in s.list('analysis'):
            if row.data.get('project_id') == p.id: s.delete(st2, 'analysis', row.id, row.version)
        new = s.create(st2, 'analysis', {'project_id': p.id, 'n': 2})
        self.assertEqual([r.data['n'] for r in s.list('analysis') if r.data.get('project_id') == p.id], [2])
        s.undo(st2, 'person')
        self.assertEqual([r.data['n'] for r in s.list('analysis') if r.data.get('project_id') == p.id], [1])
