import { useEffect, useRef, useState, type ReactNode } from 'react'
import { upload as sendFile, toolName } from './api'
import { Icon, type IconName } from './icons'

export type ToolCall = { tool: string; arguments: Record<string, unknown>; at: number; result?: string; error?: boolean; internal?: boolean; project_id?: string }
export type Turn = { n: number; from?: 'person' | 'wake' | 'goal'; mode?: 'discuss' | 'through'; prompt: string; started: string; ended?: string; seconds?: number; tool_calls: ToolCall[]; text: string[]; reply: string | null }
export type SessionInfo = { id: string; goal: string; project_id: string | null; mode?: string; status: 'working' | 'waiting' | 'idle' | 'done' | 'stopped' | 'failed'; why?: string; started: string; updated?: string; agent: string; waiting_for?: string[]; turns: number; tool_calls: number; errors: number; internal_errors?: number }
export type Session = SessionInfo & { turns: Turn[] }

const STATUS: Record<string, string> = { working: 'Working', waiting: 'Waiting for a run', idle: 'Waiting for you', done: 'Finished', stopped: 'Stopped', failed: 'Failed' }
export { toolName } from './api'   // one name table for the chat's steps and the History menu (#21)
const args = (c: ToolCall) => ((c.arguments as any)?.arguments ?? c.arguments ?? {}) as Record<string, any>   // older chats kept the proxy's wrapper

/** One line saying what a call was about: the paper, the dataset, the words searched, the experiment's title. */
function about(c: ToolCall): string {
  const a = args(c); const v = a.ref ?? a.query ?? a.find ?? a.title ?? a.dataset_id ?? a.paper_id ?? a.project_id ?? (a.part != null ? `part ${a.part}` : '')
  return typeof v === 'string' ? v : JSON.stringify(v ?? '')
}
const strip = (s: string) => s.replace(/\s*\b(WAITING|DONE)\s*$/, '').trim()

async function post(url: string, body: unknown) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail ?? r.statusText)
  return r.json()
}

/** The agent's chats from any screen: the newest ones still going, what each is doing, Open and Stop. */
export function SessionDock({ sessions, onOpen, onStop }: { sessions: SessionInfo[]; onOpen: (id: string) => void; onStop: (id: string) => void }) {
  const active = sessions.filter(s => s.status === 'working' || s.status === 'waiting')
  if (!active.length) return null
  return <section className="sessions on" aria-label="The agent at work" aria-live="polite">
    {active.map(s => <div key={s.id} className="sessionrow">
      <span className={`pulse ${s.status === 'working' ? 'on' : ''}`} aria-hidden />
      <span className="sgoal" title={s.goal}>{s.goal}</span>
      <span className="chip">{STATUS[s.status]}</span>
      <span className="ink2 num">{s.tool_calls} steps{s.errors ? `, ${s.errors} refused` : ''}{s.internal_errors ? `, ${s.internal_errors} ${s.internal_errors === 1 ? 'error' : 'errors'}` : ''}</span>
      <span className="bar" style={{ marginLeft: 'auto' }}>
        <button className="btn" onClick={() => onOpen(s.id)}><Icon name="open" size={15} />Open</button>
        <button className="btn" onClick={() => onStop(s.id)}><Icon name="stop" size={15} />Stop</button>
      </span>
    </div>)}
  </section>
}

/** A chat with the agent. Discuss, link or upload data, agree a set-up, then let it run; or give one goal and let it
 * go all the way through. Each reply's steps fold under it; the experiment it sets up opens from the chat. Results of
 * runs and fetches arrive on their own when they finish. */
