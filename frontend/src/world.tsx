import { useEffect, useRef, useState } from 'react'
import { call, fmt, ROLE_NAMES, type Row, regionInText, upload as sendFile } from './api'

export type Param = { name: string; type: string; value: any; role: string; unit?: string; range?: [number, number]; options?: string[]; label?: string; project_id: string }
export type Preview = { key: string; values: Record<string, any>; image: string; clip: string; readout: Record<string, number>; map: { views: Record<string, string> } }
export type PreviewEvent = { preview: string; key: string; stage: string; actor: string; ahead?: boolean; image?: string; error?: string; render_s?: number }
type Asset = { label: string; image?: string | null; source?: string }
const VIEW_NAMES: Record<string, string> = { left: 'Left', right: 'Right', ventral: 'Underside', posterior: 'Back' }
const STAGE_TEXT: Record<string, string> = { waiting: 'Waiting for the GPU', underway: 'Already being made ahead', render: 'Isaac is rendering', rendered: 'TRIBE is reading the clip, about a minute', drawing: 'Drawing the brain map', done: '', failed: 'Failed' }

const TILE_TEXT: Record<string, string> = { waiting: 'Queued', underway: 'Queued', render: 'Isaac', rendered: 'TRIBE', drawing: 'Map' }   // on the tile itself: few words
const fmtVal = (v: any, unit?: string) => typeof v === 'number' ? `${+v.toFixed(2)}${unit === 'deg' ? '°' : unit ? ' ' + unit : ''}` : String(v).replace(/_/g, ' ')
const same = (a: Record<string, any>, b: Record<string, any>) => Object.keys(b).every(k => JSON.stringify(a[k]) === JSON.stringify(b[k]))

/** The world and the brain side by side, with the scene script's parameters as controls underneath. Person and agent move the same controls. */
export function WorldPanel({ pid, world, script, params, previews, assets, event, steps, region, onChanged }: {
  pid: string; world: { kind: string; name: string }; script: string; params: Row<Param>[]; previews: Row<Preview>[]; assets: Record<string, Asset>
  event?: PreviewEvent; steps: any[]; region: string; onChanged: () => void
}) {
  const values = Object.fromEntries(params.map(p => [p.data.name, p.data.value]))
  const current = previews.find(p => same(p.data.values, values))?.data
  // Until the exact values are rendered, show the nearest values that have been: the world and brain answer at once
  const dist = (a: Record<string, any>) => params.reduce((t, p) => { const d = p.data, x = a[d.name], y = values[d.name]
    if (x === y) return t; if (typeof x === 'number' && typeof y === 'number' && d.range) return t + Math.abs(x - y) / ((d.range[1] - d.range[0]) || 1); return t + 1 }, 0)
  const nearest = current ? undefined : [...previews].sort((a, b) => dist(a.data.values) - dist(b.data.values))[0]?.data
  const latest = current ?? nearest
  const differs = nearest ? params.filter(p => JSON.stringify(nearest.values[p.data.name]) !== JSON.stringify(p.data.value)).map(p => `${(p.data.label ?? p.data.name).toLowerCase()} ${fmtVal(nearest.values[p.data.name], p.data.unit)}`) : []
  const working = event && !['done', 'failed'].includes(event.stage)
  const since = useRef<number | null>(null); const [, tick] = useState(0)   // how long this render has been under way, shown where it will appear
  if (working && since.current == null) since.current = Date.now(); if (!working) since.current = null
  useEffect(() => { if (!working) return; const i = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(i) }, [working])
  const elapsed = since.current ? Math.round((Date.now() - since.current) / 1000) : 0
  const making = working ? `${STAGE_TEXT[event!.stage] ?? 'Working'}, ${elapsed} s` : null
  const [view, setView] = useState('ventral'); const [showScript, setShowScript] = useState(false); const [add, setAdd] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const stepActor = Object.fromEntries(steps.map(s => [s.step_id, s.actor]))
  const update = async (p: Row<Param>, value: any) => {
    setErr(null)
    try { await call('parameter_update', { parameter_id: p.id, expect_version: p.version, value }); onChanged() } catch (e) { setErr(String(e)) }
  }
  const runImage = !latest && values.item ? assets[values.item]?.image : null   // before any preview: the run's own render of these values
  const imgSrc = working && event?.image && !nearest ? event.image : latest?.image ?? runImage
  return <div className="world">
    <div className="bar">
      <span className="mid">{world.name}</span>
      <button className="btn" onClick={() => setShowScript(s => !s)} aria-expanded={showScript}>Scene script</button>
      <div className="switch"><button className="btn" onClick={() => setAdd(a => !a)} aria-haspopup="dialog" aria-expanded={add}>Add</button>
        {add && <AddMenu pid={pid} params={params} onDone={() => { setAdd(false); onChanged() }} />}</div>
      {working && <span className="ink2"><span className="spin" /> {STAGE_TEXT[event!.stage]}{event!.actor === 'agent' ? ', changed by the agent' : ''}</span>}
      {event?.stage === 'failed' && <span className="chip flag">Render failed: {event.error}</span>}
      {err && <span className="chip flag">{err}</span>}
    </div>
    {showScript && <pre className="codebox" style={{ maxHeight: 260 }}>{script}</pre>}
    <div className="twoup">
      <div className={`stage ${working && !current ? 'stale' : ''}`}>{imgSrc ? <img src={imgSrc} alt="The world as rendered by Isaac Sim" /> : <div className="empty">No render yet. Change a control to render it.</div>}
        {working && !current && <div className="stageload" role="status"><span className="spin" /><b>Making the new render</b><span>{making}</span></div>}
        {latest && !current && <div className="stagenote">{working ? 'Showing the nearest render' : 'Nearest render'}, {differs.join(' and ')}</div>}
        {runImage && !working && <div className="stagenote">Render from the run. Change a control to render it live</div>}</div>
      <div className={`brainside ${working && !current ? 'stale' : ''}`}>
        {latest ? <>
          <img src={`/files/${latest.map.views[view]}`} alt={`TRIBE prediction, ${VIEW_NAMES[view]}`} />
          <div className="seg" role="group" aria-label="Brain view">{Object.keys(VIEW_NAMES).map(v => <button key={v} className={view === v ? 'on' : ''} onClick={() => setView(v)}>{VIEW_NAMES[v]}</button>)}</div>
          <div className="big" style={{ fontSize: 34 }}>{fmt(latest.readout[region])}</div>
          <div className="ink2">TRIBE response in the {regionInText(region)} for this render</div>
        </> : <div className="empty">TRIBE reads the world here once a control changes</div>}
      </div>
    </div>
    {working && <div className="ctlwait" role="status"><span className="spin" /> Controls wait for this render: {making}</div>}
    <div className="controls">
      {[...params].sort((a, b) => ((a.data as any).line ?? 0) - ((b.data as any).line ?? 0)).map(p => <Control key={p.id} p={p} assets={assets} byAgent={p.version > 1 && stepActor[p.step_id] === 'agent'} onSet={v => update(p, v)} disabled={!!working}
        pending={working && !current && JSON.stringify(latest?.values?.[p.data.name]) !== JSON.stringify(p.data.value) ? TILE_TEXT[event!.stage] ?? 'Working' : null} />)}
    </div>
  </div>
}

