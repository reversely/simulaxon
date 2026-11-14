"""One EgoBody moment in Isaac Sim 6.2, acted out by one body with one motion. Shared by observer/render.py (command
line, four cells per moment) and backend/workers/isaac_body_worker.py (the lab's warm worker, one cell per job).

Import inside a running SimulationApp. load(rec, k, motion_npz) builds the moment's stage: EgoBody's scan of the room
as one mesh; the camera 0.5 m behind the partner's head at the decision point, looking 0.35 m above the wearer's pelvis
with 1.6 m of body in frame; a seat box where a seated wearer has no seat in the scan; the SMPL-X human as one mesh
whose points change per frame; the Unitree G1. render(body, motion, mp4) plays the 9 s (271 frames at 30 fps).
The G1 is posed without physics: every link's world transform from its joint angles by forward kinematics
(isaac/g1_fk.py, checked against Isaac's own link poses to the millimetre), upper body retargeted per frame by limb
direction (isaac/g1_retarget.py), pelvis at the wearer's pelvis turned with it, hips and knees bent 1.5 rad when
seated. With no physics world, one process can load moment after moment.
"""
from __future__ import annotations
import glob, json, os, pickle, subprocess, sys
import numpy as np
import omni.usd, omni.replicator.core as rep
from pxr import Usd, UsdGeom, UsdLux, UsdShade, Gf, Sdf, Vt
from scipy.spatial.transform import Rotation as Rot
from PIL import Image

FEAS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(FEAS, 'isaac')); sys.path.insert(0, os.path.join(FEAS, 'observer'))
from g1_retarget import Retarget
from g1_fk import G1FK
from scan_mesh import load_scan

WORK = os.path.expanduser('~/data/egobody/work')
G1_URL = 'https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.2/Isaac/Robots/Unitree/G1/g1.usd'
KIN = os.path.join(WORK, 'g1_kinematics.json'); PEL_REST = np.array([0.0031, -0.3514, 0.0120])
REVISION = 'body-scene 1: scan room, partner-eye camera 0.35 m / 1.6 m, G1 by FK, SMPL-X mesh with normals'


def _M(m): return Gf.Matrix4d(np.asarray(m, float).T.tolist())


