import { useState, type ReactNode } from 'react'
import { fmt } from './api'

type Tip = { x: number; y: number; body: ReactNode } | null
function useTip() {
  const [tip, setTip] = useState<Tip>(null)
  const el = tip ? <div className="tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.body}</div> : null
  return { el, show: (e: React.MouseEvent, body: ReactNode) => setTip({ x: e.clientX, y: e.clientY, body }), hide: () => setTip(null) }
}

const ticks = (lo: number, hi: number, n = 4) => {
  const step = Math.pow(10, Math.floor(Math.log10((hi - lo) / n || 1)))
  const s = [1, 2, 5, 10].map(m => m * step).find(m => (hi - lo) / m <= n) ?? step * 10
  const out: number[] = []
  for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-12; v += s) out.push(Math.round(v / s) * s)
  return out
}

/** One dot per unit (pair, item or object), with the mean and its 95% interval. Single series, so no legend. */
export function DotStrip({ values, labels, mean, interval, selected, onPick }: {
  values: number[]; labels: string[]; mean: number; interval: [number, number]; selected?: number; onPick?: (i: number) => void
}) {
  const t = useTip(); const W = 640, H = 120, P = 28
  const lo = Math.min(0, ...values, interval[0]), hi = Math.max(0, ...values, interval[1]); const pad = (hi - lo) * 0.08 || 0.01
  const x = (v: number) => P + ((v - (lo - pad)) / (hi - lo + 2 * pad)) * (W - 2 * P)
  const order = values.map((v, i) => [v, i] as const).sort((a, b) => a[0] - b[0])
  const ys = new Map<number, number>(); order.forEach(([, i], k) => ys.set(i, 34 + (k % 4) * 11))
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Difference per unit">
        {ticks(lo - pad, hi + pad).map(v => <g key={v}><line className="grid" x1={x(v)} x2={x(v)} y1={20} y2={H - 24} /><text x={x(v)} y={H - 6} textAnchor="middle">{fmt(v, 2)}</text></g>)}
        <line className="axis" x1={x(0)} x2={x(0)} y1={14} y2={H - 24} strokeWidth={1.5} />
        <rect x={x(interval[0])} y={22} width={Math.max(2, x(interval[1]) - x(interval[0]))} height={58} fill="var(--a)" opacity={0.14} rx={4} />
        <line x1={x(mean)} x2={x(mean)} y1={18} y2={84} stroke="var(--a)" strokeWidth={2} />
        {values.map((v, i) => (
          <circle key={i} cx={x(v)} cy={ys.get(i)} r={i === selected ? 6.5 : 5} fill={i === selected ? 'var(--a)' : 'var(--b)'} stroke="#0e0f11" strokeWidth={2}
            style={{ cursor: onPick ? 'pointer' : 'default' }} onClick={() => onPick?.(i)}
            onMouseMove={e => t.show(e, <><b>{labels[i]}</b><div className="num">{fmt(v)}</div></>)} onMouseLeave={t.hide} />
        ))}
      </svg>
      {t.el}
    </div>
  )
}

