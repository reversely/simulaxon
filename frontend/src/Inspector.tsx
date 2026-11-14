import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { api, fmt, mediaUrl, unitLabel, unitOf, type Field, type SampleFull, type Track } from './api'
import { brk } from './brk'
// the cortex view (three.js) loads only when a sample has a cortex track: it is most of the app's code by size
const BrainView = lazy(() => import('./BrainView').then(m => ({ default: m.BrainView })))
if (typeof window !== 'undefined') (window.requestIdleCallback ?? ((f: () => void) => setTimeout(f, 1500)))(() => { import('./BrainView').then(m => m.loadMesh()) })   // first open drew in 1.3 s without this
const CORTEX_VERTICES = 20484   // fsaverage5, both hemispheres: one column per vertex in a TRIBE v2 prediction

// One sample: the media of every slice in its group, every field with the file and key it came from, and every time
// track charted on one clock with the video's playhead. Wide tracks arrive summarised; the chart says so.

const SERIES = ['var(--s1)', 'var(--s2)', 'var(--s3)', 'var(--s4)', 'var(--s5)', 'var(--s6)']   // validated on the panel colour

// end labels sorted by height and pushed apart so none overlap; each stays as near its line's last value as it can
function endLabels(items: { k: number; y: number }[], top: number, bottom: number, gap = 16) {
  const s = [...items].sort((a, b) => a.y - b.y)
  for (let i = 1; i < s.length; i++) s[i].y = Math.max(s[i].y, s[i - 1].y + gap)
  const over = s.length ? s[s.length - 1].y - bottom : 0
  if (over > 0) for (const it of s) it.y -= over
  for (let i = 0; i < s.length; i++) s[i].y = Math.max(s[i].y, top + i * gap)
  return s
}

function TrackChart({ t, now, onSeek }: { t: Track; now: number; onSeek: (s: number) => void }) {
  const W = 600, H = 140, L = 64, T = 10, B = 22
  const R = Math.min(200, Math.max(60, 14 + 7.6 * Math.max(...t.columns.slice(0, t.band ? 1 : undefined).map(c => c.length))))   // room for the longest end label
  const [hx, setHx] = useState<number | null>(null)
  const band = t.band   // a wide track: values are mean, mean minus SD, mean plus SD
  const lines = band ? [t.values[0]] : t.values
  const all = (band ? t.values : lines).flat().filter((v): v is number => v !== null && Number.isFinite(v))
  let lo = Math.min(...all), hi = Math.max(...all); if (lo === hi) { lo -= 1; hi += 1 }
  const t0 = t.time_s[0], t1 = t.time_s[t.time_s.length - 1] || 1
  const x = (s: number) => L + ((s - t0) / (t1 - t0 || 1)) * (W - L - R), y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  // a missing reading (null) breaks the line; it is never drawn as zero
  const path = (vs: (number | null)[]) => vs.map((v, i) => v === null || !Number.isFinite(v) ? '' : `${i && vs[i - 1] !== null ? 'L' : 'M'}${x(t.time_s[i]).toFixed(1)},${y(v).toFixed(1)}`).join('')
  const idx = hx === null ? null : t.time_s.reduce((b, s, i) => Math.abs(s - hx) < Math.abs(t.time_s[b] - hx) ? i : b, 0)
  const ticks = [lo, (lo + hi) / 2, hi]
  return <figure className="track">
    {(t.summary || t.caption) && <figcaption className="ink2">{[t.caption, t.summary].filter(Boolean).join('. ')}</figcaption>}
    {/* drawn in a W x H box and scaled to the panel: at a fixed 600 px it was wider than the sample panel (592 px of room)
        and the panel scrolled sideways (2026-11-14); the pointer is mapped back into the box */}
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: W, height: 'auto' }} role="img" aria-label={`Track with ${lines.length} series over ${fmt(t1 - t0)} s`}
      onMouseMove={e => { const r = e.currentTarget.getBoundingClientRect(); const px = (e.clientX - r.left) * (W / r.width); const s = t0 + ((px - L) / (W - L - R)) * (t1 - t0); setHx(Math.min(t1, Math.max(t0, s))) }}
      onMouseLeave={() => setHx(null)} onClick={() => hx !== null && onSeek(hx)}>
      {ticks.map((v, i) => <g key={i}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="grid" /><text x={L - 6} y={y(v) + 4} textAnchor="end" className="tick">{fmt(v)}</text></g>)}
      <text x={L} y={H - 4} className="tick">{fmt(t0)} s</text><text x={W - R} y={H - 4} textAnchor="end" className="tick">{fmt(t1)} s</text>
      {band && <path d={path(t.values[2]) + t.values[1].map((_, i, a) => `L${x(t.time_s[a.length - 1 - i]).toFixed(1)},${y(a[a.length - 1 - i]).toFixed(1)}`).join('') + 'Z'} className="band" />}
      {lines.map((vs, k) => <path key={k} d={path(vs)} fill="none" stroke={SERIES[k % SERIES.length]} strokeWidth={2} />)}
      {endLabels(lines.map((vs, k) => ({ k, y: y([...vs].reverse().find((v): v is number => v !== null && Number.isFinite(v)) ?? lo) })), T + 6, H - B).map(({ k, y: yy }) => <text key={k} x={W - R + 6} y={yy + 4} className="end">{t.columns[k]}</text>)}
      {now >= t0 && now <= t1 && <line x1={x(now)} x2={x(now)} y1={T} y2={H - B} className="now" />}
      {idx !== null && <line x1={x(t.time_s[idx])} x2={x(t.time_s[idx])} y1={T} y2={H - B} className="cross" />}
    </svg>
    <div className="ttip" aria-live="polite">{idx === null ? 'Hover for values. Click to move playback there' :
      <><b>{fmt(t.time_s[idx])} s</b>{lines.map((vs, k) => <span key={k}><i style={{ background: SERIES[k % SERIES.length] }} />{t.columns[k]} {fmt(vs[idx])}{unitOf(t.unit, t.columns[k]) ? ` ${unitOf(t.unit, t.columns[k])}` : ''}</span>)}</>}</div>
    <div className="legend">{lines.map((_, k) => <span key={k}><i style={{ background: SERIES[k % SERIES.length] }} />{t.columns[k]}</span>)}</div>
    <div className="src">From {brk(t.source)}</div>
  </figure>
}

