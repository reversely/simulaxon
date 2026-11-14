import { useEffect, useMemo, useRef, useState } from 'react'

// The dashboard: runs and their steps over time, GPU use per job, the planner's throughput, and the weights on the
// volume. Everything comes from /api/dashboard, which reads /data and Fuzzball; it refreshes every 15 s.

type Step = { label: string; job: string; array: boolean; status: string; start: number | null; end: number | null }
type Run = { name: string; title: string; workflow: string | null; status: string; start?: number | null; end?: number | null; steps: Step[] }
type Gpu = { file: string; workflow: string; job: string; task: string | number | null; node: string; updated: number; samples: { t: number; gpu_util_pct?: number; power_w?: number; temp_c?: number; mem_used_bytes?: number }[] }
type Planner = { t: number; requests_running?: number; requests_waiting?: number; generation_tokens_total?: number; kv_cache_usage?: number }
type Dash = { now: number; runs: Run[]; gpu: Gpu[]; planner: Planner[]; weights: { name: string; bytes: number; files: number }[] }

const hm = (t: number) => new Date(t * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
const dur = (s: number) => s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min` : s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`
// Charts are drawn at their container's pixel width, so text stays 12 px at every screen size.
function useWidth(min = 280): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null), [w, setW] = useState(600)
  useEffect(() => { const el = ref.current; if (!el) return; const o = new ResizeObserver(e => setW(Math.max(min, Math.round(e[0].contentRect.width)))); o.observe(el); return () => o.disconnect() }, [min])
  return [ref, w]
}
const gb = (b: number) => `${(b / 1e9).toFixed(b >= 1e10 ? 0 : 1)} GB`

export function Dashboard({ standalone = false }: { standalone?: boolean }) {
  const [d, setD] = useState<Dash | null>(null), [err, setErr] = useState('')
  useEffect(() => {
    const load = () => fetch('/api/dashboard').then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText))).then(x => { setD(x); setErr('') }).catch(e => setErr(String(e.message)))
    load(); const i = setInterval(load, 15000); return () => clearInterval(i)
  }, [])
  return <main className={`dash${standalone ? ' standalone' : ''}`}>
    <div className="dash-head"><h1>Dashboard</h1>
      {d && <span className="ink2">Updated {hm(d.now)}</span>}
      {!standalone && <a className="ink2" href="/dashboard" target="_blank" rel="noreferrer">Open on its own page</a>}
      {err && <span className="flag">The dashboard did not load: {err}</span>}</div>
    {!d ? <p className="ink2">Loading</p> : <>
      <section><h2>Runs</h2>{d.runs.length === 0 ? <p className="ink2">No runs defined</p> : d.runs.map(r => <RunTimeline key={r.name} r={r} now={d.now} />)}</section>
      <section><h2>GPU use</h2>{d.gpu.length === 0 ? <p className="ink2">No GPU samples yet; GPU jobs write them to /data/log/metrics/gpu</p> :
        <div className="multiples">{d.gpu.map(g => <GpuCard key={g.file} g={g} />)}</div>}</section>
      <section><h2>Planner</h2><PlannerCharts rows={d.planner} /></section>
      <section><h2>Weights</h2><table className="ftable"><thead><tr><th>Folder</th><th className="num">Size</th><th className="num">Files</th></tr></thead>
        <tbody>{d.weights.map(w => <tr key={w.name}><td>{w.name}</td><td className="num">{gb(w.bytes)}</td><td className="num">{w.files.toLocaleString()}</td></tr>)}</tbody></table></section>
    </>}
  </main>
}

