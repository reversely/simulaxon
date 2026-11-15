"""Example cards show the brain's predicted response beside the stimulus: the set-up's first contrast map, at the view
with the most colour; an example with no project shows the newest adapter for its dataset."""
import tempfile, unittest
from pathlib import Path
import numpy as np
from PIL import Image
from app_server.store import Store
from app_server.lab import examples


def png(path: Path, rgb):
    path.parent.mkdir(parents=True, exist_ok=True); a = np.zeros((20, 20, 4), np.uint8); a[..., :3] = rgb; a[..., 3] = 255
    Image.fromarray(a).save(path)


class ExampleBrain(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old = examples.FILES; examples.FILES = Path(self.tmp.name); examples._SCORES.clear()
        png(examples.FILES / 'maps/a_left.png', (128, 128, 128)); png(examples.FILES / 'maps/a_ventral.png', (220, 40, 20))   # grey surface, a red response
        png(examples.FILES / 'maps/b_left.png', (30, 60, 220))
        s = self.s = Store(); st = s.begin('agent', 'experiment_create', {})
        self.p = s.create(st, 'project', {'title': 'x', 'experiment': {'contrasts': [{'name': 'Second'}, {'name': 'First'}][::-1]}}).id
        for name, key in (('Second', 'b'), ('First', 'a')):
            m = s.create(st, 'neural_map', {'project_id': self.p, 'views': {'left': f'maps/{key}_left.png', 'ventral': f'maps/{key}_ventral.png'}})
            an = s.create(st, 'analysis', {'project_id': self.p, 'title': name})
            s.create(st, 'result', {'project_id': self.p, 'analysis_id': an.id, 'map_id': m.id})

    def tearDown(self):
        examples.FILES = self.old; self.tmp.cleanup()

    def test_first_contrast_at_its_most_coloured_view(self):
        b = examples._brain(self.s, self.p)
        self.assertEqual((b['title'], b['view'], b['image']), ('First', 'ventral', '/files/maps/a_ventral.png'))

    def test_no_map_no_brain(self):
        self.assertIsNone(examples._brain(self.s, 'other')); self.assertIsNone(examples._adapter_brain(self.s, 'no_dataset'))


if __name__ == '__main__':
    unittest.main()
