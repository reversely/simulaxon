"""Glue between the scene package and the tool registry: build scenes by method, keep objects as rows,
and compose the current rows back into USD when a renderer needs the stage."""
from __future__ import annotations
from dataclasses import asdict
import hashlib, json, os
from ..home import HOME
from pathlib import Path
from .layout import Scene, SceneObject, Asset, Source
from . import importers, usd_write

ROLES = {'context', 'manipulated', 'control'}
WORK = Path(os.environ.get('VCL_SCENE_DIR', HOME / 'feasibility' / 'out' / 'scenes'))


def to_dict(scene: Scene) -> dict:
    d = asdict(scene); d.pop('objects'); return d


def object_path(scene_id: str, obj_id: str) -> str:
    return f'{scene_id}:/World/Objects/{usd_write._safe(obj_id)}'


def object_row(scene_id: str, o: SceneObject) -> dict:
    return {'scene_id': scene_id, 'path': object_path(scene_id, o.id), **asdict(o)}


def import_file(file_path, collection, up_axis, units) -> dict:
    p = Path(file_path); fmt = p.suffix.lower().lstrip('.')
    if fmt in importers.USD_FORMATS:
        a, rep = importers.usd_file(p), {'file': p.name, 'format': fmt, 'kept': 'USD referenced as-is'}
    else:
        a, rep = importers.mesh_file(p, WORK / 'records', up_axis, units)
    return {'collection': collection, 'name': p.stem, 'asset': asdict(a), 'import_report': rep}


def build(method: str, settings: dict, store) -> Scene:
    if method == 'empty':
        return Scene(id=settings.get('name', 'scene'), name=settings.get('name', 'Empty scene'), source=Source('empty'))
    if method == 'sage_layout':
        folder = Path(settings['folder']); return importers.sage_layout(folder, folder / 'usd')
    if method == 'record':
        r = store.get('record', settings['record_id']).data
        return importers.single_object_scene(Asset(**r['asset']), Source('library', r['collection'], settings['record_id']), r['name'],
                                             settings.get('name', r['name']), settings.get('surface_height_m', 0.9))
    raise ValueError("method must be one of ['empty', 'record', 'sage_layout']")


def object_from_record(store, scene_id, record_id, position_m, rotation_deg, label, role, placed_on=None) -> dict:
    if role not in ROLES: raise ValueError(f'role must be one of {sorted(ROLES)}')
    r = store.get('record', record_id).data
    oid = f"{label or r['name']}_{hashlib.sha1(f'{record_id}{position_m}'.encode()).hexdigest()[:6]}"
    method = 'file_upload' if r['collection'] == 'Your files' else 'library'
    o = SceneObject(id=oid, label=label or r['name'], asset=Asset(**r['asset']), source=Source(method, r['collection'], record_id),
                    position_m=position_m, rotation_deg=rotation_deg, role=role, placed_on=placed_on)
    return object_row(scene_id, o)


def current(store, scene_id: str, compose: bool = False) -> dict:
    row = store.get('scene', scene_id); d = row.data['scene']
    objs = [r for r in store.list('object') if r.data.get('scene_id') == scene_id]
    out = {'scene': row, 'objects': objs}
    if compose:
        keep = set(SceneObject.__dataclass_fields__)
        sc = Scene.from_json(json.dumps({**d, 'objects': [{k: v for k, v in o.data.items() if k in keep} for o in objs]}))
        key = hashlib.sha1(json.dumps([d, [o.data for o in objs]], sort_keys=True, default=str).encode()).hexdigest()[:12]
        usd = WORK / scene_id / f'{key}.usda'; usd.parent.mkdir(parents=True, exist_ok=True)
        if not usd.exists(): usd_write.compose(sc, usd)
        (usd.with_suffix('.json')).write_text(sc.to_json())
        out['usd_path'] = str(usd)   # content-addressed: the same rows always give the same stage
    return out
