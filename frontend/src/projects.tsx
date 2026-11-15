// All projects (#32): a gallery of every project, last updated first as project_list returns them, with search, sort
// and filters by plan and status. "Last added" marks the newest project; status shows only when it is not Done.
import { useMemo, useState } from 'react'
import { count, PLAN_NAMES, type Project, type Row } from './api'
import { Icon } from './icons'

type Listed = Project & { created_at?: number | null; updated_at?: number | null; picture?: string | null; last_added?: boolean }
type Sort = 'updated' | 'newest' | 'title'

/** "3 h ago" from seconds since the epoch. */
export function ago(ts?: number | null): string {
  if (!ts) return ''
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return 'just now'
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  const d = Math.floor(s / 86400); return d === 1 ? 'yesterday' : `${d} days ago`
}

const day = (ts?: number | null) => ts ? new Date(ts * 1000).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : '–'
const thumb = (u?: string | null) => u?.startsWith('/files/') ? '/thumb/' + u.slice('/files/'.length) : u ?? undefined

/** The project's markers: "Last added" on the newest, and its status when it is not Done. */
export function Markers({ p }: { p: Listed }) {
  return <>{p.last_added && <span className="chip agent">Last added</span>}{p.status !== 'Done' && <span className={`chip ${p.status === 'Running' ? 'flag' : ''}`}>{p.status}</span>}</>
}

export function ProjectsPage({ projects, current, onOpen }: { projects: Row<Project>[]; current: string | null; onOpen: (id: string) => void }) {
  const [q, setQ] = useState(''); const [sort, setSort] = useState<Sort>('updated'); const [plan, setPlan] = useState(''); const [status, setStatus] = useState('')
  const [broken, setBroken] = useState<Record<string, boolean>>({})   // pictures that failed to load show the placeholder
  const rows = projects as Row<Listed>[]
  const plans = [...new Set(rows.map(p => p.data.plan))]; const statuses = [...new Set(rows.map(p => p.data.status))]
  const shown = useMemo(() => {
    const words = q.trim().toLowerCase()
    const out = rows.filter(p => (!plan || p.data.plan === plan) && (!status || p.data.status === status)
      && (!words || `${p.data.title} ${p.data.question}`.toLowerCase().includes(words)))
    if (sort === 'newest') return [...out].sort((a, b) => (b.data.created_at ?? 0) - (a.data.created_at ?? 0))
    if (sort === 'title') return [...out].sort((a, b) => a.data.title.localeCompare(b.data.title))
    return out   // project_list's own order: last updated first
  }, [rows, q, sort, plan, status])
  return <div className="dspage">
    <div className="bar dshead">
      <h2 className="section-title" style={{ margin: 0 }}>All projects</h2>
      <span className="ink2">{count(rows.length, 'project')}</span>
      <label className="dssearch"><Icon name="search" size={16} /><input placeholder="Search titles and questions" value={q} onChange={e => setQ(e.target.value)} aria-label="Search projects" /></label>
    </div>
    <div className="bar pjfilters">
      <label className="pjselect">Sort<select value={sort} onChange={e => setSort(e.target.value as Sort)}><option value="updated">Last updated</option><option value="newest">Newest</option><option value="title">Title</option></select></label>
      <label className="pjselect">Plan<select value={plan} onChange={e => setPlan(e.target.value)}><option value="">All</option>{plans.map(p => <option key={p} value={p}>{PLAN_NAMES[p] ?? p}</option>)}</select></label>
      <label className="pjselect">Status<select value={status} onChange={e => setStatus(e.target.value)}><option value="">All</option>{statuses.map(s => <option key={s} value={s}>{s}</option>)}</select></label>
    </div>
    {shown.length ? <div className="pjgrid">{shown.map(p => <button key={p.id} className={`pjcard ${p.id === current ? 'on' : ''}`} onClick={() => onOpen(p.id)}>
      <div className="pjpic">{p.data.picture && !broken[p.id] ? <img src={thumb(p.data.picture)} alt="" loading="lazy" onError={() => setBroken(x => ({ ...x, [p.id]: true }))} /> : <Icon name="room" size={28} />}</div>
      <div className="pjbody">
        <div className="pjmarks"><Markers p={p.data} /></div>
        <h3>{p.data.title}</h3>
        <p className="pjq ink2">{p.data.question}</p>
        <div className="pjfacts ink2"><span>{PLAN_NAMES[p.data.plan] ?? p.data.plan}</span>{p.data.counts?.clips ? <span className="num">{count(p.data.counts.clips, 'clip')}</span> : null}</div>
        <div className="pjfacts ink2 num"><span>Created {day(p.data.created_at)}</span><span>Updated {ago(p.data.updated_at)}</span></div>
      </div>
    </button>)}</div> : <div className="empty">No project matches</div>}
  </div>
}
