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
