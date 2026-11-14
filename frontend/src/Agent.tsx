import { useEffect, useRef, useState } from 'react'
import type { Stage } from './api'

// The conversation. Every reply lists the tool calls the agent made, with their arguments one click away. When the
// agent shows a view, it arrives as stages marked "by agent" in the view bar, removable like any other stage.

export type Msg = { who: 'person' | 'agent'; text: string; calls?: { tool: string; arguments: any }[]; shown?: { dataset: string; stages: Stage[]; why: string; fields_on_tiles?: string[] } | null; error?: boolean }

export function Agent({ dataset, stages, msgs, setMsgs, onShow, queued, onQueuedSent }: {
  dataset: string; stages: Stage[]; msgs: Msg[]; setMsgs: (f: (m: Msg[]) => Msg[]) => void; onShow: (d: string, s: Stage[], fields: string[]) => void
  queued?: string; onQueuedSent?: () => void   // a goal from the new-project screen, sent once
}) {
  const [text, setText] = useState(''), [busy, setBusy] = useState(false), [since, setSince] = useState(0)
  const end = useRef<HTMLDivElement>(null)
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs.length, busy])
  useEffect(() => { if (!busy) return; const t0 = Date.now(); const i = setInterval(() => setSince(Math.round((Date.now() - t0) / 1000)), 1000); return () => clearInterval(i) }, [busy])
  const send = async (given?: string) => {
    const m = (given ?? text).trim(); if (!m || busy) return
    const history = msgs.map(x => ({ who: x.who, text: x.text }))
    setMsgs(x => [...x, { who: 'person', text: m }]); if (given === undefined) setText(''); setBusy(true); setSince(0)
    try {
      const r = await fetch('/api/agent', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ dataset, stages: stages.map(({ by: _, ...s }) => s), message: m, history }) })
      const d = await r.json()
      if (!r.ok) throw new Error(d.detail || r.statusText)
      setMsgs(x => [...x, { who: 'agent', text: d.reply, calls: d.tool_calls, shown: d.show }])
      if (d.show) onShow(d.show.dataset, d.show.stages, d.show.fields_on_tiles ?? [])
    } catch (e: any) { setMsgs(x => [...x, { who: 'agent', text: `The agent did not answer: ${e.message}`, error: true }]) }
    setBusy(false)
  }
  useEffect(() => { if (queued && !busy) { onQueuedSent?.(); send(queued) } }, [queued])
  return <section className="agent" aria-label="Agent">
    <div className="msgs">
      {msgs.length === 0 && <p className="ink2">Ask about the data on screen. The agent reads it through the same views you use, and can put a view on screen.</p>}
      {msgs.map((m, i) => <div key={i} className={`msg ${m.who} ${m.error ? 'flag' : ''}`}>
        <div className="who">{m.who === 'person' ? 'You' : 'Agent'}</div>
        <div className="text">{m.text}</div>
        {m.shown && <div className="shown">Put on screen: {m.shown.why}</div>}
        {m.calls && m.calls.length > 0 && <details className="calls"><summary>{m.calls.length} tool call{m.calls.length > 1 ? 's' : ''}: {m.calls.map(c => c.tool).join(', ')}</summary>
          {m.calls.map((c, k) => <pre key={k}><b>{c.tool}</b> {JSON.stringify(c.arguments, null, 1)}</pre>)}</details>}
      </div>)}
      {busy && <div className="msg agent"><div className="who">Agent</div><div className="ink2">Working, {since} s</div></div>}
      <div ref={end} />
    </div>
    <div className="compose">
      <textarea value={text} onChange={e => setText(e.target.value)} placeholder="Ask or tell the agent" rows={3} aria-label="Message to the agent"
        onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
      <button className="btn primary" onClick={() => send()} disabled={busy || !text.trim()}>Send</button>
    </div>
  </section>
}
