/** Demo mode (#26): a guided walk through the lab that plays the real app at each step, with the architecture beside it
 * in two shared diagrams: the loop the step belongs to, and what runs where under Fuzzball on CIQ (docs/pitch.md, "How
 * it runs on CIQ"; docs/spark-layout.md for the Spark). Tiles carry one line icon; arrows carry short monospace labels. */
import { useEffect, useRef, type ReactNode } from 'react'
import { Icon, type IconName } from './icons'

export type Piece = 'app' | 'planner' | 'isaac' | 'cosmos' | 'tribe' | 'vast'
export type Go = { view: string; chat?: string | null; project?: 'experiment' | 'world'; prefer?: string[]; history?: boolean; dataset?: { id: string; tab?: 'samples' | 'adapters' } }
export type GuideStep = { id: string; title: string; text: string; tile: number; arrow?: number; pieces: Piece[]; data: string; go: Go }

const LOOP: [string, IconName][] = [['Hypothesis', 'chat'], ['Scenes', 'room'], ['Brain response', 'brain'], ['Next test', 'flask']]
const ARROWS = ['plan what to vary', 'TRIBE v2 predicts', 'compare conditions', 'follow up']

const HUMANOID = ['project_920ddb5712']   // Isaac Sim renders against their Cosmos restyles: the whole pipeline in one project
const UPLOAD_CHAT = 'session_8f10f294'   // a person uploads stills of a human and a Unitree G1 and asks; the agent sets up, runs and reports
export const GUIDE: GuideStep[] = [
  { id: 'intro', title: 'How Simulaxon works', text: 'Simulaxon turns a question about the brain into rendered scenes, predicted fMRI and a next test. The steps below walk one project through that loop.',
    tile: -1, pieces: ['app', 'planner', 'isaac', 'cosmos', 'tribe', 'vast'], data: 'projects, clips, predictions and the step log', go: { view: 'agent', chat: null } },
  { id: 'ask', title: 'Upload and ask', text: 'Upload stills or clips and write a hypothesis in the chat. The agent plans the experiment, sets it up, runs it and reports what TRIBE v2 predicts.',
    tile: 0, arrow: 0, pieces: ['app', 'planner', 'vast'], data: 'the uploads, the project and every step', go: { view: 'agent', chat: UPLOAD_CHAT } },
  { id: 'data', title: 'Bring stimuli', text: 'Import clips, images or a folder, or fetch an open dataset. Every file becomes a sample to filter, tag and save as a view.',
    tile: 0, pieces: ['app', 'vast'], data: 'datasets and their samples', go: { view: 'datasets' } },
  { id: 'scene', title: 'Build a scene', text: 'Each control is one line of the scene script. Change it and Isaac Sim renders the room again; TRIBE v2 reads the new render.',
    tile: 1, arrow: 1, pieces: ['app', 'isaac', 'tribe', 'vast'], data: 'renders and their predictions', go: { view: 'room', project: 'world', prefer: ['falls'] } },
  { id: 'run', title: 'Run the experiment', text: 'A run renders every trial, can restyle each with Cosmos so it looks filmed, and predicts the response second by second.',
    tile: 1, arrow: 1, pieces: ['app', 'isaac', 'cosmos', 'tribe', 'vast'], data: 'clips and predictions', go: { view: 'samples', project: 'experiment', prefer: HUMANOID } },
  { id: 'brain', title: 'Watch the brain', text: 'A trial and its predicted cortex play on one clock. Scrub to any second, and drag the brain to turn it.',
    tile: 2, pieces: ['app', 'vast'], data: 'predictions, drawn in your browser', go: { view: 'room', project: 'experiment', prefer: HUMANOID } },
  { id: 'results', title: 'Read the results', text: 'Each contrast with its 95% interval, its baselines and the whole cortex. Every table and figure downloads.',
    tile: 2, arrow: 2, pieces: ['app', 'vast'], data: 'the run record and its maps', go: { view: 'results', project: 'experiment', prefer: HUMANOID } },
  { id: 'follow', title: 'Follow up, or undo', text: "The agent's next tests land in the same project. Every change is a step: History says who made it, and any step can be undone.",
    tile: 3, arrow: 3, pieces: ['app', 'planner', 'vast'], data: 'the step log', go: { view: 'room', project: 'experiment', prefer: HUMANOID, history: true } },
  { id: 'adapter', title: 'Fit the model to people', text: 'Where a dataset has measured fMRI, fit an adapter in one action and see how much closer it gets on stimuli it never saw.',
    tile: 2, pieces: ['app', 'vast'], data: "measured responses and the adapter's weights", go: { view: 'datasets', dataset: { id: 'openneuro_ds004488', tab: 'adapters' } } },
]

