// Datasets (#22): the list of datasets on this machine, importing into one, its samples and fields, and the projects
// that use it. Every sample is an item in the lab's store (item_create), its fields read off the file, its folder and
// any table beside it; filters are view stages the agent reads the same way (item_query).
import { useEffect, useMemo, useRef, useState } from 'react'
import { count, call, uploadWithProgress, type Project, type Row } from './api'
import { Icon } from './icons'
import { RecordingView } from './recording'
import { AdaptersView } from './adapters'
import { Skeleton } from './wait'

type DS = { id: string; title?: string; ref?: string; licence?: string | null; fetched_at?: string; files_here?: number; gigabytes?: number
  samples: number; fields: number; media: Record<string, number>; indexed: boolean; embedded?: boolean; projects: string[]; status?: string; measured?: boolean; adapters?: number }
type Item = { id: string; path: string; media_type: string; media: string; thumb?: string | null; fields: Record<string, any>; tags: string[]; sources: Record<string, string> }
type Facet = { count: number; missing: number; kind: string; min?: number; max?: number; values?: [string, number][]; distinct?: number; hist?: number[] }
type Query = { total: number; items: Item[]; trail: { stage: string; text: string; count: number }[]; schema: { path: string; type: string; count: number }[]; facets: Record<string, Facet>; indexed: boolean }
type Stage = Record<string, any>

const n = (x: number) => x.toLocaleString()
const MEDIA_NAMES: Record<string, string> = { image: 'images', video: 'videos', audio: 'audio' }
const HIDDEN = new Set(['file', 'sha', 'folder'])
const KEPT: { list: DS[] | null } = { list: null }   // the last list, kept for the page's life: a revisit shows it at once (#30)

export function DatasetsPage({ projects, onOpenProject, show }: { projects: Row<Project>[]; onOpenProject: (id: string) => void; show?: { id: string; tab?: 'samples' | 'adapters' } | null }) {
  const [list, setShown] = useState<DS[] | null>(() => KEPT.list); const [open, setOpen] = useState<string | null>(null)
  const setList = (l: DS[]) => { KEPT.list = l; setShown(l) }
  useEffect(() => { if (show) setOpen(show.id || null) }, [show?.id, show?.tab])   // the guide (#26) opens a dataset, or the list
  const [q, setQ] = useState(''); const [creating, setCreating] = useState(false); const [err, setErr] = useState('')
  const load = () => call<DS[]>('dataset_list').then(setList).catch(e => setErr(String(e?.message ?? e)))
  useEffect(() => { load() }, [])
  useEffect(() => { const f = (e: Event) => { if ((e as CustomEvent).detail?.done) load() }; window.addEventListener('lab-dataset', f); return () => window.removeEventListener('lab-dataset', f) }, [])
  if (open) return <DatasetView id={open} ds={list?.find(d => d.id === open)} projects={projects} onBack={() => { setOpen(null); load() }} onOpenProject={onOpenProject} onChanged={load} initialTab={show?.id === open ? show.tab : undefined} />
  const shown = (list ?? []).filter(d => !q || `${d.title} ${d.id} ${d.ref}`.toLowerCase().includes(q.toLowerCase()))
  return <div className="dspage">
    <div className="bar dshead">
      <h2 className="section-title" style={{ margin: 0 }}>Datasets</h2>
      <span className="ink2">{list ? `${list.length} on this machine` : ''}</span>
      <label className="dssearch"><Icon name="search" size={16} /><input placeholder="Search datasets" value={q} onChange={e => setQ(e.target.value)} aria-label="Search datasets" /></label>
      <button className="btn primary" onClick={() => setCreating(true)}><Icon name="plus" size={16} />New dataset</button>
    </div>
    {err && <div className="empty">{err}</div>}
    {!list ? <Skeleton lines={0} blocks={[40, 56, 56, 56]} label="Reading the datasets" /> :
      <div className="tablewrap"><table className="data dstable">
        <thead><tr><th>Dataset</th><th>Samples</th><th>Media</th><th>Source</th><th>Added</th><th className="num">Projects</th></tr></thead>
        <tbody>{shown.map(d => <tr key={d.id} onClick={() => setOpen(d.id)} style={{ cursor: 'pointer' }}>
          <td><b>{d.title || d.id}</b><div className="ink2 small">{d.id}</div></td>
          <td>{d.status && d.status !== 'done' ? `Fetching, ${d.status}` : d.indexed ? `${count(d.samples, 'sample')}, ${count(d.fields, 'field')}` : `${count(d.files_here ?? 0, 'file')}, not indexed yet`}</td>
          <td className="ink2">{Object.entries(d.media ?? {}).map(([k, v]) => `${n(v)} ${MEDIA_NAMES[k] ?? k}`).join(', ') || '–'}</td>
          <td className="ink2">{d.ref === 'upload' ? 'Imported here' : d.ref}{d.licence ? `, ${d.licence}` : ''}</td>
          <td className="ink2 num">{d.fetched_at ?? '–'}</td>
          <td className="num">{d.projects?.length ?? 0}</td></tr>)}</tbody>
      </table></div>}
    {creating && <NewDataset onClose={() => setCreating(false)} onCreated={id => { setCreating(false); load(); setOpen(id) }} />}
  </div>
}