function Control({ p, assets, byAgent, onSet, disabled, pending }: { p: Row<Param>; assets: Record<string, Asset>; byAgent: boolean; onSet: (v: any) => void; disabled: boolean; pending: string | null }) {
  const load = pending ? <span className="tileload" role="status" aria-label={`Rendering, ${pending}`}><span className="spin" />{pending}</span> : null
  const d = p.data; const [v, setV] = useState(d.value); useEffect(() => setV(d.value), [d.value])
  const head = <div className="ctlhead"><span>{d.label ?? d.name}</span><span className="chip">{ROLE_NAMES[d.role] ?? d.role}</span>{byAgent && <span className="chip agent">Changed by the agent</span>}</div>
  if (d.type === 'number' || d.type === 'angle') {
    const [lo, hi] = d.range ?? [0, 1]; const step = +((hi - lo) / 20).toFixed(6); const min = +(lo + (((d.value - lo) % step) + step) % step).toFixed(6)   /* twenty steps on a grid through the current value, matching the values rendered ahead */
    return <label className="ctl">{head}<div className="bar"><input type="range" min={min} max={hi} step={step} value={v} disabled={disabled} aria-label={d.label ?? d.name}
      onChange={e => setV(parseFloat(e.target.value))} onPointerUp={() => v !== d.value && onSet(+(min + Math.round((v - min) / step) * step).toFixed(6))} onKeyUp={() => v !== d.value && onSet(+(min + Math.round((v - min) / step) * step).toFixed(6))} />
      <span className="num">{Number(v).toFixed(2).replace(/\.?0+$/, '')} {d.unit === 'deg' ? '°' : d.unit ?? ''}</span>{load}</div></label>
  }
  if (d.type === 'choice') return <div className="ctl">{head}<div className="seg" role="group" aria-label={d.label ?? d.name}>{d.options!.map(o => <button key={o} disabled={disabled} className={o === d.value ? `on ${pending ? 'pending' : ''}` : ''} onClick={() => o !== d.value && onSet(o)}>{o.replace(/_/g, ' ')}{o === d.value && load}</button>)}</div></div>
  if (d.type === 'asset') {
    const opts = d.options ?? []; const pictured = opts.filter(o => assets[o]?.image).length > opts.length / 2
    if (pictured) return <div className="ctl wide">{head}<div className="thumbs" role="listbox" aria-label={d.label ?? d.name}>{opts.map(o => <button key={o} ref={el => { if (el && o === d.value && el.parentElement) { const box = el.parentElement; box.scrollLeft = el.offsetLeft - box.offsetLeft - box.clientWidth / 2 + el.clientWidth / 2 } }}   /* scroll the strip sideways only, never the page */ role="option" aria-selected={o === d.value} aria-busy={o === d.value && !!pending} disabled={disabled} className={o === d.value ? `on ${pending ? 'pending' : ''}` : ''} onClick={() => o !== d.value && onSet(o)} title={assets[o]?.label ?? o}>
      {assets[o]?.image ? <img src={assets[o].image!} alt="" loading="lazy" /> : <span className="noimg">{assets[o]?.label ?? o}</span>}<span>{assets[o]?.label ?? o}</span>{o === d.value && load}</button>)}</div></div>
    return <label className="ctl">{head}<select value={d.value} disabled={disabled} onChange={e => onSet(e.target.value)}>{opts.map(o => <option key={o} value={o}>{o === 'none' ? 'None' : assets[o]?.label ?? o}</option>)}</select></label>
  }
  return <div className="ctl">{head}<span className="ink2">{String(d.value)}</span></div>
}

