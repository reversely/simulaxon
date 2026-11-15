/** The Experimental section (#25): the robotic empathy programme, held apart from the established experiments. Every
 * number comes from the study's run (experimental_list reads its files); example grasps play as recordings (#23). */
import { useEffect, useState } from 'react'
import { call, fmt } from './api'
import { RecordingView } from './recording'
import { Skeleton } from './wait'

type Row = { stream: string; label: string; role: string; held: number; auc: number | null }
type Diff = { contrast: string; label: string; held: number; ci95: [number, number] }
type Shake = { trials: number; random_candidate: number; oracle: number; rows: Row[]; differences: Diff[]; all_below_random: boolean; held_range: [number, number]; auc_range: [number, number] }
type Example = { trial: string; candidate: string; held_gentle: boolean; held_firm: boolean; lifted: boolean; object: string; grip_nm: number }
type Study = { id: string; experimental: boolean; missing?: string; title: string; question: string; programme: string; design: [string, string][]
  run: { when: string; candidates: number; lifted: number; held_gentle: number; held_firm: number; joint_stream_only_auc?: number; repeats_identical: string }
  shakes: Record<'gentle' | 'firm', Shake>; gates: { gate: string; result: string }[]; scope: string; source: string; examples: Example[] }

const pct = (x: number) => `${(100 * x).toFixed(1)}%`
const pp = (x: number) => `${x >= 0 ? '+' : '−'}${Math.abs(100 * x).toFixed(1)}`

