import { useEffect, useState } from 'react'
import { call, fmt, regionLabel, type Row, type Sample } from './api'
import { Icon } from './icons'
import { ClipBrain, samplePreds } from './brain3d'

export type Origin = { kind: 'dataset' | 'isaac' | 'file' | 'generated' | 'cosmos'; label: string; title?: string; ref?: string; licence?: string | null; dataset_id?: string; from?: Origin; prompt?: string; seeds?: number[] }
export type Setup = {
  conditions: { name: string; files_available: number; origin: Origin; trials: number }[]
  trial: { design: string; item_s: number; gap_s: number; items_per_trial: number; trials_per_condition: number; rest_s: number; on_s: number; clip_s: number; read_s: [number, number] }
  clips: number; minutes_estimate: number; contrasts: { name: string; weights: Record<string, number> }[]; regions: string[]
  reported: Reported[]
}
export type Reported = { contrast: string; region: string; direction?: string; where?: string; quote?: string; tribe_value?: number; tribe_interval_95?: [number, number]; area_rank_pct?: number; shuffled_labels_95?: [number, number]; result?: string }
export type Paper = { title?: string; authors?: string; year?: string | number; venue?: string; doi?: string; source?: string; full_text?: boolean }

// series colours for conditions, in this fixed order: one blue, then neutrals told apart by lightness, so the app keeps one hue
export const SERIES = ['#5aa9e6', '#9a948a', '#a8d1f2', '#5f5a53']
const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'

/** Where a stimulus came from, on every tile and stage: fetched from a dataset, rendered in Isaac Sim, made here, or Cosmos. */
export function OriginChip({ o, long }: { o?: Origin | null; long?: boolean }) {
  if (!o) return null
  const tip = o.kind === 'cosmos' ? [`Restyled by Cosmos, seeds ${o.seeds?.join(', ')}`, `Prompt: ${o.prompt}`, o.from?.title, o.from?.ref] : [o.title, o.ref, o.licence ? `Licence ${o.licence}` : 'No licence stated']
  return <span className={`origin ${o.kind}`} title={tip.filter(Boolean).join('\n')}>
    {o.kind === 'cosmos' ? (long ? `Cosmos, from ${o.from?.kind === 'dataset' ? o.from.ref?.replace(/^\w+:/, '') ?? 'a dataset' : o.from?.kind === 'isaac' ? 'Isaac Sim' : 'a file'}` : 'Cosmos')
      : o.kind === 'dataset' ? (long ? `From ${o.ref?.replace(/^\w+:/, '') ?? o.title ?? 'a dataset'}` : 'Dataset') : o.kind === 'isaac' ? 'Isaac Sim' : o.kind === 'generated' ? (long ? 'Made here from photos' : 'Made here') : 'Added file'}
  </span>
}

