import { useEffect, useState } from 'react'
import { Icon } from './icons'

export type Job = { key: string; stage: 'waiting' | 'rendering' | 'reading' | 'done'; next?: string; world?: string; lane?: string; elapsed_s?: number; project?: string; title?: string; label?: string; source?: string; actor?: string; image?: string; cached?: boolean; t: number }

const STAGES: [Job['stage'], string][] = [['rendering', 'Isaac'], ['reading', 'TRIBE'], ['done', 'Ready']]
// waiting: queued for the GPU, which runs one job at a time (runs first, then previews, then options prepared ahead)

/** The live workspace: every stimulus being generated right now, from previews, runs and demos alike, as it moves
 * through Isaac and TRIBE. Items read from cache say so. Clicking one opens its project. */
export type RunNow = { id: string; title?: string; done: number; total: number; stage?: string }

export function LiveWorkspace({ jobs, runs = [], onOpen }: { jobs: Job[]; runs?: RunNow[]; onOpen: (project: string) => void }) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t) }, [])
  const ahead = (j: Job) => j.lane === 'ahead' || /^Prepared/.test(j.source ?? '')   // renders made ahead on a guess: counted, not shown as cards
  const active = jobs.filter(j => j.stage !== 'done' && !ahead(j)); const preparing = jobs.filter(j => j.stage !== 'done' && ahead(j)).length
  const recent = jobs.filter(j => j.stage === 'done').slice(0, 6)
  const [open, setOpen] = useState(false)
  if (!jobs.length && !runs.length) return null
  if (!active.length && !open) return <section className="live compact" aria-label="Live workspace">
    {runs.length || preparing ? <div className="runsnow">{runs.map(r => <button key={r.id} className="runnow" title={r.title} onClick={() => onOpen(r.id)}>
      <span className="pulse on" aria-hidden /><b>Running</b><span className="title">{r.title}</span>
      <span className="ink2 num">{r.stage === 'comparing' ? 'Comparing' : r.total ? `${r.done} of ${r.total} clips` : 'Starting'}</span>
      {r.total > 0 && <span className="fbar" style={{ width: 120 }}><span style={{ width: `${100 * r.done / r.total}%` }} /></span>}
    </button>)}{preparing > 0 && <span className="ink2 prep"><span className="pulse" aria-hidden />{preparing} {preparing === 1 ? 'render' : 'renders'} prepared ahead, after runs and previews</span>}</div> : <><span className="pulse" aria-hidden /><b>Nothing generating</b><span className="ink2">{recent.length} generated recently</span></>}
    {recent.length > 0 && <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => setOpen(true)}><Icon name="clock" size={15} />Show recent</button>}
  </section>
  return <section className={`live ${active.length ? 'on' : ''}`} aria-label="Live workspace" aria-live="polite">
    <div className="livehead">
      <span className={`pulse ${active.length ? 'on' : ''}`} aria-hidden />
      <b>{active.length ? 'Generating now' : 'Recent'}</b>
      {active.length > 0 && <span className="ink2">{active.length} in Isaac or TRIBE{preparing ? `, and ${preparing} more prepared ahead` : ''}</span>}
      {!active.length && <button className="btn" style={{ marginLeft: 'auto' }} onClick={() => setOpen(false)}><Icon name="close" size={15} />Hide</button>}
    </div>
    <div className="livecards">
      {[...active, ...recent].slice(0, 8).map(j => <button key={j.key} className={`livecard ${j.stage}`} onClick={() => j.project && onOpen(j.project)} title={j.title}>
        {j.image ? <img src={j.image} alt="" /> : <span className="liveph"><span className="spin" /></span>}
        <span className="livetext">
          <span className="livelabel">{j.label ?? 'Stimulus'}</span>
          <span className="ink2">{j.source}{j.actor === 'agent' ? ' by the agent' : ''}</span>
          <span className="livestages">{j.cached ? <span className="chip">From cache</span> : j.stage === 'waiting' ? <span className="chip">Waiting for the GPU</span> : STAGES.map(([s, n]) => <span key={s} className={`ls ${STAGES.findIndex(x => x[0] === s) <= STAGES.findIndex(x => x[0] === j.stage) ? 'reached' : ''} ${s === j.stage && s !== 'done' ? 'now' : ''}`}>{n}</span>)}
            {j.stage !== 'done' && <span className="num ink2">{Math.round((now - j.t) / 1000 + (j.elapsed_s ?? 0))} s</span>}</span>
        </span>
      </button>)}
    </div>
  </section>
}
