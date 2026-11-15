"""The store's undo and failed-step handling, and template_list with a bare project.

Run from services/app-server: python -m unittest discover tests
"""
import unittest
from app_server.store import Conflict, Store
from app_server.tools import Tools


class Undo(unittest.TestCase):
    def setUp(self):
        self.s = Store()

    def test_step_that_writes_a_row_twice_can_be_undone(self):
        st = self.s.begin('person', 'make', {})
        p = self.s.create(st, 'project', {'title': 'a'})
        self.s.update(st, 'project', p.id, {'status': 'Draft'}, expect_version=1)
        self.s.undo(st, 'person')
        self.assertIsNone(self.s.get('project', p.id))

    def test_conflict_reverts_nothing(self):
        st = self.s.begin('person', 'make', {})
        a = self.s.create(st, 'scene', {'n': 1}); b = self.s.create(st, 'object', {'n': 2})
        later = self.s.begin('person', 'move', {})
        self.s.update(later, 'object', b.id, {'n': 3}, expect_version=1)
        steps_before = len(self.s.steps())
        with self.assertRaises(Conflict):
            self.s.undo(st, 'person')
        self.assertEqual(self.s.get('scene', a.id).data, {'n': 1})   # not half-undone
        self.assertEqual(len(self.s.steps()), steps_before)           # no undo step left behind


    def test_changes_undo_one_by_one_newest_first(self):
        st = self.s.begin('person', 'make', {}); a = self.s.create(st, 'parameter', {'value': 'vase'})
        first = self.s.begin('person', 'set', {}); self.s.update(first, 'parameter', a.id, {'value': 'bust'}, expect_version=1)
        second = self.s.begin('person', 'set', {}); self.s.update(second, 'parameter', a.id, {'value': 'other vase'}, expect_version=2)
        self.s.undo(second, 'person'); self.assertEqual(self.s.get('parameter', a.id).data, {'value': 'bust'})
        self.s.undo(first, 'person'); self.assertEqual(self.s.get('parameter', a.id).data, {'value': 'vase'})

    def test_a_later_change_still_blocks_an_undo(self):
        st = self.s.begin('person', 'make', {}); a = self.s.create(st, 'parameter', {'value': 'vase'})
        first = self.s.begin('person', 'set', {}); self.s.update(first, 'parameter', a.id, {'value': 'bust'}, expect_version=1)
        second = self.s.begin('person', 'set', {}); self.s.update(second, 'parameter', a.id, {'value': 'other vase'}, expect_version=2)
        with self.assertRaises(Conflict):
            self.s.undo(first, 'person')
        self.assertEqual(self.s.get('parameter', a.id).data, {'value': 'other vase'})

class FailedStep(unittest.TestCase):
    def test_tool_that_raises_leaves_nothing(self):
        t = Tools(Store())
        p = t.call('project_create', 'person', question='q')
        script = 'a = number(1, role="fixed")\nb = number(2, role="fixed")\n'
        t.call('parameter_create', 'person', project_id=p.id, script=script)
        steps_before = len(t.store.steps())
        with self.assertRaises(Conflict):   # a and b exist already, c is new: the call fails on a, after nothing new
            t.call('parameter_create', 'person', project_id=p.id, script='c = number(3, role="fixed")\na = number(1, role="fixed")\n')
        self.assertIsNone(t.store.get('parameter', f'{p.id}.c'))      # c, written before the conflict, is gone
        self.assertEqual(len(t.store.steps()), steps_before)          # and so is the failed step


class TemplateList(unittest.TestCase):
    def test_bare_project_does_not_break_the_list(self):
        from app_server.lab.tools import register
        t = Tools(Store()); register(t, lambda m: None)
        t.call('project_create', 'person', question='only a question')
        self.assertTrue(t.call('template_list', 'person'))


if __name__ == '__main__':
    unittest.main()
