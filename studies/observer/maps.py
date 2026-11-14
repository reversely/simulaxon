"""The observer demo, region view (doc 24 § 13): the four contrasts as cortical maps, drawn with TRIBE v2's own plotter.

Same settings as render_tribe_maps.py: half-inflated fsaverage5, sulcal shading, signed cold-hot colour that fades to
grey near zero, symmetric limits at the 99th percentile of |value|. Lateral views, where AIP, STS and MT sit, plus the
regions of the action set outlined by name in the caption file.
usage (feasibility/.venv): python observer/maps.py    reads ~/data/observer/contrast_maps.npz, writes ~/data/observer/maps/
"""
import json, os, sys
from pathlib import Path
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(HERE / 'tribev2-src'))
from tribev2.plotting import PlotBrain
from nilearn.plotting.cm import cold_hot
from matplotlib.colors import ListedColormap

OUT = Path(os.environ.get('OBS_OUT', '~/data/observer')).expanduser(); MD = OUT / 'maps'; MD.mkdir(exist_ok=True)
_c = cold_hot(np.linspace(0, 1, 256)); _c[:, 3] = np.clip(np.abs(np.linspace(-1, 1, 256)) / 0.35 - 0.15, 0, 1)
SIGNED = ListedColormap(_c)
maps = dict(np.load(OUT / 'contrast_maps.npz')); plotter = PlotBrain(mesh='fsaverage5'); made = {}
for name, vals in maps.items():
    vmax = float(np.percentile(np.abs(vals), 99)); made[name] = dict(vmax=round(vmax, 5), files=[])
    for view in ('left', 'right'):
        fig, ax = plt.subplots(figsize=(4, 3), dpi=200)
        plotter.plot_surf(vals, axes=ax, views=view, cmap=SIGNED, vmin=-vmax, vmax=vmax, symmetric_cbar=True)
        f = MD / f'{name}_{view}.png'; fig.savefig(f, bbox_inches='tight', pad_inches=0.02, facecolor='white'); plt.close(fig)
        made[name]['files'].append(str(f))
    print(name, 'drawn, limits', -vmax, vmax, flush=True)
json.dump(made, open(MD / 'maps.json', 'w'), indent=1)
