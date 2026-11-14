"""Warm Isaac Sim worker for live scene previews. Usage: isaac_scene_worker.py counter|stage. Runs in feasibility/isaac/.venv with OMNI_KIT_ACCEPT_EULA=YES and the libgomp preload.

One process, three kinds of world, switched per job:
  counter  an asset on the counter.  inputs: usd, framing (camera distance as a multiple of the object's largest side),
           yaw_deg (camera around the object), light_deg (window light elevation).
  stage    a composed USD stage, such as a SAGE room.  inputs: usda, hidden (prim paths to hide), camera (corner_a,
           corner_b or overview).
  fall     an asset dropped onto the counter.  inputs: usd, outcome (lands or hovers), drop_m, gap_m, restitution.
Outputs: rgb (still worlds) or a frames folder (fall), an object mask, mask labels, and the world's object list.
Every job is deterministic: the same inputs give the same pixels.
"""
import json, sys, time
from pathlib import Path
from isaacsim import SimulationApp
app = SimulationApp({'headless': True})
import numpy as np
from PIL import Image
import omni.usd, omni.replicator.core as rep
from pxr import Usd, UsdGeom, Gf, UsdLux, Sdf, UsdShade

TOP = 0.90
ctx = omni.usd.get_context()
state = {'kind': None, 'key': None, 'rp': None, 'annots': None}


def box(stage, path, size, pos, rgb, rough=0.5):
    c = UsdGeom.Cube.Define(stage, path); c.GetSizeAttr().Set(1.0)
    x = UsdGeom.Xformable(c); x.ClearXformOpOrder(); x.AddTranslateOp().Set(Gf.Vec3d(*pos)); x.AddScaleOp().Set(Gf.Vec3f(*size))
    m = UsdShade.Material.Define(stage, path + '_mat'); sh = UsdShade.Shader.Define(stage, path + '_mat/s'); sh.CreateIdAttr('UsdPreviewSurface')
    sh.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb)); sh.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(rough)
    m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), 'surface'); UsdShade.MaterialBindingAPI(c).Bind(m)


MODE = sys.argv[1] if len(sys.argv) > 1 else 'counter'   # one worker per kind of world, so a worker never switches stages


def counter_world():
    stage = ctx.get_stage()   # the startup stage, exactly as feasibility/isaac/render_fit.py, so renders match the runs
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z); UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    box(stage, '/World/Counter', (2.6, 0.7, 0.04), (0, 0.1, TOP - 0.02), (0.36, 0.34, 0.31), 0.35)
    box(stage, '/World/Cabinet', (2.56, 0.64, TOP - 0.04), (0, 0.12, (TOP - 0.04) / 2), (0.08, 0.09, 0.10), 0.6)
    box(stage, '/World/Wall', (4.0, 0.04, 3.0), (0, 0.48, 1.5), (0.16, 0.155, 0.15), 0.9)
    box(stage, '/World/Floor', (6, 6, 0.02), (0, -1.0, -0.01), (0.18, 0.13, 0.09), 0.6)
    box(stage, '/World/Board', (0.38, 0.24, 0.02), (-0.42, 0.18, TOP + 0.01), (0.45, 0.27, 0.12), 0.55)
    key = UsdLux.RectLight.Define(stage, '/World/WindowLight'); key.CreateIntensityAttr(3500); key.CreateWidthAttr(1.4); key.CreateHeightAttr(1.4)
    UsdLux.DomeLight.Define(stage, '/World/Ambient').CreateIntensityAttr(250)
    return stage


