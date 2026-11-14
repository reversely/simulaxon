import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { brk } from './brk'

// The cortex under a clip: TRIBE v2's predicted response on TRIBE's own plotting mesh (fsaverage5, half inflated, left
// then right hemisphere; app/scripts/brain_mesh.py), at the playing clip's time. Colours follow TRIBE's demo notebook:
// the whole clip scaled to its 1st to 99th percentile, nothing shown below 0.6 of that range, colour fading in from 0.6
// to 0.68, colorcet "fire", over grey sulcal shading. TRIBE predicts once a second; between seconds the map is
// interpolated, as TRIBE's own plot_timesteps_mp4 can (interpolated_fps).

type Mesh = { pos: Float32Array; sulc: Float32Array; faces: Uint32Array; fire: Float32Array }
let meshP: Promise<Mesh> | null = null
export function loadMesh(): Promise<Mesh> {
  meshP ??= Promise.all([fetch('/brain/fsaverage5.json').then(r => r.json()), fetch('/brain/fsaverage5.bin').then(r => r.arrayBuffer())]).then(([m, b]) => {
    const n = m.vertices, f = m.faces; let o = 0
    const pos = new Float32Array(b, o, n * 3); o += n * 12
    const sulc = new Float32Array(b, o, n); o += n * 4
    const faces = new Uint32Array(b, o, f * 3); o += f * 12
    return { pos, sulc, faces, fire: new Float32Array(b, o, 256 * 3) }
  })
  return meshP
}

type Pred = { t: number[]; v: Float32Array; cols: number; lo: number; hi: number; source: string }
async function loadPred(dataset: string, id: string, path: string): Promise<Pred> {
  const r = await fetch(`/api/datasets/${encodeURIComponent(dataset)}/samples/${encodeURIComponent(id)}/track_full?path=${encodeURIComponent(path)}`)
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
  const [, cols] = (r.headers.get('X-Shape') ?? '0,0').split(',').map(Number)
  const v = new Float32Array(await r.arrayBuffer())
  const s = Float32Array.from(v).sort()   // TRIBE's robust_normalize: 1st and 99th percentile of the whole clip
  return { t: (r.headers.get('X-Time-S') ?? '').split(',').map(Number), v, cols, lo: s[Math.floor(0.01 * (s.length - 1))], hi: s[Math.floor(0.99 * (s.length - 1))], source: r.headers.get('X-Source') ?? '' }
}

