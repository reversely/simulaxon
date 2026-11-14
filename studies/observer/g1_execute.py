"""Test 19: the Unitree G1 acts out mirroring responses where the wearer stood, in the room (Isaac Sim 6.2).

For each requested episode the G1 is the wearer: it replays the wearer's own motion, frame by frame from EgoBody's
SMPL-X fits at 30 fps, over the 8 s their view plays (the clip the models saw), base following their pelvis. At the
decision point it splits into three clips: the wearer's real next second (ground truth), and the real next second of
the moment retrieved without TRIBE, and with TRIBE paired (bench_seq.py; g1_select.py builds them at 30 fps from
EgoBody's fits, applied to this wearer's pose). Each clip then holds 1 s.
All three are identical up to the decision point. Clip time 0 = the start of the wearer's 8 s view clip.
The first version (2026-11-14) showed only a 1 s slide from the pose at the decision point to the end pose, so even the
ground truth hardly moved; the owner: "why is the ground truth never moving".

Room and camera: filmed from where the partner stood (their head at the decision point, from EgoBody's SMPL-X fit of
the interactee, 0.5 m behind it), looking at the robot, i.e. as the person being mirrored sees it. That view looks back
at the wearer's spot, which the wearer's own camera never saw, so the room is EgoBody's scan of it (a mesh coloured per
vertex), not the splat: from the robot's spot the splat showed fog or walls, and from its POV the arms stayed out of
view (2026-11-13). --room splat keeps the splat with the earlier camera rule.

Retargeting: by limb direction on the G1's own kinematics (g1_retarget.py): the waist fitted to the human torso, each
arm's shoulder and elbow fitted so its upper arm and forearm point where the human's do. Errors are logged per limb.
Placement: G1 rotated -90 deg about x (z-up to the scan's y-up), turned the way the wearer's pelvis faced, at the
wearer's pelvis (EgoBody's SMPL-X fit of the camera wearer). Standing: feet on the scanned floor. Seated (pelvis under
0.7 m above the floor): at the wearer's pelvis height, hips and knees bent 1.5 rad. Gravity off, base re-pinned every
step: only the arms and waist move.

usage (feasibility/isaac, source env.sh): .venv/bin/python g1_execute.py SPLAT_USDC CAMS.npz SCENE_OBJ SEQ.npz OUT_DIR REC K [K ...] [--room scan|splat]   (SEQ: g1_select.py)
  --demo  ignore PRED and wave, to check the retargeting and placement
"""
import argparse, json, os, sys
ap = argparse.ArgumentParser()
ap.add_argument('splat'); ap.add_argument('cams'); ap.add_argument('scene_obj'); ap.add_argument('pred'); ap.add_argument('out')
ap.add_argument('rec'); ap.add_argument('ks', nargs='+', type=int); ap.add_argument('--demo', action='store_true')
ap.add_argument('--res', default='960x540'); ap.add_argument('--room', choices=['scan', 'splat'], default='scan')
a = ap.parse_args()

from isaacsim import SimulationApp
app = SimulationApp({'headless': True, 'multi_gpu': False, 'extra_args': ['--enable', 'omni.rtx.spg', '--/renderer/multiGpu/enabled=false']})
import glob, pickle
import numpy as np
import omni.usd, omni.replicator.core as rep
from pxr import Usd, UsdGeom, Gf, Sdf, UsdPhysics
from scipy.spatial.transform import Rotation as Rot
from PIL import Image
from isaacsim.core.api import World
from isaacsim.core.prims import SingleArticulation

W, H = map(int, a.res.split('x'))
G1_URL = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/Isaac/Robots/Unitree/G1/g1.usd'
os.makedirs(a.out, exist_ok=True)


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from g1_retarget import Retarget   # by limb direction, on the G1's own kinematics (g1_kinematics.py dumps and checks them)
RT = Retarget(os.path.expanduser('~/data/egobody/work/g1_kinematics.json'))