function NewDataset({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [title, setTitle] = useState(''); const [busy, setBusy] = useState(false); const [err, setErr] = useState('')
  const create = async () => { setBusy(true); try { const r = await call<{ dataset_id: string }>('dataset_create', { title: title.trim() }); onCreated(r.dataset_id) } catch (e: any) { setErr(String(e?.message ?? e)); setBusy(false) } }
  return <div className="overlay" onClick={onClose}><div className="sheet small" onClick={e => e.stopPropagation()} role="dialog" aria-label="New dataset">
    <div className="bar"><h2 className="section-title" style={{ margin: 0 }}>New dataset</h2><button className="iconbtn" style={{ marginLeft: 'auto' }} aria-label="Close" onClick={onClose}><Icon name="close" size={18} /></button></div>
    <label className="field"><span>Name</span><input autoFocus value={title} placeholder="fLoc stimuli" onChange={e => setTitle(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && title.trim()) create() }} /></label>
    {err && <p className="ink2">{err}</p>}
    <div className="bar"><button className="btn" onClick={onClose}>Cancel</button><button className="btn primary" style={{ marginLeft: 'auto' }} disabled={!title.trim() || busy} onClick={create}>Create</button></div>
  </div></div>
}

function DatasetView({ id, ds, projects, onBack, onOpenProject, onChanged, initialTab }: { id: string; ds?: DS; projects: Row<Project>[]; onBack: () => void; onOpenProject: (id: string) => void; onChanged: () => void; initialTab?: 'samples' | 'adapters' }) {
  const [tab, setTab] = useState<'samples' | 'projects' | 'adapters'>(initialTab ?? 'samples'); useEffect(() => { if (initialTab) setTab(initialTab) }, [initialTab]); const [stages, setStages] = useState<Stage[]>([]); const [res, setRes] = useState<Query | null>(null)
  const [limit, setLimit] = useState(60); const [indexing, setIndexing] = useState<{ indexed: number; total: number } | null>(null); const [importing, setImporting] = useState(false)
  const [sample, setSample] = useState<Item | null>(null); const [openField, setOpenField] = useState<string | null>(null); const [err, setErr] = useState('')
  const [picked, setPicked] = useState<string[]>([]); const [tag, setTag] = useState(''); const [views, setViews] = useState<{ view_id: string; name: string; stages: Stage[]; items: number }[]>([])
  const [saving, setSaving] = useState(false); const [viewTitle, setViewTitle] = useState('')
  const loadViews = () => call<any[]>('view_list', { dataset_id: id }).then(setViews).catch(() => {})
  useEffect(() => { loadViews() }, [id])
  const tagPicked = async () => { await call('item_update', { item_ids: picked, add_tags: [tag.trim()] }); setPicked([]); setTag(''); load() }
  const saveView = async () => { await call('view_create', { dataset_id: id, title: viewTitle.trim(), stages }); setSaving(false); setViewTitle(''); loadViews() }
  const load = () => call<Query>('item_query', { dataset_id: id, stages, limit }).then(r => { setRes(r); setErr('') }).catch(e => setErr(String(e?.message ?? e)))
  useEffect(() => { load() }, [id, JSON.stringify(stages), limit])
  useEffect(() => {
    const f = (e: Event) => { const m = (e as CustomEvent).detail; if (m?.dataset !== id) return
      if (m.embedding != null) return
      if (m.error) { setIndexing(null); setEmbedding(null); setErr(`Stopped: ${m.error}`) } else if (m.done) { setIndexing(null); load(); onChanged() } else setIndexing({ indexed: m.indexed, total: m.total }) }
    window.addEventListener('lab-dataset', f); return () => window.removeEventListener('lab-dataset', f)
  }, [id, JSON.stringify(stages)])
  const [embedding, setEmbedding] = useState<{ done: number; total: number } | null>(null)
  useEffect(() => {
    const f = (e: Event) => { const m = (e as CustomEvent).detail; if (m?.dataset !== id || m.embedding == null) return
      if (m.embedded) { setEmbedding(null); onChanged() } else setEmbedding({ done: m.embedding, total: m.total }) }
    window.addEventListener('lab-dataset', f); return () => window.removeEventListener('lab-dataset', f)
  }, [id])
  const embed = () => { setEmbedding({ done: 0, total: res?.trail[0]?.count ?? 0 }); call('embedding_create', { dataset_id: id }).catch(e => { setEmbedding(null); setErr(String(e?.message ?? e)) }) }
  const index = () => { setIndexing({ indexed: 0, total: ds?.files_here ?? 0 }); call('item_create', { dataset_id: id }).catch(e => { setIndexing(null); setErr(String(e?.message ?? e)) }) }
  const users = projects.filter(p => (ds?.projects ?? []).includes(p.id))
  const fields = (res?.schema ?? []).filter(f => !HIDDEN.has(f.path))
  const addStage = (st: Stage) => { setLimit(60); setStages(s => [...s.filter(x => !(x.stage === st.stage && x.path === st.path)), st]) }
  return <div className="dspage">
    <div className="bar dshead">
      <button className="btn" onClick={onBack}><Icon name="back" size={16} />All datasets</button>
      <h2 className="section-title" style={{ margin: 0 }}>{ds?.title || id}</h2>
      <div className="seg" role="tablist" aria-label="Dataset">
        <button role="tab" aria-selected={tab === 'samples'} className={tab === 'samples' ? 'on' : ''} onClick={() => setTab('samples')}>Samples{res?.indexed ? ` (${n(res.trail[0]?.count ?? 0)})` : ''}</button>
        <button role="tab" aria-selected={tab === 'projects'} className={tab === 'projects' ? 'on' : ''} onClick={() => setTab('projects')}>Projects ({users.length})</button>
        {ds?.measured && <button role="tab" aria-selected={tab === 'adapters'} className={tab === 'adapters' ? 'on' : ''} onClick={() => setTab('adapters')}>Adapters ({ds.adapters ?? 0})</button>}
      </div>
      {res?.indexed && !ds?.embedded && !embedding && <button className="btn" style={{ marginLeft: 'auto' }} onClick={embed}>Compute similarity</button>}
      <button className="btn primary" style={res?.indexed && !ds?.embedded && !embedding ? undefined : { marginLeft: 'auto' }} onClick={() => setImporting(true)}><Icon name="upload" size={16} />Import</button>
    </div>
    {err && <div className="dsnote">{err}</div>}
    {embedding && <div className="dsnote" role="status"><span className="spin" /> Computing V-JEPA 2 vectors for similarity: {n(embedding.done)} of {count(embedding.total, 'sample')}.</div>}
    {indexing && <div className="dsnote" role="status"><span className="spin" /> Indexing {indexing.total ? `${n(indexing.indexed)} of ${n(indexing.total)} files` : 'the files'}: fields and filters fill in when it finishes.</div>}
    {tab === 'adapters' ? <AdaptersView datasetId={id} views={views} onChanged={onChanged} />
    : tab === 'projects' ? <div className="tablewrap"><table className="data dstable"><thead><tr><th>Project</th><th>Status</th></tr></thead>
      <tbody>{users.length ? users.map(p => <tr key={p.id} onClick={() => onOpenProject(p.id)} style={{ cursor: 'pointer' }}><td>{p.data.title}</td><td>{p.data.status}</td></tr>)
        : <tr><td colSpan={2} className="ink2">No project uses this dataset yet. A new project picks its datasets when it is created.</td></tr>}</tbody></table></div>
    : !res ? <div className="empty wait" role="status"><span className="spin" /> Reading the samples</div>
    : !res.indexed ? <div className="empty">
        <p>{ds?.files_here ? `${count(ds.files_here, 'file')} here, not indexed yet. Indexing makes each image, video and audio file a sample with its fields.` : 'No files yet. Import images, videos or a folder.'}</p>
        {!!ds?.files_here && !indexing && <button className="btn primary" onClick={index}>Index the files</button>}
      </div>
    : <div className="dsbody">
        <aside className="dsfields" aria-label="Fields">
          {views.length > 0 && <><div className="ink2 small">Saved views</div>
            {views.map(v => <button key={v.view_id} className="dsfieldhead" onClick={() => { setLimit(60); setStages(v.stages) }}><span>{v.name}</span><span className="ink2 num">{n(v.items)}</span></button>)}</>}
          <div className="ink2 small">{fields.length} fields</div>
          {fields.map(f => { const fc = res.facets[f.path]; const on = openField === f.path
            return <div key={f.path} className="dsfield">
              <button className="dsfieldhead" aria-expanded={on} onClick={() => setOpenField(on ? null : f.path)}><span>{f.path}</span><span className="ink2 num">{n(fc?.count ?? f.count)}</span></button>
              {on && fc?.kind === 'values' && <div className="dsvals">{fc.values!.map(([v, c]) => { const active = stages.some(s => s.stage === 'match' && s.path === f.path && (s.value === v || (Array.isArray(s.value) && s.value.includes(v))))
                return <label key={v} className="dsval"><input type="checkbox" checked={active} onChange={e => {
                  const cur = stages.find(s => s.stage === 'match' && s.path === f.path); const vals: string[] = cur ? (Array.isArray(cur.value) ? cur.value : [cur.value]) : []
                  const next = e.target.checked ? [...vals, v] : vals.filter(x => x !== v)
                  if (!next.length) setStages(s => s.filter(x => !(x.stage === 'match' && x.path === f.path)))
                  else addStage({ stage: 'match', path: f.path, op: 'in', value: f.type === 'list' ? next : next.map(x => f.type === 'bool' ? x === 'true' : x) })
                }} /><span>{v}</span><span className="ink2 num">{n(c)}</span></label> })}</div>}
              {on && fc?.kind === 'numeric' && <Range f={f.path} fc={fc} onApply={(lo, hi) => addStage({ stage: 'match', path: f.path, op: 'between', value: [lo, hi] })} />}
            </div> })}
        </aside>
        <section className="dsgrid-wrap">
          <div className="bar dsviewbar">
            <span className="num">{n(res.total)} of {count(res.trail[0]?.count ?? res.total, 'sample')}</span>
            {stages.map((s, i) => <span key={i} className="chip">{res.trail[i + 1]?.text ?? s.stage}<button className="iconbtn" aria-label={`Remove ${res.trail[i + 1]?.text ?? s.stage}`} onClick={() => setStages(st => st.filter((_, j) => j !== i))}><Icon name="close" size={13} /></button></span>)}
            {saving ? <span className="bar"><input aria-label="View title" placeholder="Houses" value={viewTitle} onChange={e => setViewTitle(e.target.value)} />
                <button className="btn" disabled={!viewTitle.trim()} onClick={saveView}>Save</button><button className="btn" onClick={() => setSaving(false)}>Cancel</button></span>
              : <button className="btn" onClick={() => setSaving(true)}>Save view</button>}
            {picked.length > 0 && <span className="bar"><span className="ink2">{picked.length} picked</span>
              <input aria-label="Tag" placeholder="Tag" value={tag} onChange={e => setTag(e.target.value)} /><button className="btn" disabled={!tag.trim()} onClick={tagPicked}>Tag</button>
              <button className="btn" onClick={() => setPicked([])}>Clear</button></span>}
            <label className="dssort">Sort <select value={stages.find(s => s.stage === 'sort_by')?.path ?? ''} onChange={e => setStages(st => [...st.filter(s => s.stage !== 'sort_by'), ...(e.target.value ? [{ stage: 'sort_by', path: e.target.value, reverse: true }] : [])])}>
              <option value="">File order</option>{fields.filter(f => f.type === 'int' || f.type === 'float').map(f => <option key={f.path} value={f.path}>{f.path}, largest first</option>)}</select></label>
          </div>
          <div className="dsgrid">{res.items.map(x => <div key={x.id} className={`dstile ${picked.includes(x.id) ? 'picked' : ''}`}>
            <button className="dstilemedia" onClick={() => setSample(x)} title={x.path}>{x.thumb ? <img src={x.thumb} alt={x.path} loading="lazy" /> : <span className="dsnothumb">{x.media_type}</span>}</button>
            <label className="dscap"><input type="checkbox" aria-label={`Pick ${x.path}`} checked={picked.includes(x.id)} onChange={e => setPicked(p => e.target.checked ? [...p, x.id] : p.filter(i => i !== x.id))} />
              <span>{x.path.split('/').pop()}</span>{x.tags.length > 0 && <span className="chip tiny">{x.tags.join(', ')}</span>}</label></div>)}</div>
          {res.items.length < res.total && <div className="bar" style={{ justifyContent: 'center' }}><button className="btn" onClick={() => setLimit(l => l + 120)}>Show more ({n(res.total - res.items.length)} left)</button></div>}
        </section>
      </div>}
    {sample && <SampleView item={sample} onClose={() => setSample(null)} onSimilar={ds?.embedded ? () => { setLimit(60); setStages([{ stage: 'similar_to', id: sample.id, label: sample.path.split('/').pop() }]); setSample(null) } : undefined} />}
    {importing && <ImportPanel id={id} title={ds?.title || id} onClose={() => setImporting(false)} onDone={() => { setImporting(false); index(); onChanged() }} />}
  </div>
}

