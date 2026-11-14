import { useEffect, useState } from 'react'

// Runs: what the server is executing, step by step. Everything here is read from the run's definition, its live state,
// the files it writes (gates, results) and its log. Nothing names a particular run.

type StepState = { status: string; done?: number; failed?: number; total?: number; last?: string; started?: string; finished?: string; output?: string[] }
type Run = { name: string; title: string; question: string; plan_file?: string; literature_file?: string; plan_text?: string | null; dataset_name?: string | null
  steps: { id: string; title: string; command: string[]; items?: string; workers?: number }[]
  state: { status: string; started?: string; finished?: string; steps: Record<string, StepState> }; log: string[]
  artifact_files: { file: string; exists: boolean; content: any }[] }

function Gates({ g }: { g: Record<string, string> }) {
  return <ul className="gates">{Object.entries(g).map(([k, v]) => <li key={k} className={v === 'pass' ? 'pass' : 'fail'}><b>{v === 'pass' ? 'Pass' : 'Fail'}</b> {k}</li>)}</ul>
}

function Results({ r }: { r: any }) {
  if (!r?.by_shake) return null
  return <>{Object.entries<any>(r.by_shake).map(([shake, s]) => <section key={shake} className="res">
    <h4>Shake: {shake}</h4>
    {Object.entries<any>(s.splits).map(([split, d]) => <div key={split} className="split">
      <div className="ink2">{split}: {d.trials} test trials. A random candidate holds {d.random_candidate}; the best candidate {d.oracle}</div>
      <table className="ftable"><thead><tr><th>Streams</th><th>Held when the robot chooses</th><th>AUC</th></tr></thead>
        <tbody>{Object.keys(d.held_when_choosing).map(k => <tr key={k}><td>{k}</td><td className="num">{d.held_when_choosing[k]}</td><td className="num">{d.auc[k] ?? 'n/a'}</td></tr>)}</tbody></table>
      <table className="ftable"><thead><tr><th>Difference</th><th>Held</th><th>95% interval</th></tr></thead>
        <tbody>{Object.entries<any>(d.differences).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v.held}</td><td className="num">{v.ci95[0]} to {v.ci95[1]}</td></tr>)}</tbody></table>
    </div>)}
  </section>)}</>
}

export function Runs({ onOpenDataset }: { onOpenDataset: (name: string) => void }) {
  const [runs, setRuns] = useState<Run[]>([]), [sel, setSel] = useState<string | null>(null), [err, setErr] = useState(''), [showPlan, setShowPlan] = useState(false)
  const load = () => fetch('/api/runs').then(r => r.json()).then(setRuns).catch(e => setErr(String(e)))
  useEffect(() => { load(); const i = setInterval(load, 3000); return () => clearInterval(i) }, [])
  const r = runs.find(x => x.name === sel) ?? runs[0]
  const start = async () => { const x = await fetch(`/api/runs/${encodeURIComponent(r.name)}/start`, { method: 'POST' }).then(x => x.json()); if (!x.started) setErr(x.reason || 'not started'); load() }
  if (!r) return <main className="runs"><p className="ink2">{err || 'No runs defined in backend/runs/.'}</p></main>
  return <main className="runs">
    <aside className="runlist">{runs.map(x => <button key={x.name} className={x.name === r.name ? 'sel' : ''} onClick={() => setSel(x.name)}><b>{x.title}</b><span className="ink2">{x.state.status}</span></button>)}</aside>
    <section className="rundetail">
      <h2>{r.title}</h2>
      <p>{r.question}</p>
      <div className="bar">
        <span className={`chip ${r.state.status.startsWith('stopped') ? 'flag' : ''}`}>{r.state.status}</span>
        {r.state.started && <span className="ink2">Started {r.state.started}</span>}{r.state.finished && <span className="ink2">Finished {r.state.finished}</span>}
        {r.state.status !== 'running' && r.state.status !== 'done' && <button className="btn primary" onClick={start}>{r.state.status === 'not started' ? 'Start' : 'Resume'}</button>}
        {r.state.status === 'running' && <button className="btn" onClick={async () => { await fetch(`/api/runs/${encodeURIComponent(r.name)}/stop`, { method: 'POST' }); load() }}>Stop</button>}
        {r.dataset_name && <button className="btn" onClick={() => onOpenDataset(r.dataset_name!)}>Open its samples</button>}
        {err && <span className="flag">{err}</span>}
      </div>
      <ol className="steps">{r.steps.map(s => { const st = r.state.steps[s.id] ?? { status: 'waiting' }
        return <li key={s.id} className={st.status}>
          <div className="srow"><b>{s.title}</b><span className="chip">{st.status}</span></div>
          {st.total !== undefined && <div className="prog"><div className="pbar"><i style={{ width: `${((st.done ?? 0) + (st.failed ?? 0)) / st.total * 100}%` }} /></div>
            <span className="num">{st.done ?? 0} done{st.failed ? `, ${st.failed} failed` : ''} of {st.total}{s.workers ? `, ${s.workers} at a time` : ''}</span>{st.last && <span className="ink2">Last: {st.last}</span>}</div>}
          <details><summary className="ink3">Command</summary><pre>{s.command.join(' ')}{s.items ? `\nonce per item of ${s.items}` : ''}</pre></details>
          {st.output && <details open={st.status === 'failed'}><summary className="ink3">Output</summary><pre>{st.output.join('\n')}</pre></details>}
        </li>})}</ol>
      {r.artifact_files.map(a => <section key={a.file} className="artifact"><h3>{a.file.split('/').pop()}</h3>
        {!a.exists ? <p className="ink2">Not written yet</p> : <>
          {a.content?.gates && <Gates g={a.content.gates} />}
          <Results r={a.content} />
          <details><summary className="ink3">All of {a.file}</summary><pre>{JSON.stringify(a.content, null, 1)}</pre></details></>}
      </section>)}
      <section><h3>Log</h3><pre className="log">{r.log.join('\n') || 'Nothing yet'}</pre></section>
      {r.plan_text && <section><h3>Plan <button className="btn" onClick={() => setShowPlan(!showPlan)}>{showPlan ? 'Hide' : 'Show'}</button></h3>
        <div className="ink2">{r.plan_file}{r.literature_file ? `, with the literature in ${r.literature_file}` : ''}</div>
        {showPlan && <pre className="plan">{r.plan_text}</pre>}</section>}
    </section>
  </main>
}
