"""A project's history (#21): step_list(project_id=...) returns only the steps that wrote that project's rows, and a step
undone later says which step undid it."""
import unittest
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab.tools import register


class StepHistory(unittest.TestCase):
    def setUp(self):
        self.t = Tools(Store()); register(self.t, lambda m: None); s = self.t.store
        st = s.begin('person', 'project_create', {}); self.a = s.create(st, 'project', {'title': 'A', 'status': 'Draft'}).id
        st = s.begin('agent', 'project_create', {}); self.b = s.create(st, 'project', {'title': 'B', 'status': 'Draft'}).id
        st = s.begin('agent', 'sample_create', {}); s.create(st, 'sample', {'project_id': self.a, 'index': 0}); self.sample_step = st
        st = s.begin('agent', 'sample_create', {}); s.create(st, 'sample', {'project_id': self.b, 'index': 0})

    def test_only_this_projects_steps(self):
        a = self.t.call('step_list', 'person', project_id=self.a); b = self.t.call('step_list', 'person', project_id=self.b)
        self.assertEqual(len(a), 2); self.assertEqual(len(b), 2)
        self.assertFalse({x['step_id'] for x in a} & {x['step_id'] for x in b})

    def test_undone_step_is_marked(self):
        u = self.t.call('step_undo', 'person', step_id=self.sample_step)
        a = {x['step_id']: x for x in self.t.call('step_list', 'person', project_id=self.a)}
        self.assertEqual(a[self.sample_step]['undone_by'], u)


if __name__ == '__main__':
    unittest.main()
