"""Adapters (#28): fitted from TRIBE v2's area means to measured responses, scored only on held-out categories, beside
TRIBE v2 as released and shuffled labels. A synthetic dataset where the measured response is a known linear map of TRIBE's."""
import tempfile, unittest
from pathlib import Path
import numpy as np
from app_server.lab import adapter


class Adapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); rng = np.random.default_rng(1); C, A = 60, 360
        self.T = rng.standard_normal((C, A)); W = rng.standard_normal((A, A)) * 0.05 + np.eye(A) * 0.3
        Y = self.T @ W + 0.5 * rng.standard_normal((C, A)); areas = [f'L_A{i}' for i in range(180)] + [f'R_A{i}' for i in range(180)]
        src = {'title': 'Toy, 5 people', 'categories': [f'c{i}' for i in range(C)], 'areas': areas, 'measured': Y, 'ceiling': np.full(A, 0.9), 'people': 5}
        self.old = dict(adapter.SOURCES); adapter.SOURCES['toy'] = lambda: src
        cache = Path(self.tmp.name); np.savez(cache / 'toy_tribe_areas.npz', T=self.T, n=np.full(C, 20))   # features as features() caches them
        self.cache = cache

    def tearDown(self):
        adapter.SOURCES.clear(); adapter.SOURCES.update(self.old); self.tmp.cleanup()

    def test_cross_validated_fit_beats_released_and_shuffled_is_near_zero(self):
        r = adapter.fit('toy', self.cache); s = r['summary']
        self.assertEqual(r['split']['kind'], '10-fold over categories'); self.assertEqual(len(r['areas']), 360)
        self.assertGreater(s['adapter']['median'], s['tribe_v2']['median']); self.assertLess(abs(s['shuffled']['median']), 0.1)
        self.assertEqual(r['weights']['coef'].shape, (360, 360))

    def test_scores_are_labelled_a_benchmark_on_the_fitted_dataset(self):
        r = adapter.fit('toy', self.cache)
        self.assertEqual(adapter.benchmark(r), 'Benchmark: held-out categories of the Toy')
        self.assertEqual(adapter.benchmark({'source': 'Human Action Dataset, 30 people (Zhou et al., 2023)', 'split': {'kind': '10-fold over categories'}}),
                         'Benchmark: held-out categories of the Human Action Dataset')

    def test_held_out_categories_are_never_trained_on(self):
        held = [f'c{i}' for i in range(0, 60, 4)]
        r = adapter.fit('toy', self.cache, held_out=held); self.assertEqual((r['split']['held_out'], r['split']['training']), (15, 45))
        with self.assertRaises(ValueError): adapter.fit('toy', self.cache, held_out=['nope'])

    def test_applied_in_an_experiment_matches_the_fit_and_flags_far_stimuli(self):
        """An experiment reading through the adapter (#28 item 3) gets the fit's prediction per area, spread over the area's
        vertices, and a stimulus far beyond the training inputs is counted outside the fit (#37)."""
        from unittest import mock
        from app_server.lab import regions
        r = adapter.fit('toy', self.cache); w = r.pop('weights'); names = tuple(a['area'] for a in r['areas'])
        files = Path(self.tmp.name) / 'files'; (files / 'adapters').mkdir(parents=True)
        np.savez(files / 'adapters' / 'a1.npz', **w); np.savez(files / 'adapters' / 'toy_tribe_areas.npz', T=self.T, n=np.full(60, 20))
        masks = [np.isin(np.arange(720), [2 * k, 2 * k + 1]) for k in range(360)]   # two vertices an area
        with mock.patch.object(regions, 'hcp_names', lambda: names), mock.patch.object(regions, 'hcp_areas', lambda: masks):
            A = adapter.Applied('adapter_x', {'name': 'adapter 1', 'weights': 'adapters/a1.npz', 'dataset_id': 'toy', 'areas': r['areas']}, files)
            near, far = np.repeat(self.T[3], 2), np.repeat(self.T[3] * 25, 2)
            out = A(near); want = ((self.T[3] - w['mu']) / w['sd']) @ w['coef'].T + w['intercept']
            np.testing.assert_allclose(out[::2], want, rtol=1e-5); np.testing.assert_allclose(out[1::2], want, rtol=1e-5)
            A(far); m = A.model()
        self.assertEqual(m['name'], 'TRIBE v2 with adapter 1'); self.assertEqual(m['outside_fit'], 1); self.assertIn('1 of 2 stimuli lie outside', m['note'])


class LabBaselines(unittest.TestCase):
    """The lab's readouts on other features join the benchmark only where they were scored on the same areas (#37)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name) / 'feasibility' / 'data' / 'had'; d.mkdir(parents=True)
        rows = ['parcel,ceiling,somatomotor,SigLIP | as predicted,SigLIP | both controls'] + [f'A{i},0.7,False,{i / 10},0' for i in range(5)]
        (d / 'baseline_per_parcel.csv').write_text('\n'.join(rows)); (d / 'baseline_scores.json').write_text('{"n_categories": 180, "of": 3}')
        from unittest import mock
        self.p = mock.patch.object(adapter, 'HOME', Path(self.tmp.name)); self.p.start()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def row(self, areas):
        return {'dataset_id': 'openneuro_ds004488', 'categories': 180, 'areas': [{'area': a, 'reliable': r} for a, r in areas]}

    def test_median_over_the_adapters_own_reliable_areas(self):
        b = adapter.lab_baselines(self.row([('A1', True), ('A2', True), ('A3', True), ('A4', False)]))
        self.assertEqual(b['areas'], 3); self.assertEqual(b['rows'][0]['name'], 'SigLIP image features, fitted')
        self.assertAlmostEqual(b['rows'][0]['median'], 0.2); self.assertIn('No V-JEPA 2', b['note'])

    def test_no_rows_when_the_scoring_differs(self):
        self.assertIsNone(adapter.lab_baselines(self.row([('A1', True), ('B9', True)])))   # an area the lab never scored
        self.assertIsNone(adapter.lab_baselines({**self.row([('A1', True)]), 'categories': 120}))
        self.assertIsNone(adapter.lab_baselines({**self.row([('A1', True)]), 'dataset_id': 'toy'}))


class LiveResults(unittest.TestCase):
    def test_pairs_each_adapter_run_with_the_same_experiment_as_released(self):
        from types import SimpleNamespace as N
        e = {'regions': ['FFC'], 'trial': {'seed': 1}, 'conditions': [{'name': 'Faces', 'files': ['f/*.jpg']}, {'name': 'Objects', 'files': ['o/*.jpg']}]}
        rel = N(id='p1', data={'plan': 'experiment', 'status': 'Done', 'title': 'As released', 'experiment': {**e, 'conditions': [{**c, 'name': c['name'].lower()} for c in e['conditions']]}})
        ada = N(id='p2', data={'plan': 'experiment', 'status': 'Done', 'title': 'Through it', 'experiment': {**e, 'brain_model': 'ad1'}})
        other = N(id='p3', data={'plan': 'experiment', 'status': 'Done', 'experiment': {**e, 'regions': ['PPA']}})
        res = {'p1': 'match', 'p2': 'no match: interval includes zero'}
        get = lambda pid: {'results': [{'reported': [{'contrast': 'c', 'region': 'FFC', 'result': res[pid], 'area_rank_pct': 90.0}]}]}
        out = adapter.live_results(get, [rel, ada, other], 'ad1')
        self.assertEqual(len(out), 1); self.assertEqual(out[0]['released']['project_id'], 'p1')
        self.assertEqual((out[0]['released']['result'], out[0]['adapter']['result']), ('match', 'no match: interval includes zero'))