# ---- placement from the wearer's camera at the decision point
c = np.load(a.cams); E = np.load(os.path.expanduser('~/data/egobody/work/episodes.npz'), allow_pickle=True)
P = None if a.demo else np.load(a.pred, allow_pickle=True)


def load_scan(path):
    """EgoBody's room scan OBJ, read directly (trimesh drops the per-vertex colours). Two kinds: older rooms give a
    colour per vertex ("v x y z r g b"); the 2022 rooms give texture coordinates and an 8k texture (map_Kd)."""
    vs, vts, fs = [], [], []
    for line in open(path):
        if line.startswith('v '): vs.append(line.split()[1:])
        elif line.startswith('vt '): vts.append(line.split()[1:3])
        elif line.startswith('f '): fs.append([w.split('/') for w in line.split()[1:4]])
    v = np.array(vs, float); f = np.array(fs)
    F_ = f[..., 0].astype(np.int64) - 1
    col = v[:, 3:6] if v.shape[1] >= 6 else None
    uv = np.array(vts, float) if vts else None
    Fuv = f[..., 1].astype(np.int64) - 1 if uv is not None and f.shape[-1] > 1 else None
    tex = None
    for line in open(path):
        if line.startswith('mtllib'):
            for m in open(os.path.join(os.path.dirname(path), line.split()[1])):
                if m.startswith('map_Kd'): tex = os.path.join(os.path.dirname(path), m.split()[1])
            break
    return v[:, :3], F_, col, uv, Fuv, tex


V, F_scan, COL, UV, FUV, TEX = load_scan(a.scene_obj)
print('scan:', len(V), 'vertices,', len(F_scan), 'faces,', 'texture ' + os.path.basename(TEX) if TEX else 'colour per vertex' if COL is not None else 'no colour', flush=True)
ts = (c['ts'] - c['ts'][0]) / 1e7
T_sk = c['T_scene_kin']
PELVIS = np.array([0.0031, -0.3514, 0.0120])  # SMPL-X neutral pelvis at rest (model frame); global_orient turns about it
U13 = [2, 5, 8, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]   # the 13 upper-body joints the models predict (episodes.py)
WEAR = glob.glob(os.path.expanduser(f'~/data/egobody/smplx_camera_wearer_*/{a.rec}/body_idx_*/results'))


def wearer_fit(j):
    """The wearer at camera frame j, from EgoBody's fit: the 13 joints as 6-D (as in episodes.py), pelvis in the scan,
    facing direction in the scan. None where the frame has no fit."""
    f = os.path.join(WEAR[0], f"frame_{int(c['frame'][j]):05d}", '000.pkl') if WEAR else ''
    if not os.path.exists(f): return None
    b = pickle.load(open(f, 'rb')); R = Rot.from_rotvec(b['global_orient'][0]).as_matrix()
    six = Rot.from_rotvec(b['body_pose'][0].reshape(21, 3)[U13]).as_matrix()[..., :2].reshape(13 * 6)
    pel = (T_sk @ np.r_[PELVIS + b['transl'][0], 1])[:3]; fwd = T_sk[:3, :3] @ R @ np.array([0, 0, 1.0])
    return six, pel, fwd


def body_at(kind, i):
    """A person's pelvis and head in the scan frame at camera frame i, from EgoBody's SMPL-X fit (kind: camera_wearer or
    interactee); the nearest frame with a fit within 15 frames. Head: 0.6 m above the pelvis along the body's up."""
    d = glob.glob(os.path.expanduser(f'~/data/egobody/smplx_{kind}_*/{a.rec}/body_idx_*/results'))
    for off in sorted(range(-15, 16), key=abs) if d else []:
        j = int(np.clip(i + off, 0, len(c['frame']) - 1)); f = os.path.join(d[0], f"frame_{int(c['frame'][j]):05d}", '000.pkl')
        if os.path.exists(f):
            b = pickle.load(open(f, 'rb')); R = Rot.from_rotvec(b['global_orient'][0]).as_matrix(); pel = PELVIS + b['transl'][0]
            to_s = lambda p: (T_sk @ np.r_[p, 1])[:3]
            fwd = T_sk[:3, :3] @ R @ np.array([0, 0, 1.0])   # the body's facing direction (SMPL-X +z) in the scan frame
            return to_s(pel), to_s(pel + R @ np.array([0, 0.6, 0])), off, fwd
    return None, None, None, None


