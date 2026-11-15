"""Stimuli for two seeded examples, written as a dataset the lab's experiments can use.

1. Binocular rivalry, face and house (Tong, Nakayama, Vaughan and Kanwisher 1998). TRIBE takes one video stream, so it
   cannot be shown a different image in each eye. From fLoc's face and house photos, 6 of each:
   - replay: the face and the house take turns on screen, 3 s each, face first (the physical alternation that rivalry
     studies use as their comparison; 3 s is an assumed dominance duration, not taken from the paper);
   - both: the same face and house blended half and half for all 24 s, the nearest one stream gets to two eyes;
   - face, house: each alone for 24 s, the full category difference;
   - turns of 1.5, 6 and 12 s: the same alternation at other speeds, to find where the model starts to follow.
2. A flash every few seconds (simple stimuli used with simultaneous recordings and fMRI): a full-field white flash of
   0.5 s every 4 s on mid-grey, starting at second 2, against mid-grey alone.

The data root is the app server's (SIMULAXON_HOME or SIMULAXON_DATA, app_server/home.py). fLoc's adult, house, car and
instrument photos (576 files, about 70 MB) are fetched from github:VPNL/fLoc the first time, through the app server's
own dataset code, so they land where the lab's experiments find them.

usage, from the repo root with the app server's Python:
  PYTHONPATH=services/app-server python studies/examples/stimuli.py
Writes backend/data/fetched/generated_examples/ under the data root, with its _dataset.json (repository "generated").
"""
import json, subprocess, sys, tempfile, time
from pathlib import Path
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services' / 'app-server'))
from app_server.lab import datasets   # noqa: E402  (reads the data root at import)

CATEGORIES = ('adult', 'house', 'car', 'instrument')   # faces and houses for rivalry; cars and instruments are the objects in media.py
OUT = datasets.HERE / 'generated_examples'
SIZE, FPS, N = 512, 30, 6


def floc() -> Path:
    """fLoc's photos on the volume, fetched from GitHub the first time."""
    root = datasets.HERE / 'github_vpnl_floc' / 'stimuli'
    if all(any((root / c).glob('*.jpg')) for c in CATEGORIES): return root
    did = datasets.listing('github:VPNL/fLoc')['id']; root = datasets.HERE / did / 'stimuli'
    print('fetching fLoc:', ', '.join(CATEGORIES), flush=True)
    datasets.fetch('github:VPNL/fLoc', [f'stimuli/{c}/*' for c in CATEGORIES], max_gb=1)
    while (st := datasets.status(did)) and st['status'] == 'fetching': time.sleep(2)
    if not st or st['status'] != 'done': raise RuntimeError(f"fLoc was not fetched: {st and st['error']}")
    return root


def video(segments: list[tuple[Image.Image, float]], out: Path):
    """A video made of still images, each held for its seconds, at 30 fps: one ffmpeg call, no frame-by-frame writing."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        lines = []
        for i, (im, s) in enumerate(segments):
            im.convert('RGB').save(f'{d}/{i}.png'); lines.append(f"file '{d}/{i}.png'\nduration {s}\n")
        lines.append(f"file '{d}/{len(segments) - 1}.png'\n")   # the concat demuxer needs the last image twice to keep its duration
        Path(f'{d}/list.txt').write_text(''.join(lines))
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', f'{d}/list.txt', '-vf', f'fps={FPS},format=yuv420p',
                        '-c:v', 'libx264', '-crf', '18', str(out)], check=True)


def load(p: Path) -> Image.Image:
    return Image.open(p).convert('L').resize((SIZE, SIZE))


def main():
    t0 = time.time(); FLOC = floc()
    rng = np.random.default_rng(0)
    faces = sorted((FLOC / 'adult').glob('*.jpg')); houses = sorted((FLOC / 'house').glob('*.jpg'))
    pick_f = rng.choice(len(faces), N, replace=False); pick_h = rng.choice(len(houses), N, replace=False)
    for k in range(N):
        f, h = load(faces[pick_f[k]]), load(houses[pick_h[k]]); both = Image.blend(f, h, 0.5)
        video([(f, 3), (h, 3)] * 4, OUT / f'rivalry/replay_{k}.mp4')
        for turn in (1.5, 6, 12):   # the turn-length sweep: where does the model start to follow the turns?
            video([(f, turn), (h, turn)] * int(12 / turn), OUT / f'rivalry/turns_{turn:g}s_{k}.mp4')
        video([(both, 24)], OUT / f'rivalry/both_{k}.mp4')
        video([(f, 24)], OUT / f'rivalry/face_{k}.mp4')
        video([(h, 24)], OUT / f'rivalry/house_{k}.mp4')
    grey, white = Image.new('L', (SIZE, SIZE), 128), Image.new('L', (SIZE, SIZE), 255)
    video([(grey, 2)] + [(white, 0.5), (grey, 3.5)] * 5 + [(white, 0.5), (grey, 1.5)], OUT / 'flash/flash.mp4')   # flashes at 2, 6, 10, 14, 18 and 22 s
    video([(grey, 24)], OUT / 'flash/grey.mp4')
    meta = {'id': 'generated_examples', 'ref': 'studies/examples/stimuli.py', 'repository': 'generated', 'key': 'generated_examples',
            'title': 'Rivalry and flash stimuli, made from fLoc faces and houses', 'licence': None, 'fetched_at': time.strftime('%Y-%m-%d'),
            'files': sorted(str(p.relative_to(OUT)) for p in OUT.rglob('*.mp4')),
            'faces': [faces[i].name for i in pick_f], 'houses': [houses[i].name for i in pick_h]}
    (OUT / '_dataset.json').write_text(json.dumps(meta, indent=1))
    print(len(meta['files']), 'videos in', OUT, f'({time.time() - t0:.0f} s)')


if __name__ == '__main__':
    main()
