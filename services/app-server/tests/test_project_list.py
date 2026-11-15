"""project_list (#32): last updated first, with created_at, updated_at, a picture and last_added on the newest; a step that
only rewrites a project's wording does not count as an update."""
import json, unittest
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab.tools import register


class ProjectList(unittest.TestCase):
    def setUp(self):
        self.t = Tools(Store()); register(self.t, lambda m: None); s = self.t.store
        st = s.begin('person', 'project_create', {}); self.old = s.create(st, 'project', {'title': 'Old', 'status': 'Done'})
        st = s.begin('person', 'project_create', {}); self.new = s.create(st, 'project', {'title': 'New', 'status': 'Done', 'hero': '/files/h.png'})
        st = s.begin('agent', 'sample_create', {}); s.create(st, 'sample', {'project_id': self.old.id, 'index': 1, 'image': '/files/b.png'})
        s.create(st, 'sample', {'project_id': self.old.id, 'index': 0, 'image': '/files/a.png'})   # the old project's run: its last update

    def list(self): return {r.data['title']: r for r in self.t.call('project_list', 'person')}

    def test_last_updated_first_and_newest_is_last_added(self):
        rows = self.t.call('project_list', 'person')
        self.assertEqual([r.data['title'] for r in rows], ['Old', 'New'])   # Old's samples were written after New was made
        p = self.list(); self.assertTrue(p['New'].data['last_added']); self.assertFalse(p['Old'].data['last_added'])
        self.assertLess(p['Old'].data['created_at'], p['New'].data['created_at'])

    def test_picture_is_hero_else_first_sample(self):
        p = self.list(); self.assertEqual(p['New'].data['picture'], '/files/h.png'); self.assertEqual(p['Old'].data['picture'], '/files/a.png')

    def test_a_wording_rewrite_is_not_an_update(self):
        s = self.t.store; before = self.list()['New'].data['updated_at']
        st = s.begin('agent', 'project_update', {'project_id': self.new.id, 'expect_version': 1, 'question': 'Does it?'})
        s.update(st, 'project', self.new.id, {**self.new.data, 'question': 'Does it?'}, expect_version=1)
        self.assertEqual(self.list()['New'].data['updated_at'], before)
        st = s.begin('person', 'project_update', {'project_id': self.new.id, 'expect_version': 2, 'status': 'Running'})
        s.update(st, 'project', self.new.id, {**self.new.data, 'status': 'Running'}, expect_version=2)
        self.assertGreater(self.list()['New'].data['updated_at'], before)


if __name__ == '__main__':
    unittest.main()