export function BrainView({ dataset, id, path, now }: { dataset: string; id: string; path: string; now: number }) {
  const box = useRef<HTMLDivElement>(null)
  const gl = useRef<{ r: THREE.WebGLRenderer; scene: THREE.Scene; cams: THREE.OrthographicCamera[]; col: THREE.BufferAttribute; bg: Float32Array; mesh: Mesh; draw: () => void } | null>(null)
  const [pred, setPred] = useState<Pred | null>(null), [err, setErr] = useState(''), [ready, setReady] = useState(false)

  useEffect(() => { setPred(null); setErr(''); loadPred(dataset, id, path).then(setPred).catch(e => setErr(String(e.message))) }, [dataset, id, path])

  // the scene, once: one mesh, two views (left hemisphere from the left, right from the right), light from each camera
  useEffect(() => {
    let alive = true
    loadMesh().then(mesh => {
      if (!alive || !box.current) return
      const r = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true }); r.setPixelRatio(window.devicePixelRatio)
      r.setClearColor(0x131417); r.setScissorTest(true); r.outputColorSpace = THREE.LinearSRGBColorSpace;   // TRIBE's colours are used as given, like PyVista
       box.current.appendChild(r.domElement)
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(mesh.pos, 3)); g.setIndex(new THREE.BufferAttribute(mesh.faces, 1)); g.computeVertexNormals()
      let lo = Infinity, hi = -Infinity; for (const x of mesh.sulc) { lo = Math.min(lo, x); hi = Math.max(hi, x) }
      const bg = new Float32Array(mesh.sulc.length); mesh.sulc.forEach((x, i) => { bg[i] = 1 - (x - lo) / (hi - lo + 1e-8) })   // PlotBrain: 1 - normalised sulcal depth
      const col = new THREE.BufferAttribute(new Float32Array(mesh.sulc.length * 3), 3); g.setAttribute('color', col)
      for (let i = 0; i < bg.length; i++) col.setXYZ(i, bg[i], bg[i], bg[i])
      const scene = new THREE.Scene(); scene.add(new THREE.Mesh(g, new THREE.MeshLambertMaterial({ vertexColors: true })))
      scene.add(new THREE.AmbientLight(0xffffff, 0.35 * Math.PI))   // PyVista's ambient 0.3 in PlotBrain, the rest from the light
      const cams = [-1, 1].map(side => {
        const c = new THREE.OrthographicCamera(-102, 102, 72, -72, 1, 1000); c.up.set(0, 0, 1); c.position.set(side * 400, -9, 7); c.lookAt(0, -9, 7)
        const l = new THREE.DirectionalLight(0xffffff, 0.7 * Math.PI); l.position.set(side * 400, -9, 200); scene.add(l); return c
      })
      const draw = () => {
        const W = r.domElement.width / r.getPixelRatio(), H = r.domElement.height / r.getPixelRatio()
        cams.forEach((c, j) => { r.setViewport(j * W / 2, 0, W / 2, H); r.setScissor(j * W / 2, 0, W / 2, H); r.render(scene, c) })
      }
      gl.current = { r, scene, cams, col, bg, mesh, draw }; setReady(true)
      // resizing clears the canvas, so every resize redraws (after Expand the cortex stayed blank until playback moved)
      const fit = () => { if (!box.current) return; const w = box.current.clientWidth; r.setSize(w, Math.round(w / 2 * 144 / 204)); draw() }
      fit(); new ResizeObserver(fit).observe(box.current)
    }).catch(e => setErr(String(e.message)))
    return () => { alive = false; gl.current?.r.dispose(); gl.current?.r.domElement.remove(); gl.current = null }
  }, [])

  // colour the vertices for the current time and draw both views
  const sec = pred ? Math.min(Math.max(now - pred.t[0], 0), pred.t.length - 1) : 0
  useEffect(() => {
    const G = gl.current; if (!G || !pred || pred.cols !== G.bg.length) return
    const i0 = Math.floor(sec), i1 = Math.min(i0 + 1, pred.t.length - 1), w = sec - i0, n = pred.cols, f = G.mesh.fire
    for (let v = 0; v < n; v++) {
      const raw = (1 - w) * pred.v[i0 * n + v] + w * pred.v[i1 * n + v]
      const x = Math.min(1, Math.max(0, (raw - pred.lo) / (pred.hi - pred.lo)))
      const c = Math.min(1, Math.max(0, (x - 0.6) / 0.4)), a = Math.min(1, c / 0.2), k = Math.round(c * 255) * 3, b = G.bg[v]
      G.col.setXYZ(v, a * f[k] + (1 - a) * b, a * f[k + 1] + (1 - a) * b, a * f[k + 2] + (1 - a) * b)
    }
    G.col.needsUpdate = true; G.draw()
  }, [pred, sec, ready])

  return <figure className="brain" aria-label="Predicted brain response">
    <figcaption><b>Predicted brain response</b> <span className="ink2">TRIBE v2, average viewer, {pred ? <>second <span className="num">{(sec + pred.t[0]).toFixed(1)}</span> of {pred.t.length}</> : err || 'loading'}</span></figcaption>
    <div className="cortexbox"><div ref={box} className="cortex" /><span className="hemi l">Left hemisphere</span><span className="hemi r">Right hemisphere</span></div>
    <div className="ink3">Lit: the top 40% of this clip's range, as TRIBE's demo shows it. Interpolated between seconds.</div>
    {pred && <div className="src">From {brk(pred.source)}</div>}
  </figure>
}
