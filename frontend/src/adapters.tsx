/** A dataset's adapters (#28): fit one in one action, and see how it does on held-out categories beside TRIBE v2 as
 * released, shuffled labels and the noise ceiling, per area on the cortex and in a table. lab/adapter.py has the method. */
import { useEffect, useState } from 'react'
import { call, fmt } from './api'
import { MapBrain } from './brain3d'

type Summary = { median: number; interval_95: [number, number] }
type Area = { area: string; adapter_r: number; tribe_v2_r: number; shuffled_r: number; ceiling: number; reliable: boolean }
type Adapter = { id: string; name: string; dataset_id: string; source: string; people: number; categories: number; clips: number; reliable_areas: number
  split: { kind: string; held_out: number; training: number }; input: string; target: string; summary: Record<'adapter' | 'tribe_v2' | 'shuffled' | 'ceiling', Summary>; areas?: Area[]; benchmark?: string
  lab_baselines?: { rows: LabRow[]; areas: number; categories: number; note: string } | null; live?: Live[] }
type LabRow = { name: string; features: string; median: number; interval_95?: [number, number] | null }
type Verdict = { project_id: string; result: string; area_rank_pct: number | null }
type Live = { title: string; contrast: string; region: string; direction: string; where: string | null; adapter: Verdict; released: Verdict | null }

const ROWS: [keyof Adapter['summary'], string][] = [['adapter', 'Adapter'], ['tribe_v2', 'TRIBE v2 as released'], ['shuffled', 'Adapter, labels shuffled'], ['ceiling', 'Noise ceiling']]
const MAPS: [string, string, string][] = [   // key, button, legend
  ['adapter_r', 'Adapter', 'r between the adapter\'s prediction and measured fMRI, per area: red to yellow where it follows the measured response, blue where it runs against it.'],
  ['tribe_v2_r', 'TRIBE v2', 'r between TRIBE v2\'s own prediction, as released, and measured fMRI, per area: red to yellow where it follows the measured response, blue where it runs against it.'],
  ['gain', 'Difference', 'Adapter r minus TRIBE v2 r, per area: red where the adapter is better, blue where TRIBE v2 as released is better.']]
const BAR_LO = -0.1, BAR_HI = 0.8   // the bars' r axis: shuffled labels sit near 0, the ceiling under 0.8
const barX = (r: number) => `${100 * (Math.min(BAR_HI, Math.max(BAR_LO, r)) - BAR_LO) / (BAR_HI - BAR_LO)}%`

/** One median as a bar from zero, with its 95% interval when there is one. */
function Bar({ k, label, m, ci }: { k: string; label: string; m: number; ci?: [number, number] | null }) {
  return <div className={`benchbar ${k}`}>
    <span className="lbl">{label}</span>
    <span className="track"><i className="zero" style={{ left: barX(0) }} /><i className="fill" style={{ left: barX(Math.min(0, m)), right: `calc(100% - ${barX(Math.max(0, m))})` }} />
      {ci && <i className="ci" style={{ left: barX(ci[0]), right: `calc(100% - ${barX(ci[1])})` }} />}</span>
    <span className="num val">{fmt(m)}{ci && <span className="ink2 small"> {fmt(ci[0])} to {fmt(ci[1])}</span>}</span>
  </div>
}

/** The benchmark's four medians, then the lab's readouts on other features scored the same way (#37). */
function BenchBars({ a }: { a: Adapter }) {
  const lab = a.lab_baselines?.rows ?? []
  return <div className="benchbars" role="img" aria-label={`Median r: ${[...ROWS.map(([k, l]) => `${l} ${fmt(a.summary[k].median)}`), ...lab.map(b => `${b.name} ${fmt(b.median)}`)].join(', ')}`}>
    {ROWS.map(([k, label]) => <Bar key={k} k={k} label={label} m={a.summary[k].median} ci={a.summary[k].interval_95} />)}
    {lab.length > 0 && <h5 className="benchgroup">Baselines: readouts fitted on other features</h5>}
    {lab.map(b => <Bar key={b.features} k="labbase" label={b.name} m={b.median} ci={b.interval_95} />)}
  </div>
}