function AddMenu({ pid, params, onDone }: { pid: string; params: Row<Param>[]; onDone: () => void }) {
  const assetParam = params.find(p => p.data.type === 'asset' && p.data.name === 'item')
  const [q, setQ] = useState(''); const [rows, setRows] = useState<any[]>([]); const [busy, setBusy] = useState<string | null>(null); const [err, setErr] = useState<string | null>(null)
  const file = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!q.trim()) { setRows([]); return } const t = setTimeout(() => call<any[]>('record_search', { q }).then(setRows), 250); return () => clearTimeout(t) }, [q])
  const add = async (args: Record<string, unknown>, label: string) => {
    setBusy(label); setErr(null)
    try { await call('asset_create', { project_id: pid, parameter: 'item', ...args }); onDone() } catch (e) { setErr(String(e)) } finally { setBusy(null) }
  }
  const upload = async (f: File) => {
    setBusy(f.name); setErr(null)
    try { const r = await sendFile(`/upload?name=${encodeURIComponent(f.name)}`, f); const j = await r.json(); if (!r.ok) throw new Error(j.detail); await add({ source_id: 'file', file_path: j.file_path }, f.name) } catch (e) { setErr(String(e)); setBusy(null) }
  }
  const methods: { name: string; status: string; ready: boolean }[] = [
    { name: 'Library asset', status: assetParam ? '1,013 Palatial assets, downloaded when picked' : 'This world has no asset control yet', ready: !!assetParam },
    { name: 'Your file', status: 'GLB, glTF, OBJ, PLY, STL or USD; meshes become USD', ready: !!assetParam },
    { name: 'SAGE-10k room', status: '10,000 rooms indexed; importing a new room from the app is not wired yet', ready: false },
    { name: 'Room from text', status: 'Needs the SAGE generator, which is not released', ready: false },
    { name: 'Cosmos restyle', status: 'Runs on this Spark, about 4 min a clip; not wired to the room yet', ready: false },
    { name: 'Scan or splat', status: 'Not started', ready: false },
  ]
  return <div className="menu addmenu" role="dialog" aria-label="Add to the world">
    {methods.map(m => <div key={m.name} className={`addrow ${m.ready ? '' : 'off'}`}><b>{m.name}</b><span className="ink2">{m.status}</span></div>).slice(0, 1)}
    {assetParam && <><input className="search" autoFocus aria-label="Search the library" placeholder="Search 1,013 assets, such as mug" value={q} onChange={e => setQ(e.target.value)} />
      <div className="results">{rows.map(r => <button key={r.id} disabled={!!busy} onClick={() => add({ source_id: 'palatial', record_id: r.id }, r.name)}>
        {r.image ? <img src={r.image} alt="" /> : <span className="noimg" />}<span>{r.name}<div className="ink2">{r.size_m} m{r.local ? '' : ', downloads first'}</div></span></button>)}</div></>}
    {methods.slice(1).map(m => <div key={m.name} className={`addrow ${m.ready ? '' : 'off'}`}><b>{m.name}</b><span className="ink2">{m.status}</span>
      {m.name === 'Your file' && m.ready && <><input ref={file} type="file" hidden accept=".glb,.gltf,.obj,.ply,.stl,.usd,.usda,.usdc,.usdz" onChange={e => e.target.files?.[0] && upload(e.target.files[0])} /><button className="btn" disabled={!!busy} onClick={() => file.current?.click()}>Choose file</button></>}</div>)}
    {busy && <div className="ink2"><span className="spin" /> Adding {busy}</div>}
    {err && <div className="chip flag">{err}</div>}
  </div>
}
