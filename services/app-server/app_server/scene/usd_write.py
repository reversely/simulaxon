"""USD writing with pxr (usd-core). Runs without Isaac Sim, so imports and composition can be tested on CPU.

  sage_ply_to_usd      SAGE's PLY layout (separate texcoord element, per-face texcoord indices) plus texture
  trimesh_scene_to_usd any mesh trimesh can read, with per-geometry materials and base-colour textures
  compose              Scene to one USD stage: rooms as boxes, objects as references with pose and provenance
"""
from __future__ import annotations
from pathlib import Path
import re
import numpy as np
from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf, Vt


def _safe(name: str) -> str:
    s = re.sub(r'[^A-Za-z0-9_]', '_', name)
    return s if s and not s[0].isdigit() else '_' + s


def _material(stage, path, rgb=(0.7, 0.7, 0.7), texture: str | None = None, roughness=0.6):
    mat = UsdShade.Material.Define(stage, path)
    pbr = UsdShade.Shader.Define(stage, path + '/PBR'); pbr.CreateIdAttr('UsdPreviewSurface')
    pbr.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(roughness)
    if texture:
        rd = UsdShade.Shader.Define(stage, path + '/st'); rd.CreateIdAttr('UsdPrimvarReader_float2')
        rd.CreateInput('varname', Sdf.ValueTypeNames.Token).Set('st')
        tx = UsdShade.Shader.Define(stage, path + '/Texture'); tx.CreateIdAttr('UsdUVTexture')
        tx.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(str(Path(texture).resolve()))
        tx.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(rd.ConnectableAPI(), 'result')
        tx.CreateOutput('rgb', Sdf.ValueTypeNames.Float3)
        pbr.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).ConnectToSource(tx.ConnectableAPI(), 'rgb')
    else:
        pbr.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
    mat.CreateSurfaceOutput().ConnectToSource(pbr.ConnectableAPI(), 'surface')
    return mat


def _mesh(stage, path, V, F, uv=None, uv_idx=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(np.array(V, dtype=np.float32, copy=True)))
    m.CreateFaceVertexCountsAttr(Vt.IntArray([3] * len(F)))
    m.CreateFaceVertexIndicesAttr(Vt.IntArray(np.asarray(F).reshape(-1).tolist()))
    m.CreateSubdivisionSchemeAttr('none')
    if uv is not None:
        interp = UsdGeom.Tokens.faceVarying if uv_idx is not None else UsdGeom.Tokens.vertex
        st = UsdGeom.PrimvarsAPI(m).CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, interp)
        st.Set(Vt.Vec2fArray.FromNumpy(np.array(uv, dtype=np.float32, copy=True)))
        if uv_idx is not None: st.SetIndices(Vt.IntArray(np.asarray(uv_idx).reshape(-1).tolist()))
    return m


def _new_stage(out):
    stage = Usd.Stage.CreateNew(str(out)); UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, '/Object'); stage.SetDefaultPrim(root.GetPrim()); return stage


def read_sage_ply(path):
    data = Path(path).read_bytes(); end = data.index(b'end_header\n') + len(b'end_header\n')
    counts = {}
    for line in data[:end].decode('ascii').splitlines():
        if line.startswith('element'): _, name, n = line.split(); counts[name] = int(n)
    off = end
    V = np.frombuffer(data, np.float32, counts['vertex'] * 3, off).reshape(-1, 3); off += counts['vertex'] * 12
    T = np.frombuffer(data, np.float32, counts['texcoord'] * 2, off).reshape(-1, 2); off += counts['texcoord'] * 8
    rec = np.dtype([('nv', 'u1'), ('v', '<i4', 3), ('nt', 'u1'), ('t', '<i4', 3)])
    F = np.frombuffer(data, rec, counts['face'], off)
    if not ((F['nv'] == 3).all() and (F['nt'] == 3).all()): raise ValueError('only triangle faces are supported')
    return V, T, F['v'], F['t']


def sage_ply_to_usd(ply, texture, out):
    V, T, Fv, Ft = read_sage_ply(ply); tmp = Path(out).with_suffix('.tmp.usda'); stage = _new_stage(tmp)
    m = _mesh(stage, '/Object/Mesh', V, Fv, T, Ft)
    UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(_material(stage, '/Object/Material', texture=str(texture) if texture else None))
    stage.GetRootLayer().Save(); del stage; tmp.replace(out)   # write then rename, so a failure leaves no half file


