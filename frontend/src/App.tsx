import { useEffect, useState } from 'react'
import { api, type Dataset, type Stage, type ViewResult } from './api'
import { Fields } from './Fields'
import { Grid } from './Grid'
import { Inspector } from './Inspector'
import { Agent, type Msg } from './Agent'
import { Runs } from './Runs'
import { ViewBar } from './ViewBar'
import { NewProject } from './NewProject'
import { Dashboard } from './Dashboard'

// The frame: datasets, the view bar, fields, samples and the inspector. Everything shown comes from the API. The
// dataset, stages, shown fields and selected sample live in the address, so any screen can be reopened exactly.

type Loc = { d?: string; stages: Stage[]; shown: string[]; sel: string | null; view?: 'data' | 'runs' | 'dashboard' }
const readLoc = (): Loc => { try { return { stages: [], shown: [], sel: null, ...JSON.parse(decodeURIComponent(location.hash.slice(1))) } } catch { return { stages: [], shown: [], sel: null } } }

export default function App() {
  if (location.pathname === '/dashboard') return <Dashboard standalone />   // the dashboard's own link
  return <Lab />
}

function Lab() {
  const [all, setAll] = useState<Dataset[]>([])
  const [loc, setLoc] = useState<Loc>(readLoc)
  const [v, setV] = useState<ViewResult | null>(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [tab, setTab] = useState<'agent' | 'sample'>('agent')
  const [fresh, setFresh] = useState(() => !location.hash)   // a first open shows the new-project screen
  const [queued, setQueued] = useState<string | undefined>()
  useEffect(() => { setTab(loc.sel ? 'sample' : 'agent') }, [loc.sel])   // no sample selected: never leave an empty Sample tab open
  const name = loc.d ?? all[0]?.name
  const ds = all.find(d => d.name === name)
  const go = (p: Partial<Loc>) => setLoc(l => ({ ...l, ...p }))
  useEffect(() => { history.replaceState(null, '', '#' + encodeURIComponent(JSON.stringify({ ...loc, d: name }))) }, [loc, name])
  useEffect(() => { api.datasets().then(setAll).catch(e => setErr(String(e.message))) }, [])
  useEffect(() => {
    if (!name) return
    let live = true   // a slower, older response must never replace a newer one
    setBusy(true); setErr('')
    api.view(name, loc.stages).then(r => { if (live) { setV(r); setBusy(false) } }).catch(e => { if (live) { setErr(String(e.message)); setBusy(false) } })
    return () => { live = false }
  }, [name, JSON.stringify(loc.stages)])
  const [wide, setWide] = useState(false)   // the sample expanded over the fields and grid, as FiftyOne's sample modal
  const selSample = v?.samples.find(s => s.id === loc.sel)
  const wideOn = wide && tab === 'sample' && !!loc.sel
  return <div className={`frame${wideOn ? ' wide' : ''}`}>
    <header className="top">
      <span className="brand">Visual Cortex Lab</span>
      <div className="seg" role="tablist">
        <button role="tab" aria-selected={loc.view !== 'runs'} onClick={() => go({ view: 'data' })}>Data</button>
        <button role="tab" aria-selected={loc.view === 'runs'} onClick={() => go({ view: 'runs' })}>Runs</button>
        <button role="tab" aria-selected={loc.view === 'dashboard'} onClick={() => go({ view: 'dashboard' })}>Dashboard</button>
      </div>
      {(loc.view ?? 'data') === 'data' && <select value={name ?? ''} onChange={e => setLoc({ d: e.target.value, stages: [], shown: [], sel: null })} aria-label="Dataset">
        {all.map(d => <option key={d.name} value={d.name}>{d.name}, {d.samples.toLocaleString()} samples</option>)}
      </select>}
      <button className="btn" onClick={() => setFresh(true)}>New project</button>
      {busy && <span className="ink2">Updating</span>}
      {err && <span className="flag">{err}</span>}
    </header>
    {loc.view === 'dashboard' ? <Dashboard /> : loc.view === 'runs' ? <Runs onOpenDataset={n => { setAll(a => a); api.datasets().then(setAll); setLoc({ d: n, stages: [], shown: [], sel: null, view: 'data' }) }} /> : <>
    {v && <ViewBar trail={v.trail} stages={loc.stages} fields={v.schema} onRemove={i => go({ stages: loc.stages.filter((_, k) => k !== i) })} onAdd={s => go({ stages: [...loc.stages, s] })} />}
    <div className={`body${wideOn ? ' wide' : ''}`}>
      {v && <Fields schema={v.schema} facets={v.facets} shown={loc.shown} onToggleShown={p => go({ shown: loc.shown.includes(p) ? loc.shown.filter(x => x !== p) : [...loc.shown, p] })}
        onAdd={s => go({ stages: [...loc.stages, s] })} />}
      {v ? <Grid samples={v.samples} count={v.count} shown={loc.shown} schema={v.schema} selected={loc.sel} onSelect={id => go({ sel: id })} /> : <main className="grid empty"><p className="ink2">Loading</p></main>}
      <div className="right">
        <div className="tabs" role="tablist">
          <button role="tab" aria-selected={tab === 'agent'} onClick={() => setTab('agent')}>Agent</button>
          <button role="tab" aria-selected={tab === 'sample'} onClick={() => setTab('sample')} disabled={!loc.sel}>{loc.sel ? `Sample ${loc.sel}` : 'Sample'}</button>
        </div>
        {name && <div hidden={tab !== 'agent'} className="tabbody"><Agent dataset={name} stages={loc.stages} msgs={msgs} setMsgs={setMsgs} queued={queued} onQueuedSent={() => setQueued(undefined)}
          onShow={(d, s, f) => setLoc(l => ({ ...l, d, stages: s, sel: null, shown: f.length ? f : l.shown }))} /></div>}
        {tab === 'sample' && loc.sel && name && <Inspector dataset={name} id={loc.sel} schema={v?.schema ?? []} onClose={() => { go({ sel: null }); setTab('agent'); setWide(false) }} wide={wide} onWide={setWide} shown={loc.shown}
          computed={selSample?.computed_sources && Object.keys(selSample.computed_sources).length ? { fields: selSample.fields, sources: selSample.computed_sources } : undefined} />}
      </div>
    </div></>}
    {fresh && <NewProject onClose={() => setFresh(false)}
      onOpenDataset={d => { setFresh(false); setLoc({ d, stages: [], shown: [], sel: null, view: 'data' }) }}
      onStart={(goal, d) => { setFresh(false); setLoc({ d, stages: [], shown: [], sel: null, view: 'data' }); setTab('agent'); setQueued(goal) }} />}
    <footer className="prov">{loc.view === 'runs' ? <span className="ink3">Runs are defined in backend/runs/ and run by the server; their state and logs are in backend/data/runs/</span> : ds ? <>
      <span>{ds.source.about}</span><span className="ink3">Loaded {ds.loaded_at.slice(0, 16)} by the {ds.source.loader} loader from {ds.source.source_file}</span></> : null}</footer>
  </div>
}
