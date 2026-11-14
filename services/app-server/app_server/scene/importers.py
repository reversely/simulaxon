"""Importers: each generation method in, one Scene or Asset out.

  sage_layout(dir)            a SAGE-10k scene folder (layout_*.json, objects/, materials/)
  mesh_file(path)             one uploaded mesh (GLB, glTF, OBJ, PLY, STL) converted to USD
  usd_file(path)              one uploaded or library USD, referenced as-is
  single_object_scene(...)    wraps any asset in a scene, for item-on-a-surface studies

Each returns provenance on every object and lists anything it skipped with a reason.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from .layout import Scene, Room, Wall, SceneObject, Asset, Source
from . import usd_write

MESH_FORMATS = {'glb', 'gltf', 'obj', 'ply', 'stl'}
USD_FORMATS = {'usd', 'usda', 'usdc', 'usdz'}


def _mean_rgb(png: Path, default=(0.6, 0.6, 0.6)) -> list[float]:
    try:
        from PIL import Image
        a = np.asarray(Image.open(png).convert('RGB').resize((32, 32))) / 255.0
        return [round(float(x), 3) for x in a.reshape(-1, 3).mean(0)]
    except Exception:
        return list(default)


def sage_layout(folder: str | Path, out_dir: str | Path) -> Scene:
    """SAGE-10k layout to Scene. Object meshes are SAGE PLY plus texture, converted to USD in out_dir.

    SAGE conventions, checked against the meshes: metres, Z-up, mesh origin at the bottom centre,
    objects face +Y in their own frame. Layout rotation is about Z in degrees.
    """
    folder, out_dir = Path(folder), Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    layout_path = next(folder.glob('layout_*.json')); d = json.loads(layout_path.read_text())
    scene = Scene(id=d['id'], name=(d.get('description') or d['id'])[:80],
                  source=Source('sage_layout', 'SAGE-10k', d['id'], 'CC BY 4.0'))
    mats = folder / 'materials'
    for r in d['rooms']:
        o = r['position']; dims = r['dimensions']
        wall_rgb = None
        walls = []
        for w in r['walls']:
            rgb = _mean_rgb(mats / f"{w.get('material', '')}.png", (0.85, 0.85, 0.82))
            walls.append(Wall(w['id'], [w['start_point']['x'], w['start_point']['y']], [w['end_point']['x'], w['end_point']['y']],
                              w['height'], w['thickness'], rgb))
        room = Room(r['id'], r.get('room_type', ''), [o['x'], o['y'], o['z']], [dims['width'], dims['length'], dims['height']], walls,
                    _mean_rgb(mats / f"{r.get('floor_material', '')}.png", (0.5, 0.5, 0.5)))
        scene.rooms.append(room)
        for dr in r.get('doors', []):
            scene.skipped.append({'id': dr['id'], 'kind': 'door', 'reason': 'Doors are procedural in SAGE and not converted yet. The wall is left solid.'})
        for x in r['objects']:
            ply = folder / 'objects' / f"{x['source_id']}.ply"; tex = folder / 'objects' / f"{x['source_id']}_texture.png"
            if not ply.exists():
                scene.skipped.append({'id': x['id'], 'kind': x['type'], 'reason': 'Mesh missing from the scene archive'}); continue
            usd = out_dir / f"{x['source_id']}.usda"
            if not usd.exists():
                try:
                    usd_write.sage_ply_to_usd(ply, tex if tex.exists() else None, usd)
                except Exception as e:
                    scene.skipped.append({'id': x['id'], 'kind': x['type'], 'reason': f'Conversion failed: {e}'}); continue
            p, rot, dm = x['position'], x['rotation'], x['dimensions']
            scene.objects.append(SceneObject(
                id=x['id'], label=x['type'], description=x.get('description', ''),
                asset=Asset(str(usd), 'usda', str(tex) if tex.exists() else None, 0.0),
                source=Source('sage_layout', 'SAGE-10k', x['source_id'], 'CC BY 4.0'),
                position_m=[p['x'], p['y'], p['z']], rotation_deg=[rot['x'], rot['y'], rot['z']],
                size_m=[dm['width'], dm['length'], dm['height']], placed_on=x.get('place_id')))
    return scene


def mesh_file(path: str | Path, out_dir: str | Path, up_axis: str = 'auto', units: str = 'auto') -> tuple[Asset, dict]:
    """Convert an uploaded mesh to USD. Returns the asset and a report of what was normalised."""
    import trimesh
    path, out_dir = Path(path), Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    fmt = path.suffix.lower().lstrip('.')
    if fmt not in MESH_FORMATS: raise ValueError(f'{fmt} is not a mesh format this importer reads: {sorted(MESH_FORMATS)}')
    loaded = trimesh.load(path, force='scene')
    report = {'file': path.name, 'format': fmt, 'meshes': len(loaded.geometry)}
    # glTF is Y-up by specification; OBJ, PLY and STL carry no axis, so guess from the bounds when asked.
    if up_axis == 'auto': up_axis = 'Y' if fmt in ('glb', 'gltf') else 'Z'
    if up_axis == 'Y':
        loaded.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])); report['rotated'] = 'Y-up to Z-up'
    ext = loaded.extents
    if units == 'auto':
        units = 'cm' if ext.max() > 20 else 'mm' if ext.max() > 2000 else 'm'
    scale = {'m': 1.0, 'cm': 0.01, 'mm': 0.001}[units]
    if scale != 1.0: loaded.apply_scale(scale); report['scaled'] = f'{units} to m'
    lo, hi = loaded.bounds; centre = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]
    loaded.apply_translation([-centre[0], -centre[1], -centre[2]]); report['origin'] = 'moved to bottom centre'
    report['size_m'] = [round(float(x), 3) for x in loaded.extents]
    out = out_dir / (path.stem + '.usda')
    usd_write.trimesh_scene_to_usd(loaded, out, out_dir)
    return Asset(str(out), 'usda', None, 0.0), report


def usd_file(path: str | Path) -> Asset:
    path = Path(path); fmt = path.suffix.lower().lstrip('.')
    if fmt not in USD_FORMATS: raise ValueError(f'{fmt} is not USD')
    return Asset(str(path), fmt)


def single_object_scene(asset: Asset, source: Source, label: str, scene_id: str, surface_height_m: float = 0.9) -> Scene:
    obj = SceneObject(id='item', label=label, asset=asset, source=source, position_m=[0, 0, surface_height_m], role='manipulated')
    return Scene(id=scene_id, name=label, source=source, objects=[obj])