stage_ctx = omni.usd.get_context(); stage_ctx.new_stage(); st = stage_ctx.get_stage()
UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.y); UsdGeom.SetStageMetersPerUnit(st, 1.0)
st.DefinePrim('/World', 'Xform')
if a.room == 'splat':
    st.DefinePrim('/World/Splat').GetReferences().AddReference(os.path.abspath(a.splat))
else:
    # the scan as one mesh: colour per vertex (sRGB in the OBJ, linear in USD) or its texture, through UsdPreviewSurface
    from pxr import UsdShade, Vt
    sm = UsdGeom.Mesh.Define(st, '/World/Scan')
    sm.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(V.astype(np.float32))); sm.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(F_scan), 3, np.int32)))
    sm.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(F_scan.reshape(-1).astype(np.int32))); sm.CreateDoubleSidedAttr(True)
    mat = UsdShade.Material.Define(st, '/World/ScanMat'); sh = UsdShade.Shader.Define(st, '/World/ScanMat/S'); sh.CreateIdAttr('UsdPreviewSurface')
    sh.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(1.0)
    if TEX and FUV is not None:
        pv = UsdGeom.PrimvarsAPI(sm).CreatePrimvar('st', Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying)
        pv.Set(Vt.Vec2fArray.FromNumpy(UV.astype(np.float32))); pv.SetIndices(Vt.IntArray.FromNumpy(FUV.reshape(-1).astype(np.int32)))
        rd = UsdShade.Shader.Define(st, '/World/ScanMat/UV'); rd.CreateIdAttr('UsdPrimvarReader_float2'); rd.CreateInput('varname', Sdf.ValueTypeNames.Token).Set('st')
        tx = UsdShade.Shader.Define(st, '/World/ScanMat/T'); tx.CreateIdAttr('UsdUVTexture'); tx.CreateInput('file', Sdf.ValueTypeNames.Asset).Set(TEX)
        tx.CreateInput('sourceColorSpace', Sdf.ValueTypeNames.Token).Set('sRGB'); tx.CreateInput('st', Sdf.ValueTypeNames.Float2).ConnectToSource(rd.ConnectableAPI(), 'result')
        sh.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).ConnectToSource(tx.ConnectableAPI(), 'rgb')
    else:
        col = COL if COL is not None else np.full((len(V), 3), 0.6); col = np.where(col <= 0.04045, col / 12.92, ((col + 0.055) / 1.055) ** 2.4)
        pv = UsdGeom.PrimvarsAPI(sm).CreatePrimvar('displayColor', Sdf.ValueTypeNames.Color3fArray, UsdGeom.Tokens.vertex); pv.Set(Vt.Vec3fArray.FromNumpy(col.astype(np.float32)))
        rd = UsdShade.Shader.Define(st, '/World/ScanMat/C'); rd.CreateIdAttr('UsdPrimvarReader_float3'); rd.CreateInput('varname', Sdf.ValueTypeNames.Token).Set('displayColor')
        sh.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).ConnectToSource(rd.ConnectableAPI(), 'result')
    mat.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(), 'surface'); UsdShade.MaterialBindingAPI.Apply(sm.GetPrim()).Bind(mat)
