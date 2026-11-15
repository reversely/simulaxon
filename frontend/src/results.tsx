// A run's results as a dashboard (#20), laid out as the TRIBE v2 paper shows an in-silico experiment (Fig. 4): the
// response over time by condition, each contrast over the whole cortex, every HCP area ranked; then numbered tables.
// Everything comes from run_get, the record the agent reads too, and every download is built by the server from the
// same record. Names appear as written. No region is promoted: regions named at set-up are labelled with who named
// them, and a person's pick only highlights a row.
import { useEffect, useMemo, useRef, useState } from 'react'
import { call, fmt, regionLabel } from './api'
import { Icon } from './icons'
import { MiniInterval } from './charts'
import { ConditionCourse } from './experiment'

type Contrast = {
  contrast: string; region: string; named_by?: string | null; value: number; ci_low: number | null; ci_high: number | null; n: number | null
  n_by_condition?: Record<string, number> | null; units_positive?: number | null; area_rank_pct?: number | null
  shuffled_low?: number | null; shuffled_high?: number | null; shuffled_at_least_as_far?: number | null; vjepa_random_map?: number | null
  window_s?: [number, number] | null; expected?: { direction?: string; source?: string } | null
}
export type LiveTrial = { index: number; unit: string; condition: string; label: string; image?: string; clip?: string; readout: Record<string, number> }
type Trial = LiveTrial & { origin?: string }
type Named = { region: string; named_by: string; definition: string; hcp_areas: string[] }
type Figure = { title: string; weights: Record<string, number>; window_s: [number, number | null]; views: Record<string, string>; areas: { area: string; value: number; rank: number }[] }
type Stimulus = { condition: string; clips: number; origin?: string | null; dataset?: string | null; dataset_ref?: string | null; cosmos?: { prompt?: string; seeds?: number[]; control?: string } | null }
type RunRecord = {
  project: { id: string; title: string; question: string; status: string }
  made: Record<string, any>; stimuli: Stimulus[]; regions_named: Named[]; regions_read: string[]
  contrasts: Contrast[]; trials: Trial[]; figures: Figure[]; downloads: string[]; missing: string[]
}

const when = (t?: number) => t ? new Date(t * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'Not recorded'
const pct = (v?: number | null) => v == null ? '–' : `${(100 * v).toFixed(v < 0.01 ? 1 : 0)}%`
const VIEW_NAMES: Record<string, string> = { left: 'Left', right: 'Right', ventral: 'Underside', posterior: 'Back' }
const thumb = (u?: string) => u?.startsWith('/files/') ? '/thumb/' + u.slice('/files/'.length) : u

function Download({ pid, names, figures }: { pid: string; names: string[]; figures: Figure[] }) {
  const [open, setOpen] = useState(false); const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const off = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); setOpen(false) } }
    document.addEventListener('mousedown', off); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc) }
  }, [open])
  const label = (n: string) => {
    if (n === 'all.zip') return 'Everything, one zip'
    if (n === 'run_settings.json') return 'Run settings (JSON)'
    if (n.startsWith('table1')) return 'Table 1, regions and contrasts (CSV)'
    if (n.startsWith('table2')) return 'Table 2, trials (CSV)'
    if (n.startsWith('fig3')) return 'Fig. 3, the 360 areas by contrast (CSV)'
    const m = n.match(/^fig2_map(\d+)_.*?(?:_(left|right|ventral|posterior))?\.(npy|png)$/)
    if (m) { const f = figures[Number(m[1]) - 1]?.title ?? `Map ${m[1]}`; return m[3] === 'npy' ? `Fig. 2, ${f}: values per vertex, fsaverage5 (.npy)` : `Fig. 2, ${f}: ${VIEW_NAMES[m[2]] ?? m[2]} view (PNG)` }
    return n
  }
  const groups: [string, string[]][] = [['Tables', names.filter(n => n.startsWith('table'))], ['Figures', names.filter(n => n.startsWith('fig'))],
    ['Run', names.filter(n => n === 'run_settings.json')], ['', names.filter(n => n === 'all.zip')]]
  return <div className="dl" ref={ref}>
    <button className="btn" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(o => !o)}><Icon name="download" size={16} />Download<span aria-hidden>▾</span></button>
    {open && <div className="dlmenu" role="menu">
      {groups.filter(([, xs]) => xs.length).map(([g, xs]) => <div key={g || 'all'} className="dlgroup">{g && <div className="dlhead">{g}</div>}
        {xs.map(n => <a key={n} role="menuitem" href={`/api/results/${pid}/download/${n}`} download onClick={() => setOpen(false)}>{label(n)}</a>)}</div>)}
    </div>}
  </div>
}

