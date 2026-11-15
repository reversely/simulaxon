/** The brain drawn in the browser (#27): fsaverage5 from /api/brain/mesh, coloured per vertex from TRIBE v2's
 * predictions, with a head outline for orientation, and a player that runs a clip and the brain on one clock.
 * Plain WebGL2, no library. Colours follow the server's maps (lab/maps.py): a single map is normalised at the 1st and
 * 99th percentiles and coloured above 0.6 of that range, fading in over 0.2, as TRIBE's plotter draws it; a contrast is
 * scaled by its 99th percentile of absolute values and fades to the cortex near zero. Ramps are the legend's (.ramp). */
import { useEffect, useRef, useState, type ReactNode } from 'react'

type Mesh = { n: number; pial: Float32Array; infl: Float32Array; nPial: Float32Array; nInfl: Float32Array; sulc: Float32Array; faces: Uint16Array; radius: number }
export type Preds = { rows: number; n: number; data: Float32Array; lo: number; hi: number }

let meshP: Promise<Mesh> | null = null
export function loadMesh(): Promise<Mesh> {
  meshP ??= fetch('/api/brain/mesh').then(r => { if (!r.ok) throw new Error(`brain mesh: ${r.status}`); return r.arrayBuffer() }).then(parseMesh)
  meshP.catch(() => { meshP = null })
  return meshP
}

function normals(pos: Float32Array, faces: Uint16Array): Float32Array {
  const out = new Float32Array(pos.length)
  for (let f = 0; f < faces.length; f += 3) {
    const a = faces[f] * 3, b = faces[f + 1] * 3, c = faces[f + 2] * 3
    const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2]
    const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2]
    const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx
    for (const i of [a, b, c]) { out[i] += nx; out[i + 1] += ny; out[i + 2] += nz }
  }
  for (let i = 0; i < out.length; i += 3) { const l = Math.hypot(out[i], out[i + 1], out[i + 2]) || 1; out[i] /= l; out[i + 1] /= l; out[i + 2] /= l }
  return out
}

function parseMesh(buf: ArrayBuffer): Mesh {
  const dv = new DataView(buf); const hl = dv.getUint32(0, true)
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl))); const base = 4 + hl
  const arr = (k: string) => { const a = head.arrays[k]; const len = a.shape.reduce((x: number, y: number) => x * y, 1)
    return a.dtype === 'i2' ? new Int16Array(buf, base + a.offset, len) : a.dtype === 'u2' ? new Uint16Array(buf, base + a.offset, len) : new Uint8Array(buf, base + a.offset, len) }
  const mm = (a: Int16Array) => Float32Array.from(a, v => v / head.scale)
  const pial = mm(arr('pial') as Int16Array), infl = mm(arr('infl') as Int16Array), faces = new Uint16Array(arr('faces') as Uint16Array)
  let radius = 0
  for (let i = 0; i < pial.length; i += 3) radius = Math.max(radius, Math.hypot(pial[i], pial[i + 1], pial[i + 2]), Math.hypot(infl[i], infl[i + 1], infl[i + 2]))
  return { n: head.n, pial, infl, nPial: normals(pial, faces), nInfl: normals(infl, faces), sulc: Float32Array.from(arr('sulc') as Uint8Array, v => v / 255), faces, radius }
}

let F16: Float32Array | null = null
function f16(): Float32Array {
  if (F16) return F16
  F16 = new Float32Array(65536)
  for (let h = 0; h < 65536; h++) { const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, f = h & 1023
    F16[h] = e === 0 ? s * 2 ** -14 * (f / 1024) : e === 31 ? (f ? NaN : s * Infinity) : s * 2 ** (e - 15) * (1 + f / 1024) }
  return F16
}