world = World(stage_units_in_meters=1.0); world.get_physics_context().set_gravity(0.0)
g1p = st.DefinePrim('/World/G1', 'Xform'); g1p.GetReferences().AddReference(G1_URL)
from pxr import UsdLux
dome = UsdLux.DomeLight.Define(st, '/World/Dome'); dome.CreateIntensityAttr(900.0)  # lights the G1's mesh; the splat carries its own radiance
if a.room == 'scan': dome.GetPrim().CreateAttribute('visibleInPrimaryRay', Sdf.ValueTypeNames.Bool).Set(False)  # where the scan has no wall, dark rather than a white sky
cam = UsdGeom.Camera.Define(st, '/World/Film'); cam.CreateFocalLengthAttr(14.0 if a.room == 'scan' else 18.0); cam.CreateHorizontalApertureAttr(20.955); cam.CreateVerticalApertureAttr(20.955 * H / W)
cam.CreateClippingRangeAttr(Gf.Vec2f(0.3, 100.0))
for _ in range(20): app.update()
rp = rep.create.render_product('/World/Film', (W, H)); ann = rep.AnnotatorRegistry.get_annotator('LdrColor'); ann.attach(rp)
robot = SingleArticulation('/World/G1', name='g1')
# Only a pose is shown, so the G1 must not collide with itself: with self-collision on, the retargeted arm poses pushed
# its parts into each other and the contacts threw it up to 5 m off its spot, out of the frame (2026-11-14). Nothing else
# in the scene collides (the scan has no collision, there is no ground plane).
from pxr import Usd
for pr in Usd.PrimRange(g1p):
    if pr.HasAPI(UsdPhysics.ArticulationRootAPI): pr.CreateAttribute('physxArticulation:enabledSelfCollisions', Sdf.ValueTypeNames.Bool).Set(False)
world.reset(); robot.initialize(); robot.set_enabled_self_collisions(False)
from isaacsim.core.utils.types import ArticulationAction
names = robot.dof_names
# joint angles are clipped to the G1's limits: a joint set past its limit is forced back by the solver, and with a
# floating base that threw the whole robot off its spot (1.2 and 5.7 m in one episode, 2026-11-14)
_dp = robot.dof_properties; LO, HI = np.asarray(_dp['lower'], float), np.asarray(_dp['upper'], float)
log = []; log_checks = []