const verdict = (v: Verdict | null) => !v ? <span className="ink2">Not run</span>
  : <>{v.result.startsWith('match') ? 'Match' : v.result.replace(/^no match/, 'No match')}{v.area_rank_pct != null && <span className="ink2 small"> · top {fmt(100 - v.area_rank_pct)}% of areas</span>}</>

/** Experiments run through the adapter that state a paper's result, beside TRIBE v2 as released: match or no match, no r (#37). */
function LiveTable({ live }: { live: Live[] }) {
  return <div className="adapterlive">
    <div className="benchlabel"><h4>Known results on new stimuli</h4><span className="chip">Live</span></div>
    <p className="ink2 small">Experiments on stimuli with no measured fMRI, so no r: whether each paper's reported direction holds in the predicted response.</p>
    <div className="tablewrap"><table className="data compact"><thead><tr><th>Result</th><th>Region</th><th>TRIBE v2 as released</th><th>Through this adapter</th></tr></thead>
      <tbody>{live.map((x, i) => <tr key={i}><td>{x.title}{x.where && <span className="ink2 small"> · {x.where}</span>}</td><td>{x.region}, {x.direction}</td><td>{verdict(x.released)}</td><td>{verdict(x.adapter)}</td></tr>)}</tbody></table></div>
  </div>
}

function AdapterCard({ a }: { a: Adapter }) {
  const [full, setFull] = useState<Adapter | null>(null); const [map, setMap] = useState('adapter_r'); const [all, setAll] = useState(false); const [sortBy, setSortBy] = useState<keyof Area>('adapter_r')
  useEffect(() => { call<any>('adapter_get', { adapter_id: a.id }).then(r => setFull({ id: r.id, ...r.data })).catch(() => {}) }, [a.id])
  const areas = (full?.areas ?? []).filter(x => all || x.reliable).sort((x, y) => typeof x[sortBy] === 'number' ? (y[sortBy] as number) - (x[sortBy] as number) : String(x[sortBy]).localeCompare(String(y[sortBy])))
  const csv = () => {
    const lines = ['area,adapter_r,tribe_v2_r,shuffled_r,ceiling,reliable', ...(full?.areas ?? []).map(x => [x.area, x.adapter_r, x.tribe_v2_r, x.shuffled_r, x.ceiling, x.reliable].join(','))]
    const el = document.createElement('a'); el.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' })); el.download = `${a.id}_areas.csv`; el.click()
  }
  const head = (k: keyof Area, label: string, num = true) => <th className={num ? 'num' : ''} onClick={() => setSortBy(k)} aria-sort={sortBy === k ? 'descending' : 'none'} style={{ cursor: 'pointer' }}>{label}{sortBy === k ? ' ↓' : ''}</th>
  return <div className="card adaptercard">
    <div className="benchlabel"><h3>{a.name}</h3><span className="chip">Benchmark</span><span>{(a.benchmark ?? `Benchmark: held-out categories of the ${a.source.split(',')[0]}`).replace(/^Benchmark: /, '')}</span></div>
    <div className="adapterlead">
      <div className="adaptermap">
        <div className="seg" role="group" aria-label="Map">{MAPS.map(([k, label, legend]) => <button key={k} className={map === k ? 'on' : ''} title={legend} onClick={() => setMap(k)}>{label}</button>)}</div>
        <MapBrain url={`/api/brain/adapter/${a.id}/${map}`} title={`${a.name}: ${map === 'gain' ? 'adapter minus TRIBE v2' : MAPS.find(m => m[0] === map)?.[1]} r per area`} vmax={map === 'gain' ? 0.4 : 0.8} low={map === 'gain' ? 'Δr −0.4' : 'r −0.8'} high={map === 'gain' ? '+0.4' : '+0.8'} />
        <p className="ink2 small maplegend">{MAPS.find(m => m[0] === map)?.[2]}</p>
      </div>
      <div className="adaptersum">
        <h4>Median r over {a.reliable_areas} reliable areas</h4>
        <BenchBars a={a} />
        <p className="ink2 small">{a.source}: {a.clips.toLocaleString()} clips in {a.categories} categories. {a.split.kind === '10-fold over categories' ? 'Scored 10-fold over categories' : `${a.split.held_out} categories held out, ${a.split.training} trained on`}; every score is on categories the fit never saw.</p>
        <p className="ink2 small">r between predicted and measured responses ({a.target}) across held-out categories, per area; reliable: noise ceiling above 0.5, somatomotor areas left out. Line: 95% interval, resampling areas. Input: {a.input}.</p>
        {a.lab_baselines && <p className="ink2 small">{a.lab_baselines.note}</p>}
      </div>
    </div>
    {!!a.live?.length && <LiveTable live={a.live} />}
    <details className="adapterareas">
      <summary>Areas: {all ? 'all 360' : `${a.reliable_areas} reliable`}, r per area</summary>
      <div className="bar"><div className="seg" role="group" aria-label="Areas"><button className={!all ? 'on' : ''} onClick={() => setAll(false)}>Reliable areas</button><button className={all ? 'on' : ''} onClick={() => setAll(true)}>All 360</button></div>
        <button className="btn" style={{ marginLeft: 'auto' }} onClick={csv} disabled={!full}>Download CSV</button></div>
      <div className="tablewrap tall"><table className="data compact"><thead><tr>{head('area', 'Area', false)}{head('adapter_r', 'Adapter')}{head('tribe_v2_r', 'TRIBE v2')}{head('ceiling', 'Ceiling')}</tr></thead>
        <tbody>{areas.map(x => <tr key={x.area}><td>{x.area}</td><td className="num">{fmt(x.adapter_r)}</td><td className="num">{fmt(x.tribe_v2_r)}</td><td className="num">{fmt(x.ceiling)}</td></tr>)}</tbody></table></div>
    </details>
  </div>
}

