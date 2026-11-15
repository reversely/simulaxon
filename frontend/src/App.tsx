import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { call, count, fmt, regionLabel, describeStep, whoName, agentName, type Step, PLAN_NAMES, PLAN_INFO, PLAN_ICON, ROLE_NAMES, type AnalysisItem, type MapRow, type Project, type Region, type Row, type Sample, type Template } from './api'
import { Icon, type IconName } from './icons'
import { DotStrip, MiniInterval, SignedBars, TimeCourse } from './charts'
import { FindingsView, SearchView, SourcesView } from './views'
import { WorldPanel, type Param, type Preview, type PreviewEvent } from './world'
import { LiveWorkspace, type Job } from './live'
import { DemoBar, NarrationMsg, type DemoInfo, type DemoState, type Narration } from './demo'
import { SelectionView } from './selection'
import { ResultsView, type LiveTrial } from './results'
import { DatasetsPage } from './datasets'
import { ClipBrain, samplePreds } from './brain3d'
import { GuidePanel, GUIDE } from './guide'
import { Skeleton } from './wait'
import { ExperimentalPage } from './experimental'
import { SessionDock, Chat, type SessionInfo } from './agent'
type Example = { id: string; title: string; what: string; source: string; doi: string | null; goal: string; media: string[]; project_id: string | null; here: string
  brain: { image: string; view: string; title: string } | null   // the predicted response beside the stimulus
  kind: 'replication' | 'fine_tuning' | 'new'; dataset_id: string | null }
const KINDS: [Example['kind'], string, IconName, string][] = [
  ['replication', 'Classic experiments', 'flask', 'Published results rerun on TRIBE v2 and compared with what each paper reported.'],
  ['fine_tuning', 'Fine-tuning', 'brain', "Fit TRIBE v2 to people's measured fMRI, scored on stimuli the fit never saw."],
  ['new', 'New questions', 'search', 'Studies no paper has run yet.']]
import { ExperimentSetup, ExperimentRoom, ReportedCard, OriginChip, type Setup, type Reported } from './experiment'

type View = 'room' | 'results' | 'datasets' | 'experimental' | 'samples' | 'brain' | 'search' | 'data' | 'findings' | 'sources' | 'agent'
const WIDE: View[] = ['results', 'datasets', 'experimental', 'search', 'data', 'findings', 'sources', 'agent']
type Unit = { key: string; label: string; variants: Row<Sample>[]; labels: string[] }
const VIEW_ICON: Record<string, IconName> = { room: 'room', results: 'gauge', samples: 'samples', brain: 'brain', search: 'search', data: 'table', findings: 'findings', sources: 'book' }
const PROJECT_VIEWS: View[] = ['room', 'results', 'samples', 'brain', 'search', 'data', 'findings', 'sources']   // views of the open project; Datasets, Experimental and the chat are not
const VIEWS: [View, string][] = [['room', 'Room'], ['results', 'Results'], ['samples', 'Samples'], ['brain', 'Brain'], ['search', 'Search'], ['data', 'Data'], ['findings', 'Findings'], ['sources', 'Sources']]
const ANALYSIS_NAMES: Record<string, string> = { paired: 'Difference per region', items_needed: 'Pairs needed', time_course: 'Response by second', per_object: 'Effect of each object' }
const VIEW_NAMES: Record<string, string> = { left: 'Left', right: 'Right', ventral: 'Underside', posterior: 'Back' }

/** The region a project leads with, from its own results: the largest paired effect, the first selection region,
 * the region where objects move the cortex most, or the first region read. Never a fixed name. */
/** The regions the project names: its experiment's regions, its paper's reported result, the region in its question, its
 * selection's regions. Never inferred from results (#20): a project that names none has none. */
function namedRegions(a: AnalysisItem[], s: Row<Sample>[], P?: Project): string[] {
  const read = [...(a.find(x => x.analysis.data.kind === 'paired')?.result?.data.regions ?? []).map((r: Region) => r.region), ...Object.keys(s[0]?.data.readout ?? {})]
  const exp = (P as any)?.experiment ?? (P as any)?.setup
  const own = [...(exp?.regions ?? []).map((r: any) => typeof r === 'string' ? r : r?.name), ...((P as any)?.setup?.reported ?? []).map((r: Reported) => r.region),
    String((P?.bindings as any)?.region ?? '').trim().replace(/^the\s+/i, ''), ...(a.find(x => x.analysis.data.kind === 'selection')?.analysis.data.regions ?? [])].filter(Boolean)
  const out: string[] = []
  for (const o of own) { const lo = String(o).toLowerCase(); const hit = read.find(n => n.toLowerCase() === lo || regionLabel(n).toLowerCase() === lo); if (hit && !out.includes(hit)) out.push(hit) }   // matching only; names show as written
  return out
}