/** A .npy file of float16, float32 or float64 values in C order. */
export function parseNpy(buf: ArrayBuffer): { shape: number[]; data: Float32Array } {
  const u8 = new Uint8Array(buf); const dv = new DataView(buf)
  const major = u8[6]; const hl = major === 1 ? dv.getUint16(8, true) : dv.getUint32(8, true); const off = major === 1 ? 10 : 12
  const header = new TextDecoder().decode(u8.subarray(off, off + hl))
  const descr = /'descr':\s*'([^']+)'/.exec(header)?.[1]; const shape = (/'shape':\s*\(([^)]*)\)/.exec(header)?.[1] ?? '').split(',').map(x => x.trim()).filter(Boolean).map(Number)
  if (/'fortran_order':\s*True/.test(header)) throw new Error('predictions in Fortran order')
  const n = shape.reduce((a, b) => a * b, 1); const start = off + hl
  if (descr === '<f2') { const t = f16(); const h = new Uint16Array(buf.slice(start, start + 2 * n)); const out = new Float32Array(n); for (let i = 0; i < n; i++) out[i] = t[h[i]]; return { shape, data: out } }
  if (descr === '<f4') return { shape, data: new Float32Array(buf.slice(start, start + 4 * n)) }
  if (descr === '<f8') return { shape, data: Float32Array.from(new Float64Array(buf.slice(start, start + 8 * n))) }
  throw new Error(`predictions of type ${descr}`)
}

function percentile(xs: Float32Array, q: number[]): number[] {
  const step = Math.max(1, Math.floor(xs.length / 200000)); const s = new Float32Array(Math.ceil(xs.length / step)); let k = 0
  for (let i = 0; i < xs.length; i += step) if (Number.isFinite(xs[i])) s[k++] = xs[i]
  const v = s.subarray(0, k).sort(); return q.map(p => v[Math.min(k - 1, Math.max(0, Math.round(p / 100 * (k - 1))))] ?? 0)
}

const predsCache = new Map<string, Promise<Preds>>()
/** A .npy of predictions (seconds by vertices), cached by URL: a sample's (/api/brain/preds/<id>) or a recording's tribe stream. */
export function loadPreds(url: string): Promise<Preds> {
  let p = predsCache.get(url)
  if (!p) {
    p = fetch(url).then(r => { if (!r.ok) throw new Error(`predictions: ${r.status}`); return r.arrayBuffer() }).then(b => {
      const { shape, data } = parseNpy(b); const [lo, hi] = percentile(data, [1, 99])
      return { rows: shape.length > 1 ? shape[0] : 1, n: shape[shape.length - 1], data, lo, hi }
    })
    p.catch(() => predsCache.delete(url)); predsCache.set(url, p)
  }
  return p
}
export const samplePreds = (sampleId: string) => `/api/brain/preds/${encodeURIComponent(sampleId)}`

const RAMPS: Record<'single' | 'signed', [number, string][]> = {
  single: [[0, '#2a2b2e'], [0.45, '#b3261e'], [0.75, '#ff8c1a'], [1, '#fff2a8']],
  signed: [[0, '#4fd0ff'], [0.3, '#1a6bb0'], [0.5, '#2a2b2e'], [0.7, '#b3261e'], [1, '#ffd23f']],
}
function rampPixels(stops: [number, string][]): Uint8Array {
  const rgb = (h: string) => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)); const px = new Uint8Array(256 * 4)
  for (let i = 0; i < 256; i++) { const x = i / 255; let j = 0; while (j < stops.length - 2 && x > stops[j + 1][0]) j++
    const [x0, c0] = stops[j], [x1, c1] = stops[j + 1]; const t = Math.min(1, Math.max(0, (x - x0) / (x1 - x0))); const a = rgb(c0), b = rgb(c1)
    for (let c = 0; c < 3; c++) px[i * 4 + c] = Math.round(a[c] + (b[c] - a[c]) * t); px[i * 4 + 3] = 255 }
  return px
}

