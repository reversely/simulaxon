import { useState } from 'react'
import { fmt, unitLabel, type Facet, type Field, type Stage } from './api'

// The fields panel: one row per field in the view's schema. Numbers show a histogram whose bars add a range filter;
// strings and booleans show value counts that add an equality filter. Which widget is shown depends only on the type.

function Histogram({ f, onPick }: { f: Facet; onPick: (lo: number, hi: number) => void }) {
  const [hover, setHover] = useState<number | null>(null)
  const h = f.hist!, e = f.edges!, max = Math.max(...h, 1), W = 236, H = 44, bw = W / h.length
  return <div className="hist">
    <svg width={W} height={H} role="img" aria-label={`Histogram, ${f.count} values from ${fmt(f.min)} to ${fmt(f.max)}`}>
      {h.map((c, i) => <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} onClick={() => onPick(e[i], e[i + 1])} style={{ cursor: 'pointer' }}>
        <rect x={i * bw} y={0} width={bw} height={H} fill="transparent" />
        {c > 0 && <rect x={i * bw + 1} y={H - Math.max(2, (c / max) * H)} width={bw - 2} height={Math.max(2, (c / max) * H)} rx={2} fill={hover === i ? 'var(--accent)' : 'var(--s1)'} />}
      </g>)}
    </svg>
    <div className="axis"><span>{fmt(f.min)}</span><span>{fmt(f.max)}</span></div>
    <div className="tip">{hover !== null ? `${fmt(e[hover])} to ${fmt(e[hover + 1])}: ${h[hover]} samples. Click to keep only these` : ' '}</div>
  </div>
}

export function Fields({ schema, facets, shown, onToggleShown, onAdd }: {
  schema: Field[]; facets: Record<string, Facet>; shown: string[]; onToggleShown: (p: string) => void; onAdd: (s: Stage) => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})
  return <aside className="fields" aria-label="Fields">
    <h2>Fields <span className="ink3">{schema.length}</span></h2>
    {schema.map(fd => {
      const f = facets[fd.path]; const isOpen = open[fd.path] ?? (f?.kind === 'numeric' || f?.kind === 'values')
      return <section key={fd.path} className="field">
        <div className="frow">
          <button className="fname" onClick={() => setOpen({ ...open, [fd.path]: !isOpen })} aria-expanded={isOpen}>{fd.path}</button>
          <span className="type">{fd.type}{fd.unit ? `, ${unitLabel(fd.unit)}` : ''}</span>
          <span className="count" title={`${f?.count ?? 0} samples have it, ${f?.missing ?? 0} do not`}>{f?.count ?? 0}{f?.missing ? <span className="ink3"> of {f.count + f.missing}</span> : null}</span>
          {fd.type !== 'track' && <label className="show" title="Show on tiles"><input type="checkbox" checked={shown.includes(fd.path)} onChange={() => onToggleShown(fd.path)} />Tiles</label>}
        </div>
        {fd.description && <p className="desc">{fd.description}</p>}
        {isOpen && f?.kind === 'numeric' && <Histogram f={f} onPick={(lo, hi) => onAdd({ stage: 'match', path: fd.path, op: 'between', value: [lo, hi] })} />}
        {isOpen && f?.kind === 'values' && <ul className="vals">
          {f.values!.slice(0, 12).map(([v, c]) => <li key={v}><button onClick={() => onAdd({ stage: 'match', path: fd.path, op: '==', value: fd.type === 'bool' ? v === 'true' : fd.type === 'int' ? Number(v) : v })}>
            <span className="v" title={v}>{v}</span><span className="bar" style={{ width: `${(c / f.count) * 100}%` }} /><span className="n">{c}</span></button></li>)}
          {f.distinct! > 12 && <li className="ink3">{f.distinct! - 12} more values</li>}
        </ul>}
      </section>
    })}
  </aside>
}
