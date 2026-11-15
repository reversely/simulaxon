"""The fsaverage5 cortex for the brain drawn in the browser (#27), from the copy nilearn ships with the package.

One binary file, built once and cached in the files folder: a uint32 header length, a JSON header, then the arrays the
header lists, each at a 4-byte aligned offset after the header. Pial and inflated coordinates are both sent so the page
can show either or the half-inflated mean TRIBE v2's plotter draws (tribev2.plotting.base, inflate='half'); like that
plotter, each surface's hemispheres are moved apart along x until they touch (hemisphere_gap 0). Coordinates are int16
in hundredths of a millimetre around the half-inflated brain's centre; sulcal depth is uint8 over its range.
Vertex order is TRIBE's: left hemisphere then right, 10,242 each, so a row of a predictions file colours it as is.
"""
from __future__ import annotations
import json, struct
from pathlib import Path
import numpy as np

VERSION = 1
SCALE = 100   # int16 units per millimetre


def _surfaces() -> dict:
    import nibabel as nib
    from nilearn import datasets
    fs = datasets.fetch_surf_fsaverage('fsaverage5')   # bundled with nilearn: nothing is downloaded
    out = {'pial': [], 'infl': [], 'sulc': [], 'faces': []}; offset = 0
    for hemi in ('left', 'right'):
        for kind in ('pial', 'infl'):
            xyz, faces = nib.load(getattr(fs, f'{kind}_{hemi}')).darrays
            c = xyz.data.astype(np.float64).copy()
            c[:, 0] -= c[:, 0].max() if hemi == 'left' else c[:, 0].min()
            out[kind].append(c)
            if kind == 'pial': out['faces'].append(faces.data.astype(np.int64) + offset)
        out['sulc'].append(nib.load(getattr(fs, f'sulc_{hemi}')).darrays[0].data.astype(np.float64))
        offset += len(out['pial'][-1])
    return {k: np.concatenate(v) for k, v in out.items()}


def build() -> bytes:
    s = _surfaces()
    half = (s['pial'] + s['infl']) / 2; centre = (half.min(0) + half.max(0)) / 2
    sulc = s['sulc']; sulc_u8 = np.round(255 * (sulc - sulc.min()) / (sulc.max() - sulc.min())).astype(np.uint8)
    arrays = {'pial': np.round((s['pial'] - centre) * SCALE).astype('<i2'), 'infl': np.round((s['infl'] - centre) * SCALE).astype('<i2'),
              'sulc': sulc_u8, 'faces': s['faces'].astype('<u2')}
    head, body, at = {'version': VERSION, 'scale': SCALE, 'n': len(sulc), 'n_left': int((s['faces'][:len(s['faces']) // 2]).max() + 1),
                      'centre_mm': [round(float(x), 3) for x in centre], 'arrays': {}}, b'', 0
    for k, a in arrays.items():
        head['arrays'][k] = {'offset': at, 'dtype': a.dtype.str[1:], 'shape': list(a.shape)}
        raw = a.tobytes(); pad = (-len(raw)) % 4; body += raw + b'\0' * pad; at += len(raw) + pad
    h = json.dumps(head).encode(); h += b' ' * ((-len(h)) % 4)
    return struct.pack('<I', len(h)) + h + body


def path(files: Path) -> Path:
    """The cached file, built on first use."""
    p = files / 'brain' / f'fsaverage5_v{VERSION}.bin'
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True); tmp = p.with_suffix('.tmp'); tmp.write_bytes(build()); tmp.replace(p)
    return p
