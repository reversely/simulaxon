"""The looping clips that show each seeded example in New project: its real stimulus playing, never a still.

Each clip comes from that example's run when the run is in the store, and from its stimuli on the volume when it isn't,
so a fresh store still gets a clip for every example whose stimuli are there. An example with neither is skipped and
its card shows text only.

| Clip | From the run | Otherwise from |
|---|---|---|
| rivalry, flash | | the generated stimuli (stimuli.py) |
| rivalry_face_only and the others | the rivalry project's trials | the generated stimuli |
| faces_objects | the agent's Kanwisher 1997 run | fLoc photos: 4 faces, then 4 objects, 2 s each |
| humanoid | the lab's observer render | the observer study's G1 clips |
| photoreal | the Isaac Sim and Cosmos trials | a render-score render beside its Cosmos chunk |
| action_clips | | four Human Action Dataset clips |

usage, from the repo root with the app server's Python (run stimuli.py first):
  PYTHONPATH=services/app-server python studies/examples/media.py [PORT]
PORT is the running app server, default 8790, read for the runs; without one, every clip comes from stimuli.
Writes backend/data/files/examples/*.mp4 under the data root (SIMULAXON_HOME or SIMULAXON_DATA).
"""
import json, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services' / 'app-server'))
from app_server.home import HOME          # noqa: E402
from app_server.lab import datasets       # noqa: E402
from app_server.lab.examples import EXAMPLES   # noqa: E402  (each example's project title, in one place)

DATA = HOME / 'backend' / 'data'; OUT = DATA / 'files' / 'examples'; GEN = datasets.HERE / 'generated_examples'
FLOC = datasets.HERE / 'github_vpnl_floc' / 'stimuli'; HAD = HOME / 'feasibility' / 'data' / 'had' / 'stimuli'
PORT = sys.argv[1] if len(sys.argv) > 1 else '8790'
ENC = ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '26', '-pix_fmt', 'yuv420p', '-an', '-movflags', '+faststart']
UNPAD = 'crop=iw:trunc(iw*480/832/2)*2-8:0:(ih-oh)/2'   # trials pad the 832 x 480 frame to a square with grey; cut the bands