/** A tile with one icon: the diagrams' only shape. */
function Tile({ x, y, w, h, icon, label, sub, on }: { x: number; y: number; w: number; h: number; icon?: IconName; label: string; sub?: string; on: boolean }) {
  return <g className={`gtile ${on ? 'on' : ''}`}>
    <rect x={x} y={y} width={w} height={h} rx={6} />
    {icon && <g className="gicon" transform={`translate(${x + w / 2 - 10} ${y + 10})`}><Icon name={icon} size={20} /></g>}
    <text x={x + w / 2} y={y + (icon ? 46 : h / 2 + (sub ? -2 : 5))} textAnchor="middle" className="glabel">{label}</text>
    {sub && <text x={x + w / 2} y={y + (icon ? 60 : h / 2 + 12)} textAnchor="middle" className="gsub">{sub}</text>}
  </g>
}

/** An arrow with a short monospace label set in a gap of the line, as in the reference. */
function Arrow({ d, label, lx, ly, on, head }: { d: string; label: string; lx: number; ly: number; on: boolean; head: string }) {
  return <g className={`garrow ${on ? 'on' : ''}`}>
    <path d={d} /><path d={head} className="ghead" />
    <text x={lx} y={ly} textAnchor="middle" className="gmono">{label}</text>
  </g>
}

/** The loop every step belongs to: hypothesis, scenes, brain response, next test. */
export function LoopDiagram({ tile, arrow }: { tile: number; arrow?: number }) {
  const W = 120, H = 70, L = 14, R = 266, T = 14, B = 196
  const pos = [[L, T], [R, T], [R, B], [L, B]]
  return <svg className="gdiagram" viewBox="0 0 400 280" role="img" aria-label={`The loop: ${LOOP.map(l => l[0]).join(', ')}. ${tile >= 0 ? ` This step: ${LOOP[tile][0]}.` : ''}`}>
    <Arrow on={arrow === 0} d={`M${L + W + 6} ${T + 35} H${R - 8}`} head={`M${R - 14} ${T + 30} L${R - 6} ${T + 35} L${R - 14} ${T + 40}`} label={ARROWS[0]} lx={200} ly={T + 26} />
    <Arrow on={arrow === 1} d={`M${R + 60} ${T + H + 6} V${T + H + 34} M${R + 60} ${T + H + 58} V${B - 8}`} head={`M${R + 55} ${B - 14} L${R + 60} ${B - 6} L${R + 65} ${B - 14}`} label={ARROWS[1]} lx={R + 60} ly={T + H + 50} />
    <Arrow on={arrow === 2} d={`M${R - 6} ${B + 35} H${L + W + 8}`} head={`M${L + W + 14} ${B + 30} L${L + W + 6} ${B + 35} L${L + W + 14} ${B + 40}`} label={ARROWS[2]} lx={200} ly={B + 56} />
    <Arrow on={arrow === 3} d={`M${L + 60} ${B - 6} V${B - 34} M${L + 60} ${B - 58} V${T + H + 8}`} head={`M${L + 55} ${T + H + 14} L${L + 60} ${T + H + 6} L${L + 65} ${T + H + 14}`} label={ARROWS[3]} lx={L + 60} ly={B - 42} />
    {LOOP.map(([label, icon], i) => <Tile key={label} x={pos[i][0]} y={pos[i][1]} w={W} h={H} icon={icon} label={label} on={i === tile} />)}
  </svg>
}