export function PaperLine({ p }: { p?: Paper | null }) {
  if (!p) return null
  return <div className="paperline">
    <span>{p.authors?.split(',').slice(0, 3).join(',')}{(p.authors?.split(',').length ?? 0) > 3 ? ' and others' : ''} {p.year}</span>
    {p.doi ? <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">{p.title}</a> : <span>{p.title}</span>}
    {p.full_text === false && <span className="chip flag">Abstract only</span>}
  </div>
}

/** What the agent set up, as entries: conditions with their routes, regions, comparisons and the paper's result. Every
 * entry is the agent's to edit, so Add asks the agent; nothing here is fixed to one experiment. */
export function ExperimentSetup({ setup, paper, onRun, onAsk, running, progress }: { setup: Setup; paper?: Paper | null; onRun?: () => void; onAsk: (text: string) => void; running: boolean; progress?: { done: number; total: number; stage?: string; error?: string } }) {
  const t = setup.trial
  const letter = Object.fromEntries(setup.conditions.map((c, i) => [c.name, LETTERS[i]]))
  return <div className="expsetup">
    <PaperLine p={paper} />
    {!running && progress?.stage === 'failed' && <div className="runfail" role="alert"><b>The last run stopped.</b> <span className="ink2">{progress.error}</span></div>}
    <section className="paper entries">
      <h3>Conditions</h3>
      {setup.conditions.map(c => <div key={c.name} className="entryrow">
        <span className="letter">{letter[c.name]}</span><b>{c.name}</b>
        <span className="routechips"><OriginChip o={c.origin} long />{c.origin.kind === 'cosmos' && <span className="origin cosmos">Cosmos, seeds {c.origin.seeds?.join(' and ')}</span>}<span className="arrow" aria-hidden>→</span><span className="origin stagechip">TRIBE v2</span></span>
        <span className="ink2 num count">{c.files_available} files, {c.trials} trials</span>
      </div>)}
      {!running && <button className="addentry" onClick={() => onAsk('Suggest one more condition for this experiment. Set it up only if I agree.')}><Icon name="plus" size={16} />Add condition</button>}

      <div className="entrycols">
        <div>
          <h3>Each trial</h3>
          <div className="trialbar" aria-label={`${t.items_per_trial} items of ${t.item_s} s, then ${t.rest_s} s of grey`}>
            {Array.from({ length: Math.min(t.items_per_trial, 24) }).map((_, i) => <span key={i} className="on" style={{ flex: t.item_s }} />)}
            <span className="rest" style={{ flex: t.rest_s }} />
          </div>
          <div className="ink2">{t.items_per_trial} {t.items_per_trial === 1 ? 'item' : 'items'} of {t.item_s} s, then {t.rest_s} s of grey. Read over seconds {t.read_s[0]} to {t.read_s[1]}.</div>
        </div>
        <div>
          <h3>Regions</h3>
          <div className="pills">{setup.regions.map(r => <span key={r} className="pill" title={r}>{regionLabel(r)}</span>)}
            {!running && <button className="addentry pilladd" onClick={() => onAsk('Suggest another brain region for this experiment and say why.')}><Icon name="plus" size={16} />Add region</button>}</div>
        </div>
      </div>

      <h3>Comparisons</h3>
      {setup.contrasts.map(ct => { const pos = Object.keys(ct.weights).filter(k => ct.weights[k] > 0), neg = Object.keys(ct.weights).filter(k => ct.weights[k] < 0)
        return <div key={ct.name} className="entryrow">
          {pos.map(k => <span key={k} className="letter">{letter[k]}</span>)}<span className="ink2">against</span>{neg.map(k => <span key={k} className="letter b">{letter[k]}</span>)}
          <span>{ct.name}</span>
        </div> })}
      {setup.reported.map((r, i) => <div key={i} className="entryrow reportedrow"><span className="ink2">Paper</span><span>{regionLabel(r.region)} {r.direction ?? 'higher'} for {r.contrast}</span><span className="ink2">{r.where}</span></div>)}
      {!running && <button className="addentry" onClick={() => onAsk('Suggest another comparison for this experiment. Set it up only if I agree.')}><Icon name="plus" size={16} />Add comparison</button>}

      <div className="entryfoot">
        {running ? <><div className="fbar" style={{ width: 280 }}><span style={{ width: `${progress?.total ? 100 * progress.done / progress.total : 0}%` }} /></div>
          <span className="ink2 num">{progress?.stage === 'comparing' ? 'Comparing' : progress?.stage === 'cosmos' ? `Cosmos is restyling, then TRIBE: ${progress.done} of ${progress.total} trials` : progress?.total ? `${progress.done} of ${progress.total} clips through TRIBE` : 'Starting'}</span></>
          : <><span><b>{setup.clips}</b> clips</span><span className="ink2">About {Math.max(1, Math.round(setup.minutes_estimate))} min</span>
            <span className="bar" style={{ marginLeft: 'auto' }}><button className="btn" onClick={() => onAsk('Check this set-up against the paper before it runs.')}><Icon name="chat" size={16} />Ask the agent</button>
              {onRun && <button className="btn primary" onClick={onRun}><Icon name="play" size={16} />{progress?.stage === 'failed' ? 'Run again' : 'Run'}</button>}</span></>}
      </div>
    </section>
  </div>
}

/** The paper's result beside TRIBE's: the reported direction and where, TRIBE's value with its interval, its rank among
 * the 360 areas and the shuffled-label control, then match or no match. */
export function ReportedCard({ items }: { items: Reported[] }) {
  if (!items.length) return null
  return <div className="card paper"><h3>Against the paper</h3>
    {items.map((r, i) => <div key={i} className="reported">
      <div><b>{regionLabel(r.region)}</b> <span className="ink2">{r.direction ?? 'higher'} for {r.contrast}</span>{r.where && <span className="ink2">, {r.where}</span>}</div>
      <div className="big">{fmt(r.tribe_value)}</div>
      <div className="ink2 num">Interval {fmt(r.tribe_interval_95?.[0])} to {fmt(r.tribe_interval_95?.[1])}</div>
      {r.area_rank_pct != null && <div className="ink2 num">Above {r.area_rank_pct}% of the 360 areas</div>}
      {r.shuffled_labels_95 && <div className="ink2 num">Labels shuffled: {fmt(r.shuffled_labels_95[0])} to {fmt(r.shuffled_labels_95[1])}</div>}
      <span className={`chip ${r.result === 'match' ? 'match' : ''}`}>{r.result === 'match' ? 'Match' : r.result?.replace(/^no match: /, 'No match, ') ?? ''}</span>
    </div>)}
  </div>
}

type Course = { region: string; seconds: number; conditions: { name: string; n: number; values: number[] }[] }

/** A region's response second by second, one line per condition, from the run's saved predictions. Lines are labelled at
 * their ends; moving across the chart reads every condition at that second. */
const COURSES = new Map<string, Course>()   // each project and region's course, kept for the page's life (#30)

export function ConditionCourse({ pid, region, onS }: { pid: string; region: string; onS?: number }) {
  const key = `${pid} ${region}`
  const [c, setC] = useState<Course | null>(() => COURSES.get(key) ?? null); const [hover, setHover] = useState<number | null>(null); const [err, setErr] = useState('')
  useEffect(() => { setC(COURSES.get(key) ?? null); setErr(''); call<Course>('course_get', { project_id: pid, region }).then(x => { COURSES.set(key, x); setC(x) }).catch(e => setErr(String(e.message ?? e))) }, [key])
  const W = 900, H = 260, L = 56, R = 150, T = 14, B = 34, PW = W - L - R, PH = H - T - B
  const note = `TRIBE v2, mean of each condition's trials. ${onS != null ? 'Shaded: the seconds the stimulus is on screen.' : ''}`
  if (err) return null
  if (!c) return <div className="card course" aria-busy="true">   {/* the card at its final size, the chart's place held, while the course is read */}
    <h3>{regionLabel(region)}, second by second</h3><div className="legend" />
    <div className="coursewait" role="status" aria-label="Reading the time course" style={{ aspectRatio: `${W} / ${H}` }}><span className="spin" /></div>
    <div className="ink2">{note}</div>
  </div>
  const all = c.conditions.flatMap(s => s.values); const lo = Math.min(...all, 0), hi = Math.max(...all, 0); const pad = (hi - lo) * 0.08 || 0.01
  const x = (t: number) => L + t * PW / Math.max(1, c.seconds - 1); const y = (v: number) => T + (hi + pad - v) / (hi - lo + 2 * pad) * PH
  const ticks = [lo, 0, hi].filter((v, i, a) => a.indexOf(v) === i)
  const ends = c.conditions.map((s, i) => ({ i, y: y(s.values[c.seconds - 1]) })).sort((a, b) => a.y - b.y)
  for (let k = 1; k < ends.length; k++) if (ends[k].y - ends[k - 1].y < 18) ends[k].y = ends[k - 1].y + 18   // labels never overlap
  const labelY = Object.fromEntries(ends.map(e => [e.i, e.y]))
  return <div className="card course">
    <h3>{regionLabel(region)}, second by second</h3>
    <div className="legend">{c.conditions.map((s, i) => <span key={s.name}><i style={{ background: SERIES[i % SERIES.length] }} />{s.name}{hover != null && <b className="num"> {fmt(s.values[hover])}</b>}</span>)}
      {hover != null && <span className="ink2 num">second {hover}</span>}</div>
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${regionLabel(region)}, TRIBE response second by second, by condition`}
      onMouseMove={e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const t = Math.round(((e.clientX - r.left) / r.width * W - L) / PW * (c.seconds - 1)); setHover(t >= 0 && t < c.seconds ? t : null) }}
      onMouseLeave={() => setHover(null)}>
      {onS != null && <rect x={x(0)} y={T} width={x(Math.min(onS, c.seconds - 1)) - x(0)} height={PH} fill="#24211e" />}
      {ticks.map(v => <g key={v}><line x1={L} x2={L + PW} y1={y(v)} y2={y(v)} stroke="#2a2622" /><text x={L - 8} y={y(v) + 5} textAnchor="end" fontSize="14" fill="#8a847b">{fmt(v, 2)}</text></g>)}
      {[0, Math.round((c.seconds - 1) / 2), c.seconds - 1].map(t => <text key={t} x={x(t)} y={H - 10} textAnchor="middle" fontSize="14" fill="#8a847b">{t} s</text>)}
      {c.conditions.map((s, i) => <polyline key={s.name} points={s.values.map((v, t) => `${x(t)},${y(v)}`).join(' ')} fill="none" stroke={SERIES[i % SERIES.length]} strokeWidth="2" strokeLinejoin="round" />)}
      {c.conditions.length <= 4 && c.conditions.map((s, i) => <text key={s.name} x={x(c.seconds - 1) + 10} y={labelY[i] + 5} fontSize="14" fill="#f2efe8">{s.name}</text>)}
      {hover != null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={T + PH} stroke="#b9b2a7" strokeDasharray="3 3" />}
    </svg>
    <div className="ink2">{note}</div>
  </div>
}

/** One trial of an experiment, every trial's value by condition, and the region's time course. */
/** One trial's TRIBE value in every region it was read in, names as written; regions named at set-up first and marked. */
export function ReadoutTable({ title, readout, named, focus, bare }: { title: string; readout: Record<string, number>; named: string[]; focus?: string; bare?: boolean }) {
  const rows = [...named.filter(r => r in readout), ...Object.keys(readout).filter(r => !named.includes(r))]
  const table = <table className="data compact"><thead><tr><th>Region</th><th className="num">TRIBE value</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r} className={r === focus ? 'on' : ''}><td title={r}>{regionLabel(r)}{named.includes(r) && <span className="chip tiny">Named</span>}</td><td className="num">{fmt(readout[r])}</td></tr>)}</tbody></table>
  return bare ? <div className="readouts"><div className="ink2">{title}</div><div className="tablescroll">{table}</div></div> : <div className="card"><h3>{title}</h3><div className="tablewrap">{table}</div></div>
}

export function ExperimentRoom({ pid, samples, idx, setIdx, region, onS, named = [], tag = '' }: { pid: string; samples: Row<Sample & { origin?: Origin; items?: string[] }>[]; idx: number; setIdx: (i: number) => void; region: string; onS?: number; named?: string[]; tag?: string }) {
  const row = samples[Math.min(idx, samples.length - 1)]; const s = row?.data
  if (!s) return null
  const conds = [...new Set(samples.map(x => x.data.condition))]
  const vals = samples.map(x => x.data.readout[region] ?? 0); const lo = Math.min(...vals), hi = Math.max(...vals); const x = (v: number) => hi > lo ? 100 * (v - lo) / (hi - lo) : 50
  return <>
    {s.clip ? <ClipBrain key={row.id} clip={s.clip} sampleId={row.id} predsUrl={samplePreds(row.id)} square><span className="stageorigin"><OriginChip o={s.origin} long /></span></ClipBrain>
      : <div className="stage runstage square">{s.image && <img src={s.image} alt={s.label} />}<span className="stageorigin"><OriginChip o={s.origin} long /></span></div>}
    <div className="bar">
      <span className="mid">{s.label}</span>
      <span style={{ marginLeft: 'auto' }} className="bar">
        <button className="btn" aria-label="Previous trial" disabled={idx <= 0} onClick={() => setIdx(idx - 1)}>‹</button>
        <span className="num ink2">Trial {idx + 1} of {samples.length}</span>
        <button className="btn" aria-label="Next trial" disabled={idx >= samples.length - 1} onClick={() => setIdx(idx + 1)}>›</button>
      </span>
    </div>
    <ReadoutTable title="This trial, TRIBE value by region" readout={s.readout} named={named} focus={region} />
    {region ? <><ConditionCourse pid={pid} region={region} onS={onS} />
    <div className="card"><h3>Every trial: {regionLabel(region)}{tag && <span className="chip tiny">{tag}</span>}</h3>
      {conds.map((c, ci) => { const mine = samples.map((r, i) => ({ r, i })).filter(o => o.r.data.condition === c); const mean = mine.reduce((t, o) => t + (o.r.data.readout[region] ?? 0), 0) / mine.length
        return <div key={c} className="condstrip"><span className="ink2">{c}</span><div className="strip">
          {mine.map(o => <button key={o.i} className={`dot ${o.i === idx ? 'sel' : ''}`} style={{ left: `${x(o.r.data.readout[region] ?? 0)}%`, background: o.i === idx ? undefined : SERIES[ci % SERIES.length] }} onClick={() => setIdx(o.i)} aria-label={o.r.data.label} />)}
          <span className="mean" style={{ left: `${x(mean)}%` }} /></div><span className="num">{fmt(mean)}</span></div> })}
    </div></> : <p className="ink2">Pick a region under Regions to plot it over time and across trials.</p>}
  </>
}
