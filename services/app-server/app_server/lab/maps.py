"""Brain maps drawn with TRIBE v2's own plotter (half-inflated fsaverage5, sulcal shading, colour fading to grey near zero).

render(values, kind) writes one transparent PNG per view into the files folder, cached by content hash, and returns
{view: relative url}. 'single' maps use the TRIBE demo's fire colour map; 'contrast' maps use a symmetric map.
"""
from __future__ import annotations
import hashlib, os, sys
from pathlib import Path
import numpy as np

from ..home import HOME as ROOT
sys.path.insert(0, str(ROOT / 'feasibility' / 'tribev2-src'))
VIEWS = ['left', 'right', 'ventral', 'posterior']
_plotter = None


def _signed():
    from nilearn.plotting.cm import cold_hot
    from matplotlib.colors import ListedColormap
    c = cold_hot(np.linspace(0, 1, 256)); c[:, 3] = np.clip(np.abs(np.linspace(-1, 1, 256)) / 0.35 - 0.15, 0, 1)
    return ListedColormap(c)


def _transparent(path: Path):
    from PIL import Image
    from scipy import ndimage
    a = np.asarray(Image.open(path).convert('RGB')).astype(int); white = a.min(-1) > 245
    lab, _ = ndimage.label(white); edge = set(np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])) - {0}
    Image.fromarray(np.dstack([a, np.where(np.isin(lab, list(edge)), 0, 255)]).astype(np.uint8), 'RGBA').save(path)


def render(values: np.ndarray, kind: str, files: Path, vmax: float | None = None) -> dict:
    global _plotter
    values = np.asarray(values, np.float32)
    vmax = float(vmax if vmax is not None else np.percentile(np.abs(values), 99))
    key = hashlib.sha256(values.tobytes() + kind.encode() + f'{vmax:.6f}'.encode()).hexdigest()[:16]
    out = {v: f'maps/{key}_{v}.png' for v in VIEWS}
    if all((files / p).exists() for p in out.values()): return {'views': out, 'vmax': vmax}
    import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
    os.environ.setdefault('PYVISTA_OFF_SCREEN', 'true')
    if _plotter is None:
        try: from tribev2.plotting import PlotBrain
        except ImportError as e:   # the plotter needs torch, neuralset and pyvista, which the cluster's app container lacks
            return _elsewhere(values, kind, files, vmax, out, e)
        _plotter = PlotBrain(mesh='fsaverage5')
    (files / 'maps').mkdir(parents=True, exist_ok=True)
    for v, rel in out.items():
        fig, ax = plt.subplots(figsize=(4, 3), dpi=200)
        if kind == 'single':
            _plotter.plot_surf(values, axes=ax, views=v, cmap='fire', norm_percentile=99, vmin=0.6, alpha_cmap=(0, 0.2))
        else:
            _plotter.plot_surf(values, axes=ax, views=v, cmap=_signed(), vmin=-vmax, vmax=vmax, symmetric_cbar=True)
        fig.savefig(files / rel, bbox_inches='tight', pad_inches=0.02, facecolor='white'); plt.close(fig); _transparent(files / rel)
    return {'views': out, 'vmax': vmax}


def _elsewhere(values: np.ndarray, kind: str, files: Path, vmax: float, out: dict, why: Exception) -> dict:
    """Draw the maps with TRIBE v2's own Python (render-score's environment on the volume), which has the plotter; when
    there is none, a run keeps its numbers without pictures."""
    import subprocess, tempfile
    py = Path(os.environ.get('SIMULAXON_ENVS', '/data/envs')) / 'tribe' / 'bin' / 'python'
    if not py.exists() or os.environ.get('SIMULAXON_MAPS_CHILD'): return {'views': {}, 'vmax': vmax, 'note': f'no brain pictures here: {why}'}
    with tempfile.NamedTemporaryFile(suffix='.npy', delete=False) as f: np.save(f, values); arr = f.name
    try:
        env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[2]), 'MPLBACKEND': 'Agg', 'PYVISTA_OFF_SCREEN': 'true', 'SIMULAXON_MAPS_CHILD': '1'}
        r = subprocess.run([str(py), '-m', 'app_server.lab.maps', arr, kind, str(files), repr(vmax)], env=env, capture_output=True, text=True, timeout=600)
        if r.returncode != 0 or not all((files / p).exists() for p in out.values()):
            return {'views': {}, 'vmax': vmax, 'note': f'no brain pictures here: {(r.stderr or r.stdout)[-300:]}'}
        return {'views': out, 'vmax': vmax}
    finally:
        os.unlink(arr)


if __name__ == '__main__':   # python -m app_server.lab.maps values.npy kind files_dir vmax: draw with this Python's plotter
    a = sys.argv[1:]
    render(np.load(a[0]), a[1], Path(a[2]), float(a[3]))