function RunTimeline({ r, now }: { r: Run; now: number }) {
  const steps = r.steps.filter(s => !s.array)
  const [tip, setTip] = useState<{ x: number; y: number; s: Step } | null>(null)
  const t0 = Math.min(...steps.map(s => s.start ?? Infinity), r.start ?? Infinity), t1 = Math.max(...steps.map(s => s.end ?? (s.start ? now : -Infinity)), r.end ?? -Infinity)
  const [box, W] = useWidth(), L = Math.min(130, W * 0.3), R = 16, rowH = 26, H = steps.length * rowH + 28
  const x = (t: number) => L + (t - t0) / Math.max(1, t1 - t0) * (W - L - R)
  const ticks = isFinite(t0) && isFinite(t1) ? Array.from({ length: 5 }, (_, i) => t0 + (t1 - t0) * i / 4) : []
  return <div className="card">
    <div className="card-head"><b>{r.title}</b><span className={`chip ${r.status === 'failed' ? 'flag' : ''}`}>{r.status}</span>
      {r.workflow && <span className="ink3">Workflow {r.workflow.slice(0, 8)}</span>}{isFinite(t0) && isFinite(t1) && <span className="ink2">{hm(t0)} to {hm(t1)}, {dur(t1 - t0)}</span>}</div>
    {steps.length === 0 ? <p className="ink2">Not started</p> :
    <div className="chartwrap" ref={box} onMouseLeave={() => setTip(null)}>
      <svg width={W} height={H} className="chart" role="img" aria-label={`Steps of ${r.title} over time`}>
        {ticks.map((t, i) => <g key={i}><line x1={x(t)} x2={x(t)} y1={0} y2={H - 22} className="grid" />{(W > 520 || i % 2 === 0) &&
          <text x={x(t)} y={H - 6} className="axis" textAnchor={i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'}>{hm(t)}</text>}</g>)}
        {steps.map((s, i) => { const y = i * rowH + 4, a = s.start, b = s.end ?? (a ? now : null)
          return <g key={i}>
            <text x={L - 10} y={y + 14} className="axis" textAnchor="end">{s.label}</text>
            {a && b && <rect x={x(a)} y={y + 3} width={Math.max(3, x(b) - x(a))} height={rowH - 10} rx={4}
              className={`bar ${s.status}`} onMouseMove={e => setTip({ x: e.nativeEvent.offsetX, y: e.nativeEvent.offsetY, s })} />}
            {!a && <text x={L + 4} y={y + 14} className="axis">{s.status}</text>}
          </g> })}
      </svg>
      {tip && <div className="tip" style={{ left: tip.x + 12, top: tip.y + 12 }}><b>{tip.s.label}</b><div>{tip.s.status}</div>
        {tip.s.start && <div>{hm(tip.s.start)} to {tip.s.end ? hm(tip.s.end) : 'now'}, {dur((tip.s.end ?? now) - tip.s.start)}</div>}</div>}
    </div>}
  </div>
}

type Pt = { t: number; v: number | null | undefined }
function Line({ series, unit, max, label, extra }: { series: { name: string; color: string; pts: Pt[] }[]; unit: string; max?: number; label: string; extra?: (t: number) => string }) {
  const [box, W] = useWidth(), H = 150, L = 40, R = 10, T = 10, B = 22
  const [hx, setHx] = useState<number | null>(null)
  const all = series.flatMap(s => s.pts).filter(p => p.v != null) as { t: number; v: number }[]
  const t0 = Math.min(...all.map(p => p.t)), t1 = Math.max(...all.map(p => p.t)), top = max ?? Math.max(1, ...all.map(p => p.v)) * 1.1
  const x = (t: number) => L + (t - t0) / Math.max(1, t1 - t0) * (W - L - R), y = (v: number) => T + (1 - v / top) * (H - T - B)
  if (all.length === 0) return <div ref={box}><p className="ink2">No samples yet</p></div>
  const near = hx == null ? null : all.reduce((a, p) => Math.abs(x(p.t) - hx) < Math.abs(x(a.t) - hx) ? p : a, all[0]).t
  return <div className="chartwrap" ref={box} onMouseLeave={() => setHx(null)}>
    <svg width={W} height={H} className="chart" role="img" aria-label={label} onMouseMove={e => setHx(e.nativeEvent.offsetX)}>
      {[0, .5, 1].map(f => <g key={f}><line x1={L} x2={W - R} y1={y(top * f)} y2={y(top * f)} className="grid" /><text x={L - 6} y={y(top * f) + 4} className="axis" textAnchor="end">{Math.round(top * f)}</text></g>)}
      <text x={L} y={H - 6} className="axis">{hm(t0)}</text><text x={W - R} y={H - 6} className="axis" textAnchor="end">{hm(t1)}</text>
      {series.map(s => <polyline key={s.name} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round"
        points={s.pts.filter(p => p.v != null).map(p => `${x(p.t)},${y(p.v as number)}`).join(' ')} />)}
      {near != null && <line x1={x(near)} x2={x(near)} y1={T} y2={H - B} className="cross" />}
    </svg>
    {near != null && <div className="tip" style={{ left: Math.min(Math.max(x(near), 70), W - 70), top: 8 }}><b>{hm(near)}</b>
      {series.map(s => { const p = s.pts.find(q => q.t === near); return p && p.v != null ? <div key={s.name}>{series.length > 1 ? `${s.name} ` : ''}{p.v.toFixed(1)} {unit}</div> : null })}
      {extra && <div>{extra(near)}</div>}</div>}
  </div>
}

function GpuCard({ g }: { g: Gpu }) {
  const pts = g.samples.map(s => ({ t: s.t, v: s.gpu_util_pct }))
  const extra = (t: number) => { const s = g.samples.find(q => q.t === t); return s ? [s.power_w != null && `${s.power_w.toFixed(0)} W`, s.temp_c != null && `${s.temp_c} °C`, s.mem_used_bytes != null && `${gb(s.mem_used_bytes)} memory`].filter(Boolean).join(', ') : '' }
  return <div className="card"><div className="card-head"><b>{g.job}{g.task ? ` task ${g.task}` : ''}</b><span className="ink3">{g.node}</span><span className="ink3">Workflow {String(g.workflow).slice(0, 8)}</span></div>
    <div className="ink2">GPU use, percent</div><Line series={[{ name: 'GPU use', color: 'var(--s1)', pts }]} unit="%" max={100} label={`GPU use of ${g.job}`} extra={extra} /></div>
}

function PlannerCharts({ rows }: { rows: Planner[] }) {
  const tps = useMemo(() => rows.slice(1).map((r, i) => { const a = rows[i]; const dt = r.t - a.t
    return { t: r.t, v: dt > 0 && r.generation_tokens_total != null && a.generation_tokens_total != null ? Math.max(0, (r.generation_tokens_total - a.generation_tokens_total) / dt) : null } }), [rows])
  if (rows.length === 0) return <p className="ink2">No planner samples yet; the app server samples the planner every 15 s once it runs</p>
  return <div className="multiples">
    <div className="card"><div className="ink2">Generated tokens per second</div><Line series={[{ name: 'Tokens per second', color: 'var(--s1)', pts: tps }]} unit="tokens/s" label="Planner tokens per second" /></div>
    <div className="card"><div className="ink2">Requests</div>
      <div className="legend"><span><i style={{ background: 'var(--s1)' }} />Running</span><span><i style={{ background: 'var(--s2)' }} />Waiting</span></div>
      <Line series={[{ name: 'Running', color: 'var(--s1)', pts: rows.map(r => ({ t: r.t, v: r.requests_running })) }, { name: 'Waiting', color: 'var(--s2)', pts: rows.map(r => ({ t: r.t, v: r.requests_waiting })) }]} unit="requests" label="Planner requests running and waiting" /></div>
  </div>
}