def trimesh_scene_to_usd(tscene, out, tex_dir):
    stage = _new_stage(out); tex_dir = Path(tex_dir)
    for i, (name, g) in enumerate(tscene.geometry.items()):
        nodes = tscene.graph.geometry_nodes.get(name, [None])
        for j, node in enumerate(nodes):
            M = tscene.graph.get(node)[0] if node is not None else np.eye(4)
            V = (np.c_[g.vertices, np.ones(len(g.vertices))] @ M.T)[:, :3]
            path = f'/Object/{_safe(name)}_{j}'
            uv = getattr(g.visual, 'uv', None); tex = None; rgb = (0.7, 0.7, 0.7)
            mat = getattr(g.visual, 'material', None)
            img = getattr(mat, 'baseColorTexture', None) or getattr(mat, 'image', None)
            if img is not None and uv is not None:
                tex = tex_dir / f'{Path(out).stem}_{i}.png'; img.save(tex)
                uv = np.asarray(uv)
            else:
                uv = None
                c = getattr(mat, 'baseColorFactor', None) if mat is not None else None
                if c is not None: rgb = tuple(float(x) / (255 if np.max(c) > 1 else 1) for x in c[:3])
                elif hasattr(g.visual, 'vertex_colors') and len(g.visual.vertex_colors): rgb = tuple(np.asarray(g.visual.vertex_colors)[:, :3].mean(0) / 255)
            m = _mesh(stage, path, V, g.faces, uv)
            UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(_material(stage, path + '_mat', rgb, str(tex) if tex else None))
    stage.GetRootLayer().Save()


def _box(stage, path, centre, size, rgb, yaw_deg=0.0):
    c = UsdGeom.Cube.Define(stage, path); c.GetSizeAttr().Set(1.0)
    x = UsdGeom.Xformable(c); x.AddTranslateOp().Set(Gf.Vec3d(*centre)); x.AddRotateZOp().Set(float(yaw_deg)); x.AddScaleOp().Set(Gf.Vec3f(*size))
    UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(_material(stage, path + '_mat', rgb, roughness=0.85))


def _bounds(asset_path):
    st = Usd.Stage.Open(str(asset_path)); r = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(st.GetPseudoRoot()).ComputeAlignedRange()
    return np.array(r.GetMin()), np.array(r.GetMax())


def compose(scene, out, fit_size: bool = True) -> dict:
    """Write the scene as one USD stage. Objects are references under /World/Objects/<id>, so a swap or
    an edit touches one prim. Provenance goes into each prim's customData for the interface to read."""
    stage = Usd.Stage.CreateNew(str(out)); UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    world = UsdGeom.Xform.Define(stage, '/World'); stage.SetDefaultPrim(world.GetPrim())
    report = {'objects': 0, 'rescaled': []}
    for r in scene.rooms:
        base = f'/World/Rooms/{_safe(r.id)}'; ox, oy, oz = r.origin_m; w, l, h = r.size_m
        _box(stage, base + '/Floor', (ox + w / 2, oy + l / 2, oz - 0.01), (w, l, 0.02), r.floor_colour_rgb)
        for wl in r.walls:
            a, b = np.array(wl.start_m), np.array(wl.end_m); mid = (a + b) / 2; ln = float(np.linalg.norm(b - a))
            yaw = float(np.degrees(np.arctan2(*(b - a)[::-1])))
            _box(stage, f'{base}/{_safe(wl.id)}', (ox + mid[0], oy + mid[1], oz + wl.height_m / 2), (ln, wl.thickness_m, wl.height_m), wl.colour_rgb, yaw)
    for o in scene.objects:
        p = stage.DefinePrim(f'/World/Objects/{_safe(o.id)}', 'Xform'); x = UsdGeom.Xformable(p)
        x.AddTranslateOp().Set(Gf.Vec3d(*o.position_m)); x.AddRotateXYZOp().Set(Gf.Vec3f(*o.rotation_deg))
        inner = stage.DefinePrim(p.GetPath().AppendChild('Asset'), 'Xform'); inner.GetReferences().AddReference(o.asset.path)
        ix = UsdGeom.Xformable(inner)
        if o.asset.facing_yaw_deg: ix.AddRotateZOp().Set(float(o.asset.facing_yaw_deg))
        if fit_size and o.size_m:
            lo, hi = _bounds(o.asset.path); have = hi - lo
            k = float(o.size_m[2] / have[2]) if have[2] > 1e-6 else 1.0
            if abs(k - 1) > 0.05: ix.AddScaleOp().Set(Gf.Vec3f(k, k, k)); report['rescaled'].append([o.id, round(k, 3)])
        p.SetCustomDataByKey('vcl:label', o.label); p.SetCustomDataByKey('vcl:role', o.role)
        p.SetCustomDataByKey('vcl:source_method', o.source.method); p.SetCustomDataByKey('vcl:collection', o.source.collection or '')
        p.SetCustomDataByKey('vcl:record_id', o.source.record_id or ''); p.SetCustomDataByKey('vcl:placed_on', o.placed_on or '')
        report['objects'] += 1
    stage.GetRootLayer().Save(); return report