def tool(name, **args):
    req = urllib.request.Request(f'http://127.0.0.1:{PORT}/tools/{name}', data=json.dumps(args).encode(), headers={'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=30))['result']


def run_clips(example):
    """The first trial clip of each condition in this example's finished project, and the seconds its stimulus is on
    screen; None when there is no such run, or no server to ask."""
    title = next(e['project_title'] for e in EXAMPLES if e['id'] == example)
    try:
        p = next((p for p in tool('project_list') if p['data'].get('title') == title and p['data'].get('status') == 'Done'), None)
        if p is None: return None
        out = {}
        for s in tool('sample_list', project_id=p['id']):
            f = DATA / s['data']['clip'].lstrip('/')
            if f.exists(): out.setdefault(s['data']['condition'], f)
        return (out, p['data']['setup']['trial']['on_s']) if out else None
    except (OSError, urllib.error.URLError, KeyError):
        return None


def ff(*args, out):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', *map(str, args), *ENC, str(out)], check=True)


def stills(paths, seconds, out, size=480):
    """A clip of still photos, each held for its seconds."""
    with tempfile.TemporaryDirectory() as d:
        Path(f'{d}/list.txt').write_text(''.join(f"file '{p}'\nduration {seconds}\n" for p in paths) + f"file '{paths[-1]}'\n")
        ff('-f', 'concat', '-safe', '0', '-i', f'{d}/list.txt', '-vf', f'scale={size}:{size}:force_original_aspect_ratio=decrease,pad={size}:{size}:(ow-iw)/2:(oh-ih)/2:color=gray,setsar=1,fps=30', out=out)


def rivalry():
    if not (GEN / 'rivalry' / 'replay_0.mp4').exists(): return 'no generated stimuli; run stimuli.py'
    ff('-i', GEN / 'rivalry' / 'replay_0.mp4', '-t', 12, '-vf', 'scale=480:480', out=OUT / 'rivalry.mp4')
    run = run_clips('rivalry')
    conds = {'Face only': 'face', 'House only': 'house', 'Both at once': 'both', 'Taking turns': 'replay'}
    for cond, name in [('Face only', 'face_only'), ('House only', 'house_only'), ('Both at once', 'both'), ('Taking turns', 'turns')]:
        src, on = (run[0][cond], run[1]) if run and cond in run[0] else (GEN / 'rivalry' / f'{conds[cond]}_0.mp4', 24)
        ff('-i', src, '-t', min(12, on), '-vf', 'scale=360:360,setsar=1', out=OUT / f'rivalry_{name}.mp4')
    return 'the rivalry run' if run else 'the generated stimuli'


def flash():
    if not (GEN / 'flash' / 'flash.mp4').exists(): return 'no generated stimuli; run stimuli.py'
    ff('-ss', 1, '-i', GEN / 'flash' / 'flash.mp4', '-t', 12, '-vf', 'scale=480:480', out=OUT / 'flash.mp4')   # the first flash a second in
    return 'the generated stimuli'


def faces_objects():
    run = run_clips('faces')
    if run and {'faces', 'objects'} <= set(run[0]):
        c, on = run
        ff('-t', on, '-i', c['faces'], '-t', on, '-i', c['objects'], '-filter_complex', '[0:v]scale=480:480,setsar=1[a];[1:v]scale=480:480,setsar=1[b];[a][b]concat=n=2:v=1[v]', '-map', '[v]', out=OUT / 'faces_objects.mp4')
        return 'the agent\'s run'
    faces = sorted((FLOC / 'adult').glob('*.jpg'))[:4]; objects = [p for pair in zip(sorted((FLOC / 'car').glob('*.jpg')), sorted((FLOC / 'instrument').glob('*.jpg'))) for p in pair][:4]
    if len(faces) < 4 or len(objects) < 4: return 'no fLoc photos; run stimuli.py'
    stills(faces + objects, 2, OUT / 'faces_objects.mp4')
    return 'fLoc photos'


def humanoid():
    lab = DATA / 'files' / 'runs' / 'clips' / 'observer_g1_recorded_000.mp4'
    study = sorted((HOME / 'studies' / 'observer').glob('**/clips/*_g1_recorded.mp4'))
    src = lab if lab.exists() else (study[0] if study else None)
    if src is None: return 'no observer render; run the observer study'
    ff('-i', src, '-t', 9, '-vf', 'scale=640:-2', out=OUT / 'humanoid.mp4')
    return 'the lab\'s render' if src == lab else 'the observer study'


def photoreal():
    run = run_clips('photoreal')
    if run and {'Isaac Sim', 'Cosmos'} <= set(run[0]):
        c, on = run; a, b, crop = c['Isaac Sim'], c['Cosmos'], f'{UNPAD},'
    else:
        pairs = [(r, HOME / 'chunks' / r.name) for r in sorted((HOME / 'chunks' / 'renders').glob('*.mp4')) if (HOME / 'chunks' / r.name).exists()]
        if not pairs: return 'no render with its Cosmos chunk; run render-score /score once'
        (a, b), on, crop = pairs[-1], 4, ''
    ff('-t', on, '-i', a, '-t', on, '-i', b, '-filter_complex', f'[0:v]{crop}scale=416:240,setsar=1[a];[1:v]{crop}scale=416:240,setsar=1[b];[a][b]hstack=inputs=2:shortest=1[v]', '-map', '[v]', out=OUT / 'photoreal.mp4')
    return 'the paired run' if run else 'render-score\'s render and chunk'


def action_clips():
    cats = ('Archery', 'Knitting', 'Arm_wrestling', 'Assembling_bicycle')
    clips = [next(iter(sorted((HAD / c).glob('*.mp4'))), None) for c in cats]
    if not all(clips): return 'no Human Action Dataset clips on the volume'
    chain = ';'.join(f'[{i}:v]scale=360:360,setsar=1,fps=30[v{i}]' for i in range(4)) + ';' + ''.join(f'[v{i}]' for i in range(4)) + 'concat=n=4:v=1[v]'
    ff(*[a for c in clips for a in ('-i', c)], '-filter_complex', chain, '-map', '[v]', out=OUT / 'action_clips.mp4')
    return 'Human Action Dataset clips'


def main():
    OUT.mkdir(parents=True, exist_ok=True); t0 = time.time()
    for make in (rivalry, flash, faces_objects, humanoid, photoreal, action_clips):
        made = sorted(OUT.glob(f'{make.__name__}*.mp4'))
        before = {p: p.stat().st_mtime for p in made}
        said = make(); after = [p for p in sorted(OUT.glob(f'{make.__name__}*.mp4')) if before.get(p) != p.stat().st_mtime]
        print(f'{make.__name__:14s}', f'from {said}' if after else f'skipped: {said}')
    size = sum(p.stat().st_size for p in OUT.glob('*.mp4'))
    print(f'{len(list(OUT.glob("*.mp4")))} clips, {size / 1e6:.1f} MB, in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
