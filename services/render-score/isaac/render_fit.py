"""Test 3a: a real kitchen counter in Isaac Sim with real Palatial assets.

For each asset: place it on the counter by its bounds, render
  - the stimulus camera (what TRIBE sees), 832x480;
  - the overview camera (the Scene page), 1600x1000;
with RGB, instance id mask with prim paths, depth and camera parameters.
Times each asset swap, which is the "change one thing" path.
"""
import time, json, sys
from pathlib import Path
t_start = time.time()
from isaacsim import SimulationApp
app = SimulationApp({"headless": True})
boot = time.time() - t_start

import numpy as np
from PIL import Image
import omni.usd, omni.replicator.core as rep
from pxr import Usd, UsdGeom, Gf, UsdLux, Sdf, UsdShade

HERE = Path(__file__).parent; ASSETS = HERE.parent / 'assets' / 'palatial'
import json as _j
_items = _j.load(open(sys.argv[1])); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
ITEMS_LIST = [(f"p{it['pair']:02d}_{it['kind']}", it['usd'], it.get('yaw_deg', 0)) for it in _items]
_UNUSED = {
  'banana': 'batch1/D00002 Banana/IsaacSim_assets_69f1ea3e59057a93105854a6/IsaacSim_asset_69f1ea3e59057a93105854a6.usd',
  'squeeze_bottle': 'batch2/Dijon_Mustard_Squeeze_Bottle/Dijon_Mustard_Squeeze_Bottle.usd',
  'apple': 'batch1/D00023 Berry Apple/IsaacSim_assets_69f1f0a059057a931058ba6a/IsaacSim_asset_69f1f0a059057a931058ba6a.usd',
  'bagel': 'batch15/D00005_bagel/IsaacSim_assets_6a5f180bbeb159ad854124a9/IsaacSim_asset_6a5f180bbeb159ad854124a9.usd',
  'mug': 'batch13/D00542 Mug/IsaacSim_assets_69f5f375431507ff7cffa38b/IsaacSim_asset_69f5f375431507ff7cffa38b.usd',
  'glass_jar': 'batch31/D00347_Glass_Jar/IsaacSim_assets_6a82e012b7a9c4204ad0cd39/IsaacSim_asset_6a82e012b7a9c4204ad0cd39.usd',
}
TOP = 0.90  # counter top height, metres
ctx = omni.usd.get_context(); stage = ctx.get_stage()
UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)

def box(path, size, pos, rgb, rough=0.5):
    c = UsdGeom.Cube.Define(stage, path); c.GetSizeAttr().Set(1.0)
    x = UsdGeom.Xformable(c); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(*pos)); x.AddScaleOp().Set(Gf.Vec3f(*size))
    m = UsdShade.Material.Define(stage, path + '_mat'); sh = UsdShade.Shader.Define(stage, path + '_mat/s'); sh.CreateIdAttr('UsdPreviewSurface')
    sh.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb)); sh.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(rough)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), 'surface'); UsdShade.MaterialBindingAPI(c).Bind(m)
    return c
box('/World/Counter', (2.6, 0.7, 0.04), (0, 0.1, TOP - 0.02), (0.36, 0.34, 0.31), 0.35)
box('/World/Cabinet', (2.56, 0.64, TOP - 0.04), (0, 0.12, (TOP - 0.04) / 2), (0.08, 0.09, 0.10), 0.6)
box('/World/Wall', (4.0, 0.04, 3.0), (0, 0.48, 1.5), (0.16, 0.155, 0.15), 0.9)
box('/World/Floor', (6, 6, 0.02), (0, -1.0, -0.01), (0.18, 0.13, 0.09), 0.6)
box('/World/Board', (0.38, 0.24, 0.02), (-0.42, 0.18, TOP + 0.01), (0.45, 0.27, 0.12), 0.55)
key = UsdLux.RectLight.Define(stage, '/World/WindowLight'); key.CreateIntensityAttr(3500); key.CreateWidthAttr(1.4); key.CreateHeightAttr(1.4)
kx = UsdGeom.Xformable(key); kx.AddTranslateOp().Set(Gf.Vec3d(-1.3, -0.6, 1.9)); kx.AddRotateXYZOp().Set(Gf.Vec3f(35, -45, 0))
dome = UsdLux.DomeLight.Define(stage, '/World/Ambient'); dome.CreateIntensityAttr(250)

