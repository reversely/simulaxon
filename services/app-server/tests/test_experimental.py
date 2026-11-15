"""The Experimental section (#25): a grasp of the study plays as a recording; files outside the run are refused; results
are read from the run's files and statements computed from them."""
import json, tempfile, unittest
from pathlib import Path
import numpy as np
from app_server.lab import experimental as X


class Experimental(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old = X.RUN; X.RUN = Path(self.tmp.name)
        for c, held in (('c0', True), ('c1', False)):
            d = X.RUN / 'standard_t000' / c; d.mkdir(parents=True)
            (d / 'outcome.json').write_text(json.dumps({'held': {'gentle': held, 'firm': False}, 'lifted': held, 'grip_nm': 0.2, 'object': {'shape': 'box', 'mass_kg': 0.1}}))
            (d / 'clip_third.mp4').write_bytes(b'x'); np.save(d / 'tribe_third.npy', np.zeros((6, 20484), np.float16))
            t = np.arange(0, 15, 1 / 60); np.savez(d / 'tracks.npz', t=t, q=np.zeros((len(t), 6)))
        rows = {'P+V': 0.2, 'P+V+T paired': 0.25}; split = {'trials': 60, 'random_candidate': 0.36, 'oracle': 0.63, 'held_when_choosing': rows, 'auc': {k: 0.74 for k in rows},
                                                            'differences': {'P+V+T paired minus P+V': {'held': 0.05, 'ci95': [-0.02, 0.13]}}}
        (X.RUN / 'results.json').write_text(json.dumps({'by_shake': {'gentle': {'splits': {'standard': split}}, 'firm': {'splits': {'standard': split}}}, 'gates': {'2 positive control detected': 'FAIL'}}))
        (X.RUN / 'check.json').write_text(json.dumps({'candidates_run': 8, 'lifted': 4, 'held_gentle': 3, 'held_firm': 2, 'repeat': [{'labels_identical': True}], 'gates': {'1 label rate': 'pass'}}))

    def tearDown(self): X.RUN = self.old; self.tmp.cleanup()

    def test_study_reads_the_run_and_computes_statements(self):
        s = X.study(); g = s['shakes']['gentle']
        self.assertTrue(g['all_below_random']); self.assertEqual(g['differences'][0]['label'], 'TRIBE v2, paired minus Joints and cameras')
        self.assertEqual([x['candidate'] for x in s['examples']], ['c0', 'c1']); self.assertEqual(len(s['gates']), 2)

    def test_a_grasp_is_a_recording(self):
        m = X.manifest('standard_t000', 'c0'); self.assertEqual([x['kind'] for x in m['streams']], ['video', 'tribe', 'table', 'events'])
        csv, _ = X.file('standard_t000', 'c0', 'joints.csv'); lines = csv.decode().splitlines()
        self.assertEqual(lines[0].split(',')[0], 't'); self.assertLessEqual(float(lines[-1].split(',')[0]), 6.0)   # the streams' 6 s, at 10 Hz
        with self.assertRaises(ValueError): X.file('../..', 'c0', 'recording.json')
        with self.assertRaises(ValueError): X.file('standard_t000', 'c0', 'outcome.json')
