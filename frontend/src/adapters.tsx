/** A dataset's adapters (#28): fit one in one action, and see how it does on held-out categories beside TRIBE v2 as
 * released, shuffled labels and the noise ceiling, per area on the cortex and in a table. lab/adapter.py has the method. */
import { useEffect, useState } from 'react'
import { call, fmt } from './api'
import { MapBrain } from './brain3d'

type Summary = { median: number; interval_95: [number, number] }
type Area = { area: string; adapter_r: number; tribe_v2_r: number; shuffled_r: number; ceiling: number; reliable: boolean }
type Adapter = { id: string; name: string; dataset_id: string; source: string; people: number; categories: number; clips: number; reliable_areas: number
  split: { kind: string; held_out: number; training: number }; input: string; target: string; summary: Record<'adapter' | 'tribe_v2' | 'shuffled' | 'ceiling', Summary>; areas?: Area[]; benchmark?: string }

const ROWS: [keyof Adapter['summary'], string][] = [['adapter', 'Adapter'], ['tribe_v2', 'TRIBE v2 as released'], ['shuffled', 'Adapter, labels shuffled'], ['ceiling', 'Noise ceiling']]
const MAPS: [string, string][] = [['adapter_r', 'Adapter'], ['tribe_v2_r', 'TRIBE v2'], ['gain', 'Adapter minus TRIBE v2']]

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
    <h3>{a.name}</h3>
    <div className="benchlabel"><span className="chip">Benchmark</span><span>{(a.benchmark ?? `Benchmark: held-out categories of the ${a.source.split(',')[0]}`).replace(/^Benchmark: /, '')}</span></div>
    <p className="ink2" style={{ marginTop: 0 }}>{a.source}: {a.clips.toLocaleString()} clips in {a.categories} categories. {a.split.kind === '10-fold over categories' ? 'Scored 10-fold over categories' : `${a.split.held_out} categories held out, ${a.split.training} trained on`}; every score is on categories the fit never saw.</p>
    <div className="tablescroll"><table className="data compact"><thead><tr><th>Model</th><th className="num">Median r</th><th className="num">95% interval</th></tr></thead>
      <tbody>{ROWS.map(([k, label]) => <tr key={k}><td>{label}</td><td className="num">{fmt(a.summary[k].median)}</td><td className="num">{fmt(a.summary[k].interval_95[0])} to {fmt(a.summary[k].interval_95[1])}</td></tr>)}</tbody></table></div>
    <p className="ink2 small">r between predicted and measured responses ({a.target}) across held-out categories, per area; median over {a.reliable_areas} reliable areas (noise ceiling above 0.5, somatomotor areas left out). Interval: resampling areas. Input: {a.input}.</p>
    <div className="adaptermaps">
      <div>
        <div className="seg" role="group" aria-label="Map">{MAPS.map(([k, label]) => <button key={k} className={map === k ? 'on' : ''} onClick={() => setMap(k)}>{label}</button>)}</div>
        <MapBrain url={`/api/brain/adapter/${a.id}/${map}`} title={`${a.name}: ${MAPS.find(m => m[0] === map)?.[1]} r per area`} vmax={map === 'gain' ? 0.4 : 0.8} low={map === 'gain' ? '−0.4' : 'r −0.8'} high={map === 'gain' ? '+0.4' : '+0.8'} />
      </div>
      <div>
        <div className="bar"><div className="seg" role="group" aria-label="Areas"><button className={!all ? 'on' : ''} onClick={() => setAll(false)}>Reliable areas</button><button className={all ? 'on' : ''} onClick={() => setAll(true)}>All 360</button></div>
          <button className="btn" style={{ marginLeft: 'auto' }} onClick={csv} disabled={!full}>Download CSV</button></div>
        <div className="tablewrap tall"><table className="data compact"><thead><tr>{head('area', 'Area', false)}{head('adapter_r', 'Adapter')}{head('tribe_v2_r', 'TRIBE v2')}{head('ceiling', 'Ceiling')}</tr></thead>
          <tbody>{areas.map(x => <tr key={x.area}><td>{x.area}</td><td className="num">{fmt(x.adapter_r)}</td><td className="num">{fmt(x.tribe_v2_r)}</td><td className="num">{fmt(x.ceiling)}</td></tr>)}</tbody></table></div>
      </div>
    </div>
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