export function AdaptersView({ datasetId, views, onChanged }: { datasetId: string; views: { view_id: string; name: string }[]; onChanged: () => void }) {
  const [list, setList] = useState<Adapter[] | null>(null); const [held, setHeld] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const load = () => call<Adapter[]>('adapter_list', { dataset_id: datasetId }).then(setList).catch(e => setErr(String(e?.message ?? e)))
  useEffect(() => { load() }, [datasetId])
  const fit = async () => {
    setBusy(true); setErr('')
    try { await call('adapter_create', { dataset_id: datasetId, ...(held ? { held_out_view_id: held } : {}) }); await load(); onChanged() } catch (e: any) { setErr(String(e?.message ?? e)) } finally { setBusy(false) }
  }
  return <div className="adapters">
    <div className="bar">
      <label className="ink2" htmlFor="heldout">Hold out</label>
      <select id="heldout" value={held} onChange={e => setHeld(e.target.value)}><option value="">10-fold over categories</option>{views.map(v => <option key={v.view_id} value={v.view_id}>Categories in {v.name}</option>)}</select>
      <button className="btn primary" onClick={fit} disabled={busy}>{busy ? <><span className="spin" /> Fitting</> : 'Fit an adapter'}</button>
    </div>
    <p className="ink2 small" style={{ marginTop: 0 }}>An adapter maps TRIBE v2's predicted cortex to this dataset's measured fMRI, then is scored only on categories it never saw. That score is a benchmark on this dataset's people and kind of stimulus; it does not measure new stimuli in an experiment, where no fMRI was recorded.</p>
    {err && <div className="dsnote">{err}</div>}
    {!list ? <div className="empty wait" role="status"><span className="spin" /> Reading the adapters</div>
      : !list.length ? <div className="empty">No adapter yet. Fit one to see how far it moves TRIBE v2 toward these people's measured responses.</div>
      : list.map(a => <AdapterCard key={a.id} a={a} />)}
  </div>
}
