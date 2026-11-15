// The results dashboard (#19): how the run was made, every number it produced as tables, and exports. Everything on it
// comes from run_get, the same record the agent reads, so the page and the files it saves always agree. A region is
// marked only when the project itself chose it; with none chosen, every region read is listed and none is promoted.
import { useEffect, useMemo, useState } from 'react'
import { call, fmt, regionLabel } from './api'
import { Icon } from './icons'
import { MiniInterval } from './charts'

type Contrast = {
  contrast: string; region: string; chosen: boolean; value: number; ci_low: number | null; ci_high: number | null; n: number | null
  n_by_condition?: Record<string, number> | null; units_positive?: number | null; area_rank_pct?: number | null
  shuffled_low?: number | null; shuffled_high?: number | null; shuffled_at_least_as_far?: number | null; vjepa_random_map?: number | null
  pairs_needed?: number | null; window_s?: [number, number] | null; units?: string | null; design?: string | null
}
type Trial = { index: number; unit: string; condition: string; label: string; clip?: string; image?: string; origin?: string; readout: Record<string, number> }
type Stimulus = { condition: string; clips: number; files?: number; origin?: string | null; dataset?: string | null; cosmos?: { prompt?: string; seeds?: number[]; control?: string } | null }
export type RunRecord = {
  project: { id: string; title: string; question: string; status: string }
  made: Record<string, any>; stimuli: Stimulus[]; regions_chosen: string[]; regions_read: string[]
  contrasts: Contrast[]; trials: Trial[]; other_analyses: any[]; missing: string[]
}

const when = (t?: number) => t ? new Date(t * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short' }) : 'Not recorded'
const pct = (v?: number | null) => v == null ? '–' : `${(100 * v).toFixed(v < 0.01 ? 1 : 0)}%`
const cell = (v: unknown) => v == null ? '' : typeof v === 'number' ? String(v) : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v)
function save(name: string, text: string, type: string) {
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; a.click()
  setTimeout(() => URL.revokeObjectURL(a.href), 2000)
}
const DESIGN: Record<string, string> = { event: 'Event design', block: 'Block design' }

type Col = { key: string; head: string; title?: string; num?: boolean; get: (c: Contrast) => number | string | null | undefined; show: (c: Contrast) => any }
const COLS: Col[] = [
  { key: 'contrast', head: 'Contrast', get: c => c.contrast, show: c => c.contrast },
  { key: 'region', head: 'Region', get: c => regionLabel(c.region), show: c => <span title={c.region}>{regionLabel(c.region)}{c.chosen && <span className="chip tiny">Chosen</span>}</span> },
  { key: 'value', head: 'TRIBE value', num: true, title: 'Mean difference in TRIBE units over the read-out window', get: c => c.value, show: c => fmt(c.value) },
  { key: 'ci', head: '95% interval', num: true, get: c => c.ci_low, show: c => c.ci_low == null ? '–' : `${fmt(c.ci_low)} to ${fmt(c.ci_high!)}` },
  { key: 'bar', head: '', get: () => null, show: c => c.ci_low == null ? null : <MiniInterval value={c.value} interval={[c.ci_low, c.ci_high!]} scale={0} /> },
  { key: 'n', head: 'n', num: true, title: 'Clips or pairs in the contrast', get: c => c.n, show: c => c.n_by_condition ? <span title={Object.entries(c.n_by_condition).map(([k, v]) => `${v} ${k}`).join(', ')}>{c.n}</span> : (c.n ?? '–') },
  { key: 'pos', head: 'Above zero', num: true, title: 'Pairs whose own difference is above zero', get: c => c.units_positive == null ? null : c.units_positive / (c.n || 1), show: c => c.units_positive == null ? '–' : `${c.units_positive} of ${c.n}` },
  { key: 'rank', head: 'Rank among 360 areas', num: true, title: "How far above the cortex's 360 HCP areas this region's difference ranks", get: c => c.area_rank_pct, show: c => c.area_rank_pct == null ? '–' : `above ${c.area_rank_pct}%` },
  { key: 'shuf', head: 'Shuffled labels, 95%', num: true, title: 'The same contrast with condition labels shuffled', get: c => c.shuffled_high, show: c => c.shuffled_low == null ? '–' : `${fmt(c.shuffled_low)} to ${fmt(c.shuffled_high!)}` },
  { key: 'p', head: 'Shuffles as far', num: true, title: 'Share of shuffles at least as far from zero', get: c => c.shuffled_at_least_as_far, show: c => pct(c.shuffled_at_least_as_far) },
  { key: 'vjepa', head: 'Video features only', num: true, title: 'The same contrast from V-JEPA 2 features through a fixed random map: no brain mapping', get: c => c.vjepa_random_map, show: c => c.vjepa_random_map == null ? '–' : fmt(c.vjepa_random_map) },
]