export function Chat({ sid, projectId, live, compact, header, footer, chips, onStarted, onOpenProject }: {
  sid: string | null; projectId?: string | null; live: number; compact?: boolean; header?: ReactNode; footer?: ReactNode
  chips?: { label: string; run: () => void; icon?: IconName }[]; onStarted: (id: string) => void; onOpenProject: (pid: string) => void
}) {
  const [s, setS] = useState<Session | null>(null); const [text, setText] = useState(''); const [files, setFiles] = useState<{ file: string; dataset_id: string; megabytes: number }[]>([])
  const [open, setOpen] = useState<Record<string, boolean>>({}); const [busy, setBusy] = useState(false); const [err, setErr] = useState(''); const [sent, setSent] = useState<{ text: string; mode: string } | null>(null)   // shown at once, until the chat has it
  const end = useRef<HTMLDivElement>(null); const fileIn = useRef<HTMLInputElement>(null)
  useEffect(() => { if (!sid) { setS(null); return } fetch(`/agent/sessions/${sid}`).then(r => r.json()).then(setS).catch(() => {}) }, [sid, live])
  const last = s?.turns[s.turns.length - 1]
  useEffect(() => { if (sent && s?.turns.some(t => t.prompt.replace(/^Goal: /, '') === sent.text)) setSent(null) }, [s, sent])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [s?.turns.length, last?.tool_calls.length, last?.reply])
  const running = s?.status === 'working' || s?.status === 'waiting'

  async function send(mode: 'discuss' | 'through') {
    const body = text.trim() + (files.length ? `\n\nUploaded here: ${files.map(f => f.file).join(', ')} (dataset ${files[0].dataset_id})` : '')
    if (!body.trim()) return
    setBusy(true); setErr(''); setSent({ text: body, mode })
    try {
      if (sid) await post(`/agent/sessions/${sid}/message`, { text: body, mode })
      else onStarted((await post('/agent/sessions', { text: body, mode, project_id: projectId ?? null })).id)
      setText(''); setFiles([])
    } catch (e) { setErr(String((e as Error).message)); setSent(null) }
    setBusy(false)
  }
  async function upload(list: FileList | null) {
    if (!list) return
    for (const f of Array.from(list)) {
      const r = await sendFile(`/datasets/upload?name=${encodeURIComponent(f.name)}${files[0] ? `&dataset_id=${files[0].dataset_id}` : ''}`, f)
      if (r.ok) { const j = await r.json(); setFiles(fs => [...fs, j]) } else setErr(`${f.name} was not uploaded`)
    }
  }

  return <>
    <div className={`convo chat ${compact ? 'compact' : ''}`}>
      {header}
      {!s && !header && <div className="msg"><div className="who">Agent</div>Tell me what you want to test, or a paper to replicate. Paste a link to a paper or a dataset, or upload files. We can work out the set-up together, or I can go all the way through.</div>}
      {s?.turns.map(t => {
        const fromPerson = t.from === 'person' || t.from === 'goal' || (t.from == null && t.n === 1)
        const made = t.tool_calls.find(c => c.project_id)
        const steps = t.tool_calls.filter(c => c.tool !== 'ToolSearch')
        return <div key={t.n} className="exchange">
          {fromPerson ? <div className="msg me"><div className="who">You{t.mode === 'through' ? ', set up and run' : ''}</div><div className="text">{t.prompt.replace(/^Goal: /, '')}</div></div>
            : <div className="wake">{t.prompt.split('\n').slice(0, 2).join(' ').replace(/\s*Continue\.?$/, '')}</div>}
          <div className="msg agent">
            <div className="who">Agent{t.seconds != null ? <span className="ink3 num">, {t.seconds} s</span> : ''}</div>
            {steps.length > 0 && <button className="stepsbtn" onClick={() => setOpen(o => ({ ...o, [t.n]: !o[t.n] }))} aria-expanded={!!open[t.n]}>
              {open[t.n] ? 'Hide' : 'Show'} {steps.length} {steps.length === 1 ? 'step' : 'steps'}{steps.some(c => c.error && !c.internal) ? `, ${steps.filter(c => c.error && !c.internal).length} refused` : ''}{steps.some(c => c.internal) ? `, ${steps.filter(c => c.internal).length} ${steps.filter(c => c.internal).length === 1 ? 'error' : 'errors'}` : ''}</button>}
            {open[t.n] && <ol className="calls">{steps.map((c, i) => <li key={i} className={c.error ? 'refused' : ''}>
              <details><summary className="callrow"><span>{toolName(c.tool)}</span>{!compact && <span className="ink2 about">{about(c)}</span>}{c.error && <span className="chip flag">{c.internal ? 'Error' : 'Refused'}</span>}</summary>
                <pre className="codebox">{`${c.tool}(${JSON.stringify(args(c), null, 1)})\n\n${c.result ?? 'No result yet'}`}</pre></details></li>)}</ol>}
            {made && <button className="madecard" onClick={() => onOpenProject(made.project_id!)}><span className="ink2">Set up</span><span>{String(args(made).title ?? 'Experiment')}</span><span className="ink2">Open</span></button>}
            {t.reply === null ? <div className="ink2"><span className="spin" /> {steps.length ? toolName(steps[steps.length - 1].tool) : 'Thinking'}</div>
              : <div className="text">{strip(t.reply) || (t.reply.trim() === 'WAITING' ? 'Started. I will report when it finishes.' : '')}</div>}
          </div>
        </div>
      })}
      {sent && <div className="exchange"><div className="msg me"><div className="who">You{sent.mode === 'through' ? ', set up and run' : ''}</div><div className="text">{sent.text}</div></div><div className="msg agent"><div className="ink2"><span className="spin" /> Thinking</div></div></div>}
      {s?.status === 'waiting' && <div className="wake"><span className="spin" /> Waiting for {s.waiting_for?.map(w => w.replace(/ of project .*/, '')).join(', ')}. The agent continues when it ends.</div>}
      {s?.why && s.status !== 'working' && <div className="wake">{s.why}</div>}
      {footer}
      <div ref={end} />
    </div>
    {chips && chips.length > 0 && <div className="chips">{chips.map(c => <button key={c.label} onClick={c.run}>{c.icon && <Icon name={c.icon} size={15} />}{c.label}</button>)}</div>}
    <form className="ask composer" onSubmit={e => { e.preventDefault(); send('discuss') }}>
      {files.length > 0 && <div className="attach">{files.map(f => <span key={f.file} className="origin file">{f.file}</span>)}</div>}
      <textarea aria-label="Message the agent" placeholder="Discuss, or paste a link to a paper or dataset" value={text} onChange={e => setText(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send('discuss') } }} />
      <div className="bar">
        <input ref={fileIn} type="file" multiple hidden onChange={e => { upload(e.target.files); e.target.value = '' }} aria-label="Files to upload" />
        <button type="button" className="btn" onClick={() => fileIn.current?.click()}><Icon name="upload" size={16} />Upload</button>
        {running && sid && <button type="button" className="btn" onClick={() => fetch(`/agent/sessions/${sid}/stop`, { method: 'POST' })}><Icon name="stop" size={16} />Stop</button>}
        {err && <span className="flag">{err}</span>}
        <span className="bar" style={{ marginLeft: 'auto' }}>
          <button type="submit" className="btn" disabled={busy || (!text.trim() && !files.length)}><Icon name="send" size={16} />Send</button>
          <button type="button" className="btn primary" disabled={busy || (!text.trim() && !files.length)} onClick={() => send('through')}><Icon name="play" size={16} />Set up and run</button>
        </span>
      </div>
    </form>
  </>
}