const VS = `#version 300 es
in vec3 aPial; in vec3 aInfl; in vec3 aNPial; in vec3 aNInfl; in float aSulc; in float aVal;
uniform mat4 uProj; uniform mat4 uView; uniform float uMix;
out vec3 vN; out float vSulc; out float vVal;
void main() { vec3 p = mix(aPial, aInfl, uMix); vN = mat3(uView) * normalize(mix(aNPial, aNInfl, uMix)); vSulc = aSulc; vVal = aVal; gl_Position = uProj * uView * vec4(p, 1.0); }`
const FS = `#version 300 es
precision highp float;
in vec3 vN; in float vSulc; in float vVal; uniform sampler2D uRamp; uniform int uSigned; uniform float uHas; out vec4 o;
void main() {
  vec3 n = normalize(vN); if (!gl_FrontFacing) n = -n;
  float light = 0.38 + 0.62 * max(dot(n, normalize(vec3(0.25, 0.35, 1.0))), 0.0);
  vec3 base = vec3(mix(0.74, 0.36, vSulc));
  float c; float a;
  if (uSigned == 1) { c = 0.5 + 0.5 * clamp(vVal, -1.0, 1.0); a = clamp(abs(vVal) / 0.35 - 0.15, 0.0, 1.0); }
  else { c = clamp((vVal - 0.6) / 0.4, 0.0, 1.0); a = clamp(c / 0.2, 0.0, 1.0); }
  vec3 col = mix(base, texture(uRamp, vec2(c, 0.5)).rgb, a * uHas);
  o = vec4(col * light, 1.0);
}`
const HVS = `#version 300 es
in vec3 aPos; in vec3 aNorm; uniform mat4 uProj; uniform mat4 uView; out vec3 vN; out vec3 vP;
void main() { vec4 p = uView * vec4(aPos, 1.0); vN = mat3(uView) * aNorm; vP = p.xyz; gl_Position = uProj * p; }`
const HFS = `#version 300 es
precision highp float;
in vec3 vN; in vec3 vP; out vec4 o;
void main() { float r = 1.0 - abs(dot(normalize(vN), normalize(-vP))); o = vec4(0.73, 0.70, 0.65, 0.5 * pow(r, 3.0)); }`

/** A head of our own around the brain, so its orientation reads at a glance: an ellipsoid with a nose and ears. */
function headGeometry(bx: number, by: number, bz: number): { pos: Float32Array; norm: Float32Array; idx: Uint16Array } {
  const LAT = 48, LON = 72; const pos: number[] = []; const idx: number[] = []
  const bumps: [number[], number, number][] = [[[0, 0.93, -0.36], 0.15, 0.17], [[1, -0.05, -0.12], 0.07, 0.14], [[-1, -0.05, -0.12], 0.07, 0.14]]
  for (let i = 0; i <= LAT; i++) { const th = Math.PI * i / LAT
    for (let j = 0; j <= LON; j++) { const ph = 2 * Math.PI * j / LON
      const d = [Math.sin(th) * Math.cos(ph), Math.sin(th) * Math.sin(ph), Math.cos(th)]; let s = 1
      for (const [b, h, w] of bumps) { const l = Math.hypot(...b); const ang = Math.acos(Math.min(1, (d[0] * b[0] + d[1] * b[1] + d[2] * b[2]) / l)); s += h * Math.exp(-((ang / w) ** 2)) }
      pos.push(d[0] * bx * 1.3 * s, d[1] * by * 1.17 * s, d[2] * bz * 1.32 * s - bz * 0.16) } }
  for (let i = 0; i < LAT; i++) for (let j = 0; j < LON; j++) { const a = i * (LON + 1) + j, b = a + LON + 1; idx.push(a, b, a + 1, a + 1, b, b + 1) }
  const P = new Float32Array(pos), I = new Uint16Array(idx); return { pos: P, norm: normals(P, I), idx: I }
}

type M4 = Float32Array
function persp(fovy: number, aspect: number, near: number, far: number): M4 { const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far)
  return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]) }