function Range({ f, fc, onApply }: { f: string; fc: Facet; onApply: (lo: number, hi: number) => void }) {
  const [lo, setLo] = useState(String(fc.min ?? '')); const [hi, setHi] = useState(String(fc.max ?? ''))
  const peak = Math.max(...(fc.hist ?? [1]))
  return <div className="dsrange">
    <div className="dshist" aria-hidden>{(fc.hist ?? []).map((h, i) => <i key={i} style={{ height: `${Math.max(2, 100 * h / peak)}%` }} />)}</div>
    <div className="bar"><input aria-label={`${f} from`} value={lo} onChange={e => setLo(e.target.value)} /><span className="ink2">to</span><input aria-label={`${f} to`} value={hi} onChange={e => setHi(e.target.value)} />
      <button className="btn" disabled={isNaN(+lo) || isNaN(+hi)} onClick={() => onApply(+lo, +hi)}>Filter</button></div>
  </div>
}

function SampleView({ item, onClose, onSimilar }: { item: Item; onClose: () => void; onSimilar?: () => void }) {
  useEffect(() => { const esc = (e: KeyboardEvent) => { if (e.key === 'Escape') { e.stopPropagation(); onClose() } }; document.addEventListener('keydown', esc); return () => document.removeEventListener('keydown', esc) }, [onClose])
  return <div className="overlay" onClick={onClose}><div className="sheet dssample" onClick={e => e.stopPropagation()} role="dialog" aria-label={item.path}>
    <div className="bar"><h2 className="section-title" style={{ margin: 0 }}>{item.path}</h2>
      {onSimilar && <button className="btn" style={{ marginLeft: 'auto' }} onClick={onSimilar}>Show the most similar</button>}
      <button className="iconbtn" style={onSimilar ? undefined : { marginLeft: 'auto' }} aria-label="Close" onClick={onClose}><Icon name="close" size={18} /></button></div>
    <div className="dssamplebody">
      <div className={`dsmedia ${item.media_type === 'recording' ? 'dsrec' : ''}`}>{item.media_type === 'recording' ? <RecordingView manifestUrl={item.media} /> : item.media_type === 'video' ? <video src={item.media} controls autoPlay muted playsInline /> : item.media_type === 'image' ? <img src={item.media} alt={item.path} />
        : item.media_type === 'audio' ? <audio src={item.media} controls /> : <span className="ink2">{item.media_type}</span>}</div>
      <table className="data compact"><thead><tr><th>Field</th><th>Value</th><th>From</th></tr></thead>
        <tbody>{Object.entries(item.fields).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 4 }) : String(v)}</td><td className="ink2 small">{item.sources[k] ?? ''}</td></tr>)}
          {item.tags.length > 0 && <tr><td>tags</td><td>{item.tags.join(', ')}</td><td className="ink2 small">added here</td></tr>}</tbody></table>
    </div>
  </div></div>
}

