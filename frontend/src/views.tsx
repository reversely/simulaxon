import { useEffect, useState } from 'react'
import { call, fmt, type Project, type Region, type Row, type AnalysisItem } from './api'

type Step = { label: string; query: string; kept: number; removed: number; removed_rows: { name: string; reason: string }[] }
export type Search = { reading: string; source: string; steps: Step[]; pairs_note?: string }

/** How the question became these items: the reading, then each filter with its count and what it removed. */
export function SearchView({ search }: { search?: Search | null }) {
  const [open, setOpen] = useState<number | null>(null)
  if (!search) return <div className="empty">No search was recorded for this project. Items came from the template or a hand-made list.</div>
  const top = Math.max(...search.steps.map(s => s.kept), 1)
  return <div className="wide">
    <div className="card"><h3>How the question was read</h3><p style={{ margin: 0, fontSize: 17 }}>{search.reading}</p><div className="ink2" style={{ marginTop: 8 }}>{search.source}</div></div>
    <div className="card"><h3>Step by step</h3>
      <div className="rows">{search.steps.map((s, i) => <button key={i} className={`funnel ${open === i ? 'on' : ''}`} onClick={() => setOpen(open === i ? null : i)} aria-expanded={open === i}>
        <span className="fl">{s.label}<code>{s.query}</code></span>
        <span className="num mid">{s.kept.toLocaleString()}</span>
        <span className="fbar"><span style={{ width: `${Math.max(0.5, 100 * s.kept / top)}%` }} /></span>
        {s.removed > 0 && <span className="ink2 num fr">{s.removed.toLocaleString()} removed</span>}
        {open === i && s.removed_rows.length > 0 && <ul className="list removed">{s.removed_rows.map((r, j) => <li key={j}><span>{r.name}</span><span className="ink2">{r.reason}</span></li>)}{s.removed > s.removed_rows.length && <li className="muted">and {(s.removed - s.removed_rows.length).toLocaleString()} more</li>}</ul>}
      </button>)}</div>
      {search.pairs_note && <div className="ink2" style={{ marginTop: 10 }}>{search.pairs_note}</div>}
    </div>
  </div>
}

/** Evidence across projects from the same template, assumptions with their status, and observations. */
export function FindingsView({ P, pid, projects, region, analysesFor, onOpen, onAsk }: {
  P: Project; pid: string; projects: Row<Project>[]; region: string; analysesFor: (id: string) => Promise<AnalysisItem[]>; onOpen: (id: string) => void; onAsk: (t: string) => void
}) {
  const sibs = projects.filter(p => p.data.template_id === P.template_id && p.data.status === 'Done')
  const [vals, setVals] = useState<Record<string, Region | undefined>>({})
  const [assume, setAssume] = useState<any[]>([])
  useEffect(() => { call<any[]>('assumption_list', { project_id: pid }).then(setAssume) }, [pid])
  useEffect(() => {
    let live = true
    Promise.all(sibs.map(async s => [s.id, (await analysesFor(s.id)).find(a => a.analysis.data.kind === 'paired')?.result?.data.regions.find((r: Region) => r.region === region)] as const))
      .then(rs => { if (live) setVals(Object.fromEntries(rs)) })
    return () => { live = false }
  }, [sibs.map(s => s.id).join(), region])
  const ref = vals[pid]
  return <div className="wide">
    <div className="card"><h3>Evidence, {region}</h3>
      {sibs.length < 2 ? <div className="ink2">Only one project from this template has run. Fork it with a control from Challenge to compare.</div> :
        <table className="data"><thead><tr><th>Project</th><th>Controls</th><th>Effect</th><th>Interval</th><th>Share of this project</th></tr></thead>
          <tbody>{sibs.map(s => { const v = vals[s.id]; return <tr key={s.id} onClick={() => onOpen(s.id)} style={{ cursor: 'pointer' }}>
            <td>{s.data.title}{s.id === pid && <span className="chip" style={{ marginLeft: 8 }}>This project</span>}</td>
            <td className="ink2">{[s.data.bindings.match_on && `matched on ${s.data.bindings.match_on}`, s.data.bindings.control && String(s.data.bindings.control).toLowerCase()].filter(Boolean).join(' and ') || 'None'}</td>
            <td>{fmt(v?.value)}</td><td className="ink2">{v ? `${fmt(v.interval_95[0])} to ${fmt(v.interval_95[1])}` : 'Not run'}</td>
            <td>{v && ref && ref.value !== 0 ? `${Math.round(100 * v.value / ref.value)}%` : 'None'}</td></tr> })}</tbody></table>}
    </div>
    <div className="card"><h3>Observations</h3>
      <div className="ink2" style={{ marginBottom: 10 }}>Things noticed while exploring, each with its numbers, before they are tested.</div>
      <button className="btn" onClick={() => onAsk('Look across this project and tell me what you notice, with numbers, and what test would firm each one up.')}>Ask the agent what it notices</button>
    </div>
    <div className="card"><h3>Assumptions</h3>
      <ul className="list">{assume.map(a => <li key={a.text} style={{ alignItems: 'flex-start' }}><span><span>{a.text}</span><div className="ink2" style={{ fontSize: 14 }}>{a.evidence}</div></span><span className={`chip ${a.status === 'Untested' ? 'flag' : ''}`}>{a.status}</span></li>)}</ul>
    </div>
  </div>
}

export function SourcesView() {
  const [rows, setRows] = useState<any[]>([])
  useEffect(() => { call<any[]>('source_list').then(setRows) }, [])
  return <div className="wide"><div className="tablewrap"><table className="data"><thead><tr><th>Source</th><th>Kind</th><th>Size</th><th>Licence</th><th>Where</th><th>Status</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.name}><td>{r.name}</td><td className="ink2">{r.kind}</td><td>{r.count}</td><td className="ink2">{r.licence}</td><td className="ink2">{r.where}</td>
      <td>{r.needs_person ? <span className="chip flag">{r.needs_person}</span> : r.ready ? 'Ready' : 'Not ready'}</td></tr>)}</tbody></table></div></div>
}