function lookAt(e: number[], up: number[]): M4 {
  const z = (() => { const l = Math.hypot(...e); return e.map(v => v / l) })()
  const xr = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]]; const xl = Math.hypot(...xr) || 1; const x = xr.map(v => v / xl)
  const y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
  const d = (a: number[]) => -(a[0] * e[0] + a[1] * e[1] + a[2] * e[2])
  return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, d(x), d(y), d(z), 1])
}

export const SURFACES: [string, number][] = [['Pial', 0], ['Half inflated', 0.5], ['Inflated', 1]]
export const ANGLES: Record<string, [number, number]> = { Left: [180, 8], Right: [0, 8], Underside: [90, -89], Back: [-90, 8] }   // the app's view names (VIEW_NAMES)

/** The WebGL part: one canvas, drawn on demand. */
class BrainGL {
  gl: WebGL2RenderingContext; mesh: Mesh; val: WebGLBuffer; prog: WebGLProgram; hprog: WebGLProgram; vao: WebGLVertexArrayObject; hvao: WebGLVertexArrayObject
  hcount: number; ramps: Record<string, WebGLTexture>; values = new Float32Array(0); signed = false; has = 0
  mix = 0.5; yaw = 150; pitch = 18; lastDrawMs = 0
  constructor(public canvas: HTMLCanvasElement, mesh: Mesh) {
    const gl = canvas.getContext('webgl2', { antialias: true, alpha: true, premultipliedAlpha: false }); if (!gl) throw new Error('WebGL2 is off in this browser')
    this.gl = gl; this.mesh = mesh; this.values = new Float32Array(mesh.n)
    const sh = (t: number, s: string) => { const x = gl.createShader(t)!; gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x) ?? 'shader'); return x }
    const prog = (v: string, f: string) => { const p = gl.createProgram()!; gl.attachShader(p, sh(gl.VERTEX_SHADER, v)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, f)); gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link'); return p }
    this.prog = prog(VS, FS); this.hprog = prog(HVS, HFS)
    const attr = (p: WebGLProgram, name: string, data: Float32Array, size: number, usage: number = gl.STATIC_DRAW) => { const b = gl.createBuffer()!; gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, usage)
      const loc = gl.getAttribLocation(p, name); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0); return b }
    this.vao = gl.createVertexArray()!; gl.bindVertexArray(this.vao)
    attr(this.prog, 'aPial', mesh.pial, 3); attr(this.prog, 'aInfl', mesh.infl, 3); attr(this.prog, 'aNPial', mesh.nPial, 3); attr(this.prog, 'aNInfl', mesh.nInfl, 3); attr(this.prog, 'aSulc', mesh.sulc, 1)
    this.val = attr(this.prog, 'aVal', this.values, 1, gl.DYNAMIC_DRAW)
    const ib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.faces, gl.STATIC_DRAW)
    let bx = 0, by = 0, bz = 0; const half = mesh.pial.map((v, i) => (v + mesh.infl[i]) / 2)
    for (let i = 0; i < half.length; i += 3) { bx = Math.max(bx, Math.abs(half[i])); by = Math.max(by, Math.abs(half[i + 1])); bz = Math.max(bz, Math.abs(half[i + 2])) }
    const h = headGeometry(bx, by, bz); this.hcount = h.idx.length
    this.hvao = gl.createVertexArray()!; gl.bindVertexArray(this.hvao); attr(this.hprog, 'aPos', h.pos, 3); attr(this.hprog, 'aNorm', h.norm, 3)
    const hib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, hib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, h.idx, gl.STATIC_DRAW); gl.bindVertexArray(null)
    this.ramps = Object.fromEntries((['single', 'signed'] as const).map(k => { const t = gl.createTexture()!; gl.bindTexture(gl.TEXTURE_2D, t)
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, rampPixels(RAMPS[k])); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE); return [k, t] }))
  }
  setValues(v: Float32Array | null, signed: boolean) {
    this.signed = signed; this.has = v ? 1 : 0; if (!v) return
    const gl = this.gl; gl.bindBuffer(gl.ARRAY_BUFFER, this.val); gl.bufferSubData(gl.ARRAY_BUFFER, 0, v)
  }
  draw() {
    const t0 = performance.now(); const gl = this.gl; const c = this.canvas; const dpr = Math.min(2, window.devicePixelRatio || 1)
    const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr)); if (c.width !== w || c.height !== h) { c.width = w; c.height = h }
    gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST)
    const R = this.mesh.radius * 1.12; const fov = 0.5; const dist = R / Math.sin(fov / 2) * (w < h ? h / w : 1) * 0.86
    const y = this.yaw * Math.PI / 180, p = this.pitch * Math.PI / 180
    const eye = [dist * Math.cos(p) * Math.cos(y), dist * Math.cos(p) * Math.sin(y), dist * Math.sin(p)]
    const view = lookAt(eye, Math.abs(this.pitch) > 80 ? [Math.cos(y + Math.PI) * Math.sign(-this.pitch), Math.sin(y + Math.PI) * Math.sign(-this.pitch), 0] : [0, 0, 1])
    const proj = persp(fov, w / h, Math.max(1, dist - R * 1.6), dist + R * 1.6)
    gl.useProgram(this.prog); gl.bindVertexArray(this.vao)
    gl.uniformMatrix4fv(gl.getUniformLocation(this.prog, 'uProj'), false, proj); gl.uniformMatrix4fv(gl.getUniformLocation(this.prog, 'uView'), false, view)
    gl.uniform1f(gl.getUniformLocation(this.prog, 'uMix'), this.mix); gl.uniform1i(gl.getUniformLocation(this.prog, 'uSigned'), this.signed ? 1 : 0); gl.uniform1f(gl.getUniformLocation(this.prog, 'uHas'), this.has)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.ramps[this.signed ? 'signed' : 'single']); gl.uniform1i(gl.getUniformLocation(this.prog, 'uRamp'), 0)
    gl.disable(gl.BLEND); gl.depthMask(true); gl.drawElements(gl.TRIANGLES, this.mesh.faces.length, gl.UNSIGNED_SHORT, 0)
    gl.useProgram(this.hprog); gl.bindVertexArray(this.hvao)
    gl.uniformMatrix4fv(gl.getUniformLocation(this.hprog, 'uProj'), false, proj); gl.uniformMatrix4fv(gl.getUniformLocation(this.hprog, 'uView'), false, view)
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.depthMask(false); gl.drawElements(gl.TRIANGLES, this.hcount, gl.UNSIGNED_SHORT, 0); gl.depthMask(true)
    gl.bindVertexArray(null); this.lastDrawMs = performance.now() - t0; c.dataset.drawMs = this.lastDrawMs.toFixed(2)
  }
  dispose() { this.gl.getExtension('WEBGL_lose_context')?.loseContext() }
}