def place_usd(usd, item_yaw=0):
    p = stage.GetPrimAtPath('/World/Counter/Item') if False else stage.GetPrimAtPath('/World/Item')
    if p: stage.RemovePrim('/World/Item')
    prim = stage.DefinePrim('/World/Item', 'Xform'); prim.GetReferences().AddReference(str(ASSETS / usd))
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedRange()
    lo, hi = bb.GetMin(), bb.GetMax(); cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    x = UsdGeom.Xformable(prim); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(-cx, -cy, TOP - lo[2])); x.AddRotateZOp().Set(float(item_yaw))
    return [round(hi[i] - lo[i], 3) for i in range(3)]

def look(cam_path, eye, target, focal):
    cam = UsdGeom.Camera.Define(stage, cam_path); cam.GetFocalLengthAttr().Set(focal); cam.GetHorizontalApertureAttr().Set(36.0)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))  # USD's default near plane is 1 m, which clips anything on the counter
    m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
    x = UsdGeom.Xformable(cam); x.ClearXformOpOrder(); x.AddTransformOp().Set(m)
    return cam_path
d, yaw, h = 0.62, np.radians(8), 0.20
stim = look('/World/TribeCamera', (np.sin(yaw) * d, -np.cos(yaw) * d, TOP + 0.03 + h), (0, 0, TOP + 0.03), 35.0)
over = look('/World/OverviewCamera', (-0.95, -1.55, 1.62), (0.12, -0.22, 0.86), 28.0)
products = {'tribe': rep.create.render_product(stim, (832, 480))}
annots = {}
for k, rp in products.items():
    for a in ['rgb', 'instance_id_segmentation', 'distance_to_camera', 'camera_params']:
        an = rep.AnnotatorRegistry.get_annotator(a, init_params={'colorize': False} if a == 'instance_id_segmentation' else None); an.attach(rp); annots[(k, a)] = an
for _ in range(30): app.update()

report = {'boot_s': round(boot, 1), 'items': {}}
for i, (name, usd, item_yaw) in enumerate(ITEMS_LIST):
    t0 = time.time(); size = place_usd(usd, item_yaw)
    _h = max(size[2], 0.05); _r = max(size) ; _c = TOP + _h / 2
    _d = 2.6 * _r + 0.15
    look(stim, (np.sin(yaw) * _d, -np.cos(yaw) * _d, _c + 0.35 * _d), (0, 0, _c), 35.0)
    rep.orchestrator.step(rt_subframes=16)
    rgb = annots[('tribe', 'rgb')].get_data()
    while rgb is None or np.asarray(rgb).size == 0:
        rep.orchestrator.step(rt_subframes=16); rgb = annots[('tribe', 'rgb')].get_data()
    dt = time.time() - t0
    rec = {'size_m': size, 'swap_and_render_s': round(dt, 2)}
    for k in products:
        Image.fromarray(np.asarray(annots[(k, 'rgb')].get_data())[..., :3]).save(OUT / f'{name}_{k}.png')
        seg = annots[(k, 'instance_id_segmentation')].get_data()
        np.save(OUT / f'{name}_{k}_ids.npy', np.asarray(seg['data']))
        rec[f'{k}_id_to_path'] = {str(a): b for a, b in seg['info']['idToLabels'].items()}
        np.save(OUT / f'{name}_{k}_depth.npy', np.asarray(annots[(k, 'distance_to_camera')].get_data()).astype(np.float16))
        cp = annots[(k, 'camera_params')].get_data()
        rec[f'{k}_camera'] = {kk: np.asarray(cp[kk]).tolist() for kk in ['cameraViewTransform', 'cameraProjection', 'cameraFocalLength', 'cameraAperture', 'renderProductResolution'] if kk in cp}
    report['items'][name] = rec
    print(name, rec['size_m'], rec['swap_and_render_s'], flush=True)
json.dump(report, open(OUT / 'report.json', 'w'), indent=1, default=str)
print('DONE'); app.close()
