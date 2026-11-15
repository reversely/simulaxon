import { useEffect, useState } from 'react'
import { fmt, type Row, type Sample } from './api'

type Cond = { name: string; ids: string[]; mean_a: number; mean_b: number; score: number; random_95: [number, number]; share_random_at_least: number }
type Res = { k: number; n: number; n_random: number; conditions: Record<string, Cond>; points: { id: string; a: number; b: number }[] }

/** Every screened stimulus by its response in two regions, with one selection condition picked out, and the stimuli it keeps. */
export function SelectionView({ result, regions, samples, condition }: { result: Res; regions: [string, string]; samples: Row<Sample>[]; condition?: string }) {
  const keys = Object.keys(result.conditions); const [c, setC] = useState(condition && keys.includes(condition) ? condition : keys[0]); const cond = result.conditions[c]
  useEffect(() => { if (condition && keys.includes(condition)) setC(condition) }, [condition])   // a demo step names the condition it narrates
  const byId = Object.fromEntries(samples.map(s => [s.data.unit, s.data])); const sel = new Set(cond.ids)
  const [tip, setTip] = useState<{ x: number; y: number; id: string } | null>(null)
  const W = 640, H = 380, L = 72, B = 44, T = 14, R = 18
  const xs = result.points.map(p => p.a), ys = result.points.map(p => p.b)
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
  const px = (v: number) => L + (v - x0) / (x1 - x0 || 1) * (W - L - R), py = (v: number) => T + (1 - (v - y0) / (y1 - y0 || 1)) * (H - T - B)
  return <div className="card">
    <div className="bar" style={{ marginBottom: 8 }}>
      <h3 style={{ margin: 0 }}>{result.n} screened stimuli</h3>
      <div className="seg" role="group" aria-label="Selection condition">{keys.map(k => <button key={k} className={k === c ? 'on' : ''} onClick={() => setC(k)}>{result.conditions[k].name}</button>)}</div>
    </div>
    <div className="legend" style={{ marginBottom: 4 }}>
      <span><svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="6" fill="var(--a)" /></svg> Kept, {cond.name}</span>
      <span><svg width="14" height="14" aria-hidden><circle cx="7" cy="7" r="4" fill="var(--b)" opacity="0.55" /></svg> Screened</span>
    </div>
    <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${regions[0]} against ${regions[1]}`}>
      <line className="axis" x1={L} x2={W - R} y1={H - B} y2={H - B} /><line className="axis" x1={L} x2={L} y1={T} y2={H - B} />
      <text x={(L + W - R) / 2} y={H - 8} textAnchor="middle">{regions[0]}</text>
      <text x={14} y={(T + H - B) / 2} textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`}>{regions[1]}</text>
      {[x0, x1].map((v, i) => <text key={'x' + i} x={px(v) + (i ? -2 : 12)} y={H - B + 18} textAnchor={i ? 'end' : 'start'}>{fmt(v, 2)}</text>)}
      {[y0, y1].map((v, i) => <text key={'y' + i} x={L - 8} y={py(v) + (i ? 12 : -4)} textAnchor="end">{fmt(v, 2)}</text>)}
      {result.points.filter(p => !sel.has(p.id)).map(p => <circle key={p.id} cx={px(p.a)} cy={py(p.b)} r={4} fill="var(--b)" opacity={0.55} onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, id: p.id })} onMouseLeave={() => setTip(null)} />)}
      {result.points.filter(p => sel.has(p.id)).map(p => <circle key={p.id} cx={px(p.a)} cy={py(p.b)} r={6.5} fill="var(--a)" stroke="#0e0f11" strokeWidth={2} onMouseEnter={e => setTip({ x: e.clientX, y: e.clientY, id: p.id })} onMouseLeave={() => setTip(null)} />)}
    </svg>
    {tip && <div className="tip" style={{ left: tip.x + 14, top: tip.y + 14 }}><b>{byId[tip.id]?.label ?? tip.id}</b><div className="num">{regions[0]} {fmt(result.points.find(p => p.id === tip.id)!.a)}</div><div className="num">{regions[1]} {fmt(result.points.find(p => p.id === tip.id)!.b)}</div></div>}
    <div className="headline" style={{ marginTop: 6 }}><span className="big">{cond.score.toFixed(2)}</span>
      <span className="ink2">{cond.name}: mean scaled score of the {result.k} kept. Random sets of {result.k}: {cond.random_95[0].toFixed(2)} to {cond.random_95[1].toFixed(2)}. {(cond.share_random_at_least * 100).toFixed(2)}% of {result.n_random.toLocaleString()} reach it</span></div>
    <div className="thumbs">{cond.ids.map(id => <div key={id} className="thumbstatic">{byId[id]?.image && <img src={byId[id].image!} alt="" />}<span>{byId[id]?.label ?? id}</span></div>)}</div>
  </div>
}