/** Values of one moment: rows linearly interpolated at t seconds, scaled for the shader. */
function frameAt(p: Preds, t: number, out: Float32Array): Float32Array {
  const r = Math.min(p.rows - 1, Math.max(0, t)); const i0 = Math.floor(r), i1 = Math.min(p.rows - 1, i0 + 1), f = r - i0; const span = p.hi - p.lo || 1
  for (let v = 0; v < p.n; v++) { const x = p.data[i0 * p.n + v] * (1 - f) + p.data[i1 * p.n + v] * f; out[v] = Number.isFinite(x) ? Math.min(1, Math.max(0, (x - p.lo) / span)) : 0 }
  return out
}

/** The canvas and its view controls; `onReady` hands back the drawer so a player can recolour it without React. */
export function BrainCanvas({ onReady, values, signed = false, label }: { onReady?: (b: BrainGL | null) => void; values?: Float32Array | null; signed?: boolean; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null); const gl = useRef<BrainGL | null>(null)
  const [err, setErr] = useState<string | null>(null); const [ready, setReady] = useState(false)
  const [surface, setSurface] = useState(0.5); const [angle, setAngle] = useState<string | null>(null)
  useEffect(() => {
    let live = true
    loadMesh().then(m => { if (!live || !ref.current) return; try { gl.current = new BrainGL(ref.current, m); gl.current.draw(); setReady(true); onReady?.(gl.current) } catch (e) { setErr(String(e)) } }).catch(e => live && setErr(String(e)))
    const ro = new ResizeObserver(() => gl.current?.draw()); if (ref.current) ro.observe(ref.current)
    return () => { live = false; ro.disconnect(); onReady?.(null); gl.current?.dispose(); gl.current = null }
  }, [])
  useEffect(() => { if (!gl.current || values === undefined) return; gl.current.setValues(values, signed); gl.current.draw() }, [values, signed, ready])
  useEffect(() => { if (gl.current) { gl.current.mix = surface; gl.current.draw() } }, [surface])
  const drag = useRef<{ x: number; y: number } | null>(null)
  const down = (e: React.PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY }; (e.target as Element).setPointerCapture(e.pointerId) }
  const move = (e: React.PointerEvent) => { const d = drag.current; const b = gl.current; if (!d || !b) return
    b.yaw -= (e.clientX - d.x) * 0.5; b.pitch = Math.max(-89, Math.min(89, b.pitch + (e.clientY - d.y) * 0.4)); drag.current = { x: e.clientX, y: e.clientY }; setAngle(null); b.draw() }
  const turn = (k: string) => { const b = gl.current; if (!b) return; [b.yaw, b.pitch] = ANGLES[k]; setAngle(k); b.draw() }
  return <div className="brain3d">
    <div className="brain3dcanvas">
      <canvas ref={ref} role="img" aria-label={label} onPointerDown={down} onPointerMove={move} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} />
      {!ready && !err && <div className="brain3dwait" role="status"><span className="spin" /> Loading the brain</div>}
      {err && <div className="brain3dwait">{err}</div>}
    </div>
    <div className="bar">
      <div className="seg" role="group" aria-label="Surface">{SURFACES.map(([n, v]) => <button key={n} className={surface === v ? 'on' : ''} onClick={() => setSurface(v)}>{n}</button>)}</div>
      <div className="seg" role="group" aria-label="Turn to">{Object.keys(ANGLES).map(k => <button key={k} className={angle === k ? 'on' : ''} onClick={() => turn(k)}>{k}</button>)}</div>
    </div>
  </div>
}