function StudyCard({ s }: { s: Study }) {
  const [shake, setShake] = useState<'gentle' | 'firm'>('gentle'); const [ex, setEx] = useState(0)
  const S = s.shakes[shake]; const gate2 = s.gates.find(g => g.gate.startsWith('2 '))
  const e = s.examples[ex]
  return <article className="card expstudy">
    <div className="bar"><span className="chip flag">Experimental</span><span className="ink2 small">{s.programme}</span></div>
    <h2 className="section-title" style={{ margin: 0 }}>{s.title}</h2>
    <p style={{ margin: 0 }}><b>Question.</b> {s.question}</p>
    <div className="tablescroll"><table className="data compact"><tbody>{s.design.map(([k, v]) => <tr key={k}><td className="mid">{k}</td><td>{v}</td></tr>)}</tbody></table></div>
    <p className="ink2" style={{ margin: 0 }}>Run {s.run.when}: {s.run.candidates} grasps, {s.run.lifted} lifted, {s.run.held_gentle} held under the gentle shake and {s.run.held_firm} under the firm one. The same grasp run twice gave the same result in {s.run.repeats_identical}.</p>

    {e && <section className="expex">
      <div className="bar"><b>A grasp, as the robot and the observer's predicted cortex saw it</b>
        <div className="seg" role="group" aria-label="Example grasp" style={{ marginLeft: 'auto' }}>{s.examples.map((x, i) => <button key={`${x.trial}${x.candidate}`} className={i === ex ? 'on' : ''} onClick={() => setEx(i)}>
          {x.trial.replace('standard_t', 'Trial ')} {x.candidate}, {x.held_gentle ? 'held' : 'dropped'}</button>)}</div></div>
      <p className="ink2 small" style={{ margin: 0 }}>{e.object}, grip {e.grip_nm} N m. {e.held_gentle ? `Held under the gentle shake${e.held_firm ? ' and the firm one' : ', dropped under the firm one'}.` : e.lifted ? 'Lifted, then dropped.' : 'Not lifted.'} The streams end at 6 s, before the lift.</p>
      <RecordingView key={`${e.trial}/${e.candidate}`} manifestUrl={`/api/experimental/grasp/${e.trial}/${e.candidate}/recording.json`} />
    </section>}

    <div className="bar"><b>Results on {S.trials} held-out trials</b>
      <div className="seg" role="group" aria-label="Shake" style={{ marginLeft: 'auto' }}>{(['gentle', 'firm'] as const).map(k => <button key={k} className={shake === k ? 'on' : ''} onClick={() => setShake(k)}>{k === 'gentle' ? 'Gentle shake' : 'Firm shake'}</button>)}</div></div>
    <figure className="fig" style={{ margin: 0 }}>
      <figcaption><b>Table 1.</b> Share of trials whose chosen grasp held, by the streams the robot chose with; AUC of its hold prediction over every candidate.</figcaption>
      <div className="tablescroll"><table className="data compact"><thead><tr><th>Streams</th><th>Role</th><th className="num">Held</th><th className="num">AUC</th></tr></thead>
        <tbody>
          <tr className="base"><td>A random candidate</td><td className="ink2">baseline</td><td className="num">{pct(S.random_candidate)}</td><td /></tr>
          <tr className="base"><td>The best of the four</td><td className="ink2">ceiling</td><td className="num">{pct(S.oracle)}</td><td /></tr>
          {S.rows.map(r => <tr key={r.stream} className={r.stream === 'P+V+T paired' ? 'on' : ''}><td>{r.label}</td><td className="ink2">{r.role}</td><td className="num">{pct(r.held)}</td><td className="num">{r.auc != null ? fmt(r.auc) : ''}</td></tr>)}
        </tbody></table></div>
    </figure>
    <figure className="fig" style={{ margin: 0 }}>
      <figcaption><b>Table 2.</b> Differences in the share held, in percentage points, with 95% intervals from a paired bootstrap over trials.</figcaption>
      <div className="tablescroll"><table className="data compact"><thead><tr><th>Contrast</th><th className="num">Held</th><th className="num">95% interval</th></tr></thead>
        <tbody>{S.differences.map(d => <tr key={d.contrast}><td>{d.label}</td><td className="num">{pp(d.held)}</td><td className="num">{pp(d.ci95[0])} to {pp(d.ci95[1])}</td></tr>)}</tbody></table></div>
    </figure>
    <figure className="fig" style={{ margin: 0 }}>
      <figcaption><b>Table 3.</b> The gates set before the run.</figcaption>
      <div className="tablescroll"><table className="data compact"><tbody>{s.gates.map(g => <tr key={g.gate}><td>{g.gate.replace(/^\d+ /, '')}</td><td className={g.result === 'pass' ? 'num' : 'num flagtext'}>{g.result === 'pass' ? 'Pass' : 'Fail'}</td></tr>)}</tbody></table></div>
    </figure>
    <div className="expread">
      {S.all_below_random && <p>Every chooser, with or without TRIBE v2, picked grasps that held less often than a random pick: {pct(S.held_range[0])} to {pct(S.held_range[1])} against {pct(S.random_candidate)}, although each ranked all candidates with an AUC of {fmt(S.auc_range[0])} to {fmt(S.auc_range[1])}.</p>}
      {gate2?.result !== 'pass' && <p>The positive control was not detected, so at this size the test cannot show a stream that makes the robot hold more.</p>}
      <p className="ink2">{s.scope} Source: {s.source}.</p>
    </div>
  </article>
}

const KEPT: { list: Study[] | null } = { list: null }   // the last list, kept for the page's life: a revisit shows it at once (#30)

export function ExperimentalPage() {
  const [list, setList] = useState<Study[] | null>(() => KEPT.list); const [err, setErr] = useState('')
  useEffect(() => { call<Study[]>('experimental_list').then(l => { KEPT.list = l; setList(l) }).catch(x => setErr(String(x?.message ?? x))) }, [])
  return <div className="exppage">
    <h1 className="q">Experimental</h1>
    <p className="ink2" style={{ marginTop: 0 }}>Studies apart from the established experiments: the robotic empathy programme. Each states its controls, its gates and what it cannot say.</p>
    {err && <div className="dsnote">{err}</div>}
    {!list ? <Skeleton lines={2} blocks={[420]} label="Reading the studies" />
      : list.map(s => s.missing ? <div key={s.id} className="empty">{s.missing}</div> : <StudyCard key={s.id} s={s} />)}
  </div>
}
