"""Recordings (#23): a sample exports as a recording (video, TRIBE v2, audio, regions by second); a dataset holding one
indexes it as one item that names its streams, not as loose files."""
import io, json, subprocess, tempfile, unittest, zipfile
from pathlib import Path
import numpy as np
from app_server.lab import datasets as dsets, curation, recording


class Recording(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); d = Path(self.tmp.name)
        self.clip = d / 'clip.mp4'   # 2 s of colour with a tone, so the audio stream is exported too
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=64x64:d=2:r=10', '-f', 'lavfi', '-i', 'sine=f=440:d=2',
                        '-shortest', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(self.clip)], check=True)
        self.preds = d / 'p.npy'; np.save(self.preds, np.random.default_rng(0).standard_normal((3, 20484)).astype(np.float16))
        mask = np.zeros(20484, bool); mask[:100] = True
        self.zip = recording.export({'preds': str(self.preds), 'project_id': 'p1', 'label': 'trial 1', 'condition': 'a', 'index': 0}, self.clip, 'A trial', ['MT', 'nope'],
                                    lambda r: mask if r == 'MT' else (_ for _ in ()).throw(ValueError(r)))

    def tearDown(self): self.tmp.cleanup()

    def test_export_holds_every_stream(self):
        z = zipfile.ZipFile(io.BytesIO(self.zip)); m = json.loads(z.read('recording.json'))
        self.assertEqual(m['format'], 'simulaxon.recording'); self.assertEqual([s['kind'] for s in m['streams']], ['video', 'tribe', 'audio', 'table'])
        self.assertEqual(np.load(io.BytesIO(z.read('tribe.npy'))).shape, (3, 20484))
        rows = z.read('regions.csv').decode().splitlines(); self.assertEqual(rows[0], 't,MT'); self.assertEqual(len(rows), 4)   # an unknown region is left out
        p = np.load(self.preds); self.assertAlmostEqual(float(rows[1].split(',')[1]), float(p[0][:100].mean()), places=4)
        self.assertGreaterEqual(m['duration_s'], 3)

    def test_dataset_indexes_a_recording_as_one_item(self):
        old = dsets.HERE; dsets.HERE = Path(self.tmp.name) / 'fetched'
        try:
            root = dsets.HERE / 'recs'; (root / 'run1').mkdir(parents=True)
            zipfile.ZipFile(io.BytesIO(self.zip)).extractall(root / 'run1' / 'trial_1')
            (root / 'loose.mp4').write_bytes(self.clip.read_bytes())
            items = {x['path']: x for x in curation.index('recs')}
            self.assertEqual(sorted(items), ['loose.mp4', 'run1/trial_1'])   # the recording's own files are not items
            r = items['run1/trial_1']; self.assertEqual(r['media_type'], 'recording'); self.assertEqual(r['video'], 'run1/trial_1/video.mp4')
            self.assertEqual((r['fields']['streams'], r['fields']['has_tribe'], r['fields']['category']), ('video, tribe, audio, regions', True, 'run1'))
            pub = curation.public({**r, 'tags': []}); self.assertTrue(pub['media'].endswith('/recording.json')); self.assertIn('video.mp4', pub['thumb'])
            (root / 'run1' / 'trial_1' / 'tribe.npy').unlink()   # a manifest naming a missing file is skipped, not indexed
            self.assertEqual(sorted(x['path'] for x in curation.index('recs')), ['loose.mp4'])
        finally: dsets.HERE = old
