export type Row<T = any> = { kind: string; id: string; version: number; data: T; step_id: string }

export async function call<T = any>(tool: string, args: Record<string, unknown> = {}, actor = 'person'): Promise<T> {
  const r = await fetch(`/tools/${tool}`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Actor': actor }, body: JSON.stringify(args) })
  const j = await r.json()
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail))
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
  PHA1: 'Parahippocampal area 1', PHA2: 'Parahippocampal area 2', PHA3: 'Parahippocampal area 3', 'Place area': 'Parahippocampal place area',
  LO1: 'Lateral occipital area 1', LO2: 'Lateral occipital area 2', LO3: 'Lateral occipital area 3', AIP: 'Anterior intraparietal area',
  STV: 'Superior temporal visual area', TPOJ1: 'Temporal, parietal and occipital junction 1', A1: 'Primary auditory cortex', '4': 'Primary motor cortex',
}
export const regionLabel = (r: string): string => {
  if (AREA_NAMES[r]) return AREA_NAMES[r]
  const m = r.match(/^([LR])_(.+)$/)
  if (m && AREA_NAMES[m[2]]) return `${m[1] === 'L' ? 'Left' : 'Right'} ${AREA_NAMES[m[2]].replace(/^./, c => c.toLowerCase())}`
  return r
}
/** A region's plain name inside a sentence: the full name in lower case, or the word itself. */
export const regionInText = (r: string) => { const l = regionLabel(r); return l === r ? inText(r) : l.replace(/^./, c => c.toLowerCase()) }
/** A region's name inside a sentence: words in lower case, atlas codes such as FFC or V1 kept as they are. */
export const inText = (r: string) => /^[LR]?_?[A-Z0-9][A-Za-z0-9_-]*$/.test(r) && /[A-Z]{2}|\d/.test(r) ? r : r.toLowerCase()
export const fmt = (v: number | null | undefined, d = 3) => v == null || Number.isNaN(v) ? 'None' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(d)
export const PLAN_NAMES: Record<string, string> = { matched: 'Matched pairs', leave_one_out: 'Leave one out', adaptive: 'Adaptive search', selection: 'Selection', grid: 'Grid', random: 'Random', factorial: 'Two by two', experiment: 'Experiment' }
export const ROLE_NAMES: Record<string, string> = { manipulated: 'Manipulated', matched: 'Matched', fixed: 'Fixed', randomized: 'Randomized', measured: 'Measured', split: 'Split' }
