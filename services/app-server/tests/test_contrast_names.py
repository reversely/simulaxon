"""Conditions and contrasts are named in words (#39): experiment_create refuses a snake-case name before it plans anything."""
import unittest
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab.tools import register


class ContrastNames(unittest.TestCase):
    def setUp(self):
        self.t = Tools(Store()); register(self.t, lambda m: None)

    def create(self, conditions, contrasts):
        return self.t.call('experiment_create', 'agent', title='Faces', question='Do faces move FFA?', conditions=conditions,
                           regions=['FFA'], contrasts=contrasts)

    def test_snake_case_contrast_is_refused(self):
        conds = [{'name': 'Faces', 'files': ['none/*.png']}, {'name': 'Objects', 'files': ['none/*.png']}]
        with self.assertRaisesRegex(ValueError, 'faces_vs_objects'):
            self.create(conds, [{'name': 'faces_vs_objects', 'weights': {'Faces': 1, 'Objects': -1}}])

    def test_snake_case_condition_is_refused(self):
        conds = [{'name': 'whole_body_sports', 'files': ['none/*.png']}, {'name': 'Hands', 'files': ['none/*.png']}]
        with self.assertRaisesRegex(ValueError, 'whole_body_sports'):
            self.create(conds, None)


if __name__ == '__main__':
    unittest.main()
