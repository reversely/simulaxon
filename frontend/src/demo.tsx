import { fmt } from './api'

export type DemoStep = { title: string; flow: string; paper?: string; here?: string }
export type DemoInfo = { id: string; title: string | null; paper: string; url: string; template: string; steps: DemoStep[]; written: boolean; writing: boolean; missing_projects?: string[] }
export type DemoState = { demo: string | null; step: number; status: 'idle' | 'playing' | 'paused' | 'waiting' | 'done' | 'failed'; error?: string | null; title?: string; paper?: string; url?: string; steps?: DemoStep[] }
export type Narration = { demo: string; step: number; title: string; paper: string; here: string; reading?: any; read?: any }

const STATUS: Record<string, string> = { playing: 'Playing', paused: 'Paused', waiting: 'Waiting for live results', done: 'Finished', failed: 'Step failed' }

/** The player for a paper demo: where it is in the paper's order, and Play, Pause, Next and Stop. */
export function DemoBar({ state, onControl }: { state: DemoState; onControl: (a: 'pause' | 'resume' | 'next' | 'stop') => void }) {
  if (!state.demo || state.status === 'idle' || !state.steps) return null
  return <section className="demobar" aria-label="Paper demo">
    <div className="bar">
      <span className="mid">{state.title}</span>
      <a className="ink2" href={state.url} target="_blank" rel="noreferrer">{state.paper}</a>
      <span className={`chip ${state.status === 'waiting' || state.status === 'failed' ? 'flag' : ''}`}>{STATUS[state.status]}</span>
      {state.status === 'failed' && state.error && <span className="ink2">{state.error}</span>}
      <span className="bar" style={{ marginLeft: 'auto' }}>
        {state.status === 'paused' ? <button className="btn primary" onClick={() => onControl('resume')}>Play</button>
          : !['done', 'failed'].includes(state.status) && <button className="btn" onClick={() => onControl('pause')}>Pause</button>}
        {!['done', 'failed'].includes(state.status) && <button className="btn" onClick={() => onControl('next')}>Next step</button>}
        <button className="btn" onClick={() => onControl('stop')}>{['done', 'failed'].includes(state.status) ? 'Close' : 'Stop'}</button>
      </span>
    </div>
    <ol className="stepper">{state.steps.map((s, i) => <li key={i} className={i < state.step || state.status === 'done' ? 'past' : i === state.step ? 'now' : ''}>
      <span className="num">{i + 1}</span>{s.title}</li>)}</ol>
  </section>
}

/** One narrated step: what the paper did, what happens here, and the live reading, never a typed-in number. */
export function NarrationMsg({ n }: { n: Narration }) {
  const r = n.reading
  return <div className="msg narr">
    <div className="who">Agent, step {n.step + 1}: {n.title}</div>
    <p><b>In the paper.</b> {n.paper}</p>
    <p><b>Here.</b> {n.here}</p>
    {r && r.value !== undefined && <p className="reading"><span className="mid num">{fmt(r.value)}</span> in {String(r.region)}, interval {fmt(r.interval_95[0])} to {fmt(r.interval_95[1])}, {r.units_positive} of {r.n} above zero</p>}
    {r && r.score !== undefined && <p className="reading"><span className="mid num">{r.score.toFixed(2)}</span> for {r.condition}, against random sets {r.random_95[0].toFixed(2)} to {r.random_95[1].toFixed(2)}. {(r.share_random_at_least * 100).toFixed(2)}% of random sets reach it</p>}
    {n.read && !r && <p className="ink2">The live result is not in yet.</p>}
  </div>
}