def stage_world(usda):
    ctx.open_stage(str(usda)); [app.update() for _ in range(20)]; stage = ctx.get_stage()
    S = json.loads(Path(usda).with_suffix('.json').read_text()); r = S['rooms'][0]; ox, oy, oz = r['origin_m']; w, l, h = r['size_m']
    for i, (fx, fy) in enumerate([(0.25, 0.25), (0.75, 0.5)]):
        L = UsdLux.RectLight.Define(stage, f'/World/Lights/ceiling{i}'); L.CreateIntensityAttr(4000); L.CreateWidthAttr(1.2); L.CreateHeightAttr(1.2)
        UsdGeom.Xformable(L).AddTranslateOp().Set(Gf.Vec3d(ox + w * fx, oy + l * fy, oz + h - 0.05))
    UsdLux.DomeLight.Define(stage, '/World/Lights/ambient').CreateIntensityAttr(300)
    c = (ox + w / 2, oy + l / 2, oz + 0.8)
    state['cams'] = {'corner_a': ((ox + 0.3, oy + 0.3, oz + 1.6), c, 18.0), 'corner_b': ((ox + w - 0.3, oy + l - 0.3, oz + 1.6), c, 18.0),
                     'overview': ((ox + w / 2, oy - 0.2 * l, oz + h * 1.9), (c[0], c[1], c[2] - 0.6), 16.0)}
    return stage


def look(stage, eye, target, focal, aperture):
    cam = UsdGeom.Camera.Define(stage, '/World/PreviewCam'); cam.GetFocalLengthAttr().Set(focal); cam.GetHorizontalApertureAttr().Set(aperture)
    cam.GetClippingRangeAttr().Set(Gf.Vec2f(0.01, 100.0))
    m = Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*target), Gf.Vec3d(0, 0, 1)).GetInverse()
    x = UsdGeom.Xformable(cam); x.ClearXformOpOrder(); x.AddTransformOp().Set(m)


def ensure(kind, key, builder):
    if state['kind'] == kind and state['key'] == key: return ctx.get_stage()
    if state['rp']:
        for a in state['annots'].values(): a.detach()
        state['rp'].destroy(); state['rp'] = None
    stage = builder()
    look(stage, (0, -1, 1.5), (0, 0, 1), 35.0, 36.0)
    rp = rep.create.render_product('/World/PreviewCam', (832, 480))
    an = {'rgb': rep.AnnotatorRegistry.get_annotator('rgb'),
          'seg': rep.AnnotatorRegistry.get_annotator('instance_id_segmentation', init_params={'colorize': False})}
    for a in an.values(): a.attach(rp)
    state.update(kind=kind, key=key, rp=rp, annots=an)
    for _ in range(10): app.update()
    return stage