export function ResultsView({ pid, status, region, onPickRegion, onOpenTrial }: {
  pid: string; status: string; region: string; onPickRegion: (r: string) => void; onOpenTrial: (i: number, unit: string) => void
}) {
  const [rec, setRec] = useState<RunRecord | null>(null); const [err, setErr] = useState('')
  const [scope, setScope] = useState<'chosen' | 'all'>('chosen'); const [sort, setSort] = useState<{ key: string; dir: number } | null>(null)
  useEffect(() => {
    setRec(null); setErr(''); setSort(null)
    if (status === 'Done') call<RunRecord>('run_get', { project_id: pid }).then(r => { setRec(r); setScope(r.regions_chosen.length ? 'chosen' : 'all') }).catch(e => setErr(String(e?.message ?? e)))
  }, [pid, status])
  const rows = useMemo(() => {
    if (!rec) return []
    const out = rec.contrasts.filter(c => scope === 'all' || c.chosen)
    if (!sort) return out
    const col = COLS.find(c => c.key === sort.key)!
    return [...out].sort((a, b) => { const x = col.get(a), y = col.get(b); if (x == null) return 1; if (y == null) return -1; return sort.dir * (typeof x === 'number' ? (x as number) - (y as number) : String(x).localeCompare(String(y))) })
  }, [rec, scope, sort])
  if (status !== 'Done') return <div className="empty">The results appear here when the run finishes.</div>
  if (err) return <div className="empty">Could not read this run's record: {err}</div>
  if (!rec) return <div className="empty" role="status"><span className="spin" /> Reading the run's record</div>

  const m = rec.made; const scale = Math.max(...rec.contrasts.flatMap(c => [c.ci_low, c.ci_high, c.value].filter((v): v is number => v != null).map(Math.abs)), 1e-6)
  const cols = COLS.filter(c => rec.contrasts.some(r => c.key === 'contrast' || c.key === 'region' || c.key === 'bar' ? true : c.get(r) != null))
  const trialRegions = rec.regions_chosen.length ? rec.regions_chosen.filter(r => rec.regions_read.includes(r)) : rec.regions_read
  const windows = [...new Set(rec.contrasts.map(c => c.window_s ? `seconds ${c.window_s[0]} to ${c.window_s[1]}` : '').filter(Boolean))]
  const cosmos = rec.stimuli.filter(s => s.cosmos)
  const conn = (role: string) => (m.connectors ?? []).filter((c: any) => c.role === role).map((c: any) => `${c.name} (${c.version}${c.recorded === false ? ', current' : ''})`).join(', ')
  const t = m.trial
  const base = rec.project.title.replace(/[^\w]+/g, '_').slice(0, 60)

  const contrastsCsv = () => save(`${base}_contrasts.csv`, [
    ['contrast', 'region', 'region_name', 'chosen_by_project', 'tribe_value', 'ci95_low', 'ci95_high', 'n', 'n_by_condition', 'units_above_zero', 'rank_among_360_areas_pct',
      'shuffled_labels_ci95_low', 'shuffled_labels_ci95_high', 'shuffles_at_least_as_far', 'video_features_random_map', 'pairs_needed', 'window_start_s', 'window_end_s', 'units'].join(','),
    ...rec.contrasts.map(c => [c.contrast, c.region, regionLabel(c.region), c.chosen, c.value, c.ci_low, c.ci_high, c.n,
      c.n_by_condition ? Object.entries(c.n_by_condition).map(([k, v]) => `${k}:${v}`).join('; ') : '', c.units_positive, c.area_rank_pct,
      c.shuffled_low, c.shuffled_high, c.shuffled_at_least_as_far, c.vjepa_random_map, c.pairs_needed, c.window_s?.[0], c.window_s?.[1], c.units].map(cell).join(','))].join('\n'), 'text/csv')
  const trialsCsv = () => save(`${base}_trials.csv`, [
    ['index', 'unit', 'condition', 'label', 'source', 'clip', ...rec.regions_read].map(cell).join(','),
    ...rec.trials.map(x => [x.index, x.unit, x.condition, x.label, x.origin, x.clip ? location.origin + x.clip : '', ...rec.regions_read.map(r => x.readout[r])].map(cell).join(','))].join('\n'), 'text/csv')
  const recordJson = () => save(`${base}_run_record.json`, JSON.stringify(rec, null, 1), 'application/json')

  return <div className="dash">
    <div className="bar dashbar">
      <h2 className="section-title" style={{ margin: 0 }}>Results</h2>
      <span className="ink2">{m.finished_at ? `Finished ${when(m.finished_at)}` : 'Finish time not recorded'}</span>
      <span className="bar exports">
        <button className="btn" onClick={contrastsCsv}><Icon name="download" size={16} />Contrasts CSV</button>
        <button className="btn" onClick={trialsCsv}><Icon name="download" size={16} />Trials CSV</button>
        <button className="btn" onClick={recordJson}><Icon name="download" size={16} />Run record JSON</button>
      </span>
    </div>

    <div className="stats">
      <div className="stat"><span className="k">Clips</span><span className="v">{rec.trials.length}</span></div>
      <div className="stat"><span className="k">Conditions</span><span className="v">{rec.stimuli.length}</span></div>
      <div className="stat"><span className="k">Contrasts</span><span className="v">{new Set(rec.contrasts.map(c => c.contrast)).size}</span></div>
      <div className="stat"><span className="k">Regions read</span><span className="v">{rec.regions_read.length}</span></div>
      <div className="stat"><span className="k">Run time</span><span className="v">{m.minutes != null ? `${m.minutes} min` : '–'}</span></div>
    </div>

    <div className="grid2">
      <section className="card">
        <h3>How this run was made</h3>
        <div className="kv made">
          <span className="k">Started</span><span>{when(m.started_at)}{m.started_by ? `, by the ${m.started_by}` : ''}</span>
          <span className="k">Brain model</span><span>{m.brain_model}{conn('neural model') ? `; ${conn('neural model')}` : ''}</span>
          {windows.length > 0 && <><span className="k">Read over</span><span>{windows.join('; ')} of each clip</span></>}
          {conn('renderer') && <><span className="k">Renderer</span><span>{conn('renderer')}{m.renderer_revisions?.length ? `; ${m.renderer_revisions.join(', ')}` : ''}</span></>}
          {conn('generator') && <><span className="k">Generator</span><span>{conn('generator')}</span></>}
          {t && <><span className="k">Design</span><span>{[`${DESIGN[t.design] ?? t.design}: ${t.items_per_trial ?? 1} item${(t.items_per_trial ?? 1) > 1 ? 's' : ''}${t.item_s != null ? ` of ${t.item_s} s` : ''}`,
            t.rest_s != null ? `${t.rest_s} s rest` : null, t.trials_per_condition != null ? `${t.trials_per_condition} trials per condition` : null, t.paired ? 'paired' : null,
            t.seed != null ? `seed ${t.seed}` : null].filter(Boolean).join(', ')}</span></>}
          {m.parameters && Object.keys(m.parameters).length > 0 && <><span className="k">Parameters</span><span>{Object.entries(m.parameters).map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`).join(', ')}</span></>}
          <span className="k">Regions</span><span>{rec.regions_chosen.length ? `Chosen by the project: ${rec.regions_chosen.map(regionLabel).join(', ')}` : 'None chosen by the project'}</span>
          <span className="k">Code</span><span className="num">{m.code ?? 'Not recorded'}</span>
        </div>
        {rec.missing.length > 0 && <p className="muted" style={{ marginBottom: 0 }}>This run is older than run records, so it did not record {rec.missing.join(', ')}.</p>}
      </section>
      <section className="card">
        <h3>Stimuli</h3>
        <div className="tablewrap"><table className="data">
          <thead><tr><th>Condition</th><th className="num">Clips</th><th>Source</th></tr></thead>
          <tbody>{rec.stimuli.map(s => <tr key={s.condition}><td>{s.condition}</td><td className="num">{s.clips}</td>
            <td className="ink2">{s.origin ?? '–'}{s.dataset ? `, ${s.dataset}` : ''}</td></tr>)}</tbody>
        </table></div>
        {cosmos.map(s => <p key={s.condition} className="ink2" style={{ marginBottom: 0 }}>{s.condition} through Cosmos: {s.cosmos!.control} control, seeds {s.cosmos!.seeds?.join(', ')}. Prompt: “{s.cosmos!.prompt}”</p>)}
      </section>
    </div>

    <section className="card">
      <div className="bar" style={{ marginBottom: 10 }}>
        <h3 style={{ margin: 0 }}>Contrasts</h3>
        {rec.regions_chosen.length ? <div className="seg" role="group" aria-label="Regions shown">
          <button className={scope === 'chosen' ? 'on' : ''} onClick={() => setScope('chosen')}>Chosen regions ({rec.contrasts.filter(c => c.chosen).length})</button>
          <button className={scope === 'all' ? 'on' : ''} onClick={() => setScope('all')}>All regions ({rec.contrasts.length})</button>
        </div> : <span className="ink2">The project chose no region, so every region read is listed.</span>}
        <span className="muted" style={{ marginLeft: 'auto' }}>Click a heading to sort, a row to follow that region</span>
      </div>
      <div className="tablewrap"><table className="data contrasts">
        <thead><tr>{cols.map(c => <th key={c.key} className={c.num ? 'num' : ''} title={c.title} aria-sort={sort?.key === c.key ? (sort.dir < 0 ? 'descending' : 'ascending') : 'none'}
          onClick={() => c.key !== 'bar' && setSort(s => ({ key: c.key, dir: s?.key === c.key ? -s.dir : c.num ? -1 : 1 }))}>{c.head}{sort?.key === c.key ? (sort.dir < 0 ? ' ↓' : ' ↑') : ''}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={`${r.contrast}|${r.region}|${i}`} className={r.region === region ? 'on' : ''} onClick={() => onPickRegion(r.region)} style={{ cursor: 'pointer' }}>
          {cols.map(c => <td key={c.key} className={c.num ? 'num' : ''}>{c.key === 'bar' ? (r.ci_low == null ? null : <MiniInterval value={r.value} interval={[r.ci_low, r.ci_high!]} scale={scale} />) : c.show(r)}</td>)}</tr>)}</tbody>
      </table></div>
      <p className="muted" style={{ marginBottom: 0 }}>TRIBE v2 predicts an average viewer's fMRI response from the video; these are predictions, not measured brains.</p>
    </section>

    <section className="card">
      <div className="bar" style={{ marginBottom: 10 }}><h3 style={{ margin: 0 }}>Trials</h3>
        <span className="ink2">{rec.trials.length} clips, response in {rec.regions_chosen.length ? 'the chosen regions' : 'every region read'}; the Trials CSV has every region</span></div>
      <div className="tablewrap tall"><table className="data">
        <thead><tr><th className="num">#</th><th>Condition</th><th>Unit</th><th>Clip</th>{trialRegions.map(r => <th key={r} className="num" title={r}>{regionLabel(r)}</th>)}</tr></thead>
        <tbody>{rec.trials.map((x, i) => <tr key={i} onClick={() => onOpenTrial(i, x.unit)} style={{ cursor: 'pointer' }}>
          <td className="num">{(x.index ?? i) + 1}</td><td>{x.condition}</td><td className="ink2">{x.unit}</td><td className="ink2 clipname">{x.label}</td>
          {trialRegions.map(r => <td key={r} className="num">{fmt(x.readout[r])}</td>)}</tr>)}</tbody>
      </table></div>
    </section>
  </div>
}