const SPEEDS = [0.5, 1, 2]

/** One stream on the timeline: values over time (a line), a span (a bar), or labelled moments (ticks). */
export type Lane = { name: string; start?: number; dur?: number; times?: number[]; values?: number[]; labels?: string[]; ticks?: boolean }

function Timeline({ lanes, t, T, onSeek }: { lanes: Lane[]; t: number; T: number; onSeek: (x: number) => void }) {
  const X = (s: number) => 1000 * Math.min(1, Math.max(0, s / (T || 1)))
  const at = (e: React.PointerEvent) => { const r = (e.currentTarget as Element).getBoundingClientRect(); onSeek(Math.max(0, Math.min(T, (e.clientX - r.left) / r.width * T))) }
  return <div className="lanes">{lanes.map(l => {
    const s0 = l.start ?? 0; let mark: ReactNode = null
    if (l.ticks && l.times) mark = l.times.map((x, i) => <line key={i} x1={X(s0 + x)} x2={X(s0 + x)} y1={3} y2={21} className="lanetick"><title>{`${(s0 + x).toFixed(2)} s${l.labels?.[i] ? `: ${l.labels[i]}` : ''}`}</title></line>)
    else if (l.values && l.values.length > 1) {
      const lo = Math.min(...l.values), hi = Math.max(...l.values), ts = l.times ?? l.values.map((_, i) => i)
      mark = <polyline className="laneline" points={l.values.map((v, i) => `${X(s0 + ts[i]).toFixed(1)},${(21 - 18 * (hi > lo ? (v - lo) / (hi - lo) : 0.5)).toFixed(1)}`).join(' ')} />
    } else if (l.dur) mark = <rect className="lanespan" x={X(s0)} y={7} width={X(s0 + l.dur) - X(s0)} height={10} rx={2} />
    return <div key={l.name} className="lane"><span className="ink2 small">{l.name}</span>
      <svg viewBox="0 0 1000 24" preserveAspectRatio="none" onPointerDown={at} role="img" aria-label={`${l.name} over the recording`}>{mark}<line className="lanecursor" x1={X(t)} x2={X(t)} y1={0} y2={24} /></svg></div>
  })}</div>
}

