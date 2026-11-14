import { useState, useEffect } from 'react'
import type { Field, Stage, TrailStep } from './api'

// The view: every stage in order, as written by the server, with the number of samples left after it. Any stage can
// be removed. New stages are built from the fields that exist; nothing here knows a field name.

const OPS = ['==', '!=', '<', '<=', '>', '>=']
const scalar = (f: Field) => ['int', 'float', 'str', 'bool'].includes(f.type)
const parse = (f: Field | undefined, v: string) => f?.type === 'bool' ? v === 'true' : f && ['int', 'float'].includes(f.type) ? Number(v) : v

function Cond({ fields, value, onChange, label }: { fields: Field[]; value: Stage; onChange: (s: any) => void; label: string }) {
  const f = fields.find(x => x.path === value.path)
  // the box keeps the text as typed: showing String(Number(text)) dropped a trailing '.', so typing 1.0 gave 10
  const [raw, setRaw] = useState(String(value.value ?? ''))
  useEffect(() => { setRaw(String(value.value ?? '')) }, [value.path])  // a new field starts from its own value
  return <span className="cond" aria-label={label}>
    <select value={value.path} onChange={e => onChange({ ...value, path: e.target.value })} aria-label={`${label} field`}>{fields.filter(scalar).map(x => <option key={x.path}>{x.path}</option>)}</select>
    <select value={value.op} onChange={e => onChange({ ...value, op: e.target.value })} aria-label={`${label} test`}>{OPS.map(o => <option key={o}>{o}</option>)}</select>
    {f?.type === 'bool' ? <select value={String(value.value)} onChange={e => onChange({ ...value, value: e.target.value === 'true' })} aria-label={`${label} value`}><option>true</option><option>false</option></select>
      : <input value={raw} onChange={e => { setRaw(e.target.value); onChange({ ...value, value: parse(f, e.target.value) }) }} aria-label={`${label} value`} size={8} inputMode={f && ['int', 'float'].includes(f.type) ? 'decimal' : undefined} />}
  </span>
}

export function ViewBar({ trail, stages, fields, onRemove, onAdd }: { trail: TrailStep[]; stages: Stage[]; fields: Field[]; onRemove: (i: number) => void; onAdd: (s: Stage) => void }) {
  const first = fields.find(scalar)?.path ?? ''
  const [kind, setKind] = useState<string>('')
  const [a, setA] = useState<any>({ path: first, op: '==', value: '' })
  const [b, setB] = useState<any>({ path: first, op: '==', value: '' })
  const [on, setOn] = useState<string[]>([])
  const [sortPath, setSortPath] = useState(first)
  const add = () => {
    if (kind === 'match') onAdd({ stage: 'match', ...a })
    if (kind === 'sort_by') onAdd({ stage: 'sort_by', path: sortPath, reverse: false })
    if (kind === 'pair_nearest' && on.length) onAdd({ stage: 'pair_nearest', left: a, right: b, on })
    setKind('')
  }
  return <section className="viewbar" aria-label="View">
    <ol className="trail">
      {trail.map((t, i) => <li key={i} className={i === 0 ? 'base' : ''}>
        {i > 0 && stages[i - 1]?.by === 'agent' && <span className="by">Agent</span>}<span className="ttext">{t.text}</span><span className="tcount">{t.count.toLocaleString()}</span>{t.note && <span className="ink2">{t.note}</span>}
        {i > 0 && <button className="x" aria-label={`Remove stage: ${t.text}`} onClick={() => onRemove(i - 1)}>Remove</button>}
      </li>)}
    </ol>
    <div className="add">
      <select value={kind} onChange={e => setKind(e.target.value)} aria-label="Add a stage">
        <option value="">Add a stage</option><option value="match">Keep samples where</option><option value="sort_by">Sort by</option><option value="pair_nearest">Pair each sample with its nearest match</option>
      </select>
      {kind === 'match' && <Cond fields={fields} value={a} onChange={setA} label="Keep" />}
      {kind === 'sort_by' && <select value={sortPath} onChange={e => setSortPath(e.target.value)} aria-label="Sort field">{fields.filter(scalar).map(x => <option key={x.path}>{x.path}</option>)}</select>}
      {kind === 'pair_nearest' && <>
        <Cond fields={fields} value={a} onChange={setA} label="Left side" /><span className="ink2">with nearest</span><Cond fields={fields} value={b} onChange={setB} label="Right side" />
        <span className="ink2">on</span>
        <select multiple value={on} onChange={e => setOn([...e.target.selectedOptions].map(o => o.value))} aria-label="Fields to match on" size={3}>
          {fields.filter(x => ['int', 'float'].includes(x.type)).map(x => <option key={x.path}>{x.path}</option>)}</select>
      </>}
      {kind && <button className="btn primary" onClick={add} disabled={kind === 'pair_nearest' && !on.length}>Add</button>}
    </div>
    {stages.length > 0 && <details className="json"><summary>Stages as data</summary><pre>{JSON.stringify(stages, null, 1)}</pre></details>}
  </section>
}
