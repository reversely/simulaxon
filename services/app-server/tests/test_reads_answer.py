"""Read tools answer for every project instead of refusing it for its kind or state: experiment_get on a matched project,
run_get before a run has finished, course_get with no predictions; an unknown project gets a clear Missing."""
import unittest
from app_server.store import Missing, Store
from app_server.tools import Tools
from app_server.lab.tools import register


class ReadsAnswer(unittest.TestCase):
    def setUp(self):
        self.t = Tools(Store()); register(self.t, lambda m: None); s = self.t.store
        st = s.begin('person', 'project_create', {})
        self.matched = s.create(st, 'project', {'title': 'Faces versus vases', 'plan': 'matched', 'status': 'Done'}).id
        self.draft = s.create(st, 'project', {'title': 'Draft one', 'plan': 'experiment', 'status': 'Draft'}).id

    def test_experiment_get_answers_for_a_matched_project(self):
        r = self.t.call('experiment_get', 'agent', project_id=self.matched)
        self.assertEqual((r['plan'], r['status'], r['results']), ('matched', 'Done', []))

    def test_run_get_before_a_run_finishes(self):
        r = self.t.call('run_get', 'agent', project_id=self.draft)
        self.assertFalse(r['finished']); self.assertIn('Draft', r['note'])

    def test_course_get_without_predictions(self):
        r = self.t.call('course_get', 'agent', project_id=self.draft, region='V1')
        self.assertEqual(r['conditions'], [])

    def test_a_read_ignores_arguments_it_does_not_take(self):
        r = self.t.call('experiment_get', 'agent', project_id=self.matched, include_trials=True)
        self.assertEqual(r['plan'], 'matched')

    def test_a_write_still_refuses_an_argument_it_does_not_take(self):
        with self.assertRaises(ValueError): self.t.call('project_update', 'agent', project_id=self.draft, colour='red')

    def test_unknown_project_is_missing_not_a_crash(self):
        with self.assertRaises(Missing): self.t.call('experiment_get', 'agent', project_id='nope')


if __name__ == '__main__':
    unittest.main()