/** A clip and its predicted brain on one clock: play, pause, speed and a scrubber; scrubbing recolours the brain at once.
 * A recording adds its audio on the same clock and a timeline with one lane per stream (#23). */
export function ClipBrain({ clip, image, predsUrl, sampleId, audio, lanes, square, children }: { clip: string | null; image?: string | null; predsUrl: string | null; sampleId?: string
  audio?: string | null; lanes?: Lane[]; square?: boolean; children?: ReactNode }) {
  const video = useRef<HTMLVideoElement>(null); const sound = useRef<HTMLAudioElement>(null); const brain = useRef<BrainGL | null>(null); const preds = useRef<Preds | null>(null)
  const buf = useRef<Float32Array | null>(null); const tRef = useRef(0); const raf = useRef(0); const last = useRef(0)
  const [t, setT] = useState(0); const [dur, setDur] = useState(0); const [playing, setPlaying] = useState(true); const [speed, setSpeed] = useState(1)
  const [state, setState] = useState<'loading' | 'ready' | 'none'>('loading'); const playingRef = useRef(true); const speedRef = useRef(1); const [mean, setMean] = useState<number[] | null>(null)
  const total = () => Math.max(dur, preds.current?.rows ?? 0)
  const paint = () => { const b = brain.current, p = preds.current; if (!b || !p) return; buf.current ??= new Float32Array(p.n); b.setValues(frameAt(p, tRef.current, buf.current), false); b.draw() }
  const follow = (m: HTMLMediaElement | null) => { if (!m || !m.duration) return; const want = Math.min(tRef.current, m.duration - 0.02)
    if (!playingRef.current || tRef.current >= m.duration) { if (!m.paused) m.pause(); if (Math.abs(m.currentTime - want) > 0.03) m.currentTime = want; return }
    m.playbackRate = speedRef.current; if (m.paused) m.play().catch(() => {}); if (Math.abs(m.currentTime - want) > 0.25) m.currentTime = want }
  const sync = () => { follow(video.current); follow(sound.current) }
  useEffect(() => {
    let live = true; setState('loading'); preds.current = null; buf.current = null; tRef.current = 0; setT(0); setMean(null)
    if (!predsUrl) { setState('none'); return }
    loadPreds(predsUrl).then(p => { if (!live) return; preds.current = p; setState('ready'); paint()
      setMean(Array.from({ length: p.rows }, (_, i) => { let s = 0; for (let v = 0; v < p.n; v++) { const x = p.data[i * p.n + v]; if (Number.isFinite(x)) s += x } return s / p.n })) }).catch(() => live && setState('none'))
    return () => { live = false }
  }, [predsUrl])
  useEffect(() => {
    const tick = (now: number) => {
      const dt = last.current ? (now - last.current) / 1000 : 0; last.current = now
      if (playingRef.current && (preds.current || dur)) { const T = total() || 1; tRef.current += dt * speedRef.current; if (tRef.current >= T) tRef.current = 0; paint(); sync(); setT(tRef.current) }
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf.current)
  }, [dur])
  const seek = (x: number) => { tRef.current = x; paint(); sync(); setT(x) }
  const toggle = () => { playingRef.current = !playingRef.current; setPlaying(playingRef.current); last.current = 0; sync() }
  const T = total(); const canPlay = state === 'ready' || (state === 'none' && dur > 0)
  const allLanes = lanes && [...(mean ? [{ name: 'TRIBE v2, cortex mean', values: mean }] : []), ...lanes]
  return <div className="clipbrain">
    <div className="twoup">
      <div className={`stage runstage ${square ? 'square' : ''}`}>
        {clip ? <video ref={video} src={clip} muted playsInline preload="auto" onLoadedMetadata={e => { setDur((e.target as HTMLVideoElement).duration); sync() }} /> : image && <img src={image} alt="" />}
        {children}
      </div>
      <div className="brainside">
        <BrainCanvas label="TRIBE v2 prediction on the cortex, second by second" onReady={b => { brain.current = b; if (b) paint() }} />
        <div className="headline"><span className="legend">Low <span className="ramp single" /> High</span></div>
        {state === 'none' && <div className="ink2">No TRIBE v2 predictions in this {sampleId ? 'sample' : 'recording'}</div>}
      </div>
    </div>
    {audio && <audio ref={sound} src={audio} preload="auto" />}
    <div className="bar player">
      <button className="btn" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'} disabled={!canPlay}>{playing ? 'Pause' : 'Play'}</button>
      <input type="range" aria-label="Time" min={0} max={T || 1} step={0.01} value={Math.min(t, T || 1)} disabled={!canPlay} onChange={e => seek(Number(e.target.value))} />
      <span className="num ink2">{t.toFixed(1)} of {T.toFixed(0)} s</span>
      <div className="seg" role="group" aria-label="Speed">{SPEEDS.map(s => <button key={s} className={speed === s ? 'on' : ''} onClick={() => { speedRef.current = s; setSpeed(s); sync() }}>{s}×</button>)}</div>
      {sampleId && state === 'ready' && <a className="btn" href={`/api/recording/${encodeURIComponent(sampleId)}`} download>Download recording</a>}
    </div>
    {allLanes && allLanes.length > 0 && <Timeline lanes={allLanes} t={t} T={T} onSeek={seek} />}
    <div className="ink2 small">TRIBE v2 prediction for an average viewer at each second of the clip{T > dur + 0.5 && dur > 0 ? `; the clip ends at ${dur.toFixed(1)} s and the response runs on` : ''}. Drag the brain to turn it.</div>
  </div>
}

