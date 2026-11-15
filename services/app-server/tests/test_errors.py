"""A caller's mistake is a refusal that says what to do; a fault inside a tool is a 500 naming the tool (#14)."""
import unittest
from fastapi.testclient import TestClient
from app_server.server import create_app
from app_server.store import Store


class Errors(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Store()); self.c = TestClient(self.app); self.tools = self.app.state.tools

        @self.tools.tool('demo', 'get', writes_project=False)
        def demo_get(actor, demo_id):
            return {}['missing_key']   # a fault in the tool's own code
        self.st = self.tools.store.begin('person', 'seed', {})
        self.sel = self.tools.store.create(self.st, 'project', {'title': 'Selection', 'plan': 'selection', 'status': 'Done'})

    def post(self, name, **body):
        return self.c.post(f'/tools/{name}', json=body)

    def test_a_missing_project_is_refused_by_name(self):
        r = self.post('project_get', project_id='no_such_project')
        self.assertEqual(r.status_code, 422); self.assertIn('no project no_such_project', r.text)

    def test_a_read_passes_an_argument_it_does_not_take(self):   # the answer is the same without it (#34)
        self.assertEqual(self.post('project_get', project_id=self.sel.id, bogus=1).status_code, 200)

    def test_a_write_refuses_an_argument_it_does_not_take_plainly(self):
        r = self.post('project_create', question='Does it?', bogus=1)
        self.assertEqual(r.status_code, 422); self.assertIn('takes no argument bogus', r.text); self.assertNotIn('<locals>', r.text)

    def test_a_fault_inside_a_tool_is_a_500_naming_it(self):
        r = self.post('demo_get', demo_id='x')
        self.assertEqual(r.status_code, 500); self.assertIn('internal error in demo_get: KeyError', r.text); self.assertNotIn('Traceback', r.text)
