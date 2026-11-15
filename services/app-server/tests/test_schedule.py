"""A trial's schedule (#31): the spans its clip is composed of, recorded for every design, and given to runs from before
schedules were recorded from the project's trial set-up, without a rerun."""
import unittest
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab import experiment
from app_server.lab.tools import register


class Schedule(unittest.TestCase):
    def test_event_design_is_the_stimulus_then_rest(self):
        t = experiment._defaults({'design': 'event', 'item_s': 2, 'rest_s': 6})
        self.assertEqual(experiment.schedule(t), [{'start_s': 0.0, 'end_s': 2.0, 'kind': 'stimulus', 'label': 'Stimulus'},
                                                  {'start_s': 2.0, 'end_s': 8.0, 'kind': 'rest', 'label': 'Rest'}])

    def test_block_design_with_gaps_follows_the_clip(self):
        t = experiment._defaults({'item_s': 0.5, 'gap_s': 0.25, 'items_per_trial': 4, 'rest_s': 8})
        sp = experiment.schedule(t)
        self.assertEqual([x['kind'] for x in sp], ['stimulus', 'gap'] * 4 + ['rest'])
        self.assertEqual(sp[-1]['end_s'], t['clip_s']); self.assertEqual(sp[2]['label'], 'Item 2')
        self.assertTrue(all(a['end_s'] == b['start_s'] for a, b in zip(sp, sp[1:])))

    def test_old_runs_get_their_schedule_from_the_set_up(self):
        tools = Tools(Store()); register(tools, lambda m: None); s = tools.store; st = s.begin('person', 'project_run', {})
        trial = experiment._defaults({'item_s': 2, 'items_per_trial': 4, 'rest_s': 6})
        pid = s.create(st, 'project', {'title': 'Faces against objects', 'plan': 'experiment', 'status': 'Done', 'setup': {'trial': trial}}).id
        s.create(st, 'sample', {'project_id': pid, 'index': 0, 'readout': {}})
        rows = tools.call('sample_list', 'person', project_id=pid)
        self.assertEqual(rows[0].data['schedule'], experiment.schedule(trial))
        self.assertNotIn('schedule', s.get('sample', rows[0].id).data)   # read, not written


if __name__ == '__main__':
    unittest.main()