/** Mean response by second for two conditions, with the seconds on screen shaded. Two series: legend plus end labels. */
export function TimeCourse({ a, b, labels, window }: { a: number[]; b: number[]; labels: [string, string]; window: [number, number] }) {
  const t = useTip(); const W = 640, H = 220, L = 56, R = 120, T = 14, B = 34
  const all = [...a, ...b]; const lo = Math.min(...all), hi = Math.max(...all); const pad = (hi - lo) * 0.1 || 0.01
  const n = a.length; const x = (i: number) => L + (i / (n - 1)) * (W - L - R); const y = (v: number) => T + (1 - (v - lo + pad) / (hi - lo + 2 * pad)) * (H - T - B)
  const path = (s: number[]) => s.map((v, i) => `${i ? 'L' : 'M'}${x(i)},${y(v)}`).join('')
  const [hover, setHover] = useState<number | null>(null)
  return (
    <div>
      <div className="legend" style={{ marginBottom: 6 }}>
        <span><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke="var(--a)" strokeWidth="2" /></svg> {labels[0]}</span>
        <span><svg width="22" height="10"><line x1="0" x2="22" y1="5" y2="5" stroke="var(--b)" strokeWidth="2" /></svg> {labels[1]}</span>
        <span className="muted">Shaded: on screen</span>
      </div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Response by second"
        onMouseMove={e => { const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect(); const px = (e.clientX - r.left) / r.width * W; const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1)))); setHover(i); t.show(e, <><b>Second {i}</b><div className="num">{labels[0]} {fmt(a[i])}</div><div className="num">{labels[1]} {fmt(b[i])}</div></>) }}
        onMouseLeave={() => { setHover(null); t.hide() }}>
        <rect x={x(window[0])} y={T} width={x(Math.min(window[1], n - 1)) - x(window[0])} height={H - T - B} fill="#ffffff" opacity={0.04} />
        {ticks(lo - pad, hi + pad).map(v => <g key={v}><line className="grid" x1={L} x2={W - R} y1={y(v)} y2={y(v)} /><text x={L - 8} y={y(v) + 4} textAnchor="end">{fmt(v, 2)}</text></g>)}
        {a.map((_, i) => <text key={i} x={x(i)} y={H - 10} textAnchor="middle">{i}</text>)}
        <text x={W - R + 8} y={H - 10}>seconds</text>
        <path d={path(b)} fill="none" stroke="var(--b)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <path d={path(a)} fill="none" stroke="var(--a)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(n - 1)} cy={y(a[n - 1])} r={4} fill="var(--a)" stroke="#0e0f11" strokeWidth={2} />
        <circle cx={x(n - 1)} cy={y(b[n - 1])} r={4} fill="var(--b)" stroke="#0e0f11" strokeWidth={2} />
        <text x={x(n - 1) + 9} y={y(a[n - 1]) + (a[n - 1] >= b[n - 1] ? -2 : 12)}>{labels[0]}</text>
        <text x={x(n - 1) + 9} y={y(b[n - 1]) + (a[n - 1] >= b[n - 1] ? 12 : -2)}>{labels[1]}</text>
        {hover != null && <line className="axis" x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} />}
      </svg>
      {t.el}
    </div>
  )
}

/** Signed bars, one per object, sorted. Positive in the accent, negative in teal, from one zero baseline. */
export function SignedBars({ items, selected, onPick }: { items: { key: string; label: string; value: number; note?: string }[]; selected?: string; onPick?: (k: string) => void }) {
  const t = useTip(); const W = 640, row = 30, L = 210, R = 70
  const m = Math.max(...items.map(i => Math.abs(i.value)), 1e-6); const H = items.length * row + 8
  const x = (v: number) => L + (W - L - R) / 2 + (v / m) * (W - L - R) / 2
  return (
    <div>
      <svg className="chart" viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Effect of each object">
        <line className="axis" x1={x(0)} x2={x(0)} y1={0} y2={H} />
        {items.map((it, k) => {
          const y0 = k * row + 6, w = Math.abs(x(it.value) - x(0)), on = it.key === selected
          return (
            <g key={it.key} style={{ cursor: 'pointer' }} onClick={() => onPick?.(it.key)}
              onMouseMove={e => t.show(e, <><b>{it.label}</b><div className="num">{fmt(it.value)}</div>{it.note && <div className="muted">{it.note}</div>}</>)} onMouseLeave={t.hide}>
              <rect x={0} y={y0 - 3} width={W} height={row} fill={on ? '#1c1f23' : 'transparent'} />
              <text x={L - 12} y={y0 + 15} textAnchor="end" style={{ fill: on ? 'var(--ink)' : undefined }}>{it.label.length > 24 ? it.label.slice(0, 23) + '…' : it.label}</text>
              <rect x={it.value >= 0 ? x(0) : x(0) - w} y={y0 + 3} width={Math.max(w, 1)} height={16} rx={4} fill={it.value >= 0 ? 'var(--a)' : 'var(--b)'} />
              <text x={it.value >= 0 ? x(0) + w + 6 : x(0) - w - 6} y={y0 + 15} textAnchor={it.value >= 0 ? 'start' : 'end'}>{fmt(it.value)}</text>
            </g>
          )
        })}
      </svg>
      {t.el}
    </div>
  )
}

/** A small interval around zero for a list row. */
export function MiniInterval({ value, interval, scale }: { value: number; interval: [number, number]; scale: number }) {
  const W = 84, x = (v: number) => W / 2 + (v / scale) * (W / 2 - 6); const clear = interval[0] > 0 || interval[1] < 0
  return (
    <svg width={W} height={18} aria-hidden>
      <line x1={W / 2} x2={W / 2} y1={2} y2={16} stroke="var(--rule-strong)" />
      <line x1={x(interval[0])} x2={x(interval[1])} y1={9} y2={9} stroke={clear ? 'var(--a)' : 'var(--b)'} strokeWidth={2} strokeLinecap="round" />
      <circle cx={x(value)} cy={9} r={4} fill={clear ? 'var(--a)' : 'var(--b)'} stroke="#131417" strokeWidth={2} />
    </svg>
  )
}
