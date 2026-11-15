"""Dataset curation (#22): files become items with fields read off each file, its folder and a CSV beside it; views
filter, sort and take; tags and saved views are steps; a saved view can be an experiment condition."""
import tempfile, time, unittest
from pathlib import Path
from PIL import Image
from app_server.store import Store
from app_server.tools import Tools
from app_server.lab import datasets as dsets, curation
from app_server.lab.tools import register


class Curation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.old = dsets.HERE; dsets.HERE = Path(self.tmp.name)
        root = dsets.HERE / 'toy'
        for cat, grey in (('house', 200), ('face', 60)):
            (root / cat).mkdir(parents=True)
            for i in range(3): Image.new('L', (32, 24), grey + i).save(root / cat / f'{cat}{i}.png')
        Image.new('L', (32, 24), 60).save(root / 'face' / 'face_copy.png')   # same bytes as face0
        (root / 'ratings.csv').write_text('file,rating\nhouse0.png,4\nface1.png,2\n')
        (root / '_dataset.json').write_text('{"id": "toy", "ref": "upload", "title": "Toy", "files": []}')
        self.t = Tools(Store()); register(self.t, lambda m: None)

    def tearDown(self):
        dsets.HERE = self.old; self.tmp.cleanup()

    def index(self):
        self.t.call('item_create', 'person', dataset_id='toy')
        for _ in range(100):
            if len(self.t.store.list('item')) == 7: return
            time.sleep(0.05)
        self.fail('indexing did not finish')

    def test_fields_from_file_folder_and_csv(self):
        self.index()
        q = self.t.call('item_query', 'person', dataset_id='toy', limit=100)
        by = {x['path']: x['fields'] for x in q['items']}
        self.assertEqual(q['total'], 7); self.assertEqual(by['house/house0.png']['category'], 'house')
        self.assertEqual(by['house/house0.png']['rating'], 4); self.assertEqual(by['face/face0.png']['duplicates'], 1)
        self.assertAlmostEqual(by['face/face0.png']['luminance'], 60, delta=1)

    def test_stages_tags_and_views(self):
        self.index()
        q = self.t.call('item_query', 'person', dataset_id='toy', stages=[{'stage': 'match', 'path': 'category', 'op': '==', 'value': 'house'},
                                                                          {'stage': 'sort_by', 'path': 'luminance', 'reverse': True}])
        self.assertEqual([x['path'] for x in q['items']], ['house/house2.png', 'house/house1.png', 'house/house0.png'])
        self.assertEqual([t['count'] for t in q['trail']], [7, 3, 3])
        ids = [x['id'] for x in q['items'][:2]]
        self.t.call('item_update', 'person', item_ids=ids, add_tags=['keep'])
        self.assertEqual(self.t.call('item_query', 'person', dataset_id='toy', stages=[{'stage': 'tagged', 'tag': 'keep'}])['total'], 2)
        v = self.t.call('view_create', 'person', dataset_id='toy', title='Houses', stages=[{'stage': 'match', 'path': 'category', 'op': '==', 'value': 'house'}])
        self.assertEqual(v['items'], 3)
        self.assertEqual(self.t.call('item_query', 'person', dataset_id='toy', view_id=v['view_id'])['total'], 3)
        self.assertEqual(self.t.call('dataset_list', 'person')[0]['samples'], 7)

    def test_similar_to_sorts_by_vector(self):
        import numpy as np
        items = [{'id': i, 'fields': {}} for i in ('a', 'b', 'c', 'd')]
        v = np.array([[1, 0], [0.6, 0.8], [0.99, 0.141], [0, 1]], np.float32)
        out, trail = curation.apply(items, [{'stage': 'similar_to', 'id': 'a', 'label': 'a.png'}], (['a', 'b', 'c', 'd'], v))
        self.assertEqual([x['id'] for x in out], ['a', 'c', 'b', 'd']); self.assertEqual(trail[-1]['text'], 'most like a.png')
        with self.assertRaises(ValueError): curation.apply(items, [{'stage': 'similar_to', 'id': 'a'}], None)


if __name__ == '__main__':
    unittest.main()