for k in a.ks:
    i_ep = np.where((E['rec'] == a.rec) & (E['k'] == k))[0][0]; t = float(E['t'][i_ep])
    i = int(np.clip(np.searchsorted(ts, t), 0, len(ts) - 1)); c2s = c['c2s'][i]
    head = c2s[:3, 3]; fw = c2s[:3, 2]; fw_h = np.array([fw[0], 0, fw[2]]); fw_h /= np.linalg.norm(fw_h)
    near = V[np.linalg.norm(V[:, [0, 2]] - head[[0, 2]], axis=1) < 1.0]
    floor = np.percentile(near[:, 1], 5) if len(near) > 50 else head[1] - 1.6
    # where the wearer's body was: seated when the pelvis is under 0.7 m above the floor (then the G1 sits at that height,
    # hips and knees bent; standing, it stood in the couch the wearer sat on, 2026-11-14)
    w_pel, _, _, w_fwd = body_at('camera_wearer', i)
    # the G1 turns with the wearer's pelvis: the retargeted joints (SMPL-X body_pose) are relative to it, not to the head
    face = np.array([w_fwd[0], 0, w_fwd[2]]) / np.linalg.norm(w_fwd[[0, 2]]) if w_fwd is not None else fw_h
    head_off = np.degrees(np.arctan2(np.cross(face, fw_h)[1], face @ fw_h))
    phi = np.arctan2(-face[2], face[0])
    seated = w_pel is not None and w_pel[1] - floor < 0.7
    legs = {f'{sd}_{jn}': v for sd in ('left', 'right') for jn, v in (('hip_pitch_joint', -1.5), ('knee_joint', 1.5))} if seated else {}
    rot = Rot.from_euler('y', phi) * Rot.from_euler('x', -90, degrees=True)  # G1 +x (forward) along the wearer's pelvis facing; check: G1_MARKER=1 puts a ball 0.6 m along +x
    xz = w_pel if w_pel is not None else head
    base_pos = np.array([xz[0], (w_pel[1] if seated else floor + 0.80), xz[2]]); base_q = rot.as_quat()[[3, 0, 1, 2]]
    target = base_pos + np.array([0, 0.15, 0])   # the upper body, the only part that moves: from the hands in the lap to the head
    _, ph, off, _ = body_at('interactee', i) if a.room == 'scan' else (None, None, None, None)
    if ph is not None:
        back = ph - target; back[1] = 0; back /= np.linalg.norm(back)
        eye = ph + 0.5 * back; look = target; cam_note = ('seated' if seated else 'standing') + f' G1 facing the wearer\'s pelvis (head turned {head_off:+.0f} deg from it); partner head {np.linalg.norm((ph - target)[[0, 2]]):.2f} m from the robot (fit {off:+d} frames from the decision point), 0.5 m behind it'
    else:
        # splat: one of the wearer's own camera poses (a trained view) 1.2 to 3.5 m from the robot's spot looking towards
        # it; otherwise the robot's POV
        best, bi = None, None
        for j in range(0, len(c['c2s']), 3):
            p_ = c['c2s'][j][:3, 3]; f_ = c['c2s'][j][:3, 2]; v = target - p_; dist = np.linalg.norm(v[[0, 2]])
            if 1.2 <= dist <= 3.5:
                ang = np.degrees(np.arccos(np.clip(f_ @ v / np.linalg.norm(v), -1, 1)))
                if ang < 20 and (best is None or ang < best): best, bi = ang, j
        if bi is not None:
            eye = c['c2s'][bi][:3, 3].copy(); look = target; cam_note = f'wearer pose {bi} ({best:.0f} deg off the robot)'
        else:
            eye = head.copy(); down = np.radians(30); look = eye + fw_h * np.cos(down) - np.array([0, 1, 0]) * np.sin(down); cam_note = 'robot POV'
    if a.room == 'scan':  # frame 1.1 m tall at the robot, whatever the partner's distance: the upper body fills it, so the
        # arms read at the app's slice size (1.4 to 1.8 m left the G1 about 100 px tall in a 300 px slice, 2026-11-14; a
        # fixed 14 mm before that left a G1 2.7 m away a fifth of the frame)
        fl = float(np.clip(np.linalg.norm(eye - look) * 20.955 * H / W / 1.1, 12, 60)); cam.GetFocalLengthAttr().Set(fl); cam_note += f', {fl:.0f} mm'
    print('camera:', cam_note, flush=True)
    zc = (eye - look) / np.linalg.norm(eye - look); xc = np.cross([0, 1, 0], zc); xc /= np.linalg.norm(xc); yc = np.cross(zc, xc)
    M = np.eye(4); M[:3, 0], M[:3, 1], M[:3, 2], M[:3, 3] = xc, yc, zc, eye
    UsdGeom.Xformable(cam).ClearXformOpOrder(); UsdGeom.Xformable(cam).AddTransformOp().Set(Gf.Matrix4d(M.T.tolist()))
    if os.environ.get('G1_MARKER'):  # orientation check: a red ball 0.6 m along the G1's own +x
        mk = UsdGeom.Sphere.Define(st, '/World/Marker'); mk.CreateRadiusAttr(0.08); mk.CreateDisplayColorAttr([(1, 0, 0)])
        UsdGeom.Xformable(mk).ClearXformOpOrder(); UsdGeom.Xformable(mk).AddTranslateOp().Set(Gf.Vec3d(*(base_pos + rot.apply([0.6, 0, 0]) + [0, 0.3, 0])))
    def pose_robot(q, pos, quat):
        robot.set_world_pose(position=pos, orientation=quat)
        qa = robot.get_joint_positions()
        for n, v in {**q, **legs}.items():
            if n in names: qa[names.index(n)] = v
        n_clip = int(np.sum((qa < LO) | (qa > HI))); qa = np.clip(qa, LO, HI)
        robot.set_joint_positions(qa); robot.set_joint_velocities(np.zeros_like(qa))
        robot.apply_action(ArticulationAction(joint_positions=qa))   # drives hold the pose instead of pulling back to zero
        world.step(render=True); rep.orchestrator.step()
        return qa, n_clip

    def grab(): return np.asarray(ann.get_data())[..., :3].astype(np.uint8)

    def check(name, qa, n_clip, pos):
        got_p, _ = robot.get_world_pose(); jerr = float(np.max(np.abs(robot.get_joint_positions() - qa)))
        drift = float(np.linalg.norm(np.asarray(got_p) - pos))
        print('pose check', name, f'base off by {drift:.3f} m, largest joint error {jerr:.3f} rad, {n_clip} joints clipped to limits', flush=True)
        log_checks.append(dict(arm=name, base_drift_m=round(drift, 4), joint_err_rad=round(jerr, 4), joints_clipped=n_clip))

    def write(name, frames, e1, extra):
        out = os.path.join(a.out, f'{a.rec}_{k:03d}_{name}.mp4')
        import subprocess
        h_, w_ = frames[0].shape[:2]
        ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{w_}x{h_}', '-r', '30', '-i', '-',
                               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', out], stdin=subprocess.PIPE)
        for fr_ in frames: ff.stdin.write(np.ascontiguousarray(fr_).tobytes())
        ff.stdin.close(); ff.wait()
        Image.fromarray(frames[-1]).save(out[:-4] + '_end.png')
        log.append(dict(rec=a.rec, k=k, arm=name, video=out, check=log_checks[-1], retarget_err_deg=None if e1 is None else {kk: round(vv, 2) for kk, vv in e1.items()},
                        base=base_pos.round(3).tolist(), floor=round(float(floor), 3), seated=bool(seated), camera=cam_note, **extra))
        print('wrote', out, len(frames), 'frames', flush=True)

    if a.demo:
        frames = []
        for f in range(31):
            u = f / 30; q = {n: 0.0 for n in names}; q['left_shoulder_roll_joint'] = 1.2 * u; q['left_elbow_joint'] = 1.2 * np.sin(6 * u) ** 2
            q['right_shoulder_pitch_joint'] = -1.0 * u; q['waist_yaw_joint'] = 0.3 * np.sin(3 * u)
            qa, nc = pose_robot(q, base_pos, base_q); frames.append(grab())
        check('demo', qa, nc, base_pos); write('demo', frames, None, {}); continue

    # where the scan has no seat under a seated wearer (a chair brought in after the scan), a plain box stands in for it
    seat = None
    if seated:
        below = V[(np.linalg.norm(V[:, [0, 2]] - base_pos[[0, 2]], axis=1) < 0.25) & (V[:, 1] > floor + 0.2) & (V[:, 1] < base_pos[1] - 0.05)]
        if len(below) < 30:
            seat = UsdGeom.Cube.Define(st, f'/World/Seat_{k}'); seat.CreateSizeAttr(1.0); seat.CreateDisplayColorAttr([(0.25, 0.25, 0.27)])
            top = base_pos[1] - 0.08; xf = UsdGeom.Xformable(seat); xf.ClearXformOpOrder()
            xf.AddTranslateOp().Set(Gf.Vec3d(float(base_pos[0]), float((top + floor) / 2), float(base_pos[2])))
            xf.AddScaleOp().Set(Gf.Vec3f(0.45, float(top - floor), 0.45))
            print(f'seat: the scan has no seat under the seated wearer ({len(below)} scan points), a box stands in for it', flush=True)
    # the wearer's motion: one fit per output frame at 30 fps, the nearest camera frame within 50 ms, else the last fit held
    taus = t - 8.0 + np.arange(30 * 9 + 1) / 30
    fits, n_held, last = [], 0, None
    for tau in taus:
        j = int(np.argmin(np.abs(ts - tau))); ft = wearer_fit(j) if abs(ts[j] - tau) < 0.05 else None
        if ft is None: n_held += 1; ft = last
        fits.append(ft); last = ft if ft is not None else last
    first = next(f_ for f_ in fits if f_ is not None); fits = [f_ if f_ is not None else first for f_ in fits]
    qs, errs, prev = [], [], None
    for six, _, _ in fits:
        q, e = RT.fit(six, prev); qs.append(q); errs.append(e); prev = q
    def base_of(n):
        _, pel, fwd = fits[n]; fh = np.array([fwd[0], 0, fwd[2]]) / np.linalg.norm(fwd[[0, 2]]); ph_ = np.arctan2(-fh[2], fh[0])
        r_ = Rot.from_euler('y', ph_) * Rot.from_euler('x', -90, degrees=True)
        return np.array([pel[0], pel[1] if seated else floor + 0.80, pel[2]]), r_.as_quat()[[3, 0, 1, 2]]
    n_t = int(np.searchsorted(taus, t, side='right'))   # frames up to the decision point
    worst = max(max(e.values()) for e in errs)
    print(f'wearer motion: {len(taus)} frames from {taus[0]:.2f} to {taus[-1]:.2f} s, {n_held} without a fit (held), worst retarget error {worst:.1f} deg', flush=True)
    for _ in range(4): pose_robot(qs[0], *base_of(0))   # let the renderer settle on the new camera and pose before the first kept frame
    hist = []
    for n in range(n_t):
        pos, quat = base_of(n); qa, nc = pose_robot(qs[n], pos, quat); hist.append(grab())
    pos_t, quat_t = base_of(n_t - 1); q_t = qs[n_t - 1]
    extra = dict(frames=len(taus) + 30, decision_frame=n_t, frames_without_fit=n_held, worst_motion_retarget_deg=round(worst, 2),
                 seat_added=seat is not None, clip_start_s=round(float(taus[0]), 3), decision_s=round(float(t), 3))
    # the ground truth: the wearer's real next second
    fr_h = list(hist)
    for n in range(n_t, len(taus)):
        pos, quat = base_of(n); qa, nc = pose_robot(qs[n], pos, quat); fr_h.append(grab())
    check('human', qa, nc, pos); write('human', fr_h + [fr_h[-1]] * 30, errs[-1], extra)
    # the predictions: the real next second of the moment each arm retrieved (g1_select.py, bench_seq.py), 30 fps,
    # applied to this wearer's pose at the decision point; upper body only, as predicted, so the base stays put
    for name in ('no_tribe', 'tribe_paired'):
        seq = P[f'{a.rec}#{k}|{name}']; fr_p = list(hist); q, e1, worst_p = q_t, None, 0.0
        for n in range(n_t, len(taus)):
            q, e1 = RT.fit(seq[int(np.clip(round((taus[n] - t) * 30), 0, len(seq) - 1))], q); worst_p = max(worst_p, max(e1.values()))
            qa, nc = pose_robot(q, pos_t, quat_t); fr_p.append(grab())
        print('retarget', name, f'worst over its motion {worst_p:.1f} deg; end pose:', ', '.join(f'{kk} {vv:.1f}' for kk, vv in e1.items()), flush=True)
        check(name, qa, nc, pos_t); write(name, fr_p + [fr_p[-1]] * 30, e1, {**extra, 'worst_prediction_retarget_deg': round(worst_p, 2)})
    if seat is not None: st.RemovePrim(seat.GetPath())
json.dump(log, open(os.path.join(a.out, f'g1_{a.rec}.json'), 'w'), indent=1)
app.close()