/** Fig. 3: every HCP area for one contrast, ranked, with the areas of the named regions coloured. */
function AreaRanks({ fig, named }: { fig: Figure; named: Named[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const mine = new Set(named.flatMap(n => n.hcp_areas)); const a = fig.areas; const W = 900, H = 170, L = 44, T = 10, B = 22, PW = W - L - 8, PH = H - T - B
  const lo = Math.min(0, ...a.map(x => x.value)), hi = Math.max(0, ...a.map(x => x.value)); const y = (v: number) => T + (hi - v) / ((hi - lo) || 1) * PH; const bw = PW / a.length
  const hits = a.filter(x => mine.has(x.area))
  return <div className="figpanel">
    <div className="legend"><span><i style={{ background: 'var(--a)' }} />Areas in the named regions</span><span><i style={{ background: 'var(--ink-3)' }} />Other areas</span>
      {hover != null && <span className="num"><b>{a[hover].area}</b> {fmt(a[hover].value)}, rank {a[hover].rank} of {a.length}</span>}</div>
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${fig.title}: all ${a.length} HCP areas ranked`} onMouseLeave={() => setHover(null)}>
      <line x1={L} x2={W - 8} y1={y(0)} y2={y(0)} stroke="var(--rule-strong)" />
      {[hi, 0, lo].filter((v, i, xs) => xs.indexOf(v) === i).map(v => <text key={v} x={L - 6} y={y(v) + 4} textAnchor="end" className="axis">{fmt(v, 2)}</text>)}
      {a.map((x, i) => <rect key={x.area} x={L + i * bw} y={Math.min(y(x.value), y(0))} width={Math.max(1, bw - 0.6)} height={Math.max(1, Math.abs(y(x.value) - y(0)))}
        fill={mine.has(x.area) ? 'var(--a)' : 'var(--ink-3)'} opacity={hover == null || hover === i ? 1 : 0.55} onMouseEnter={() => setHover(i)} />)}
      <text x={L} y={H - 4} className="axis">Rank 1</text><text x={W - 8} y={H - 4} textAnchor="end" className="axis">Rank {a.length}</text>
    </svg>
    {hits.length > 0 ? <p className="ink2 small">{hits.map(x => `${x.area} rank ${x.rank}`).join(', ')}</p>
      : <p className="ink2 small">{named.length ? 'The named regions are anatomical groups, not HCP areas, so none is coloured.' : 'No region was named, so none is coloured.'}</p>}
  </div>
}

export function ResultsView({ pid, status, progress, live, focus, agentName, onPickRegion, onOpenTrial }: {
  pid: string; status: string; progress?: { done: number; total: number; stage?: string }; live?: LiveTrial[]; focus: string; agentName: string
  onPickRegion: (r: string) => void; onOpenTrial: (i: number, unit: string) => void
}) {
  const [rec, setRec] = useState<RunRecord | null>(null); const [err, setErr] = useState('')
  const [scope, setScope] = useState<'named' | 'all'>('named'); const [sort, setSort] = useState<{ key: keyof Contrast; dir: number } | null>(null)
  useEffect(() => {
    setRec(null); setErr(''); setSort(null)
    if (status === 'Done') call<RunRecord>('run_get', { project_id: pid }).then(r => { setRec(r); setScope(r.regions_named.length ? 'named' : 'all') }).catch(e => setErr(String(e?.message ?? e)))
  }, [pid, status])
  const by = (who?: string | null) => who === 'agent' ? agentName : who === 'person' ? 'you' : who === 'paper' ? 'the paper' : 'set-up'
  const rows = useMemo(() => {
    if (!rec) return []
    const out = rec.contrasts.filter(c => scope === 'all' || c.named_by)
    if (!sort) return out
    return [...out].sort((a, b) => { const x = a[sort.key] as any, y = b[sort.key] as any; if (x == null) return 1; if (y == null) return -1; return sort.dir * (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) })
  }, [rec, scope, sort])

  if (status === 'Running') {   // during a run: the header counts trials and Table 2 fills in as each one finishes
    const regs = [...new Set((live ?? []).flatMap(t => Object.keys(t.readout)))]
    return <div className="dash">
      <div className="card runhead"><span className="chip flag">Running{progress?.total ? `, ${progress.done} of ${progress.total} trials` : ''}</span>
        <span className="ink2">{progress?.stage === 'comparing' ? 'Every trial is in; computing the contrasts, baselines and maps' : 'The figures and Table 1 are computed once every trial is in'}</span></div>
      <section className="card"><h3>Table 2. Trials so far</h3>
        {live?.length ? <div className="tablewrap tall"><table className="data"><thead><tr><th>Trial</th><th>Stimulus</th><th>Condition</th>{regs.map(r => <th key={r} className="num" title={r}>{regionLabel(r)}</th>)}</tr></thead>
          <tbody>{live.map(t => <tr key={t.index}><td className="num">{t.index + 1}</td><td>{t.image && <img className="thumbcell" src={thumb(t.image)} alt={t.label} />}</td><td>{t.condition}</td>
            {regs.map(r => <td key={r} className="num">{fmt(t.readout[r])}</td>)}</tr>)}</tbody></table></div>
          : <p className="ink2">Trials appear here as TRIBE reads each one.</p>}
      </section>
    </div>
  }
  if (status !== 'Done') return <div className="empty">This project has no finished run yet.</div>
  if (err) return <div className="empty">Could not read this run's record: {err}</div>
  if (!rec) return <div className="empty" role="status"><span className="spin" /> Reading the run's record</div>

  const m = rec.made; const t = m.trial ?? {}
  const scale = Math.max(...rec.contrasts.flatMap(c => [c.ci_low, c.ci_high, c.value].filter((v): v is number => v != null).map(Math.abs)), 1e-6)
  const named = rec.regions_named; const namedNames = named.map(n => n.region)
  const plotted = focus && !namedNames.includes(focus) ? [...namedNames, focus] : namedNames
  const tribe = (m.connectors ?? []).find((c: any) => c.name === 'tribe_v2')
  const sources = [...new Set(rec.stimuli.map(s => s.dataset ? `${s.dataset}${s.dataset_ref ? ` (${s.dataset_ref})` : ''}` : s.origin ?? '').filter(Boolean))]
  const seed = t.seed ?? m.parameters?.seed
  const window = rec.contrasts.find(c => c.window_s)?.window_s
  const trialRegions = [...namedNames.filter(r => rec.regions_read.includes(r)), ...rec.regions_read.filter(r => !namedNames.includes(r))]
  const head = (k: keyof Contrast, text: string, num = true, title?: string) => <th className={num ? 'num' : ''} title={title} aria-sort={sort?.key === k ? (sort.dir < 0 ? 'descending' : 'ascending') : 'none'}
    onClick={() => setSort(s => ({ key: k, dir: s?.key === k ? -s.dir : num ? -1 : 1 }))}>{text}{sort?.key === k ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}</th>
  const has = (k: keyof Contrast) => rec.contrasts.some(c => c[k] != null)

  return <div className="dash">
    <div className="card runhead">
      <h3 className="runid">{m.run_id ? <>Run <span className="num">{m.run_id}</span></> : 'Last run'}</h3>
      <span className="chip">Finished</span>
      <div className="runfacts">
        {m.started_at && <span><span className="k">Started</span> {when(m.started_at)}{m.started_by ? `, by ${by(m.started_by)}` : ''}</span>}
        {m.minutes != null && <span><span className="k">Took</span> {m.minutes} min</span>}
        <span><span className="k">Trials</span> {rec.trials.length}</span>
        <span><span className="k">Model</span> TRIBE v2, average subject{tribe ? ` (${tribe.version}${tribe.recorded === false ? ', current' : ''})` : ''}</span>
        {sources.length > 0 && <span><span className="k">Stimuli</span> {sources.join('; ')}</span>}
        {seed != null && <span><span className="k">Seed</span> {seed}</span>}
      </div>
      <Download pid={pid} names={rec.downloads} figures={rec.figures} />
    </div>
    {(rec.missing.length > 0 || !m.started_at || seed == null) && <p className="muted" style={{ margin: 0 }}>Not recorded by this run: {[...(m.started_at ? [] : ['its start and duration']), ...(m.run_id ? [] : ['a run ID']), ...rec.missing, ...(seed == null ? ['a seed'] : [])].join(', ')}.</p>}

    <figure className="card fig">
      <figcaption><b>Fig. 1.</b> Response over time by condition{plotted.length ? `, ${plotted.map(regionLabel).join(', ')}` : ''}: the mean of each condition's trials.</figcaption>
      {plotted.length ? <div className="figgrid">{plotted.map(r => <div key={r}><div className="figtag">{r === focus && !namedNames.includes(r) ? 'Your pick' : `Named by ${by(named.find(n => n.region === r)?.named_by)}`}</div>
        <ConditionCourse pid={pid} region={r} onS={t.item_s ?? window?.[1]} /></div>)}</div>
        : <p className="ink2">No region was named for this project. Pick one in Table 1 to plot it here.</p>}
    </figure>

    {rec.figures.some(f => Object.keys(f.views).length) && <figure className="card fig">
      <figcaption><b>Fig. 2.</b> Each contrast over the whole cortex, unthresholded, from TRIBE v2's plotter. Read over seconds {window ? `${window[0]} to ${window[1]}` : 'on screen'}.</figcaption>
      {rec.figures.map(f => <div key={f.title} className="mapsrow"><div className="mid">{f.title}</div>
        <div className="maps">{Object.entries(f.views).map(([v, u]) => <div key={v}><img src={u} alt={`${f.title}, ${VIEW_NAMES[v] ?? v}`} /><span className="ink2 small">{VIEW_NAMES[v] ?? v}</span></div>)}</div></div>)}
    </figure>}

    {rec.figures.length > 0 && <figure className="card fig">
      <figcaption><b>Fig. 3.</b> All {rec.figures[0].areas.length} HCP-MMP1 areas for each contrast, ranked by value.</figcaption>
      {rec.figures.map(f => <div key={f.title}><div className="mid">{f.title}</div><AreaRanks fig={f} named={named} /></div>)}
    </figure>}

    <section className="card">
      <div className="bar" style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Table 1. Regions and contrasts</h3>
        {named.length > 0 && <div className="seg" role="group" aria-label="Regions in the table">
          <button className={scope === 'named' ? 'on' : ''} onClick={() => setScope('named')}>Named regions ({rec.contrasts.filter(c => c.named_by).length})</button>
          <button className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>All regions read ({rec.contrasts.length})</button>
        </div>}
      </div>
      <div className="tablewrap"><table className="data contrasts">
        <thead><tr>{head('contrast', 'Contrast', false)}{head('region', 'Region', false)}<th>Named by</th>{has('expected') && <th>Expected</th>}{head('value', 'TRIBE value', true, 'Mean difference over the read-out window')}
          {head('ci_low', '95% interval')}<th aria-hidden />{head('n', 'n')}{has('units_positive') && head('units_positive', 'Above zero')}
          {has('area_rank_pct') && head('area_rank_pct', 'Rank among 360 areas')}{has('shuffled_high') && head('shuffled_high', 'Shuffled labels, 95%')}
          {has('shuffled_at_least_as_far') && head('shuffled_at_least_as_far', 'Shuffles as far')}{has('vjepa_random_map') && head('vjepa_random_map', 'Video features only', true, 'V-JEPA 2 features through a fixed random map: no brain mapping')}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={`${r.contrast}|${r.region}|${i}`} className={r.region === focus ? 'on' : ''} onClick={() => onPickRegion(r.region)} style={{ cursor: 'pointer' }}>
          <td>{r.contrast}</td><td title={r.region}>{regionLabel(r.region)}</td><td className="ink2">{r.named_by ? by(r.named_by) : '–'}</td>{has('expected') && <td>{r.expected ? `${(r.expected.direction ?? '').replace(/^./, c => c.toUpperCase())} (${r.expected.source ?? 'recorded before the run'})` : '–'}</td>}
          <td className="num">{fmt(r.value)}</td><td className="num">{r.ci_low == null ? '–' : `${fmt(r.ci_low)} to ${fmt(r.ci_high!)}`}</td>
          <td>{r.ci_low != null && <MiniInterval value={r.value} interval={[r.ci_low, r.ci_high!]} scale={scale} />}</td>
          <td className="num" title={r.n_by_condition ? Object.entries(r.n_by_condition).map(([k, v]) => `${k}: ${v}`).join(', ') : undefined}>{r.n ?? '–'}</td>
          {has('units_positive') && <td className="num">{r.units_positive == null ? '–' : `${r.units_positive} of ${r.n}`}</td>}
          {has('area_rank_pct') && <td className="num">{r.area_rank_pct == null ? '–' : `Above ${r.area_rank_pct}%`}</td>}
          {has('shuffled_high') && <td className="num">{r.shuffled_low == null ? '–' : `${fmt(r.shuffled_low)} to ${fmt(r.shuffled_high!)}`}</td>}
          {has('shuffled_at_least_as_far') && <td className="num">{pct(r.shuffled_at_least_as_far)}</td>}
          {has('vjepa_random_map') && <td className="num">{r.vjepa_random_map == null ? '–' : fmt(r.vjepa_random_map)}</td>}</tr>)}</tbody>
      </table></div>
      <div className="tablenote">
        <p>TRIBE v2 is Meta's model that predicts an average viewer's fMRI response from video. Values are its output (z-scored BOLD), the mean over seconds {window ? `${window[0]} to ${window[1]}` : 'on screen'} of each clip. Click a row to highlight its region.</p>
        <p>Expected: the direction recorded before the run, from the paper or the project's question. Rank among 360 areas: where the value falls among TRIBE's 360 HCP-MMP1 areas (Glasser et al., 2016). Shuffled labels: the same contrast with the condition labels shuffled, and the share of shuffles at least as far from zero. Video features only: V-JEPA 2 video features through a fixed random map, with no brain mapping.</p>
        {named.length ? named.map(n => <p key={n.region}><b>{n.region}</b>, named by {by(n.named_by)}: {n.definition}.</p>) : <p>No region was named for this project; every region read is listed.</p>}
      </div>
    </section>

    <section className="card">
      <h3>Table 2. Trials</h3>
      <div className="tablewrap tall"><table className="data">
        <thead><tr><th>Trial</th><th>Stimulus</th><th>Condition</th><th>Unit</th>{trialRegions.map(r => <th key={r} className="num" title={r}>{regionLabel(r)}</th>)}</tr></thead>
        <tbody>{rec.trials.map((x, i) => <tr key={i} onClick={() => onOpenTrial(i, x.unit)} style={{ cursor: 'pointer' }}>
          <td className="num">{(x.index ?? i) + 1}</td><td>{x.image && <img className="thumbcell" src={thumb(x.image)} alt={x.label} loading="lazy" />}</td>
          <td>{x.condition}</td><td className="ink2">{x.unit}</td>{trialRegions.map(r => <td key={r} className="num">{fmt(x.readout[r])}</td>)}</tr>)}</tbody>
      </table></div>
      <div className="tablenote"><p>One row per clip; TRIBE v2 value per region, in Table 1's units. Click a row to open the trial.</p></div>
    </section>
  </div>
}