// columns with different units never share an axis: one chart per unit, in column order
function byUnit(t: Track): Track[] {
  if (!t.unit || typeof t.unit === 'string') return [t]
  const groups = new Map<string, number[]>()
  t.columns.forEach((c, i) => { const u = unitOf(t.unit, c) || 'no unit'; groups.set(u, [...(groups.get(u) ?? []), i]) })
  return [...groups.entries()].map(([u, idx]) => ({ ...t, unit: u === 'no unit' ? null : u, columns: idx.map(i => t.columns[i]), values: idx.map(i => t.values[i]),
    caption: `${idx.map(i => t.columns[i]).join(', ')}${u === 'no unit' ? '' : `, ${u}`}` }))
}

export function Inspector({ dataset, id, computed, schema, onClose, wide, onWide, shown = [] }: { dataset: string; id: string; computed?: { fields: Record<string, any>; sources: Record<string, string> }; schema: Field[]; onClose: () => void; wide?: boolean; onWide?: (w: boolean) => void; shown?: string[] }) {
  const unit = (p: string) => schema.find(f => f.path === p)?.unit
  const [s, setS] = useState<SampleFull | null>(null), [err, setErr] = useState('')
  const [tracks, setTracks] = useState<Record<string, Track | string>>({})
  const [now, setNow] = useState(0)
  const vids = useRef<HTMLVideoElement[]>([])
  // a group's clips share one clock: playing, pausing or seeking one does the same to the others (a clip that has
  // already ended stays on its last frame); the open sample's clip drives the playhead and the cortex, every frame
  const lock = useRef(false)
  const together = (i: number, act: (v: HTMLVideoElement, t: number) => void) => {
    if (lock.current) return; lock.current = true
    const t = vids.current[i]?.currentTime ?? 0
    vids.current.forEach((v, j) => { if (v && j !== i) act(v, t) })
    setTimeout(() => { lock.current = false }, 80)
  }
  const playAt = (v: HTMLVideoElement, t: number) => { if (t < v.duration - 0.05) { v.currentTime = t; v.play().catch(() => {}) } else { v.pause(); v.currentTime = v.duration } }
  const clockIdx = useRef(0)
  useEffect(() => {
    let raf = 0
    const tick = () => { const v = vids.current[clockIdx.current]; if (v && !v.paused) setNow(v.currentTime); raf = requestAnimationFrame(tick) }
    raf = requestAnimationFrame(tick); return () => cancelAnimationFrame(raf)
  }, [])
  useEffect(() => { setS(null); setTracks({}); setErr(''); api.sample(dataset, id).then(setS).catch(e => setErr(String(e.message))) }, [dataset, id])
  const trackPaths = s ? Object.keys(s.fields).filter(p => s.fields[p]?._kind === 'track') : []
  const open = (p: string) => { setTracks(t => ({ ...t, [p]: 'Loading' })); api.track(dataset, id, p).then(tr => setTracks(t => ({ ...t, [p]: tr }))).catch(e => setTracks(t => ({ ...t, [p]: `Could not load: ${e.message}` }))) }
  const seek = (sec: number) => { lock.current = true; vids.current.forEach(v => { if (v) v.currentTime = Math.min(sec, v.duration || sec) }); setNow(sec); setTimeout(() => { lock.current = false }, 80) }
  if (err) return <aside className="inspector"><p className="flag">{err}</p></aside>
  if (!s) return <aside className="inspector"><p className="ink2">Loading {id}</p></aside>
  const scalars = Object.keys(s.fields).filter(p => s.fields[p]?._kind !== 'track')
  const cortex = trackPaths.find(p => s.fields[p]?.shape?.[1] === CORTEX_VERTICES)
  clockIdx.current = Math.max(0, s.group_members.findIndex(m => m.id === s.id))
  const added = Object.keys(computed?.sources ?? {})
  return <aside className="inspector" aria-label={`Sample ${s.id}`}>
    <header><h2>{brk(s.id)}</h2><span className="hbtns">{onWide && <button className="btn" onClick={() => onWide(!wide)} aria-pressed={!!wide}>{wide ? 'Collapse' : 'Expand'}</button>}<button className="btn" onClick={onClose}>Close</button></span></header>
    {s.group_members.length > 1 && <div className="ink2">Group {s.group}, {s.group_members.length} slices</div>}
    <div className={`slices${s.group_members.length > 2 ? ' many' : ''}`}>{s.group_members.map((m, i) => <div key={m.id} className={`slice${m.id === s.id ? ' this' : ''}`}>
      {m.slice && <div className="side">Slice {m.slice}{m.id === s.id ? ', this sample' : ''}</div>}
      {m.media_type === 'video' ? <video ref={el => { if (el) vids.current[i] = el }} src={mediaUrl(m.media!)} controls muted playsInline aria-label={`Slice ${m.slice ?? m.id} video`}
        onTimeUpdate={e => { if (i === clockIdx.current) setNow(e.currentTarget.currentTime) }}
        onPlay={() => together(i, playAt)} onPause={e => { if (!e.currentTarget.ended) together(i, v => v.pause()) }} onSeeked={() => together(i, (v, t) => { v.currentTime = Math.min(t, v.duration || t) })} />
        : m.media_type === 'image' ? <img src={mediaUrl(m.media!)} alt={m.id} /> : m.media_type === 'audio' ? <audio src={mediaUrl(m.media!)} controls onTimeUpdate={e => setNow(e.currentTarget.currentTime)} /> : <div className="nomedia">No media file</div>}
      {shown.some(p => m.fields?.[p] !== undefined) && <div className="svals">{shown.filter(p => m.fields?.[p] !== undefined).map(p => <span key={p}><span className="ink3">{p}</span> <b className="num">{fmt(m.fields![p])}</b>{typeof unit(p) === 'string' ? ` ${unit(p)}` : ''}</span>)}</div>}
      {m.media && <div className="src" title={m.media}>{wide ? m.media : brk(m.media)}{s.sources._media && m.id === s.id ? <>, {brk(s.sources._media)}</> : ''}</div>}
    </div>)}</div>
    <div className="below">
    {cortex && <Suspense fallback={<p className="ink2">Loading the cortex</p>}><BrainView dataset={dataset} id={s.id} path={cortex} now={now} /></Suspense>}
    {trackPaths.length > 0 && <section><h3>Tracks</h3>{trackPaths.map(p => {
      const t = tracks[p]
      return <div key={p} className="tblock">
        <button className="fname" onClick={() => t ? setTracks(({ [p]: _, ...rest }) => rest) : open(p)} aria-expanded={!!t}>{p}</button> <span className="ink3">{fmt(s.fields[p])}{unit(p) ? `, ${unitLabel(unit(p))}` : ''}</span>
        {typeof t === 'string' ? <p className="ink2">{t}</p> : t && byUnit(t).map((part, i) => <TrackChart key={i} t={part} now={now} onSeek={seek} />)}
      </div>
    })}</section>}
    <section className="fsec"><h3>Fields</h3><table className="ftable"><thead><tr><th>Field</th><th>Value</th><th>From</th></tr></thead>
      <tbody>{added.map(p => <tr key={p} className="added"><td>{p}</td><td className="num">{brk(fmt(computed!.fields[p]))}</td><td className="src">{brk(computed!.sources[p])}</td></tr>)}
        {scalars.map(p => <tr key={p}><td>{p}</td><td className="num">{brk(fmt(s.fields[p]))}{typeof unit(p) === 'string' ? ` ${unit(p)}` : ''}</td><td className="src">{brk(s.sources[p] ?? 'not recorded')}</td></tr>)}</tbody></table></section>
    </div>
  </aside>
}