const PIECES: { id: Piece; label: string; sub?: string; box: 'app' | 'video' }[] = [
  { id: 'app', label: 'App server', sub: 'tools, store, page', box: 'app' }, { id: 'planner', label: 'Planner', sub: 'Nemotron Super 120B', box: 'app' },
  { id: 'isaac', label: 'Isaac Sim', sub: 'renders', box: 'video' }, { id: 'cosmos', label: 'Cosmos 3 Nano', sub: 'restyles', box: 'video' }, { id: 'tribe', label: 'TRIBE v2', sub: 'predicts fMRI', box: 'video' },
]

/** What runs where: Fuzzball starts the app and the video pipeline on two workstations that share VAST at /data. */
export function PlacementDiagram({ pieces, data }: { pieces: Piece[]; data: string }) {
  const on = new Set(pieces); const app = PIECES.filter(p => p.box === 'app'), video = PIECES.filter(p => p.box === 'video')
  return <svg className="gdiagram" viewBox="0 0 400 300" role="img" aria-label={`What runs where. This step uses ${PIECES.filter(p => on.has(p.id)).map(p => p.label).join(', ')}${on.has('vast') ? `, and VAST /data: ${data}` : ''}.`}>
    <rect x={4} y={4} width={392} height={292} rx={8} className="gframe" />
    <text x={16} y={24} className="gmono">Fuzzball on CIQ</text>
    <rect x={14} y={34} width={172} height={182} rx={6} className="gbox" /><text x={24} y={52} className="gsub">App workstation, 128 GB</text>
    <rect x={214} y={34} width={172} height={182} rx={6} className="gbox" /><text x={224} y={52} className="gsub">Video workstation, 128 GB</text>
    {app.map((p, i) => <Tile key={p.id} x={24} y={62 + i * 54} w={152} h={46} label={p.label} sub={p.sub} on={on.has(p.id)} />)}
    {video.map((p, i) => <Tile key={p.id} x={224} y={62 + i * 51} w={152} h={44} label={p.label} sub={p.sub} on={on.has(p.id)} />)}
    <g className={`garrow ${on.has('app') && (on.has('isaac') || on.has('tribe') || on.has('cosmos')) ? 'on' : ''}`}><path d="M176 85 H224" /><path d="M218 80 L224 85 L218 90" className="ghead" /><text x={200} y={110} textAnchor="middle" className="gmono">jobs</text></g>
    <g className={`garrow ${on.has('vast') ? 'on' : ''}`}><path d="M100 216 V238 M300 216 V238" /><path d="M95 232 L100 238 L105 232 M295 232 L300 238 L305 232" className="ghead" /></g>
    <Tile x={14} y={240} w={372} h={46} label="VAST, /data" sub={on.has('vast') ? data : 'shared by both workstations'} on={on.has('vast')} />
  </svg>
}

/** The guide's first page: one slide over the app. The loop as four stages joined by arrows, each naming the model that
 * does it and its maker, then where it all runs. A stage opens the guide at its first step. */
const STAGES: { label: string; icon: IconName; does: string; by: string }[] = [
  { label: 'Upload and ask', icon: 'upload', does: 'Upload stills or clips and ask a question; the agent plans the test', by: 'Nemotron Super 120B, NVIDIA' },
  { label: 'Scenes', icon: 'room', does: 'Renders each trial and restyles it', by: 'Isaac Sim and Cosmos 3 Nano, NVIDIA' },
  { label: 'Brain response', icon: 'brain', does: 'Predicts fMRI second by second', by: 'TRIBE v2, Meta' },
  { label: 'Next test', icon: 'flask', does: 'Compares conditions and picks a follow-up', by: 'Nemotron Super 120B, NVIDIA' },
]

