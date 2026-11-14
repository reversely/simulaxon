"""The observer demo, one picture: each moment's four cells at the decision point, in one sheet.
Rows are moments; columns are human recorded, human robotic (android), G1 recorded, G1 robotic (robot).
usage (feasibility/.venv): python observer/contact_sheet.py    writes ~/data/observer/contact_sheet.jpg
"""
import json, os
from pathlib import Path
from PIL import Image, ImageDraw

O = Path(os.environ.get('OBS_OUT', '~/data/observer')).expanduser(); CELLS = ['human_recorded', 'human_robotic', 'g1_recorded', 'g1_robotic']
LABEL = {'human_recorded': 'Human, recorded motion', 'human_robotic': 'Human, robotic motion', 'g1_recorded': 'G1, recorded motion', 'g1_robotic': 'G1, robotic motion'}
ms = json.load(open(O / 'moments.json'))['moments']; w, h = 320, 180; pad = 28
sheet = Image.new('RGB', (4 * w, pad + len(ms) * h), (18, 18, 20)); d = ImageDraw.Draw(sheet)
for j, c in enumerate(CELLS): d.text((j * w + 8, 8), LABEL[c], fill=(235, 235, 235))
for i, m in enumerate(ms):
    for j, c in enumerate(CELLS):
        f = O / 'clips' / f"{m['rec']}_{m['k']:03d}_{c}_decision.png"
        if f.exists(): sheet.paste(Image.open(f).convert('RGB').resize((w, h)), (j * w, pad + i * h))
sheet.save(O / 'contact_sheet.jpg', quality=88); print('saved', O / 'contact_sheet.jpg')