class BodyScene:
    def __init__(self, app, W=960, H=540):
        self.app, self.W, self.H = app, W, H; self.ctx = omni.usd.get_context(); self.loaded = None; self.rp = self.ann = None
        self.RT = Retarget(KIN); self.FK = G1FK(KIN)
        kin = json.load(open(KIN))['joints']
        self.links = sorted({b for j in kin.values() for b in (j['body0'], j['body1']) if b}, key=lambda p: p.count('/'))

    # ---- one moment's stage
    def load(self, rec: str, k: int, motion_npz: str) -> dict:
        key = (rec, k, motion_npz)
        if self.loaded == key: return self.info
        if self.rp is not None: self.ann.detach(); self.rp.destroy(); self.rp = None
        self.Mo = Mo = np.load(motion_npz); W, H = self.W, self.H
        c = np.load(os.path.join(WORK, 'cams', rec + '.npz'), allow_pickle=True); ts = (c['ts'] - c['ts'][0]) / 1e7
        scene = str(c['scene']); V, F, COL, UV, FUV, TEX = load_scan(os.path.expanduser(f'~/data/egobody/scene_mesh/{scene}/{scene}.obj'))
        t = float(Mo['decision_t']); self.n_t = int(np.searchsorted(Mo['taus'], t, side='right')); self.N = len(Mo['taus'])
        self.ctx.new_stage(); st = self.st = self.ctx.get_stage()
        UsdGeom.SetStageUpAxis(st, UsdGeom.Tokens.y); UsdGeom.SetStageMetersPerUnit(st, 1.0); st.DefinePrim('/World', 'Xform')
        sm = UsdGeom.Mesh.Define(st, '/World/Scan')
        sm.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(V.astype(np.float32))); sm.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(F), 3, np.int32)))
        sm.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(F.reshape(-1).astype(np.int32))); sm.CreateDoubleSidedAttr(True)
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
        self.g1 = st.DefinePrim('/World/G1', 'Xform'); self.g1.GetReferences().AddReference(G1_URL)
        dome = UsdLux.DomeLight.Define(st, '/World/Dome'); dome.CreateIntensityAttr(900.0)
        dome.GetPrim().CreateAttribute('visibleInPrimaryRay', Sdf.ValueTypeNames.Bool).Set(False)
        self.hm = hm = UsdGeom.Mesh.Define(st, '/World/Human'); self.FH = FH = Mo['faces']
        hm.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(FH), 3, np.int32))); hm.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(FH.reshape(-1)))
        hm.CreateSubdivisionSchemeAttr('none'); hm.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(Mo['recorded_verts'][0])); hm.CreateNormalsAttr(); hm.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        hmat = UsdShade.Material.Define(st, '/World/SkinMat'); hs = UsdShade.Shader.Define(st, '/World/SkinMat/S'); hs.CreateIdAttr('UsdPreviewSurface')
        hs.CreateInput('diffuseColor', Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(0.62, 0.45, 0.37)); hs.CreateInput('roughness', Sdf.ValueTypeNames.Float).Set(0.6)
        hmat.CreateSurfaceOutput().ConnectToSource(hs.ConnectableAPI(), 'surface'); UsdShade.MaterialBindingAPI.Apply(hm.GetPrim()).Bind(hmat)
        cam = UsdGeom.Camera.Define(st, '/World/Film'); cam.CreateHorizontalApertureAttr(20.955); cam.CreateVerticalApertureAttr(20.955 * H / W)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.3, 100.0))
        for _ in range(20): self.app.update()
        # camera and placement at the decision point
        i = int(np.clip(np.searchsorted(ts, t), 0, len(ts) - 1)); head = c['c2s'][i][:3, 3]
        near = V[np.linalg.norm(V[:, [0, 2]] - head[[0, 2]], axis=1) < 1.0]; self.floor = floor = float(np.percentile(near[:, 1], 5) if len(near) > 50 else head[1] - 1.6)
        w_pel = Mo['recorded_pel'][self.n_t - 1]; self.seated = seated = bool(w_pel[1] - floor < 0.7)
        self.legs = {f'{sd}_{jn}': v for sd in ('left', 'right') for jn, v in (('hip_pitch_joint', -1.5), ('knee_joint', 1.5))} if seated else {}
        target = np.array([w_pel[0], w_pel[1] if seated else floor + 0.80, w_pel[2]]) + np.array([0, 0.35, 0])
        ph, off = self._partner_head(rec, c, i)
        back = ph - target; back[1] = 0; back /= np.linalg.norm(back); eye = ph + 0.5 * back
        fl = float(np.clip(np.linalg.norm(eye - target) * 20.955 * H / W / 1.6, 12, 60)); cam.CreateFocalLengthAttr(fl)
        zc = (eye - target) / np.linalg.norm(eye - target); xc = np.cross([0, 1, 0], zc); xc /= np.linalg.norm(xc); yc = np.cross(zc, xc)
        Mx = np.eye(4); Mx[:3, 0], Mx[:3, 1], Mx[:3, 2], Mx[:3, 3] = xc, yc, zc, eye
        UsdGeom.Xformable(cam).ClearXformOpOrder(); UsdGeom.Xformable(cam).AddTransformOp().Set(_M(Mx))
        seat = False
        if seated:
            below = V[(np.linalg.norm(V[:, [0, 2]] - w_pel[[0, 2]], axis=1) < 0.25) & (V[:, 1] > floor + 0.2) & (V[:, 1] < w_pel[1] - 0.05)]
            if len(below) < 30:
                b = UsdGeom.Cube.Define(st, '/World/Seat'); b.CreateSizeAttr(1.0); b.CreateDisplayColorAttr([(0.25, 0.25, 0.27)])
                top = w_pel[1] - 0.08; xf = UsdGeom.Xformable(b); xf.ClearXformOpOrder()
                xf.AddTranslateOp().Set(Gf.Vec3d(float(w_pel[0]), float((top + floor) / 2), float(w_pel[2]))); xf.AddScaleOp().Set(Gf.Vec3f(0.45, float(top - floor), 0.45)); seat = True
        self.rp = rep.create.render_product('/World/Film', (W, H)); self.ann = rep.AnnotatorRegistry.get_annotator('LdrColor'); self.ann.attach(self.rp)
        cache = UsdGeom.XformCache(); self.pelvis_rest = np.array(cache.GetLocalToWorldTransform(st.GetPrimAtPath('/World/G1/pelvis'))).T
        self.loaded = key
        self.info = dict(rec=rec, k=k, frames=self.N, decision_frame=self.n_t, seated=seated, seat_added=seat, floor=round(floor, 3), focal_mm=round(fl, 1),
                         camera=f"{'seated' if seated else 'standing'}; partner head {np.linalg.norm((ph - target)[[0, 2]]):.2f} m from the body (fit {off:+d} frames), camera 0.5 m behind it, {fl:.0f} mm",
                         frames_without_fit=int(Mo['frames_without_fit']))
        return self.info

    def _partner_head(self, rec, c, i):
        d = glob.glob(os.path.expanduser(f'~/data/egobody/smplx_interactee_*/{rec}/body_idx_*/results')); T_sk = c['T_scene_kin']
        for off in sorted(range(-15, 16), key=abs):
            j = int(np.clip(i + off, 0, len(c['frame']) - 1)); f = os.path.join(d[0], f"frame_{int(c['frame'][j]):05d}", '000.pkl')
            if os.path.exists(f):
                b = pickle.load(open(f, 'rb')); R = Rot.from_rotvec(b['global_orient'][0]).as_matrix(); pel = PEL_REST + b['transl'][0]
                return (T_sk @ np.r_[pel + R @ np.array([0, 0.6, 0]), 1])[:3], off
        raise RuntimeError(f'no partner fit near the decision point of {rec}')

    # ---- bodies
    def _show(self, body):
        (UsdGeom.Imageable(self.hm).MakeVisible if body == 'human' else UsdGeom.Imageable(self.hm).MakeInvisible)()
        (UsdGeom.Imageable(self.g1).MakeVisible if body == 'g1' else UsdGeom.Imageable(self.g1).MakeInvisible)()

    def _human(self, n, motion):
        v = self.Mo[f'{motion}_verts'][n]; FH = self.FH; fn = np.cross(v[FH[:, 1]] - v[FH[:, 0]], v[FH[:, 2]] - v[FH[:, 0]])
        nv = np.zeros_like(v); [np.add.at(nv, FH[:, j], fn) for j in range(3)]; nv /= np.linalg.norm(nv, axis=1, keepdims=True) + 1e-12
        self.hm.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(v)); self.hm.GetNormalsAttr().Set(Vt.Vec3fArray.FromNumpy(nv.astype(np.float32)))

    def _g1(self, q, n, motion):
        pel, fwd = self.Mo[f'{motion}_pel'][n], self.Mo[f'{motion}_fwd'][n]
        fh = np.array([fwd[0], 0, fwd[2]]) / np.linalg.norm(fwd[[0, 2]]); r_ = Rot.from_euler('y', np.arctan2(-fh[2], fh[0])) * Rot.from_euler('x', -90, degrees=True)
        P = np.eye(4); P[:3, :3] = r_.as_matrix(); P[:3, 3] = [pel[0], pel[1] if self.seated else self.floor + 0.80, pel[2]]
        UsdGeom.Xformable(self.g1).ClearXformOpOrder(); UsdGeom.Xformable(self.g1).AddTransformOp().Set(_M(P))
        B = P @ self.pelvis_rest; qq = {**q, **self.legs}; world = {'/World/G1': P}
        for path in self.links:
            name = path.split('/')[-1]; parent = path.rsplit('/', 1)[0]
            Mw = B if name == 'pelvis' else self.FK.link_world(name, qq, B)
            if parent not in world: world[parent] = world['/World/G1'] @ np.array(UsdGeom.Xformable(self.st.GetPrimAtPath(parent)).GetLocalTransformation()).T
            prim = self.st.GetPrimAtPath(path); xf = UsdGeom.Xformable(prim); xf.ClearXformOpOrder(); xf.AddTransformOp().Set(_M(np.linalg.inv(world[parent]) @ Mw))
            world[path] = Mw

    # ---- one cell
    def render(self, body: str, motion: str, out_mp4: str) -> dict:
        assert body in ('human', 'g1') and motion in ('recorded', 'robotic')
        self._show(body); qs, prev, worst = [], None, 0.0
        if body == 'g1':
            for n in range(self.N):
                q, e = self.RT.fit(self.Mo[f'{motion}_six'][n], prev); qs.append(q); prev = q; worst = max(worst, max(e.values()))
        frames = []
        for n in range(-4, self.N):   # four settling frames before the first kept one
            m = max(n, 0)
            self._g1(qs[m], m, motion) if body == 'g1' else self._human(m, motion)
            self.app.update(); rep.orchestrator.step()
            if n >= 0: frames.append(np.asarray(self.ann.get_data())[..., :3].astype(np.uint8))
        os.makedirs(os.path.dirname(out_mp4), exist_ok=True)
        ff = subprocess.Popen(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{self.W}x{self.H}', '-r', '30', '-i', '-',
                               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '18', out_mp4], stdin=subprocess.PIPE)
        for fr in frames: ff.stdin.write(np.ascontiguousarray(fr).tobytes())
        ff.stdin.close(); ff.wait()
        still = out_mp4[:-4] + '_decision.png'; Image.fromarray(frames[self.n_t - 1]).save(still)
        return {'clip': out_mp4, 'rgb': still, 'frames': len(frames), 'decision_frame': self.n_t, 'on_s': [1, 9],
                'retarget_worst_deg': round(worst, 2) if body == 'g1' else None, **{k: v for k, v in self.info.items() if k not in ('rec', 'k')}}