const contrastCache = new Map<string, Promise<Float32Array>>()
/** One contrast map on the cortex: values scaled by their 99th percentile of absolute values, as lab/maps.py scales them. */
export function ContrastBrain({ projectId, index, title }: { projectId: string; index: number; title: string }) {
  const [values, setValues] = useState<Float32Array | null>(null); const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    const url = `/api/brain/contrast/${encodeURIComponent(projectId)}/${index}`; let live = true
    let p = contrastCache.get(url)
    if (!p) {
      p = fetch(url).then(r => { if (!r.ok) throw new Error(`contrast map: ${r.status}`); return r.arrayBuffer() }).then(b => {
        const { data } = parseNpy(b); const [vmax] = percentile(data.map(Math.abs), [99]); return data.map(x => Number.isFinite(x) ? x / (vmax || 1) : 0) })
      p.catch(() => contrastCache.delete(url)); contrastCache.set(url, p)
    }
    p.then(v => live && setValues(v)).catch(e => live && setErr(String(e)))
    return () => { live = false }
  }, [projectId, index])
  return <div className="brainside">
    <BrainCanvas label={`${title}, on the cortex`} values={values} signed />
    <div className="headline"><span className="legend">Lower <span className="ramp" /> Higher</span></div>
    {err && <div className="ink2">{err}</div>}
  </div>
}
