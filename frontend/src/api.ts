export type Row<T = any> = { kind: string; id: string; version: number; data: T; step_id: string }

export async function call<T = any>(tool: string, args: Record<string, unknown> = {}, actor = 'person'): Promise<T> {
  const r = await fetch(`/tools/${tool}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Actor': actor }, body: JSON.stringify(args) })
  const j = await r.json()
  const d = j.detail; const said = d && typeof d === 'object' && Object.values(d).every(v => typeof v === 'string') ? Object.values(d).join('; ') : null   // {conflict: '...'}: the message itself
  if (!r.ok) throw new Error(typeof d === 'string' ? d : said ?? JSON.stringify(d))
  return j.result as T
}

export type Region = { region: string; value: number; interval_95: [number, number]; n: number; units_positive: number; per_unit: number[]; pairs_needed: number | null; area_rank_pct?: number | null; vjepa_random_map?: number | null }
export type Project = {
  title: string; question: string; template_id: string; bindings: Record<string, unknown>; plan: string; status: string
  parameters: { name: string; type: string; role: string; value: unknown; unit?: string }[]
  provenance: string[]; note: string; counts?: Record<string, number>; hero?: string; forked_from?: string | null
}
export type Sample = { project_id: string; index: number; unit: string; condition: string; label: string; image: string | null; clip: string | null; readout: Record<string, number> }
export type Template = {
  id: string; title: string; question: string; blurb: string; plan: string; projects: number; unit_noun: string; stimulus: 'still' | 'motion' | 'video'
  parameters: Project['parameters']; analyses: string[]; controls: string[]; handoff: string[]
  walkthrough: { flow: string; flow_name: string; text: string }[]
  cells?: { id: string; label: string; values: Record<string, string> }[]   // factorial templates: every unit in every cell
}
export type AnalysisItem = { analysis: Row; result: Row | null; stale: boolean }
export type MapRow = { title: string; kind: string; views: Record<string, string>; vmax: number }

/** A brain area's standard full name, so no code reaches a reader without one: HCP-MMP1 codes as TRIBE reports them, an
 * L_ or R_ prefix as left or right; names that are already words pass through. */
const AREA_NAMES: Record<string, string> = {
  V1: 'Primary visual cortex', V2: 'Visual area 2', V3: 'Visual area 3', V4: 'Visual area 4', V3A: 'Visual area 3A', V6: 'Visual area 6',
  MT: 'Middle temporal motion area', MST: 'Medial superior temporal area', FFC: 'Fusiform face area', VVC: 'Ventral visual complex',
  PPA: 'Parahippocampal place area', FFA: 'Fusiform face area', V5: 'Motion area V5', PHA1: 'Parahippocampal area 1', PHA2: 'Parahippocampal area 2', PHA3: 'Parahippocampal area 3', 'Place area': 'Parahippocampal place area',
  LO1: 'Lateral occipital area 1', LO2: 'Lateral occipital area 2', LO3: 'Lateral occipital area 3', AIP: 'Anterior intraparietal area',
  STV: 'Superior temporal visual area', TPOJ1: 'Temporal, parietal and occipital junction 1', A1: 'Primary auditory cortex', '4': 'Primary motor cortex',
}
export const regionLabel = (r: string): string => {
  if (AREA_NAMES[r]) return AREA_NAMES[r]
  const m = r.match(/^([LR])_(.+)$/)
  if (m && AREA_NAMES[m[2]]) return `${AREA_NAMES[m[2]]} (${m[1] === 'L' ? 'left' : 'right'} hemisphere)`
  return r
}
/** A region's plain name inside a sentence: the full name in lower case, or the word itself. */
/** A count with its noun: 1 file, 2 files. */
export const count = (x: number, word: string) => `${x.toLocaleString()} ${word}${x === 1 ? '' : 's'}`
export const fmt = (v: number | null | undefined, d = 3) => v == null || Number.isNaN(v) ? 'None' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d)
/** How each plan works, in one plain sentence, shown wherever the plan is first met (a template card), and on hover elsewhere. */
export const PLAN_INFO: Record<string, string> = {
  matched: 'Each item beside a look-alike; the result is the difference within each pair.',
  leave_one_out: 'Each object hidden in turn; the result is what changes without it.',
  selection: 'Every stimulus scored first; the ones that fit the question are kept.',
  factorial: 'Every combination of two choices, so each one\'s effect reads on its own.',
  experiment: 'Conditions from a paper or a dataset, compared, with the paper\'s result beside them.',
  adaptive: 'Each run chooses the next values from what the last one showed.',
  grid: 'Every value of the controls, on an even grid.',
  random: 'Values drawn at random across the controls.',
}
export const PLAN_ICON: Record<string, string> = { matched: 'pairs', leave_one_out: 'leaveout', selection: 'funnel', factorial: 'samples', experiment: 'flask', adaptive: 'branch', grid: 'table', random: 'shuffle' }
export const PLAN_NAMES: Record<string, string> = { matched: 'Matched pairs', leave_one_out: 'Leave one out', adaptive: 'Adaptive search', selection: 'Selection', grid: 'Grid', random: 'Random', factorial: 'Two by two', experiment: 'Experiment' }
export const ROLE_NAMES: Record<string, string> = { manipulated: 'Manipulated', matched: 'Matched', fixed: 'Fixed', randomized: 'Randomized', measured: 'Measured', split: 'Split' }

/** Sends a file a person adds. A large file that compresses well goes gzipped (Content-Encoding: gzip), which the
 * server unpacks as it streams to disk, so more fits under its 2 GB upload limit. Files already compressed (video,
 * images, archives) go as they are. */
const PACKED = /\.(zip|gz|tgz|bz2|xz|7z|zst|mp4|mov|mkv|webm|avi|jpe?g|png|webp|gif|npz|parquet)$/i
/** Sends one file with its progress, for the import page (#22): files go as they are, one request each. */
export function uploadWithProgress(url: string, f: Blob, onProgress: (sent: number, total: number) => void): Promise<any> {
  return new Promise((ok, fail) => {
    const x = new XMLHttpRequest(); x.open('POST', url)
    x.upload.onprogress = e => onProgress(e.loaded, e.total || f.size)
    x.onload = () => x.status < 300 ? ok(JSON.parse(x.responseText || '{}')) : fail(new Error(x.responseText || `status ${x.status}`))
    x.onerror = () => fail(new Error('the upload did not reach the lab server'))
    x.send(f)
  })
}
export async function upload(url: string, f: File): Promise<Response> {
  if (f.size > 32e6 && !PACKED.test(f.name) && typeof CompressionStream !== 'undefined') {
    const gz = await new Response(f.stream().pipeThrough(new CompressionStream('gzip'))).blob()
    if (gz.size < f.size * 0.9) return fetch(url, { method: 'POST', headers: { 'Content-Encoding': 'gzip' }, body: gz })
  }
  return fetch(url, { method: 'POST', body: f })
}

/** Every tool a step or a chat can record, in plain words (#21). One table for the History menu and the chat's steps; a
 * tool missing here fails services/app-server/tests/test_tool_names.py rather than showing its code name. */
export const TOOL_NAMES: Record<string, string> = {
  experimental_list: 'Read the experimental section', adapter_create: 'Fitted an adapter',
  adapter_get: 'Read an adapter', adapter_list: 'Listed the adapters',
  analysis_create: 'Added an analysis', dataset_create: 'Made a dataset', dataset_delete: 'Removed a dataset', embedding_create: 'Computed similarity vectors', item_create: 'Indexed a dataset', item_query: 'Looked through a dataset',
  item_update: 'Tagged samples', view_create: 'Saved a view', view_list: 'Listed the saved views', analysis_list: 'Read the analyses', analysis_run: 'Ran an analysis', asset_create: 'Added an asset', asset_list: 'Listed the assets',
  assumption_list: 'Read the assumptions', course_get: 'Read a time course', dataset_fetch: 'Fetched data', dataset_get: 'Looked at a dataset', dataset_list: 'Checked the data here',
  demo_create: 'Wrote a demo', demo_get: 'Read a demo', demo_list: 'Listed the demos', demo_run: 'Played a demo', demo_update: 'Changed a demo', display_get: 'Read the display',
  display_update: 'Changed the display', example_list: 'Listed the examples', experiment_create: 'Set up the experiment', experiment_get: 'Read the results', file_list: 'Listed files',
  machine_get: 'Checked the machine', neural_map_create: 'Made a brain map', neural_map_get: 'Read a brain map', object_create: 'Added an object', object_delete: 'Removed an object',
  object_get: 'Looked at an object', object_list: 'Listed the objects', object_update: 'Changed an object', paper_fetch: 'Fetched the paper', paper_read: 'Read the paper',
  paper_search: 'Searched papers', parameter_create: 'Added a parameter', parameter_list: 'Read the parameters', parameter_update: 'Changed a parameter',
  preview_create: 'Rendered a preview', preview_list: 'Listed the previews', preview_run: 'Rendered previews', preview_search: 'Searched the previews',
  project_create: 'Created the project', project_delete: 'Deleted a project', project_get: 'Read the project', project_list: 'Listed the projects', project_run: 'Ran the project',
  project_update: 'Changed the project', record_create: 'Recorded a finding', record_search: 'Searched the findings', region_search: 'Looked up regions', roi_list: 'Listed the regions',
  run_get: "Read a run's record", run_list: 'Checked the runs', run_stop: 'Stopped a run', sample_create: 'Added a sample', sample_list: 'Read the samples', scene_create: 'Built a scene',
  scene_get: 'Read the scene', source_list: 'Listed the sources', source_search: 'Searched the sources', source_update: 'Changed a source', step_list: 'Read the history',
  step_undo: 'Undid a step', template_list: 'Listed the templates', ToolSearch: 'Loaded its tools',
}
export const toolName = (t: string) => TOOL_NAMES[t] ?? 'Used a tool'

export type Step = { step_id: string; actor: string; tool: string; args: string; ts: string | number; undoes?: string | null; undone_by?: string | null }
const stepArgs = (s: Step): Record<string, any> => { try { return JSON.parse(s.args || '{}') ?? {} } catch { return {} } }
/** What a step did, in plain words: a project change says which part changed. */
export function describeStep(s: Step, byId: Record<string, Step> = {}): string {
  const a = stepArgs(s)
  if (s.tool === 'step_undo') { const u = byId[a.step_id ?? s.undoes ?? '']; return `Undid: ${u ? describeStep(u, byId).replace(/^./, c => c.toLowerCase()) : 'a step'}` }
  if (s.tool === 'project_update') {
    if (a.bindings) return 'Changed the question'
    if (a.title) return 'Renamed the project'
    if (a.question) return 'Rewrote the question'
    if (a.controls) return 'Saved the controls'
    if (a.status === 'Running') return 'Started a run'
    if (a.status === 'Done') return a.counts?.clips ? `Finished a run of ${a.counts.clips} trials` : 'Finished a run'
    if (a.status === 'Draft') return 'Returned the project to draft'
    if (a.pairs || a.labels) return 'Changed the pairs'
  }
  if (s.tool === 'parameter_update' && a.parameter_id && 'value' in a) {   // name the control and its new value, so two changes never read as one
    const v = typeof a.value === 'string' ? a.value.replace(/_/g, ' ') : typeof a.value === 'number' ? String(a.value) : JSON.stringify(a.value)
    const id = String(a.parameter_id).split('.').pop()!, deg = /_deg$/.test(id)   // a unit suffix becomes the value's unit
    return `Set ${id.replace(/_deg$/, '').replace(/_/g, ' ')} to ${v}${deg ? '°' : ''}`
  }
  return toolName(s.tool)
}
/** Who took a step, as the header names them: never the stored value "person" or "agent". */
export const whoName = (actor: string, agent: string) => actor === 'person' ? 'You' : actor === 'agent' ? (agent === 'the agent' ? 'The agent' : agent) : 'The app'
/** A stored contrast or condition name as words (#39): "faces_vs_objects" reads "Faces against objects". Names with a
 * space are the project's own wording and show as written. */
export const words = (name?: string | null) => { const s = String(name ?? ''); if (!s.includes('_') || /\s/.test(s)) return s
  const w = s.replace(/_(vs|versus|minus|against)_/gi, ' against ').replace(/_+/g, ' ').trim(); return w.charAt(0).toUpperCase() + w.slice(1) }
/** The agent as the page names it (#40), from machine_get's agent name; a missing or runtime name ("Claude Code") reads "the agent". */
export const agentName = (name?: string | null) => !name || /claude/i.test(name) ? 'the agent' : name