type Up = { name: string; size: number; sent: number; state: 'waiting' | 'sending' | 'done' | 'failed'; error?: string }
function ImportPanel({ id, title, onClose, onDone }: { id: string; title: string; onClose: () => void; onDone: () => void }) {
  const [files, setFiles] = useState<{ f: File; rel: string }[]>([]); const [ups, setUps] = useState<Up[]>([]); const [busy, setBusy] = useState(false); const [over, setOver] = useState(false)
  const pick = useRef<HTMLInputElement>(null); const folder = useRef<HTMLInputElement>(null)
  const add = (list: FileList | null) => { if (!list) return; const xs = [...list].map(f => ({ f, rel: (f as any).webkitRelativePath || f.name })); setFiles(fs => [...fs, ...xs]); setUps(u => [...u, ...xs.map(x => ({ name: x.rel, size: x.f.size, sent: 0, state: 'waiting' as const }))]) }
  const total = useMemo(() => files.reduce((t, x) => t + x.f.size, 0), [files])
  const send = async () => {
    setBusy(true)
    for (let i = 0; i < files.length; i++) {
      const { f, rel } = files[i]; setUps(u => u.map((x, j) => j === i ? { ...x, state: 'sending' } : x))
      try { await uploadWithProgress(`/datasets/upload?name=${encodeURIComponent(rel)}&dataset_id=${encodeURIComponent(id)}`, f, sent => setUps(u => u.map((x, j) => j === i ? { ...x, sent } : x)))
        setUps(u => u.map((x, j) => j === i ? { ...x, sent: x.size, state: 'done' } : x)) }
      catch (e: any) { setUps(u => u.map((x, j) => j === i ? { ...x, state: 'failed', error: String(e?.message ?? e).slice(0, 160) } : x)) }
    }
    setBusy(false)
  }
  const finished = ups.length > 0 && ups.every(u => u.state === 'done' || u.state === 'failed')
  return <div className="overlay" onClick={() => !busy && onClose()}><div className="sheet" onClick={e => e.stopPropagation()} role="dialog" aria-label={`Import into ${title}`}>
    <div className="bar"><h2 className="section-title" style={{ margin: 0 }}>Import into {title}</h2><button className="iconbtn" style={{ marginLeft: 'auto' }} aria-label="Close" disabled={busy} onClick={onClose}><Icon name="close" size={18} /></button></div>
    <p className="ink2" style={{ marginTop: 0 }}>Files are copied to this machine. Each image, video and audio file becomes a sample; a folder's name becomes its category, and a CSV that names the files adds its columns as fields. Archives are unpacked.</p>
    <div className={`dsdrop ${over ? 'over' : ''}`} onDragOver={e => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); add(e.dataTransfer.files) }} onClick={() => pick.current?.click()} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') pick.current?.click() }}>
      <Icon name="upload" size={22} /><b>Drop images, videos, audio, archives or a CSV here</b><span className="ink2">or click to choose files</span>
    </div>
    <input ref={pick} type="file" multiple hidden onChange={e => { add(e.target.files); e.target.value = '' }} />
    <input ref={folder} type="file" multiple hidden {...({ webkitdirectory: '', directory: '' } as any)} onChange={e => { add(e.target.files); e.target.value = '' }} />
    <button className="btn" onClick={() => folder.current?.click()} disabled={busy}><Icon name="samples" size={16} />Choose a folder instead</button>
    {ups.length > 0 && <div className="dsups"><div className="ink2 small">{count(ups.length, 'file')}, {(total / 1e6).toFixed(1)} MB</div>
      {ups.slice(0, 200).map((u, i) => <div key={i} className="dsup"><span className="dsupname" title={u.name}>{u.name}</span>
        <span className="dsbar"><i style={{ width: `${u.size ? 100 * u.sent / u.size : 0}%` }} className={u.state} /></span>
        <span className="ink2 small">{u.state === 'failed' ? `Failed: ${u.error}` : u.state === 'done' ? 'Done' : u.state === 'sending' ? `${Math.round(100 * u.sent / (u.size || 1))}%` : 'Waiting'}</span></div>)}
      {ups.length > 200 && <div className="ink2 small">and {ups.length - 200} more</div>}</div>}
    <div className="bar"><button className="btn" onClick={onClose} disabled={busy}>Cancel</button>
      {finished ? <button className="btn primary" style={{ marginLeft: 'auto' }} onClick={onDone}>Index {count(ups.filter(u => u.state === 'done').length, 'file')}</button>
        : <button className="btn primary" style={{ marginLeft: 'auto' }} disabled={!files.length || busy} onClick={send}>{busy ? 'Copying' : files.length ? `Import ${count(files.length, 'file')}` : 'Import files'}</button>}</div>
  </div></div>
}