export function IntroSlide({ onStep, onClose }: { onStep: (i: number) => void; onClose: () => void }) {
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }; addEventListener('keydown', k); return () => removeEventListener('keydown', k) }, [onClose])
  const first = (t: number) => GUIDE.findIndex(g => g.id !== 'intro' && g.tile === t)
  return <div className="gslide-scrim" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
    <section className="gslide" role="dialog" aria-modal="true" aria-labelledby="gslide-title">
      <button className="iconbtn gslide-x" aria-label="Close the guide" onClick={onClose}><Icon name="close" size={18} /></button>
      <h2 id="gslide-title">Welcome to Simulaxon</h2>
      <p className="gslide-lede">Upload stimuli and ask a question about the brain. Simulaxon renders the scenes, predicts the fMRI response and plans the next test.</p>
      <div className="gloop">
        <ol className="gstages">
          {STAGES.map((st, i) => <li key={st.label}>
            <button className="gstage" onClick={() => onStep(first(i))}>
              <Icon name={st.icon} size={22} /><b>{st.label}</b><span className="gdoes">{st.does}</span><span className="gby">{st.by}</span>
            </button>
            {i < STAGES.length - 1 && <svg className="garr" viewBox="0 0 28 12" aria-hidden="true"><path d="M1 6H25M20 1l5 5-5 5" /></svg>}
          </li>)}
        </ol>
        <div className="greturn" aria-hidden="true"><svg viewBox="0 0 12 10"><path d="M1 9l5-7 5 7" /></svg><span>follow up</span></div>
      </div>
      <p className="gslide-run">Runs on <b>Fuzzball</b> by CIQ, across two workstations that share one <b>VAST</b> volume.</p>
      <div className="gslide-nav">
        <button className="btn" onClick={onClose}>Close</button>
        <button className="btn primary" onClick={() => onStep(1)}>Start</button>
      </div>
    </section>
  </div>
}

/** The guide's panel: the step, its two diagrams, and Back and Next. */
export function GuidePanel({ step, onStep, onClose, children }: { step: number; onStep: (i: number) => void; onClose: () => void; children?: ReactNode }) {
  const s = GUIDE[step]; const top = useRef<HTMLElement>(null)
  useEffect(() => { top.current?.scrollIntoView({ block: 'start' }) }, [step])   // each step opens at its title, never mid-diagram where Next was
  return <section className="guide" aria-label="Guide" ref={top}>
    <div className="bar">
      <span className="gmono ink2">Guide, step {step} of {GUIDE.length - 1}</span>
      <button className="iconbtn" style={{ marginLeft: 'auto' }} aria-label="Close the guide" onClick={onClose}><Icon name="close" size={18} /></button>
    </div>
    <h2 className="section-title" style={{ margin: 0 }}>{s.title}</h2>
    <p style={{ margin: 0 }}>{s.text}</p>
    {children}
    <LoopDiagram tile={s.tile} arrow={s.arrow} />
    <PlacementDiagram pieces={s.pieces} data={s.data} />
    <div className="bar gnav">
      <button className="btn" onClick={() => onStep(step - 1)}>Back</button>
      <ol className="gdots" aria-label="Steps">{GUIDE.map((g, i) => i > 0 && <li key={g.id}><button className={i === step ? 'on' : ''} aria-label={`Step ${i}: ${g.title}`} aria-current={i === step ? 'step' : undefined} onClick={() => onStep(i)} /></li>)}</ol>
      {step < GUIDE.length - 1 ? <button className="btn primary" style={{ marginLeft: 'auto' }} onClick={() => onStep(step + 1)}>Next</button>
        : <button className="btn primary" style={{ marginLeft: 'auto' }} onClick={onClose}>Finish</button>}
    </div>
  </section>
}
