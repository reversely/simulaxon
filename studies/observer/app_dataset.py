"""The observer demo in the app (doc 24 § 13): every clip as a sample, the moment as a group, the cell as a slice.

Hardlinks ~/data/observer/clips/*.mp4 and *.tribe.npy into feasibility/data/observer, writes the table from cells.csv
(observer/analyse.py), writes backend/sources/observer_demo.json, and asks the running data server to load it.
Fields per sample: body, motion, the moment's upper-body speed, AIP and action-set means, whole-cortex mean, motion
energy and luminance; the TRIBE prediction is a track at 1 Hz.
usage (repo root): python3 feasibility/observer/app_dataset.py
"""
import csv, json, os, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.expanduser(os.environ.get('OBS_OUT', '~/data/observer')); NAME = os.environ.get('OBS_DATASET', 'Observer demo, humanoid look and motion')
SLUG = ''.join(ch if ch.isalnum() else '_' for ch in NAME.lower()).strip('_')[:60]
DST = os.path.join(REPO, 'feasibility', 'data', 'observer' if SLUG.startswith('observer_demo') else SLUG); os.makedirs(os.path.join(DST, 'clips'), exist_ok=True)
for f in sorted(os.listdir(os.path.join(SRC, 'clips'))):
    if f.endswith('.mp4') or f.endswith('.tribe.npy') or f.endswith('_decision.png'):
        s, d = os.path.join(SRC, 'clips', f), os.path.join(DST, 'clips', f)
        if not (os.path.exists(d) and os.path.samefile(s, d)):
            if os.path.exists(d): os.remove(d)
            os.link(s, d)
speed = {(m['rec'], m['k']): m['upper_body_speed_rad_s'] for m in json.load(open(os.path.join(SRC, 'moments.json')))['moments']}
rows = []
for r in csv.DictReader(open(os.path.join(SRC, 'cells.csv'))):
    body, motion = r['cell'].split('_')
    rows.append(dict(recording=r['rec'], episode=int(r['k']), cell=r['cell'], body={'g1': 'Unitree G1', 'human': 'SMPL-X human'}[body],
                     motion=motion, upper_body_speed=speed[(r['rec'], int(r['k']))], aip=round(float(r['aip']), 5),
                     action_set=round(float(r['action']), 5), cortex_mean=round(float(r['cortex_mean']), 5),
                     motion_energy=round(float(r['motion_energy']), 3), luminance=round(float(r['luminance']), 2)))
json.dump(rows, open(os.path.join(DST, 'app_table.json'), 'w'), indent=1)
source = {
    'name': NAME,
    'loader': 'table',
    'about': ('The observer demo (research/24_simulated_studies_plan.md section 13; question in 25_observer_question.md). '
              'Six EgoBody moments, chosen by a fixed rule (the most upper-body motion), each acted out four ways in Isaac Sim '
              'in the scan of the real room, seen from where the partner stood: the SMPL-X human body or the Unitree G1, '
              'moving with the wearer\'s recorded motion or with the same poses every 0.5 s joined at constant speed (robotic). '
              'TRIBE v2 predicts the observer\'s cortex for each 9 s clip. AIP is where Saygin et al. 2012 report the android effect.'),
    'file': os.path.relpath(os.path.join(DST, 'app_table.json'), REPO),
    'id': '{recording}_{episode:03d}_{cell}',
    'group': '{recording} #{episode}',
    'slice': '{cell}',
    'media': os.path.relpath(DST, REPO) + '/clips/{recording}_{episode:03d}_{cell}.mp4',
    'require_media': True,
    'tracks': [{'name': 'tribe', 'file': os.path.relpath(DST, REPO) + '/clips/{recording}_{episode:03d}_{cell}.tribe.npy', 'rate_hz': 1}],
    'units': {'tribe': 'TRIBE output units', 'upper_body_speed': 'rad/s', 'aip': 'TRIBE output units', 'action_set': 'TRIBE output units',
              'cortex_mean': 'TRIBE output units', 'motion_energy': 'grey levels per frame', 'luminance': 'grey level'},
}
SRCF = os.path.join(REPO, 'backend', 'sources', ('observer_demo' if SLUG.startswith('observer_demo') else SLUG) + '.json'); json.dump(source, open(SRCF, 'w'), indent=1)
print(len(rows), 'rows written')
req = urllib.request.Request('http://localhost:8791/api/datasets/load', method='POST', headers={'Content-Type': 'application/json'},
                             data=json.dumps({'source': os.path.relpath(SRCF, REPO)}).encode())
try:
    print(urllib.request.urlopen(req, timeout=300).read()[:300].decode())
except Exception as e:
    print('data server not reachable, load skipped:', e)
