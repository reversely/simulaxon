"""run_get, the record behind the results dashboard (#19): it promotes no region a project did not choose, marks the ones
it did, and refuses a project that has not finished a run."""
import unittest
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab.tools import register


def _project(t, regions, bindings=None):
    s = t.store; st = s.begin('agent', 'project_create', {})
    p = s.create(st, 'project', {'title': 'x', 'question': 'q', 'plan': 'experiment', 'status': 'Done', 'bindings': bindings or {},
                                 'experiment': {'conditions': [{'name': 'A'}, {'name': 'B'}], 'regions': regions, 'trial': {'design': 'event', 'item_s': 3}},
                                 'run_info': {'started_at': 100.0, 'finished_at': 400.0, 'started_by': 'person', 'code': 'abc', 'connectors': []}})
    for i, c in enumerate(('A', 'B', 'A', 'B')):
        s.create(st, 'sample', {'project_id': p.id, 'index': i, 'unit': f'u{i // 2}', 'condition': c, 'label': c, 'readout': {'PPA': 0.1 * i, 'MT': -0.1 * i}})
    an = s.create(st, 'analysis', {'project_id': p.id, 'kind': 'paired', 'title': 'A against B', 'window_s': [0, 3]})
    s.create(st, 'result', {'analysis_id': an.id, 'project_id': p.id, 'regions': [
        {'region': 'PPA', 'value': 0.2, 'interval_95': [0.1, 0.3], 'n': {'A': 2, 'B': 2}}, {'region': 'MT', 'value': -0.1, 'interval_95': [-0.2, 0.0], 'n': {'A': 2, 'B': 2}}]})
    return p.id


class RunRecord(unittest.TestCase):
    def setUp(self):
        self.t = Tools(Store()); register(self.t, lambda m: None)

    def test_chosen_regions_marked(self):
        r = self.t.call('run_get', 'person', project_id=_project(self.t, ['PPA']))
        self.assertEqual([x['region'] for x in r['regions_named']], ['PPA'])
        self.assertEqual({c['region']: bool(c['named_by']) for c in r['contrasts']}, {'PPA': True, 'MT': False})
        self.assertEqual(r['made']['minutes'], 5.0); self.assertEqual(len(r['trials']), 4); self.assertEqual(r['contrasts'][0]['n'], 4)

    def test_no_region_promoted(self):
        r = self.t.call('run_get', 'person', project_id=_project(self.t, []))
        self.assertEqual(r['regions_named'], []); self.assertFalse(any(c['named_by'] for c in r['contrasts']))

    def test_named_area_in_the_question_counts(self):
        r = self.t.call('run_get', 'person', project_id=_project(self.t, [], {'region': 'the parahippocampal place area'}))
        self.assertEqual([x['region'] for x in r['regions_named']], ['PPA'])

    def test_unfinished_refused(self):
        s = self.t.store; st = s.begin('agent', 'project_create', {}); p = s.create(st, 'project', {'title': 'x', 'status': 'Draft'})
        with self.assertRaises(ValueError): self.t.call('run_get', 'person', project_id=p.id)


if __name__ == '__main__':
    unittest.main()