def place(stage, usd, z_extra=0.0):
    if stage.GetPrimAtPath('/World/Item'): stage.RemovePrim('/World/Item')
    prim = stage.DefinePrim('/World/Item', 'Xform'); prim.GetReferences().AddReference(str(usd))
    bb = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ['default', 'render']).ComputeWorldBound(prim).ComputeAlignedRange()
    lo, hi = bb.GetMin(), bb.GetMax(); cx, cy = (lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2
    x = UsdGeom.Xformable(prim); x.ClearXformOpOrder(); op = x.AddTranslateOp(); op.Set(Gf.Vec3d(-cx, -cy, TOP - lo[2] + z_extra))
    return op, (-cx, -cy, TOP - lo[2]), [hi[i] - lo[i] for i in range(3)]


def capture(subframes=16, steps=3):
    for _ in range(steps): rep.orchestrator.step(rt_subframes=subframes)
    rgb = state['annots']['rgb'].get_data(); n = 0
    while (rgb is None or np.asarray(rgb).size == 0) and n < 10: rep.orchestrator.step(rt_subframes=subframes); rgb = state['annots']['rgb'].get_data(); n += 1
    return np.asarray(rgb)[..., :3], state['annots']['seg'].get_data()


def mask(seg, depth=4):
    ids = np.asarray(seg['data']).astype(np.int64); labels = {}; out = np.zeros(ids.shape, np.int16); order = []
    for k, path in seg['info']['idToLabels'].items():
        top = '/'.join(path.split('/')[:depth])
        if top not in order: order.append(top)
        out[ids == int(k)] = order.index(top) + 1
    return out, order


def run(j):
    i, s = j['inputs'], j['settings']
    if (i['kind'] == 'stage') != (MODE == 'stage'): raise ValueError(f"this worker renders {MODE} worlds, not {i['kind']}")
    out = Path(i['out_dir']); out.mkdir(parents=True, exist_ok=True); stem = i['name']; t0 = time.time()
    if i['kind'] == 'counter':
        stage = ensure('counter', 'counter', counter_world)
        _, _, size = place(stage, i['usd'])
        r = max(size); hgt = max(size[2], 0.05); cz = TOP + hgt / 2; d = float(i.get('framing', 2.6)) * r + 0.15; yaw = np.radians(float(i.get('yaw_deg', 8)))
        look(stage, (np.sin(yaw) * d, -np.cos(yaw) * d, cz + 0.35 * d), (0, 0, cz), 35.0, 36.0)
        lt = stage.GetPrimAtPath('/World/WindowLight'); x = UsdGeom.Xformable(lt); x.ClearXformOpOrder()
        el = np.radians(float(i.get('light_deg', 35))); x.AddTranslateOp().Set(Gf.Vec3d(-1.3, -0.6, 1.9 + 2.0 * (np.sin(el) - np.sin(np.radians(35)))))   # 35 deg reproduces the runs' light exactly; x.AddRotateXYZOp().Set(Gf.Vec3f(float(np.degrees(el)), -45, 0))
        focus = i.get('focus', 'whole_frame')
        if focus == 'background_only': UsdGeom.Imageable(stage.GetPrimAtPath('/World/Item')).MakeInvisible()
        rgb, seg = capture(s.get('rt_subframes', 16), steps=1); m, order = mask(seg, 3)   # one step of 16, as render_fit.py made every counter run
        if focus == 'background_only': UsdGeom.Imageable(stage.GetPrimAtPath('/World/Item')).MakeVisible()
        item = (m == order.index('/World/Item') + 1) if '/World/Item' in order else np.zeros(m.shape, bool)
        if focus == 'item_only':   # TRIBE averages over the frame, so focus is made in the stimulus: everything but the item is mid-grey
            rgb = np.where(item[..., None], rgb, 128).astype(np.uint8)
        if focus == 'zoom_to_item' and item.any():   # crop to the item with a margin, at the frame's aspect, then scale back up
            ys, xs = np.nonzero(item); cy, cx = (ys.min() + ys.max()) / 2, (xs.min() + xs.max()) / 2
            hh = max(ys.max() - ys.min(), (xs.max() - xs.min()) * 480 / 832) * 0.75 + 8; hw = hh * 832 / 480
            y0, x0 = int(max(0, cy - hh)), int(max(0, cx - hw)); y1, x1 = int(min(480, cy + hh)), int(min(832, cx + hw))
            rgb = np.asarray(Image.fromarray(rgb[y0:y1, x0:x1]).resize((832, 480), Image.LANCZOS))
    elif i['kind'] == 'stage':
        stage = ensure('stage', i['usda'], lambda: stage_world(i['usda']))
        for p in stage.Traverse():
            if str(p.GetPath()).startswith('/World/Objects/') and p.GetPath().pathElementCount == 3: UsdGeom.Imageable(p).MakeVisible()
        for h in i.get('hidden', []):
            p = stage.GetPrimAtPath(h)
            if p: UsdGeom.Imageable(p).MakeInvisible()
        eye, tgt, f = state['cams'][i.get('camera', 'corner_a')]; look(stage, eye, tgt, f, 20.955)
        rgb, seg = capture(s.get('rt_subframes', 24)); m, order = mask(seg, 4)
    elif i['kind'] == 'fall':
        stage = ensure('counter', 'counter', counter_world)
        op, base, size = place(stage, i['usd'])
        from pxr import UsdPhysics   # assets carry rigid bodies; kinematic, so only the scripted motion moves them, never gravity
        for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Item')):
            if p.HasAPI(UsdPhysics.RigidBodyAPI): UsdPhysics.RigidBodyAPI(p).CreateKinematicEnabledAttr(True)
        look(stage, (0.12, -1.15, TOP + 0.38), (0, 0, TOP + 0.2), 35.0, 36.0)
        lt = UsdGeom.Xformable(stage.GetPrimAtPath('/World/WindowLight')); lt.ClearXformOpOrder()   # every fall sets its own light, never the last job's
        lt.AddTranslateOp().Set(Gf.Vec3d(-1.3, -0.6, 1.9)); lt.AddRotateXYZOp().Set(Gf.Vec3f(35, -45, 0))
        frames = out / f'{stem}_frames'; frames.mkdir(exist_ok=True)
        drop, gap, e, g, fps = float(i.get('drop_m', 0.4)), float(i.get('gap_m', 0.08)), float(i.get('restitution', 0.35)), 9.81, 30
        tf = np.sqrt(2 * drop / g); zs = []
        for f in range(90):
            t = f / fps
            if t < 0.5: z = drop
            elif t - 0.5 < tf: z = drop - 0.5 * g * (t - 0.5) ** 2
            else:
                tt, v, z = t - 0.5 - tf, e * g * tf, 0.0
                while v > 0.05:
                    tb = 2 * v / g
                    if tt < tb: z = v * tt - 0.5 * g * tt * tt; break
                    tt -= tb; v *= e
            zs.append(max(z, 0.0))
        if i.get('outcome') == 'hovers_bouncing':   # the landing's motion, falling to a floor of air at the gap and bouncing there: only support is violated
            zs = [gap + z * (drop - gap) / drop for z in zs]
        if i.get('outcome') == 'hovers':
            stopped = False; out_z = []
            for k, z in enumerate(zs):
                stopped = stopped or (k > 0 and z <= gap and out_z[-1] > z); out_z.append(gap if stopped else z)
            zs = out_z
        for f, z in enumerate(zs):
            op.Set(Gf.Vec3d(base[0], base[1], base[2] + z)); rep.orchestrator.step(rt_subframes=4)
            Image.fromarray(np.asarray(state['annots']['rgb'].get_data())[..., :3]).save(frames / f'frame_{f:03d}.png')
        rgb = np.asarray(Image.open(frames / 'frame_045.png')); seg = state['annots']['seg'].get_data(); m, order = mask(seg, 3)
    else:
        raise ValueError(f"unknown kind {i['kind']}")
    if i.get('colour') == 'greyscale':   # Rec. 709 luminance, the same grey for every pixel's colour
        rgb = np.repeat((rgb[..., :3].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)).clip(0, 255).astype(np.uint8)[..., None], 3, axis=2)
        if i['kind'] == 'fall':
            for f in sorted((out / f'{stem}_frames').glob('frame_*.png')):
                a = np.asarray(Image.open(f))[..., :3].astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
                Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert('RGB').save(f)
    Image.fromarray(rgb).save(out / f'{stem}.png'); np.save(out / f'{stem}_objects.npy', m)
    res = {'rgb': str(out / f'{stem}.png'), 'objects_mask': str(out / f'{stem}_objects.npy'), 'mask_labels': order, 'render_s': round(time.time() - t0, 2)}
    if i['kind'] == 'fall': res['frames'] = str(out / f'{stem}_frames')
    return res


print(json.dumps({'ready': True}), flush=True)
for line in sys.stdin:
    j = json.loads(line)
    try: print(json.dumps({'job_id': j['job_id'], 'outputs': run(j)}, default=str), flush=True)
    except Exception as e: print(json.dumps({'job_id': j['job_id'], 'error': f'{type(e).__name__}: {e}'}), flush=True)
app.close()
