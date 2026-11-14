import { useEffect, useState } from 'react'

// The new-project screen: a goal for the agent, prefilled with the sample in services/app-server/startup.json, with the
// paper, the study's images and its dataset one click away. Start hands the goal to the agent panel.

type Startup = { prompt: string; paper: { title: string; url: string }; images: { title: string; url: string; exists: boolean }[]; dataset: string; dataset_loaded: boolean }

export function NewProject({ onStart, onOpenDataset, onClose }: { onStart: (goal: string, dataset: string) => void; onOpenDataset: (name: string) => void; onClose: () => void }) {
  const [s, setS] = useState<Startup | null>(null), [goal, setGoal] = useState(''), [err, setErr] = useState('')
  useEffect(() => { fetch('/api/startup').then(r => r.ok ? r.json() : Promise.reject(new Error(r.statusText))).then((d: Startup) => { setS(d); setGoal(d.prompt) }).catch(e => setErr(String(e.message))) }, [])
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }; addEventListener('keydown', k); return () => removeEventListener('keydown', k) }, [onClose])
  const images = s?.images.filter(i => i.exists) ?? []
  return <div className="modal-back" role="dialog" aria-modal="true" aria-labelledby="np-title">
    <div className="modal">
      <div className="modal-head"><h2 id="np-title">New project</h2><button className="btn" onClick={onClose}>Close</button></div>
      <h3>Goal</h3>
      <p className="ink2">The agent runs the study on Fuzzball and compares TRIBE with the paper</p>
      {err && <p className="flag">The sample did not load: {err}</p>}
      <textarea className="goal" value={goal} onChange={e => setGoal(e.target.value)} rows={5} aria-label="Goal for the agent" placeholder="Replicate the main result of a paper: its DOI, title or link" />
      <div className="np-actions"><button className="btn primary" disabled={!goal.trim() || !s} onClick={() => s && onStart(goal.trim(), s.dataset)}>Start</button></div>
      {s && <div className="np-refs">
        <section><h3>Paper</h3><a href={s.paper.url} target="_blank" rel="noreferrer">{s.paper.title}</a></section>
        <section><h3>Dataset</h3>{s.dataset_loaded ? <button className="linkish" onClick={() => onOpenDataset(s.dataset)}>{s.dataset}</button> : <span className="ink2">{s.dataset} is not loaded yet</span>}</section>
        {images.length > 0 && <section className="np-images"><h3>Study images</h3><div className="thumbs">
          {images.map(i => <a key={i.url} href={i.url} target="_blank" rel="noreferrer" title={i.title}><img src={i.url} alt={i.title} loading="lazy" /><span className="ink2">{i.title}</span></a>)}
        </div></section>}
      </div>}
    </div>
  </div>
}