export default function App() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [projects, setProjects] = useState<Row<Project>[]>([]); const [projectsLoaded, setProjectsLoaded] = useState(false)
  const [fontsIn, setFontsIn] = useState(false)
  useEffect(() => {   // the faces the first screen uses, loaded before it is drawn so no text reflows when they arrive (#30); at most 1 s
    const faces = ['400 15px Inter', '600 15px Inter', '300 34px "Inter Tight"', '500 17px "Inter Tight"']
    Promise.race([Promise.all(faces.map(f => document.fonts.load(f))), new Promise(r => setTimeout(r, 1000))]).catch(() => {}).finally(() => setFontsIn(true))
  }, [])
  const [want, setPid] = useState<string | null>(() => new URLSearchParams(location.search).get('project'))   // the project asked for
  const [shownPid, setShown] = useState<string | null>(null)   // the project on screen: it changes only together with its own rows (#30)
  const pid = shownPid ?? (projects.some(p => p.id === want) ? want : null)   // on first load, the project asked for, its rows still empty
  const [samples, setSamples] = useState<Row<Sample>[]>([])
  const [analyses, setAnalyses] = useState<AnalysisItem[]>([])
  const [steps, setSteps] = useState<any[]>([])
  const [view, setView] = useState<View>(() => (new URLSearchParams(location.search).get('view') as View) || 'room')
  const [hist, setHist] = useState(false)   // the project's History menu (#21), closed until asked for
  const [guide, setGuide] = useState<number | null>(null)   // demo mode (#26): the guide's step, or null when it is closed
  const [dsShow, setDsShow] = useState<{ id: string; tab?: 'samples' | 'adapters' } | null>(null)
  const [picked, setPicked] = useState(false)   // a person or a demo chose the region shown; else only the project's own region counts as chosen (#19)
  const [region, setRegion] = useState('')   // set from the first project's own results; a person's or a demo's choice carries over
  const [unitIdx, setUnitIdx] = useState(0)
  const [variant, setVariant] = useState(0)
  const [sheet, setSheet] = useState<null | 'templates'>(null)
  const [switcher, setSwitcher] = useState(false)
  const [loadedFor, setLoadedFor] = useState<string | null>(null)   // the project the rows below belong to
  const [params, setParams] = useState<Row<Param>[]>([])
  const [previews, setPreviews] = useState<Row<Preview>[]>([])
  const [assets, setAssets] = useState<Record<string, any>>({})
  const [pev, setPev] = useState<Record<string, PreviewEvent>>({})
  const [jobs, setJobs] = useState<Job[]>([])
  const [demo, setDemo] = useState<DemoState>({ demo: null, step: 0, status: 'idle' })
  const [narr, setNarr] = useState<Narration[]>([])
  const [demos, setDemos] = useState<DemoInfo[]>([])
  const [writeErr, setWriteErr] = useState<Record<string, string>>({})
  const [runTrials, setRunTrials] = useState<Record<string, LiveTrial[]>>({})   // each run's trials as TRIBE finishes them, for the live Table 2 (#20)
  const [runProg, setRunProg] = useState<Record<string, { done: number; total: number; stage?: string; error?: string }>>({})
  const [offline, setOffline] = useState(false)   // the server is restarting or down: say so instead of failing quietly
  const follow = useRef<{ unit?: number } | null>(null)
  const [showCond, setShowCond] = useState<string | undefined>()   // what a demo step asks a view to display
  useEffect(() => { call<DemoInfo[]>('demo_list').then(setDemos); call<DemoState>('demo_get').then(d => d.demo && setDemo(d)) }, [])
  const [machine, setMachine] = useState<{ agent: string; world_node: string; brain_node: string; dashboard?: boolean } | null>(null)
  const [widen, setWiden] = useState(false)
  const [sessions, setSessions] = useState<SessionInfo[]>([]); const [openSession, setOpenSession] = useState<string | null>(null); const [sessionTick, setSessionTick] = useState(0)
  const loadSessions = () => fetch('/agent/sessions').then(r => r.json()).then(setSessions).catch(() => {})
  useEffect(() => { if (sheet === 'templates') call<Example[]>('example_list').then(setExamples).catch(() => {}) }, [sheet])
  useEffect(() => { loadSessions(); call<Record<string, { done: number; total: number; stage?: string }>>('run_list').then(p => setRunProg(r => ({ ...p, ...r }))).catch(() => {}) }, [])
  const demoRegion = useRef<{ pid: string; region: string } | null>(null)
  const projRef = useRef<Row<Project>[]>([])
  const [examples, setExamples] = useState<Example[]>([])
  const lastCentre = useRef<View>('room')
  useEffect(() => { const go = () => call('machine_get').then(setMachine).catch(() => {}); go(); const t = setInterval(go, 8000); return () => clearInterval(t) }, [])
  useEffect(() => { if (!WIDE.includes(view)) lastCentre.current = view }, [view])
  useEffect(() => { const k = (e: KeyboardEvent) => { if (e.key === 'Escape' && WIDE.includes(view) && !document.querySelector('.overlay, .histpop, .dlmenu')) setView(lastCentre.current) }; addEventListener('keydown', k); return () => removeEventListener('keydown', k) }, [view])

  /** Demo mode (#26): open what a guide step shows, in the real app. A step about an experiment or a world uses the open
   * project when it is one that has run, else the first that has. */
  const guideTo = (i: number) => {
    const g = GUIDE[i].go; setGuide(i)
    const ok = (p?: Row<Project>) => !!p && p.data.status === 'Done' && (g.project === 'experiment' ? p.data.plan === 'experiment' && (p.data.counts?.clips ?? 0) > 0 : !!(p.data as any).world)
    // The guide shows the pipeline: stimuli from Cosmos first, then Isaac Sim; fetched datasets only when nothing else has run.
    const made = (p: Row<Project>) => { const o = (((p.data as any).setup?.conditions ?? []) as any[]).map(c => `${c.origin?.kind ?? ''} ${c.origin?.label ?? ''}`).join(' ').toLowerCase()
      return (/cosmos/.test(o) ? 2 : 0) + (/isaac/.test(o) || (p.data as any).world ? 1 : 0) }
    const cur = projects.find(p => p.id === pid)
    if (g.project) { const named = g.prefer?.map(id => projects.find(p => p.id === id)).find(ok)
      const best = named ?? projects.filter(ok).sort((a, b) => made(b) - made(a))[0]
      if (best && (named ? cur?.id !== best.id : !ok(cur) || made(cur!) < made(best))) setPid(best.id) }
    setHist(!!g.history); setDsShow(g.view === 'datasets' ? g.dataset ?? { id: '' } : null); setView(g.view as View)
  }

  const refreshProjects = useCallback(async () => {
    const [t, p] = await Promise.all([call<Template[]>('template_list'), call<Row<Project>[]>('project_list')])
    setTemplates(t); setProjects(p); setProjectsLoaded(true)
    if ((!want || !p.some(x => x.id === want)) && p.length) setPid(p[0].id)
  }, [want])
  useEffect(() => { refreshProjects() }, [refreshProjects])

  const loadProject = useCallback(async (id: string, quiet = false) => {
    const [s, a, st, pr, pv, as] = await Promise.all([call<Row<Sample>[]>('sample_list', { project_id: id }), call<AnalysisItem[]>('analysis_list', { project_id: id }), call<any[]>('step_list', { project_id: id, limit: 60 }),
      call<Row<Param>[]>('parameter_list', { project_id: id }), call<Row<Preview>[]>('preview_list', { project_id: id }), call<Record<string, any>>('asset_list', { project_id: id }).catch(() => ({}))])
    if (live.current.want !== id) return   // the person has asked for another project since: these rows are not its
    if (live.current.pid !== id) { setUnitIdx(0); setVariant(0) }   // a project newly on screen opens on its first unit
    setSamples(s); setAnalyses(a); setSteps(st); setParams(pr); setPreviews(pv); setAssets(as); setLoadedFor(id); setShown(id)   // one render: the project and its own rows
    const P = projRef.current.find(x => x.id === id)?.data; const shown = demoRegion.current?.pid === id ? demoRegion.current.region : null
    if (!quiet) { demoRegion.current = null; setPicked(!!shown) }
    const names = [...((a.find(x => x.analysis.data.kind === 'paired')?.result?.data.regions ?? []) as Region[]).map(r => r.region), ...Object.keys(s[0]?.data.readout ?? {})]
    // a project opens on its own region (the one its question or paper names); a demo's choice wins; a quiet reload keeps the person's
    setRegion(r => shown ?? (quiet && r && names.includes(r) ? r : (namedRegions(a, s, P)[0] ?? '')))   // a person's pick, else the first region named at set-up, else none
    if (follow.current?.unit != null) { setUnitIdx(follow.current.unit); follow.current = null }
  }, [])
  useEffect(() => {
    if (!want) return
    loadProject(want)   // the project on screen stays until this one's rows arrive; then both change in one render, never paired with another's rows
    call('preview_search', { project_id: want }).catch(() => {})   // choice options render in the background, so picking one answers from cache
    const u = new URL(location.href); u.searchParams.set('project', want); history.replaceState(null, '', u)
  }, [want, loadProject])
  useEffect(() => { const u = new URL(location.href); u.searchParams.set('view', view); history.replaceState(null, '', u) }, [view])
  const live = useRef({ pid, want, refreshProjects, loadProject }); live.current = { pid, want, refreshProjects, loadProject }
  useEffect(() => {   // one event socket for the page's life, so no event is lost when the project changes; reconnects if dropped
    let ws: WebSocket; let closed = false
    const open = () => { ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/events`); ws.onmessage = onMsg
      ws.onopen = () => { setOffline(false); live.current.refreshProjects(); call('run_list').then(p => setRunProg(r => ({ ...r, ...p }))).catch(() => {}) }
      ws.onclose = () => { if (!closed) { setOffline(true); setTimeout(open, 1000) } } }
    const onMsg = (m: MessageEvent) => {
      const { pid, refreshProjects, loadProject } = live.current
      let msg: any = {}; try { msg = JSON.parse(m.data) } catch { /* plain event */ }
      if (msg.dataset) { window.dispatchEvent(new CustomEvent('lab-dataset', { detail: msg })); return }   // indexing progress for the Datasets page (#22)
      if (msg.session) { setSessionTick(k => k + 1); loadSessions(); if (msg.stage === 'project' || msg.stage === 'turn_done' || msg.stage === 'ended') refreshProjects(); return }   // the agent's long run: its own view updates
      if (msg.fetch) { loadSessions(); return }
      if (msg.job) { const j = { ...msg.job, t: Date.now() }; setJobs(js => [j, ...js.filter(x => x.key !== j.key)].slice(0, 40)); return }
      if (msg.run && msg.done) {
        setRunProg(r => ({ ...r, [msg.run]: { done: msg.done, total: msg.total } }))
        if (msg.trial) setRunTrials(x => ({ ...x, [msg.run]: [...(msg.done === 1 ? [] : (x[msg.run] ?? []).filter(t => t.index !== msg.trial.index)), msg.trial] }))
        return
      }
      if (msg.run && msg.stage === 'failed') { setRunProg(r => ({ ...r, [msg.run]: { done: 0, total: 0, stage: 'failed', error: msg.error } as any })); live.current.refreshProjects(); return }
      if (msg.run && msg.stage === 'comparing') { setRunProg(r => ({ ...r, [msg.run]: { ...(r[msg.run] ?? { done: 0, total: 0 }), stage: 'comparing' } })); return }
      if (msg.demo_writing) { call<DemoInfo[]>('demo_list').then(setDemos); setWriteErr(e => ({ ...e, [msg.demo_writing]: msg.stage === 'failed' ? msg.error : '' })); return }
      if ('demo' in msg && 'status' in msg) {
        call<DemoState>('demo_get').then(setDemo)
        if (msg.show?.project) { setPid(msg.show.project); if (msg.show.view) setView(msg.show.view); if (msg.show.region) { setRegion(msg.show.region); setPicked(true); demoRegion.current = { pid: msg.show.project, region: msg.show.region } } follow.current = { unit: msg.show.unit }; setShowCond(msg.show.condition); if (msg.narration && !msg.narration.reading) document.querySelector('.centre')?.scrollTo({ top: 0, behavior: 'smooth' }) }
        if (msg.narration) setNarr(ns => [...ns.filter(n => !(n.demo === msg.demo && n.step === msg.step)), { demo: msg.demo, step: msg.step, ...msg.narration }])
        if (msg.status === 'idle') setNarr([])
        return
      }
      if (msg.preview) {   // a finished preview changes only the previews: reload those, not the whole project
        setPev(e => {   // a render made ahead finishing must not clear the room's own preview, still under way
          const cur = e[msg.preview]
          if (msg.ahead && cur && cur.key !== msg.key && !['done', 'failed'].includes(cur.stage)) return e
          return { ...e, [msg.preview]: msg }
        })
        if ((msg.stage === 'done' || msg.stage === 'failed') && msg.preview === pid) call<Row<Preview>[]>('preview_list', { project_id: pid }).then(setPreviews)
        return
      }
      if (msg.tool === 'parameter_update' || msg.tool === 'preview_create') {   // a control moved: its row and the step that moved it
        if (pid) Promise.all([call<Row<Param>[]>('parameter_list', { project_id: pid }), call<any[]>('step_list', { project_id: pid, limit: 60 })]).then(([pr, st]) => { setParams(pr); setSteps(st) })
        return
      }
      refreshProjects(); if (pid) loadProject(pid, true)
    }
    open()
    return () => { closed = true; ws.close() }
  }, [])

  projRef.current = projects
  const project = projects.find(p => p.id === pid) ?? null
  const opening = !!want && want !== pid   // a switch still waiting for its rows: the switcher says so, seen after 300 ms (styles.css .spin)
  const P = project?.data
  const template = templates.find(t => t.id === P?.template_id)
  const byKind = (k: string) => analyses.find(a => a.analysis.data.kind === k)
  const paired = byKind('paired'); const perObject = byKind('per_object'); const needed = byKind('items_needed'); const course = byKind('time_course')

  const units: Unit[] = useMemo(() => {
    if (P?.plan === 'leave_one_out') {
      const ref = samples.find(s => s.data.unit === 'full'); if (!ref) return []
      return samples.filter(s => s !== ref).map(s => ({ key: s.data.unit, label: s.data.label, variants: [ref, s], labels: ['Full room', `Room without ${s.data.label}`] }))
    }
    const g = new Map<string, Row<Sample>[]>()
    samples.forEach(s => g.set(s.data.unit, [...(g.get(s.data.unit) ?? []), s]))
    return [...g.entries()].map(([k, v]) => ({ key: k, label: v.length === 2 && v[0].data.label !== v[1].data.label ? `${v[0].data.label} and ${v[1].data.label}` : v[0].data.label, variants: v, labels: v.map(x => x.data.condition) }))
  }, [samples, P?.plan])
  const named = namedRegions(analyses, samples, P)
  const regionTag = !region ? '' : picked ? 'Your pick' : named.includes(region) ? 'Named at set-up' : ''
  const pickRegion = (r: string) => { setRegion(r); setPicked(true) }
  const openTrial = (i: number, unitKey: string) => { if (P?.plan === 'experiment') setUnitIdx(i); else setUnitIdx(Math.max(0, units.findIndex(u => u.key === unitKey))); setView('room') }
  const diff = (u: Unit, r = region) => (u.variants[0].data.readout[r] ?? 0) - (u.variants[1]?.data.readout[r] ?? 0)
  const unit = units[Math.min(unitIdx, Math.max(0, units.length - 1))]
  const regionsPaired: Region[] = paired?.result?.data.regions ?? []
  const regionNames = regionsPaired.length ? regionsPaired.map(r => r.region) : Object.keys(samples[0]?.data.readout ?? {})
  const objects: any[] = perObject?.result?.data.objects ?? []
  const pickUnitByKey = (k: string) => { const i = units.findIndex(u => u.key === k); if (i >= 0) { setUnitIdx(i); setVariant(P?.plan === 'leave_one_out' ? 1 : 0) } }
  const flowNow = P?.status === 'Draft' ? 'build' : P?.status === 'Running' ? 'run' : view === 'brain' || view === 'room' ? 'compare' : view === 'samples' ? 'run' : 'compare'

  const projectChat = sessions.find(x => x.project_id === pid)?.id ?? null   // the newest chat about this project
  async function send(text: string, mode: 'discuss' | 'through' = 'discuss') {
    if (!pid || !text.trim()) return
    const opts = (body: unknown) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    if (projectChat) await fetch(`/agent/sessions/${projectChat}/message`, opts({ text, mode }))
    else await fetch('/agent/sessions', opts({ text, mode, project_id: pid }))
    loadSessions()
  }

  async function createFromTemplate(t: Template, title: string, bindings: Record<string, string>, from?: string, datasets?: string[]) {
    const row = await call<Row<Project>>('project_create', { template_id: t.id, title, bindings, from_project_id: from ?? null })
    if (datasets?.length) await call('project_update', { project_id: row.id, expect_version: (row as any).version ?? 1, datasets })   // the datasets it draws its stimuli from (#22)
    // the template's pattern is only the form's preview: the agent writes the real question to the guidelines (#24)
    fetch('/agent/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mode: 'discuss', project_id: row.id, max_turns: 4,
      text: "Write this project's question to the question guidelines and save it with project_update(question=...). Read the project first; change nothing else." }) }).then(loadSessions).catch(() => {})
    await refreshProjects(); setSheet(null); setPid(row.id); setView('room')
  }

  const reloadWorld = () => { if (pid) Promise.all([call<Row<Param>[]>('parameter_list', { project_id: pid }), call<Row<Preview>[]>('preview_list', { project_id: pid })]).then(([pr, pv]) => { setParams(pr); setPreviews(pv) }) }   // a control change touches only the world

  const runsNow = projects.filter(p => p.data.status === 'Running').map(p => ({ id: p.id, title: p.data.title, done: runProg[p.id]?.done ?? 0, total: runProg[p.id]?.total ?? 0, stage: runProg[p.id]?.stage }))

  const buildingChat = sessions.find(s => s.project_id === pid && (s.status === 'working' || s.status === 'waiting'))   // a chat at work on this project
  function chipsFor(): { label: string; run: () => void; icon?: IconName }[] {
    if (!P) return []
    if (P.status === 'Running' || buildingChat) return []   // the agent is already at work on it: no button that asks it again
    if (P.status !== 'Done') return [P.plan === 'experiment' ? { label: 'Ask the agent to check it', run: () => send(`Check this experiment against its paper before it runs: ${P.question}`) }
      : { label: 'Ask the agent to build it', run: () => send(`Build and run this project: ${P.question}`) }]
    const out: { label: string; run: () => void; icon?: IconName }[] = []
    if (view !== 'brain') out.push({ label: 'Show the brain', run: () => setView('brain') })
    if ((P as any).search && view !== 'search') out.push({ label: 'How were the items chosen?', run: () => setView('search') })
    const sibs = projects.filter(p => p.data.template_id === P.template_id && p.id !== pid && p.data.status === 'Done')
    if (sibs.length && view !== 'findings') out.push({ label: 'Compare with the other runs', run: () => setView('findings') })
    if (template?.controls[0]) out.push({ label: 'What should challenge this next?', run: () => send(`Which control from this template would challenge this project most, what would it take to run, and what would each outcome mean?`) })
    return out.slice(0, 4)
  }

  const sheetEl = sheet === 'templates' && <TemplateSheet examples={examples} onOpenProject={id => { setSheet(null); setPid(id); setView('room') }}
        onOpenDataset={id => { setSheet(null); setDsShow({ id, tab: 'adapters' }); setView('datasets') }}
        onGoal={goal => fetch('/agent/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: goal, mode: 'discuss' }) }).then(r => r.json()).then(s => { setSheet(null); loadSessions(); setOpenSession(s.id); setView('agent') })}
        onChat={() => { setSheet(null); setOpenSession(null); setView('agent') }} templates={templates} demos={demos} writeErr={writeErr} onWrite={id => call('demo_create', { seed_id: id }).then(() => call<DemoInfo[]>('demo_list').then(setDemos))} onClose={() => setSheet(null)} onCreate={createFromTemplate}
        onPlay={id => { setSheet(null); setNarr([]); call<DemoState>('demo_run', { demo_id: id }).then(setDemo) }} />

  // opening the lab: until the fonts, the projects and the first project's own rows are in, only the ground (and after 300 ms a
  // skeleton), so the header and columns appear once at their final size instead of growing in place (#30)
  if (!fontsIn || !projectsLoaded || (projects.length > 0 && !shownPid)) return <div className="frame"><div className="centre"><Skeleton lines={2} blocks={[320]} label="Opening the lab" /></div>{sheetEl}</div>

  // no project yet, as on a fresh install: the agent's chat and New project, never a spinner that waits for nothing
  if (!project || !P) return <div className="frame">
    <header className="top"><span className="brand">Simulaxon</span><button className="btn" onClick={() => setSheet('templates')}><Icon name="plus" size={16} />New project</button>
      {machine?.dashboard && <a className="btn" href="/dashboard" target="_blank" rel="noreferrer"><Icon name="gauge" size={16} />Dashboard</a>}
      {offline && <span className="chip flag" role="status">Reconnecting to the lab server</span>}</header>
    <div className="body chatonly"><main className="col centre"><div className="chatwide"><h1 className="q">{sessions.find(x => x.id === openSession)?.goal ?? 'New chat with the agent'}</h1>
      <Chat sid={openSession} live={sessionTick} onStarted={id => { setOpenSession(id); loadSessions() }} onOpenProject={id => { setPid(id); setView('room') }} /></div></main></div>
    {sheetEl}
  </div>

  return (
    <div className="frame">
      <header className="top">
        <span className="brand">Simulaxon</span>
        <div className="switch">
          <button onClick={() => setSwitcher(s => !s)} aria-haspopup="menu" aria-expanded={switcher} aria-busy={opening}><span>{(projects.find(x => x.id === want)?.data ?? P).title}</span>{opening ? <span className="spin" aria-label="Opening the project" /> : <span aria-hidden>▾</span>}</button>
          {switcher && <div className="menu" role="menu" onMouseLeave={() => setSwitcher(false)}>
            {projects.map(p => <button key={p.id} role="menuitem" className={p.id === want ? 'on' : ''} onClick={() => { setPid(p.id); setSwitcher(false) }}>
              <span>{p.data.title}<div className="sub">{templates.find(t => t.id === p.data.template_id)?.title}</div></span>
              <span className={`chip ${p.data.status === 'Running' ? 'flag' : ''}`}>{p.data.status}</span>
            </button>)}
          </div>}
        </div>
        <button className={`btn ${view === 'datasets' ? 'on' : ''}`} onClick={() => setView('datasets')}><Icon name="table" size={16} />Datasets</button>
        <button className={`btn ${view === 'experimental' ? 'on' : ''}`} onClick={() => setView('experimental')}><Icon name="flask" size={16} />Experimental</button>
        <button className="btn" aria-haspopup="dialog" aria-expanded={hist} onClick={() => setHist(h => !h)}><Icon name="clock" size={16} />History</button>
        <button className={`btn ${guide !== null ? 'on' : ''}`} aria-pressed={guide !== null} onClick={() => guide === null ? guideTo(0) : setGuide(null)}><Icon name="book" size={16} />Guide</button>
        {hist && <History pid={pid!} agent={agentName(machine?.agent)} tick={steps.length ? steps[steps.length - 1].step_id : ''} onClose={() => setHist(false)}
          onUndo={async id => { await call('step_undo', { step_id: id }); refreshProjects(); loadProject(pid!) }} />}
        <button className="btn" onClick={() => setSheet('templates')}><Icon name="plus" size={16} />New project</button>
        {machine?.dashboard && <a className="btn" href="/dashboard" target="_blank" rel="noreferrer"><Icon name="gauge" size={16} />Dashboard</a>}
        {machine && <div className="status" aria-label="Machine status">
          <span><span className={`dot ${machine.world_node !== 'Idle' ? 'busy' : ''}`} />World node {machine.world_node === 'Idle' ? 'idle' : machine.world_node}</span>
          <span><span className={`dot ${machine.brain_node !== 'Idle' ? 'busy' : ''}`} />Brain node {machine.brain_node === 'Idle' ? 'idle' : machine.brain_node}</span>
        </div>}
        {offline && <span className="chip flag" role="status">Reconnecting to the lab server</span>}
        <nav className="tabs">{VIEWS.map(([v, n]) => <button key={v} className={`tab ${view === v ? 'on' : ''}`} onClick={() => setView(v)}><Icon name={VIEW_ICON[v]} size={16} />{n}</button>)}</nav>
      </header>

      <div className={`body ${widen ? 'wideconvo' : ''} ${view === 'agent' ? 'chatonly' : ''} ${guide !== null ? 'guided' : ''}`}>
        {view !== 'agent' && <aside className="col left">
          <Conversation P={P} pid={pid!} template={template} flowNow={flowNow} steps={steps} narr={demo.demo ? narr.filter(n => n.demo === demo.demo) : []} widen={widen} onWiden={() => setWiden(w => !w)}
            chips={chipsFor()} onUndo={async id => { await call('step_undo', { step_id: id }); refreshProjects(); loadProject(pid!) }}
            sid={projectChat} live={sessionTick} onStarted={() => loadSessions()} onOpenProject={id => { setPid(id); setView('room') }} />
        </aside>}

        <main className={`col centre ${WIDE.includes(view) && guide === null ? 'span2' : ''}`}>
          {<div className="dock">
            <SessionDock sessions={sessions} onOpen={id => { setOpenSession(id); setView('agent') }} onStop={id => fetch(`/agent/sessions/${id}/stop`, { method: 'POST' }).then(loadSessions)} />
            <DemoBar state={demo.status === 'done' && (demo as any).show?.project !== pid ? { ...demo, status: 'idle' } : demo} onControl={a => call<DemoState>('demo_update', { action: a }).then(setDemo)} />
            <LiveWorkspace jobs={jobs} runs={runsNow} onOpen={id => { setPid(id); setView('room') }} />
          </div>}
          {view === 'datasets' ? <DatasetsPage projects={projects} onOpenProject={id => { setPid(id); setView('room') }} show={dsShow} /> : view === 'experimental' ? <ExperimentalPage /> : view === 'agent' ? <div className="chatwide"><h1 className="q">{sessions.find(x => x.id === openSession)?.goal ?? 'New chat with the agent'}</h1>
            <Chat sid={openSession} live={sessionTick} onStarted={id => { setOpenSession(id); loadSessions() }} onOpenProject={id => { setPid(id); setView('room') }} /></div> : <>
          <div>
            <h1 className="q">{P.template_id && !(P as any).question_written ? P.title : P.question}</h1>
            <div className="bar" style={{ marginTop: 8 }}>
              <span className="ink2">{template?.title}</span>
              <span className="chip" title={PLAN_INFO[P.plan]}>{PLAN_ICON[P.plan] && <Icon name={PLAN_ICON[P.plan] as IconName} size={14} />}{PLAN_NAMES[P.plan] ?? P.plan}</span>
              <span className={`chip ${P.status === 'Running' ? 'flag' : ''}`}>{P.status}</span>
              {P.counts && P.status === 'Done' && <span className="ink2 num">{P.counts.clips} clips</span>}
            </div>
          </div>
          {loadedFor !== pid ? <Skeleton lines={0} blocks={[320, 140]} label="Opening the project" /> : P.status !== 'Done' && view !== 'room' ? (['samples', 'brain', 'data'].includes(view) && <Pending view={view} P={P} onSetup={() => setView('room')} />)
            : P.status !== 'Done' && P.plan === 'experiment' && (P as any).setup ? <ExperimentSetup setup={(P as any).setup as Setup} paper={(P as any).paper}
              running={P.status === 'Running'} progress={runProg[pid!]} onRun={() => call('project_run', { project_id: pid }).then(() => refreshProjects())} onAsk={text => send(text)} />
            : P.status !== 'Done' ? <>{(P as any).world && <WorldPanel pid={pid!} world={(P as any).world} script={(P as any).script} params={params} previews={previews} assets={assets}
              event={pev[pid!]} steps={steps} region={region} named={named} onChanged={reloadWorld} />}
              <NotRun P={P} template={template} progress={runProg[pid!]} building={!!buildingChat} onOpenChat={() => { if (buildingChat) { setOpenSession(buildingChat.id); setView('agent') } }} onAsk={() => send(`Build and run this project: ${P.question}`)} onRun={(P as any).pairs || (P as any).units ? () => call('project_run', { project_id: pid }).then(() => refreshProjects()) : undefined} /></> : <>
            {view === 'room' && P.plan === 'selection' && byKind('selection')?.result && <SelectionView result={byKind('selection')!.result!.data} regions={byKind('selection')!.analysis.data.regions} samples={samples} condition={showCond} />}
            {view === 'room' && (P as any).world && <WorldPanel pid={pid!} world={(P as any).world} script={(P as any).script} params={params} previews={previews} assets={assets}
              event={pev[pid!]} steps={steps} region={region} named={named} onChanged={reloadWorld} />}

            {view === 'room' && P.plan === 'experiment' && <ExperimentRoom pid={pid!} samples={samples as any} idx={unitIdx} setIdx={setUnitIdx} region={region} named={named} tag={regionTag} onS={(P as any).setup?.trial?.on_s} />}
            {view === 'room' && unit && P.plan !== 'selection' && P.plan !== 'experiment' && <h2 className="section-title">The run, {P.counts?.clips} clips</h2>}
            {view === 'room' && unit && P.plan !== 'selection' && P.plan !== 'experiment' && <RoomView P={P} template={template} unit={unit} units={units} unitIdx={unitIdx} setUnitIdx={i => { setUnitIdx(i); setVariant(P.plan === 'leave_one_out' ? 1 : 0) }} variant={variant} setVariant={setVariant}
              region={region} tag={regionTag} diff={diff} objects={objects} onPickObject={pickUnitByKey} paired={regionsPaired.find(r => r.region === region)} />}
            {view === 'samples' && <SamplesView samples={samples} region={region} units={units} isaac={!!(P as any).world} onOpen={(u, v) => { setUnitIdx(u); setVariant(v); setView('room') }} />}
            {view === 'brain' && <BrainView P={P} unit={unit} variant={variant} objects={objects} analyses={analyses} course={course} region={region} />}
            {view === 'data' && <DataView units={units} regions={regionNames} onOpen={i => { setUnitIdx(i); setView('room') }} />}
          </>}
          {view === 'results' && <ResultsView pid={pid!} status={P.status} progress={runProg[pid!]} live={runTrials[pid!]} focus={picked ? region : ''} agentName={agentName(machine?.agent)}
            onPickRegion={pickRegion} onOpenTrial={openTrial} />}
          {view === 'search' && <SearchView search={(P as any).search} />}
          {view === 'findings' && <FindingsView P={P} pid={pid!} projects={projects} region={region} analysesFor={id => call('analysis_list', { project_id: id })} onOpen={id => { setPid(id) }} onAsk={send} />}
          {view === 'sources' && <SourcesView />}
          </>}
          {WIDE.includes(view) && <div className="muted">Escape returns to the {lastCentre.current}</div>}
        </main>

        {guide !== null && <aside className="guidefloat"><GuidePanel step={guide} onStep={guideTo} onClose={() => setGuide(null)}>{GUIDE[guide].id === 'ask' && P && !opening && <GuideProject P={P} />}</GuidePanel></aside>}
        {guide !== null ? <aside className="col guidegap" aria-hidden="true" /> : !WIDE.includes(view) && <aside className="col right">
          <Inspector P={P} pid={pid!} template={template} projects={projects} paired={paired} needed={needed} objects={objects} perObject={perObject} region={region} setRegion={pickRegion} picked={picked} named={named} onAsk={send}
            unit={unit} diff={diff} units={units} samples={samples} onFork={(c) => template && createFromTemplate(template, `${P.title}: ${c}`, { ...(P.bindings as Record<string, string>), control: c }, pid!)}
            onOpenProject={setPid} onPickObject={k => { pickUnitByKey(k); setView('room') }} template_analyses={template?.analyses ?? []} analyses={analyses} />
        </aside>}
      </div>

      {PROJECT_VIEWS.includes(view) && <footer className="prov" aria-label="Provenance">
        {P.provenance?.length ? (P.plan === 'experiment' && (P as any).setup ? [...P.provenance.slice(0, -1).map(provShort), regionCount((P as any).setup.regions as string[])] : P.provenance.map(provShort))
          .map((s, i) => <span key={i} style={{ display: 'contents' }}>{i > 0 && <span className="arrow">→</span>}<span title={typeof s === 'string' ? undefined : s.title}>{typeof s === 'string' ? s : s.text}</span></span>) : <span>Nothing has run in this project yet</span>}
      </footer>}

      {sheetEl}
    </div>
  )
}

/** A provenance step as the bar shows it: the thing itself, without versions, settings or read windows. The stored
 * step keeps its full text for Results and exports. */
function provShort(s: string): string {
  let m = s.match(/^(\d+) trials, one ([\d.]+) s clip each$/); if (m) return `${m[1]} trials × ${Number(m[2])} s`
  m = s.match(/^([\d.]+) s (?:on screen|of motion), then ([\d.]+) s grey$/); if (m) return `${m[1]} s on, ${m[2]} s grey`
  if (/^TRIBE v2\b/.test(s)) return 'TRIBE v2'
  if (/^Isaac Sim\b/.test(s)) return 'Isaac Sim'
  if (/ and /.test(s) && /isaac|cosmos|dataset/i.test(s))   // the stimuli's origins, one per condition: each by its source's name
    return [...new Set(s.split(' and ').map(o => o.split(', ')[0].replace(/^Rendered in /i, '')))].join(' and ')
  return s.split(', ')[0]
}
const regionCount = (rs: string[]) => ({ text: `${rs.length} ${rs.length === 1 ? 'region' : 'regions'}`, title: rs.map(regionLabel).join(', ') })

function Conversation({ P, pid, template, flowNow, narr, widen, onWiden, chips, sid, live, onStarted, onOpenProject }: {
  P: Project; pid: string; template?: Template; flowNow: string; steps?: any[]; narr: Narration[]; onUndo?: (id: string) => void; widen: boolean; onWiden: () => void
  chips: { label: string; run: () => void; icon?: IconName }[]; sid: string | null; live: number; onStarted: (id: string) => void; onOpenProject: (pid: string) => void
}) {
  const header = <>
    <div className="msg me"><div className="who">Question</div>{P.template_id && !(P as any).question_written ? <span className="ink2">The agent is writing this project's question.</span> : P.question}</div>
    {template && <div className="msg">
      <div className="who">Agent</div>
      <div style={{ marginBottom: 8 }}>I started this from the template <b>{template.title}</b>. Here is how it runs.</div>
      {template.walkthrough.map(w => <div key={w.flow} className={`flowline ${w.flow === flowNow ? 'now' : ''}`}><b>{w.flow_name}</b><span className="ink2">{w.text}</span></div>)}
    </div>}
    {P.note && <div className="msg"><div className="who">Agent</div>{P.note}</div>}
    {narr.map(n => <NarrationMsg key={n.step} n={n} />)}
  </>
  return <Chat sid={sid} projectId={pid} live={live} compact={!widen} header={header} onStarted={onStarted} onOpenProject={onOpenProject}
    chips={[...chips.slice(0, 3), { label: widen ? 'Narrow' : 'Widen', run: onWiden, icon: widen ? 'shrink' : 'expand' }]} />
}

/** A tab of a project that hasn't finished: what will appear here, and how far the run has got. */
function Pending({ view, P, onSetup }: { view: string; P: Project; onSetup: () => void }) {
  const what = view === 'brain' ? 'Brain maps appear' : view === 'samples' ? 'Every trial appears' : 'The table of results appears'
  return <div className="empty" style={{ textAlign: 'left' }}>
    <div className="mid" style={{ marginBottom: P.status === 'Running' ? 0 : 6 }}>{what} here when the run is done.</div>
    {P.status !== 'Running' && <><p className="ink2" style={{ marginTop: 0 }}>Not run yet.</p><button className="btn" onClick={onSetup}>Open the set-up</button></>}
  </div>
}

function NotRun({ P, template, onAsk, onRun, progress, building, onOpenChat }: { P: Project; template?: Template; onAsk: () => void; onRun?: () => void; progress?: { done: number; total: number; stage?: string }; building?: boolean; onOpenChat?: () => void }) {
  if (building && P.status !== 'Running') return <div className="empty" style={{ textAlign: 'left' }} role="status">   {/* the loader where the work is: the agent is building this project (#15) */}
    <div className="mid" style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 10 }}><span className="spin" />The agent is building this</div>
    <p className="ink2" style={{ marginTop: 0 }}>It sets up the world and the pairs, then runs them. Follow it in the chat.</p>
    <button className="btn" onClick={onOpenChat}><Icon name="chat" size={16} />Open the chat</button>
  </div>
  return <div className="empty" style={{ textAlign: 'left' }}>
    <div className="mid" style={{ marginBottom: 6 }}>{P.status === 'Running' ? 'Running now' : 'Not run yet'}</div>
    <p className="ink2" style={{ marginTop: 0 }}>{P.status === 'Running' ? (progress?.stage === 'comparing' ? 'Every clip is through TRIBE. Comparing the cells and drawing the maps.' : progress ? `${progress.done} of ${progress.total} clips through Isaac and TRIBE. Results appear when all are done.` : 'Results appear here when every clip has been through TRIBE.') : `${PLAN_NAMES[P.plan] ?? P.plan} plan from the template ${template?.title}.`}</p>
    {P.status === 'Running' && progress && <div className="fbar" style={{ maxWidth: 420 }}><span style={{ width: `${100 * progress.done / progress.total}%` }} /></div>}
    {P.status === 'Running' && progress?.stage === 'comparing' && <span className="ink2"><span className="spin" /> Comparing</span>}
    {P.status === 'Draft' && <div className="bar">{onRun && <button className="btn primary" onClick={onRun}>Run {(P as any).units ? (P as any).units.length * (template?.cells?.length ?? 1) : ((P as any).pairs?.length ?? 0) * 2} clips</button>}<button className={onRun ? 'btn' : 'btn primary'} onClick={onAsk}>Ask the agent to build it</button></div>}
  </div>
}

function RoomView({ P, template, unit, units, unitIdx, setUnitIdx, variant, setVariant, region, tag, diff, objects, onPickObject, paired }: {
  P: Project; template?: Template; unit: Unit; units: Unit[]; unitIdx: number; setUnitIdx: (i: number) => void; variant: number; setVariant: (v: number) => void
  region: string; tag: string; diff: (u: Unit, r?: string) => number; objects: any[]; onPickObject: (k: string) => void; paired?: Region
}) {
  const isLoo = P.plan === 'leave_one_out'; const [mode, setMode] = useState<'frame' | 'clip'>(template?.stimulus === 'motion' ? 'clip' : 'frame')
  const [boxes, setBoxes] = useState(true); const [hoverBox, setHoverBox] = useState<string | null>(null)
  const row = unit.variants[Math.min(variant, unit.variants.length - 1)]; const s = row.data
  const noun = template?.unit_noun ?? 'unit'; const unitWord = noun[0].toUpperCase() + noun.slice(1)
  const showBoxes = isLoo && boxes && variant === 0
  return <>
    {mode === 'clip' && s.clip ? <ClipBrain key={row.id} clip={s.clip} sampleId={row.id} predsUrl={samplePreds(row.id)}><span className="stageorigin"><OriginChip o={(s as any).origin ?? { kind: 'isaac', label: 'Rendered in Isaac Sim' }} /></span></ClipBrain> : <div className="stage runstage">
      {s.image ? <img src={s.image} alt={s.label} /> : <div className="empty">No frame</div>}
      <span className="stageorigin"><OriginChip o={(s as any).origin ?? { kind: 'isaac', label: 'Rendered in Isaac Sim' }} /></span>
      {showBoxes && <svg viewBox="0 0 832 480" preserveAspectRatio="none">
        {objects.map(o => { const [x0, y0, x1, y1] = o.bbox_px; return <rect key={o.object} className={`box ${o.object === unit.key ? 'sel' : ''}`} x={x0} y={y0} width={x1 - x0} height={y1 - y0} rx={4}
          onMouseEnter={() => setHoverBox(o.object)} onMouseLeave={() => setHoverBox(null)} onClick={() => onPickObject(o.object)} /> })}
      </svg>}
      {showBoxes && objects.filter(o => o.object === hoverBox || o.object === unit.key).map(o => <div key={o.object} className="boxlabel" style={{ left: `${(o.bbox_px[0] + o.bbox_px[2]) / 2 / 8.32}%`, top: `${o.bbox_px[1] / 4.8}%` }}>{o.label} <span className="num">{fmt(o.regions[region])}</span></div>)}
    </div>}
    <div className="bar">
      <div className="seg" role="group" aria-label="Variant">{unit.labels.map((l, i) => <button key={i} className={variant === i ? 'on' : ''} onClick={() => setVariant(i)}>{l}</button>)}</div>
      {unit.variants.some(v => v.data.clip) && <div className="seg" role="group" aria-label="Frame or clip"><button className={mode === 'frame' ? 'on' : ''} onClick={() => setMode('frame')}>Frame</button><button className={mode === 'clip' ? 'on' : ''} onClick={() => setMode('clip')}>Clip</button></div>}
      {isLoo && <div className="seg" role="group" aria-label="Object outlines"><button className={boxes ? 'on' : ''} onClick={() => setBoxes(true)}>Outlines</button><button className={!boxes ? 'on' : ''} onClick={() => setBoxes(false)}>No outlines</button></div>}
      <span style={{ marginLeft: 'auto' }} className="bar">
        <button className="btn" aria-label={`Previous ${unitWord.toLowerCase()}`} disabled={unitIdx <= 0} onClick={() => setUnitIdx(unitIdx - 1)}>‹</button>
        <span className="num ink2">{unitWord} {unitIdx + 1} of {units.length}</span>
        <button className="btn" aria-label={`Next ${unitWord.toLowerCase()}`} disabled={unitIdx >= units.length - 1} onClick={() => setUnitIdx(unitIdx + 1)}>›</button>
      </span>
    </div>
    <div className="headline">
      <span className="big">{fmt(diff(unit))}</span>
      <span className="ink2">{unit.labels[0]} minus {unit.labels[1] ?? 'the reference'}{region ? <> in {regionLabel(region)}{tag && <span className="chip tiny">{tag}</span>}</> : '. Pick a region under Regions to plot it.'}</span>
    </div>
    <div className="card">
      <h3>{isLoo ? 'Every object' : `Every ${unitWord}`}{region ? `: ${regionLabel(region)}` : ''}</h3>
      {isLoo
        ? <SignedBars items={objects.map(o => ({ key: o.object, label: o.label, value: o.regions[region], note: `${(o.share_of_frame * 100).toFixed(1)}% of the frame` })).sort((a, b) => b.value - a.value)} selected={unit.key} onPick={onPickObject} />
        : paired && <DotStrip values={units.map(u => diff(u))} labels={units.map(u => u.label)} mean={paired.value} interval={paired.interval_95} selected={unitIdx} onPick={setUnitIdx} />}
      {!isLoo && paired && <div className="ink2 num">Mean {fmt(paired.value)}, interval {fmt(paired.interval_95[0])} to {fmt(paired.interval_95[1])}, {paired.units_positive} of {paired.n} above zero</div>}
    </div>
  </>
}

function SamplesView({ samples, region, units, isaac, onOpen }: { samples: Row<Sample>[]; region: string; units: Unit[]; isaac: boolean; onOpen: (u: number, v: number) => void }) {
  const [sort, setSort] = useState<'order' | 'high' | 'low'>('order'); const [group, setGroup] = useState<string>('All')
  const conds = ['All', ...new Set(samples.map(s => s.data.condition))]
  let list = samples.filter(s => group === 'All' || s.data.condition === group)
  if (sort !== 'order') list = [...list].sort((a, b) => (sort === 'high' ? -1 : 1) * ((a.data.readout[region] ?? 0) - (b.data.readout[region] ?? 0)))
  const locate = (s: Row<Sample>) => { for (let i = 0; i < units.length; i++) { const v = units[i].variants.findIndex(x => x.id === s.id); if (v >= 0) return [i, v]; } return [0, 0] }
  return <>
    <div className="bar">
      <div className="seg" role="group" aria-label="Condition">{conds.map(c => <button key={c} className={group === c ? 'on' : ''} onClick={() => setGroup(c)}>{c}</button>)}</div>
      <div className="seg" role="group" aria-label="Sort"><button className={sort === 'order' ? 'on' : ''} onClick={() => setSort('order')}>In order</button><button className={sort === 'high' ? 'on' : ''} onClick={() => setSort('high')}>Highest first</button><button className={sort === 'low' ? 'on' : ''} onClick={() => setSort('low')}>Lowest first</button></div>
      <span className="ink2 num">{count(list.length, 'sample')}{region ? `, ${regionLabel(region)}` : ''}</span>
    </div>
    <div className="grid">
      {list.map(s => <button key={s.id} className="tile" onClick={() => { const [u, v] = locate(s); onOpen(u, v) }}>
        {s.data.image && <img src={s.data.image.startsWith('/files/') ? '/thumb/' + s.data.image.slice(7) : s.data.image} alt={s.data.label} loading="lazy" />}
        <div className="cap"><span>{s.data.label}</span><span className="num">{region ? fmt(s.data.readout[region]) : ''}</span><span className="ink2">{s.data.label.startsWith(s.data.condition) ? '' : s.data.condition}</span><OriginChip o={(s.data as any).origin ?? (isaac ? { kind: 'isaac', label: 'Rendered in Isaac Sim' } : null)} /></div>
      </button>)}
    </div>
  </>
}

function BrainView({ P, unit, variant, objects, analyses, course, region }: { P: Project; unit?: Unit; variant: number; objects: any[]; analyses: AnalysisItem[]; course?: AnalysisItem; region: string }) {
  const contrastId = analyses.find(a => a.result?.data.map_id)?.result?.data.map_id as string | undefined
  const isLoo = P.plan === 'leave_one_out'
  const objMapId = isLoo ? objects.find(o => o.object === unit?.key)?.map_id : undefined
  const [which, setWhich] = useState<'project' | 'unit'>('project')
  const [map, setMap] = useState<MapRow | null>(null); const [busy, setBusy] = useState(false)
  const sample = unit?.variants[Math.min(variant, (unit?.variants.length ?? 1) - 1)]
  const playable = which === 'unit' && !isLoo && !!sample?.data.clip
  useEffect(() => {
    let live = true; setBusy(!playable)
    const go = async () => {
      let row: Row<MapRow> | null = null
      if (playable) { setMap(null); return }
      if (which === 'project' && contrastId) row = await call('neural_map_get', { map_id: contrastId })
      else if (which === 'unit' && isLoo && objMapId) row = await call('neural_map_get', { map_id: objMapId })
      else if (which === 'unit' && sample) row = await call('neural_map_create', { sample_id: sample.id })
      if (live) { setMap(row?.data ?? null); setBusy(false) }
    }
    go().catch(() => live && setBusy(false)); return () => { live = false }
  }, [which, contrastId, objMapId, sample?.id, isLoo])
  const unitTitle = isLoo ? `Without ${unit?.label}` : sample?.data.label
  const tc = course?.result?.data.regions.find((r: any) => r.region === region)
  return <>
    <div className="bar">
      <div className="seg" role="group" aria-label="Which map">
        <button className={which === 'project' ? 'on' : ''} onClick={() => setWhich('project')}>{isLoo ? 'Full room' : 'Whole project'}</button>
        <button className={which === 'unit' ? 'on' : ''} onClick={() => setWhich('unit')}>{isLoo ? `Effect of ${unit?.label}` : `This sample: ${unitTitle}`}</button>
      </div>
      {busy && <span className="ink2"><span className="spin" /> Drawing the map</span>}
    </div>
    {playable && sample?.data.clip ? <ClipBrain key={sample.id} clip={sample.data.clip} sampleId={sample.id} predsUrl={samplePreds(sample.id)} /> : map && <>
      <div className="headline"><span className="mid">{map.title}</span><span className="legend">{map.kind === 'contrast' ? <>Lower <span className="ramp" /> Higher</> : <>Low <span className="ramp single" /> High</>}</span></div>
      <div className="brains">{Object.entries(map.views).map(([v, url]) => <figure key={v}><img src={`/files/${url}`} alt={`${map.title}, ${VIEW_NAMES[v] ?? v}`} /><figcaption>{VIEW_NAMES[v] ?? v}</figcaption></figure>)}</div>
      <div className="ink2">TRIBE v2 prediction for an average viewer, over the seconds the stimulus is on screen.</div>
    </>}
    {tc && <div className="card"><h3>Response by second, {region}</h3><TimeCourse a={tc.a} b={tc.b} labels={course!.analysis.data.labels} window={course!.analysis.data.window_s} /></div>}
  </>
}

function DataView({ units, regions, onOpen }: { units: Unit[]; regions: string[]; onOpen: (i: number) => void }) {
  const [sortBy, setSortBy] = useState<string | null>(null); const [dir, setDir] = useState(-1)
  const rows = units.map((u, i) => ({ i, u, vals: Object.fromEntries(regions.map(r => [r, (u.variants[0].data.readout[r] ?? 0) - (u.variants[1]?.data.readout[r] ?? 0)])) }))
  if (sortBy) rows.sort((a, b) => dir * (a.vals[sortBy] - b.vals[sortBy]))
  const head = (r: string) => <th key={r} onClick={() => { setDir(sortBy === r ? -dir : -1); setSortBy(r) }} aria-sort={sortBy === r ? (dir < 0 ? 'descending' : 'ascending') : 'none'}>{r}{sortBy === r ? (dir < 0 ? ' ↓' : ' ↑') : ''}</th>
  const csv = () => {
    const lines = [['unit', 'compared', ...regions].join(','), ...rows.map(r => [JSON.stringify(r.u.label), JSON.stringify(r.u.labels.join(' minus ')), ...regions.map(x => r.vals[x].toFixed(5))].join(','))]
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' })); a.download = 'differences.csv'; a.click()
  }
  return <>
    <div className="bar"><span className="ink2">Difference per unit and region, {units[0]?.labels[0]} minus {units[0]?.labels[1] ?? 'the reference'}. Click a column to sort, a row to open it.</span><button className="btn" style={{ marginLeft: 'auto' }} onClick={csv}>Download CSV</button></div>
    <div className="tablewrap"><table className="data"><thead><tr><th>Unit</th><th>Compared</th>{regions.map(head)}</tr></thead>
      <tbody>{rows.map(r => <tr key={r.u.key} onClick={() => onOpen(r.i)} style={{ cursor: 'pointer' }}><td>{r.u.label}</td><td className="ink2">{r.u.labels.join(' minus ')}</td>{regions.map(x => <td key={x}>{fmt(r.vals[x])}</td>)}</tr>)}</tbody></table></div>
  </>
}

function Inspector({ P, pid, template, projects, paired, needed, objects, perObject, region, setRegion, picked, named, onAsk, unit, diff, samples, onFork, onOpenProject, template_analyses, analyses, onPickObject }: {
  P: Project; pid: string; template?: Template; projects: Row<Project>[]; paired?: AnalysisItem; needed?: AnalysisItem; objects: any[]; perObject?: AnalysisItem
  region: string; setRegion: (r: string) => void; picked: boolean; named: string[]; onAsk: (text: string) => void; unit?: Unit; diff: (u: Unit, r?: string) => number; units: Unit[]; samples: Row<Sample>[]
  onFork: (control: string) => void; onOpenProject: (id: string) => void; template_analyses: string[]; analyses: AnalysisItem[]; onPickObject: (k: string) => void
}) {
  const regs: Region[] = paired?.result?.data.regions ?? []
  const cur = regs.find(r => r.region === region)
  const need = (needed?.result?.data.regions ?? []).find((r: any) => r.region === region)
  const scale = Math.max(...regs.flatMap(r => r.interval_95.map(Math.abs)), 1e-6)
  const siblings = projects.filter(p => p.data.template_id === P.template_id && p.id !== pid)
  const obj = objects.find(o => o.object === unit?.key)
  const bundle = () => {
    const out = { project: P, results: { paired: paired?.result?.data, items_needed: needed?.result?.data, per_object: perObject?.result?.data },
      stimuli: samples.map(s => ({ unit: s.data.unit, condition: s.data.condition, label: s.data.label, image: s.data.image, clip: s.data.clip })),
      note: 'TRIBE v2 predictions for an average viewer. Screening, not measured brains.' }
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' })); a.download = `${pid}_handoff.json`; a.click()
  }
  const reported = analyses.flatMap(a => (a.result?.data.reported ?? []) as Reported[])
  return <>
    {P.status === 'Done' && <ReportedCard items={reported} />}
    {P.status === 'Done' && !picked && <div className="card"><h3>Focus region</h3>
      <p className="ink2" style={{ margin: 0 }}>None picked. {named.length ? `Named at set-up: ${named.map(regionLabel).join(', ')}.` : 'The project named no region.'} Pick one under Regions to follow it through the views.</p></div>}
    {P.status === 'Done' && cur && picked && <div className="card">
      <h3 title={region}>{regionLabel(region)}<span className="chip tiny">Your pick</span></h3>
      <div className="big" style={{ color: 'var(--ink)' }}>{fmt(cur.value)}</div>
      <div className="ink2 num">Interval {fmt(cur.interval_95[0])} to {fmt(cur.interval_95[1])}</div>
      <div className="ink2 num">{cur.units_positive != null ? `${cur.units_positive} of ${cur.n} above zero` : Object.entries(cur.n as any).map(([c, n]) => `${n} ${c}`).join(', ') + ' trials'}</div>
      {(cur as any).shuffled_labels_95 && <div className="ink2 num">Labels shuffled: {fmt((cur as any).shuffled_labels_95[0])} to {fmt((cur as any).shuffled_labels_95[1])}</div>}
      {cur.area_rank_pct != null && <div className="ink2 num">Above {cur.area_rank_pct}% of the cortex's 360 areas</div>}
      {cur.vjepa_random_map != null && <div className="ink2 num">Same contrast from the video features, no brain mapping: {fmt(cur.vjepa_random_map)}</div>}
      {!reported.some(r => r.region === region) && <div className="muted" style={{ marginTop: 6 }}>No prediction recorded before the run</div>}
    </div>}
    {P.status === 'Done' && obj && <div className="card">
      <h3>{obj.label}</h3>
      <div className="big">{fmt(obj.regions[region])}</div>
      <div className="ink2">Full room minus the room without it, {region}</div>
      <div className="kv" style={{ marginTop: 10 }}><span className="k">Share of the frame</span><span className="num">{(obj.share_of_frame * 100).toFixed(1)}%</span>
        <span className="k">Change across the cortex</span><span className="num">{obj.whole_cortex.toFixed(3)}</span></div>
      {obj.description && <p className="ink2" style={{ marginBottom: 0 }}>{obj.description}</p>}
      {perObject?.result?.data.size_correlation != null && <p className="muted" style={{ marginBottom: 0 }}>Across objects, change across the cortex and share of the frame correlate at r {perObject.result.data.size_correlation.toFixed(2)}.</p>}
    </div>}
    {P.status === 'Done' && <div className="card">
      <h3>{!regs.length && unit ? `${unit.label} by region` : 'Regions'}</h3>
      <div className="rows">{(regs.length ? regs : Object.keys(samples[0]?.data.readout ?? {}).map(r => ({ region: r }) as any)).map((r: any) =>
        <button key={r.region} className={`rowbtn ${r.region === region ? 'on' : ''}`} onClick={() => setRegion(r.region)}>
          <span title={r.region}>{regionLabel(r.region)}{named.includes(r.region) && <span className="chip tiny">Named</span>}</span>
          <span className="num" style={{ textAlign: 'right' }}>{fmt(r.value ?? (unit ? diff(unit, r.region) : null))}</span>
          {r.interval_95 ? <MiniInterval value={r.value} interval={r.interval_95} scale={scale} /> : <span />}
        </button>)}
      </div>
      <div className="muted" style={{ marginTop: 8 }}>Brain areas from two standard atlases, in TRIBE's own units</div>
    </div>}
    {P.status === 'Done' && paired?.result?.data.baselines && <div className="card">
      <h3>Baselines</h3>
      <div className="rows">{paired.result.data.baselines.map((b: any) => <div key={b.name} className="rowbtn" style={{ cursor: 'default' }}>
        <span>{b.name}<span className="ink2" style={{ display: 'block', fontSize: 14 }}>{b.units}</span></span><span className="num" style={{ textAlign: 'right', gridColumn: '2 / 4' }}>{fmt(b.value)}<span className="ink2" style={{ display: 'block', fontSize: 14 }}>{fmt(b.interval_95[0])} to {fmt(b.interval_95[1])}</span></span></div>)}</div>
      <div className="muted" style={{ marginTop: 8 }}>The same contrast on the whole cortex and on the clips themselves</div>
    </div>}
    {need && <div className="card"><h3>Hand off</h3>
      <div className="kv"><span className="k">{(template?.unit_noun ?? 'unit')[0].toUpperCase() + (template?.unit_noun ?? 'unit').slice(1)}s needed, {region}</span><span className="mid">{need.pairs_needed ?? 'None'}</span></div>
      <div className="muted" style={{ marginTop: 4 }}>For 80% power at this effect and spread, in TRIBE</div>
      <ul className="list" style={{ marginTop: 8 }}>{template?.handoff.map(h => <li key={h}><span>{h}</span></li>)}</ul>
      <button className="btn" style={{ marginTop: 8 }} onClick={bundle}><Icon name="download" size={16} />Download bundle</button>
    </div>}
    {!need && P.status === 'Done' && <div className="card"><h3>Hand off</h3><ul className="list">{template?.handoff.map(h => <li key={h}><span>{h}</span></li>)}</ul><button className="btn" style={{ marginTop: 8 }} onClick={bundle}><Icon name="download" size={16} />Download bundle</button></div>}
    {(P as any).scene && <SceneCard scene={(P as any).scene} selected={unit?.key} onPick={onPickObject} />}
    {!template && P.status !== 'Done' && <div className="card"><h3>Results</h3><div className="ink2">After the run: TRIBE beside the paper's result, with baselines.</div></div>}
    {template && <>
    <div className="card"><h3>Analyses</h3>
      <ul className="list">{template_analyses.map(k => { const a = analyses.find(x => x.analysis.data.kind === k); return <li key={k}><span>{a?.analysis.data.title ?? ANALYSIS_NAMES[k] ?? k}</span><span className="ink2">{a?.result ? (a.stale ? 'Out of date' : 'Done') : 'Not run'}</span></li> })}</ul>
    </div>
    <div className="card"><h3>Challenge</h3>
      {((P as any).controls ?? []).length ? <ul className="list">{((P as any).controls as string[]).map(c => <li key={c}><span>{c}</span><button className="btn" onClick={() => onFork(c)}><Icon name="branch" size={16} />Fork</button></li>)}</ul>
        : <><p className="ink2" style={{ marginTop: 0 }}>No controls for this project yet.</p>
          <button className="btn" onClick={() => onAsk(`Which controls would challenge this project's result most? Write them for its own stimuli and regions, and save them on the project with project_update(controls=[...]).`)}><Icon name="chat" size={16} />Ask the agent for controls</button></>}
      {siblings.length > 0 && <><div className="ink2" style={{ margin: '10px 0 4px' }}>Same template</div><ul className="list">{siblings.map(s => <li key={s.id}><button className="tab" style={{ padding: 0, textAlign: 'left' }} onClick={() => onOpenProject(s.id)}>{s.data.title}</button><span className="chip">{s.data.status}</span></li>)}</ul></>}
    </div>
    <div className="card"><h3>Parameters</h3>
      <ul className="list">{P.parameters.map(p => <li key={p.name}><span><span>{p.name.replace(/_/g, ' ')}</span><div className="ink2" style={{ fontSize: 14 }}>{ROLE_NAMES[p.role] ?? p.role}</div></span><span className="num" style={{ textAlign: 'right' }}>{String(p.value)}{p.unit ? ` ${p.unit}` : ''}</span></li>)}</ul>
    </div></>}
  </>
}

function TemplateSheet({ examples, onOpenProject, onOpenDataset, onGoal, onChat, templates, demos, writeErr, onWrite, onClose, onCreate, onPlay }: { examples: Example[]; onOpenProject: (id: string) => void; onOpenDataset: (id: string) => void; onGoal: (goal: string) => void; onChat: () => void; templates: Template[]; demos: DemoInfo[]; writeErr: Record<string, string>; onWrite: (id: string) => void; onClose: () => void; onCreate: (t: Template, title: string, b: Record<string, string>, from?: string, datasets?: string[]) => void; onPlay: (id: string) => void }) {
  const [pick, setPick] = useState<Template | null>(null); const [vals, setVals] = useState<Record<string, string>>({}); const [title, setTitle] = useState('')
  const blanks = pick ? [...new Set([...pick.question.matchAll(/\{(\w+)\}/g)].map(m => m[1]))] : []
  const [atlas, setAtlas] = useState<any>(null)
  const [dsets, setDsets] = useState<{ id: string; title?: string; samples: number; files_here?: number }[] | null>(null); const [chosen, setChosen] = useState<string[]>([])
  useEffect(() => { if (pick && !dsets) call<any[]>('dataset_list').then(setDsets).catch(() => setDsets([])) }, [pick])
  useEffect(() => { if (blanks.includes('region') && !atlas) call<any>('region_search', { query: '' }).then(setAtlas).catch(() => {}) }, [pick])
  return <div className="overlay" onClick={onClose}>
    <div className="sheet" onClick={e => e.stopPropagation()} role="dialog" aria-label="New project">
      <div className="sheethead"><h2>New project</h2><button className="iconbtn" onClick={onClose} aria-label="Close" title="Close"><Icon name="close" size={20} /></button></div>
      {!pick ? <>
        <p className="ink2 sheetlede">Brain responses are predicted by TRIBE v2, Meta's model of the human brain. Start one of three ways.</p>
        <div className="startways">
          <button className="startway first" onClick={onChat}><Icon name="chat" size={26} /><b>Chat with the agent</b><span>Describe what to test, or paste a paper or a dataset. Set it up together, or let the agent run it.</span></button>
          <button className="startway" onClick={() => document.getElementById('start-examples')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}><Icon name="flask" size={26} /><b>Open a classic experiment</b><span>Set up already, ready to run or change.</span></button>
          <button className="startway" onClick={() => document.getElementById('start-templates')?.scrollIntoView({ behavior: 'smooth', block: 'start' })}><Icon name="template" size={26} /><b>Start from a template</b><span>A study design with blanks to fill in.</span></button>
        </div>
        {KINDS.filter(([k]) => examples.some(e => e.kind === k)).map(([k, head, icon, about], ki) => <section key={k}>
        <h3 className="sechead" id={ki === 0 ? 'start-examples' : undefined}><Icon name={icon} />{head}</h3>
        <p className="ink2 seclede">{about}</p>
        <div className="excards">{examples.filter(e => e.kind === k).map(e => <article key={e.id} className="excard">
          {(e.media.length > 0 || e.brain) && <div className={`pics ${e.brain ? 'split' : ''}`}>
            <div className="stim">{e.media.map(src => src.endsWith('.mp4') ? <video key={src} src={src} autoPlay muted loop playsInline preload="metadata" aria-label={`${e.title}, the stimulus`} /> : <img key={src} src={src} alt="" />)}</div>
            {e.brain && <figure className="exbrain"><img src={e.brain.image} alt={`Predicted brain response: ${e.brain.title}`} /><figcaption>{e.brain.title}</figcaption></figure>}
          </div>}
          <div className="exbody">
            <h3>{e.title}</h3>
            <div>{e.what}</div>
            <div className="ink2">{e.doi ? <a href={`https://doi.org/${e.doi}`} target="_blank" rel="noreferrer">{e.source}</a> : e.source}</div>
            <div className="here"><span>{e.here}</span>{e.project_id ? <button className="btn primary" onClick={() => onOpenProject(e.project_id!)}><Icon name="open" size={16} />Open</button>
              : e.kind === 'fine_tuning' && e.dataset_id ? <button className="btn primary" onClick={() => onOpenDataset(e.dataset_id!)}><Icon name="open" size={16} />Open fitting</button>
              : <button className="btn" onClick={() => onGoal(e.goal)}><Icon name="chat" size={16} />Start with the agent</button>}</div>
          </div>
        </article>)}</div></section>)}
        <h3 className="sechead" id="start-templates"><Icon name="template" />Templates</h3>
        <p className="ink2">Every template runs the same six steps: build a world, choose what varies, run, compare, challenge, hand off.</p>
        <div className="cards">{templates.map(t => <div key={t.id} className="tcard">
          <h3>{t.title}</h3>
          <div className="qq">{t.question.replace(/\{(\w+)\}/g, '…')}</div>
          <div className="ink2">{t.blurb}</div>
          <div className="planline">{PLAN_ICON[t.plan] && <Icon name={PLAN_ICON[t.plan] as IconName} />}<span><b>{PLAN_NAMES[t.plan]}.</b>{PLAN_INFO[t.plan] ? ` ${PLAN_INFO[t.plan]}` : ''}</span></div>
          <div className="ink2 num">{t.projects} {t.projects === 1 ? 'project' : 'projects'} made from it</div>
          <button className="btn primary" style={{ marginTop: 'auto' }} onClick={() => { setPick(t); setTitle(''); setVals({}) }}><Icon name="template" size={16} />Use template</button>
        </div>)}</div>
        <h3 className="sechead"><Icon name="play" />Paper demos</h3>
        <p className="ink2">The agent reads a paper, writes its steps with the templates above, and replays it in the paper's order. Every render and reading is real.</p>
        <div className="cards">{demos.map(d => <div key={d.id} className="tcard">
          <h3>{d.title ?? d.paper}</h3><a className="ink2" href={d.url} target="_blank" rel="noreferrer">{d.paper}</a>
          {d.written ? <ol className="ministeps">{d.steps.map((s, i) => <li key={i}>{s.title}</li>)}</ol> : <span className="ink2">{d.writing ? <><span className="spin" /> The agent is reading the paper and writing the steps</> : 'Not written yet'}</span>}
          {writeErr[d.id] && <span className="chip flag">{writeErr[d.id]}</span>}
          <div className="bar"><span className="chip">{templates.find(t => t.id === d.template)?.title}</span>{d.written && <span className="ink2">Written by the agent</span>}</div>
          <div className="bar" style={{ marginTop: 'auto' }}>
            {d.written && !d.missing_projects?.length && <button className="btn primary" onClick={() => onPlay(d.id)}><Icon name="play" size={16} />Play</button>}
            {d.missing_projects?.length ? <span className="chip flag">Its study was deleted</span> : null}
            <button className={d.written && !d.missing_projects?.length ? 'btn' : 'btn primary'} disabled={d.writing} onClick={() => onWrite(d.id)}>{d.written ? 'Write again' : 'Write with the agent'}</button>
          </div>
        </div>)}</div>
      </> : <div style={{ maxWidth: 620, display: 'flex', flexDirection: 'column', gap: 14, marginTop: 14 }}>
        <div className="mid">{pick.title}</div>
        <p className="ink2" style={{ marginTop: 0 }}>{pick.title}. The agent writes the project's question from these fields when it is made.</p>
        <label className="field"><span>Project name</span><input value={title} onChange={e => setTitle(e.target.value)} /></label>
        {blanks.map(b => <label key={b} className="field"><span>{b === 'a' ? 'First condition' : b === 'b' ? 'Second condition' : b.replace(/_/g, ' ').replace(/^./, c => c.toUpperCase())}</span>{b === 'region' ? <select value={vals[b] ?? ''} onChange={e => setVals(v => ({ ...v, [b]: e.target.value }))}>
          <option value="">{atlas ? 'Choose a region' : 'Loading the atlas'}</option>
          {atlas?.named_areas?.length > 0 && <optgroup label="Named areas">{atlas.named_areas.map((x: any) => { const n = x.about.split(':')[0]; return <option key={x.region} value={x.region}>{n} ({x.region})</option> })}</optgroup>}
          {atlas?.named_groups?.length > 0 && <optgroup label="Region groups">{atlas.named_groups.map((x: any) => <option key={x.region} value={x.region}>{x.region} ({x.known_for})</option>)}</optgroup>}
          {atlas?.hcp_codes?.length > 0 && <optgroup label="HCP areas">{atlas.hcp_codes.map((c: string) => <option key={c} value={c}>{regionLabel(c) !== c ? `${regionLabel(c)} (${c})` : c}</option>)}</optgroup>}
        </select> : <input value={vals[b] ?? ''} onChange={e => setVals(v => ({ ...v, [b]: e.target.value }))} />}</label>)}
        <div className="field"><span>Datasets</span>
          <div className="dspick">{dsets === null ? <span className="ink2">Reading the datasets</span> : dsets.length === 0 ? <span className="ink2">No datasets yet; import one under Datasets.</span>
            : dsets.map(d => <label key={d.id} className="dsval"><input type="checkbox" checked={chosen.includes(d.id)} onChange={e => setChosen(c => e.target.checked ? [...c, d.id] : c.filter(x => x !== d.id))} />
              <span>{d.title || d.id}</span><span className="ink2 num">{d.samples ? count(d.samples, 'sample') : count(d.files_here ?? 0, 'file')}</span></label>)}</div>
        </div>
        <div className="bar"><button className="btn" onClick={() => setPick(null)}><Icon name="back" size={16} />Back</button><button className="btn primary" disabled={!title.trim() || blanks.some(b => !vals[b]?.trim())} onClick={() => onCreate(pick, title.trim(), vals, undefined, chosen)}>Create project</button></div>
      </div>}
    </div>
  </div>
}

function SceneCard({ scene, selected, onPick }: { scene: { room: string; objects: { path: string; label: string; collection: string; placed_on: string; tested: boolean }[] }; selected?: string; onPick: (k: string) => void }) {
  const [q, setQ] = useState('')
  const groups = new Map<string, typeof scene.objects>()
  scene.objects.filter(o => !q || o.label.toLowerCase().includes(q.toLowerCase())).forEach(o => groups.set(o.collection, [...(groups.get(o.collection) ?? []), o]))
  return <div className="card"><h3>Objects in the {scene.room} <span className="ink2 num">{scene.objects.length}</span></h3>
    <input className="search" aria-label="Search objects" placeholder={`Search ${scene.objects.length} objects`} value={q} onChange={e => setQ(e.target.value)} />
    <div style={{ maxHeight: 300, overflow: 'auto', marginTop: 8 }}>{[...groups.entries()].map(([g, os]) => <div key={g}>
      <div className="ink2" style={{ margin: '8px 0 2px' }}>{g} <span className="num">{os.length}</span></div>
      <ul className="list">{os.map(o => <li key={o.path}>{o.tested ? <button className={`tab ${o.path === selected ? 'on' : ''}`} style={{ padding: '2px 6px', textAlign: 'left' }} onClick={() => onPick(o.path)}>{o.label}</button> : <span>{o.label}</span>}
        <span className="ink2">{o.tested ? 'Tested' : `On ${o.placed_on || 'floor'}`}</span></li>)}</ul></div>)}</div>
  </div>
}

/** The project's history (#21): its own steps, newest first, in plain words, who took each and when; repeated identical
 * steps collapse into one row. Undo and the tool call sit behind each row's menu. Closed until asked for. */
function History({ pid, agent, tick, onUndo, onClose }: { pid: string; agent: string; tick: string; onUndo: (id: string) => Promise<void>; onClose: () => void }) {
  const [steps, setSteps] = useState<Step[] | null>(null); const [menu, setMenu] = useState<string | null>(null); const [shown, setShown] = useState<string | null>(null)
  const [failed, setFailed] = useState<{ id: string; why: string } | null>(null)   // an undo the store refused, said under its row
  const ref = useRef<HTMLDivElement>(null)
  const load = () => call<Step[]>('step_list', { project_id: pid }).then(setSteps).catch(() => setSteps([]))
  useEffect(() => { load() }, [pid, tick])
  useEffect(() => {
    const off = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node) && !(e.target as HTMLElement).closest('[aria-haspopup="dialog"]')) onClose() }
    const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }
    document.addEventListener('mousedown', off); document.addEventListener('keydown', esc)
    return () => { document.removeEventListener('mousedown', off); document.removeEventListener('keydown', esc) }
  }, [onClose])
  const [all, setAll] = useState(false)
  const byId = Object.fromEntries((steps ?? []).map(s => [s.step_id, s]))
  // A change worth listing alters the project. Picking which item the scene shows is viewing, a preview is a by-product,
  // and a change that was undone cancels out with its undo; all three stay behind the switch at the bottom.
  const quiet = (s: Step) => { let a: any = {}; try { a = JSON.parse(s.args || '{}') ?? {} } catch { /* unreadable args: list it */ }
    return !!s.undone_by || s.tool === 'step_undo' || s.tool.startsWith('preview_') || (s.tool === 'parameter_update' && /(^|\.)item$/.test(String(a.parameter_id ?? ''))) }
  const hidden = (steps ?? []).filter(quiet).length
  const rows: { text: string; who: string; steps: Step[] }[] = []
  for (const s of [...(steps ?? [])].filter(s => all || !quiet(s)).reverse()) {
    const text = describeStep(s, byId); const who = whoName(s.actor, agent); const last = rows[rows.length - 1]
    if (last && last.text === text && last.who === who && !s.undone_by && !last.steps[0].undone_by) last.steps.push(s); else rows.push({ text, who, steps: [s] })
  }
  const day = (ts: string | number) => { const d = new Date(Number(ts) * 1000), t = new Date(); const n = Math.round((new Date(t.toDateString()).getTime() - new Date(d.toDateString()).getTime()) / 864e5)
    return n === 0 ? 'Today' : n === 1 ? 'Yesterday' : d.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' }) }
  const ago = (ts: string | number) => { const m = Math.round((Date.now() / 1000 - Number(ts)) / 60); return m < 1 ? 'just now' : m < 60 ? `${m} min ago` : m < 1440 ? `${Math.round(m / 60)} h ago` : `${Math.round(m / 1440)} d ago` }
  const call_ = (s: Step) => { try { return JSON.stringify(JSON.parse(s.args || '{}'), null, 1) } catch { return s.args } }
  return <div className="histpop" role="dialog" aria-label="Project history" ref={ref}>
    <div className="histhead"><b>History</b><button className="iconbtn" aria-label="Close" onClick={onClose}><Icon name="close" size={16} /></button></div>
    {steps === null ? <div className="ink2 wait" role="status"><span className="spin" /> Reading the history</div> : !rows.length ? <p className="ink2">No changes to this project yet.</p> :
      <ul className="histlist">{rows.map((r, i) => { const s = r.steps[0]; const canUndo = !s.undone_by && s.tool !== 'step_undo' && !s.undoes
        const head = i === 0 || day(rows[i - 1].steps[0].ts) !== day(s.ts)
        return <Fragment key={s.step_id}>{head && <li className="histday">{day(s.ts)}</li>}<li className={s.undone_by ? 'undone' : ''}>
          <div className="histrow">
            <span className="what">{r.text}{r.steps.length > 1 ? ` ${r.steps.length} times` : ''}{s.undone_by && <span className="chip tiny">Undone</span>}</span>
            <button className="iconbtn" aria-label={`More actions: ${r.text}`} aria-haspopup="menu" aria-expanded={menu === s.step_id} onClick={() => setMenu(m => m === s.step_id ? null : s.step_id)}>⋯</button>
            <span className="ink2 small">{r.who}, <span title={new Date(Number(s.ts) * 1000).toLocaleString()}>{ago(s.ts)}</span></span>
          </div>
          {menu === s.step_id && <div className="rowmenu" role="menu">
            {canUndo && <button role="menuitem" onClick={async () => { setMenu(null); setFailed(null); try { await onUndo(s.step_id) } catch (e: any) { setFailed({ id: s.step_id, why: String(e?.message ?? e) }) } load() }}><Icon name="undo" size={15} />Undo</button>}
            <button role="menuitem" onClick={() => { setShown(o => o === s.step_id ? null : s.step_id); setMenu(null) }}><Icon name="code" size={15} />{shown === s.step_id ? 'Hide call' : 'Show call'}</button>
          </div>}
          {failed?.id === s.step_id && <div className="dsnote" role="alert">Not undone: {failed.why}</div>}
          {shown === s.step_id && <pre className="codebox">{`${s.tool}(${call_(s)})`}</pre>}
        </li></Fragment> })}</ul>}
    {steps !== null && hidden > 0 && <label className="histall"><input type="checkbox" checked={all} onChange={e => setAll(e.target.checked)} />Show item picks, previews and undone changes ({hidden})</label>}
  </div>
}

/** The open project on the guide's first experiment step: its question, and the plan the agent made from it. */
function GuideProject({ P }: { P: Project }) {
  const conds = (((P as any).setup?.conditions ?? []) as any[])
  const prov = ((P as any).provenance ?? []) as string[]
  return <div className="gproj">
    <span className="gmono ink2">This project</span>
    <p className="gq">{P.question}</p>
    {conds.length > 0 && <><span className="gmono ink2">The plan the agent made from it</span>
      <ul>{conds.map(c => <li key={c.name}><b>{c.name}</b>{c.origin?.label ? `: ${c.origin.label.replace(/^Rendered in /, 'rendered in ').replace(/^Cosmos, from rendered in isaac sim$/i, 'the Isaac Sim render, restyled by Cosmos 3 Nano')}` : ''}</li>)}
        {prov[1] && <li>{prov[1]}</li>}{prov[3] && <li>Reads {prov[3]}</li>}</ul></>}
  </div>
}

