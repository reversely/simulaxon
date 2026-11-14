// The data API (backend/vcl/data/server.py). The interface is a function of what these return: nothing here names a
// dataset, a field or an experiment.

export type Unit = string | Record<string, string> | null | undefined
export type Field = { path: string; type: string; types: string[]; count: number; unit?: Unit; description?: string | null }
export type Stage = Record<string, any> & { stage: string }
export type TrailStep = { stage: string; text: string; count: number; note?: string }
export type Facet = { count: number; missing: number; kind: string; min?: number; max?: number; edges?: number[]; hist?: number[]; values?: [string, number][]; distinct?: number }
export type Sample = { id: string; group: string | null; slice: string | null; media: string | null; media_type: string | null; fields: Record<string, any>; computed_sources?: Record<string, string> }
export type Dataset = { name: string; source: Record<string, any>; loaded_at: string; samples: number }
export type ViewResult = { count: number; trail: TrailStep[]; schema: Field[]; facets: Record<string, Facet>; samples: Sample[] }
export type SampleFull = Sample & { sources: Record<string, string>; group_members: { id: string; slice: string | null; media: string | null; media_type: string | null; fields?: Record<string, any> }[] }
export type Track = { time_s: number[]; columns: string[]; values: number[][]; summary: string | null; band: boolean; caption?: string; unit?: Unit; source: string }

const j = async (r: Response) => { if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText); return r.json() }
const ds = (n: string) => `/api/datasets/${encodeURIComponent(n)}`

export const api = {
  datasets: (): Promise<Dataset[]> => fetch('/api/datasets').then(j),
  view: (name: string, stages: Stage[], offset = 0, limit = 120): Promise<ViewResult> =>
    fetch(`${ds(name)}/view`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ stages, offset, limit }) }).then(j),
  sample: (name: string, id: string): Promise<SampleFull> => fetch(`${ds(name)}/samples/${encodeURIComponent(id)}`).then(j),
  track: (name: string, id: string, path: string): Promise<Track> => fetch(`${ds(name)}/samples/${encodeURIComponent(id)}/track?path=${encodeURIComponent(path)}`).then(j),
}

/** A unit as text: one unit, or for a track whose columns differ, the unit of one column. */
export const unitOf = (u: Unit, column?: string): string => !u ? '' : typeof u === 'string' ? u : column ? u[column] ?? '' : ''
export const unitLabel = (u: Unit): string => !u ? '' : typeof u === 'string' ? u : 'units per column'

export const mediaUrl = (p: string) => '/media/' + p.split('/').map(encodeURIComponent).join('/')

export function fmt(v: any): string {
  if (v === null || v === undefined) return 'missing'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) :   // no digit grouping: whole numbers are often ids
    Math.abs(v) >= 1e6 ? v.toExponential(3) : Math.abs(v) >= 1000 ? v.toFixed(1) : v.toPrecision(4).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '')
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (Array.isArray(v)) return '[' + v.map(fmt).join(', ') + ']'
  if (typeof v === 'object' && v._kind === 'track') return `track, ${v.shape.join(' × ')}${v.rate_hz ? `, ${v.rate_hz} Hz` : ''}`
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}
