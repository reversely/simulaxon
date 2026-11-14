import { useEffect, useRef, useState } from 'react'
import { fmt, mediaUrl, unitOf, type Field, type Sample } from './api'
import { brk } from './brk'

// Samples, media first, with the fields chosen in the fields panel under each. When a pairing stage has run, the
// samples carry pair.* fields and are laid out as the pairs they are, with the distance and each matched field's
// difference shown on the pair.

function Media({ s }: { s: Sample }) {
  if (!s.media) return <div className="nomedia">No media file</div>
  // a video tile rests on its middle frame (the first frame of many clips is a start pose or black); moving the mouse
  // across it scrubs: the left edge is the first frame, the right edge the last, and the bar shows where you are
  if (s.media_type === 'video') return <Scrub src={mediaUrl(s.media)} />
  if (s.media_type === 'image') return <img src={mediaUrl(s.media)} alt={s.id} loading="lazy" />
  if (s.media_type === 'audio') return <div className="audio" onClick={e => e.stopPropagation()}><audio src={mediaUrl(s.media)} controls preload="metadata" /></div>
  return <div className="nomedia">{s.media_type} file</div>
}

// A tile holds a real <video> only while it is on screen (or 300 px from it). With one <video> per tile, a view of
// 120 clips ran 120 decoders at once: the browser stalled for tens of seconds on every view change and some tiles
// stayed black (test 19, 2026-11-13).
function useOnScreen<T extends Element>() {
  const ref = useRef<T>(null), [on, setOn] = useState(false)
  useEffect(() => {
    const el = ref.current; if (!el) return
    // the root is the grid's own scroll box: against the window, the 300 px margin never reached tiles hidden below the
    // grid's edge, so each one mounted only once on screen and showed black while it loaded (2026-11-14)
    const io = new IntersectionObserver(([e]) => setOn(e.isIntersecting), { root: el.closest('main.grid'), rootMargin: '300px' })
    io.observe(el); return () => io.disconnect()
  }, [])
  return [ref, on] as const
}

function Scrub({ src }: { src: string }) {
  const [at, setAt] = useState<number | null>(null), [dur, setDur] = useState(0)
  const [ref, on] = useOnScreen<HTMLDivElement>()
  // shown once its middle frame is decoded: until then the tile is its plain placeholder, never a black box (each new
  // tile was black for about 0.2 s after every stage or scroll, 2026-11-14)
  const [ready, setReady] = useState(false)
  useEffect(() => { if (!on) setReady(false) }, [on])
  const mid = (v: HTMLVideoElement) => { if (Number.isFinite(v.duration)) { setDur(v.duration); v.currentTime = v.duration / 2 } else setReady(true) }  // no duration: no seek, so show the first frame
  return <div className="scrub" ref={ref}>
    {!on ? <div className="vholder" /> : <video src={src} muted playsInline preload="metadata" className={ready ? 'ready' : ''} onSeeked={() => setReady(true)} onLoadedMetadata={e => mid(e.currentTarget)}
      onMouseMove={e => { const v = e.currentTarget, r = v.getBoundingClientRect(); if (!dur) return; const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)); v.currentTime = f * dur; setAt(f * dur) }}
      onMouseLeave={e => { mid(e.currentTarget); setAt(null) }} />}
    <div className="sbar"><i style={{ width: `${((at ?? dur / 2) / (dur || 1)) * 100}%` }} /></div>
    {dur > 0 && <span className="stime">{at === null ? 'Middle frame' : `${at.toFixed(1)} of ${dur.toFixed(1)} s`}</span>}
  </div>
}

function Tile({ s, shown, units, selected, onSelect }: { s: Sample; shown: string[]; units: Record<string, string>; selected: boolean; onSelect: () => void }) {
  return <button className={`tile ${selected ? 'sel' : ''}`} onClick={onSelect} aria-pressed={selected}>
    <Media s={s} />
    <div className="tid"><span>{brk(s.id)}</span>{s.slice && <span className="ink3">slice {s.slice}</span>}</div>
    {shown.length > 0 && <dl>{shown.map(p => <div key={p}><dt>{p}</dt><dd>{fmt(s.fields[p])}{units[p] && s.fields[p] != null ? ` ${units[p]}` : ''}</dd></div>)}</dl>}
  </button>
}

export function Grid({ samples, count, shown, schema, selected, onSelect }: { samples: Sample[]; count: number; shown: string[]; schema: Field[]; selected: string | null; onSelect: (id: string) => void }) {
  const units = Object.fromEntries(schema.filter(f => typeof f.unit === 'string').map(f => [f.path, unitOf(f.unit)]))
  const paired = samples.some(s => s.fields['pair.id'])
  const note = count > samples.length ? <p className="ink2 more">Showing {samples.length} of {count.toLocaleString()}</p> : null
  if (!samples.length) return <main className="grid empty"><p>No samples in this view. Remove a stage above.</p></main>
  if (!paired) return <main className="grid">{samples.map(s => <Tile key={s.id} s={s} shown={shown} units={units} selected={selected === s.id} onSelect={() => onSelect(s.id)} />)}{note}</main>
  const pairs: Record<string, Sample[]> = {}
  for (const s of samples) (pairs[s.fields['pair.id']] ??= []).push(s)
  return <main className="pairs">{Object.entries(pairs).sort().map(([pid, ss]) => {
    const L = ss.find(s => s.fields['pair.role'] === 'left'), R = ss.find(s => s.fields['pair.role'] === 'right')
    const diffs = Object.keys((L ?? R)!.fields).filter(k => k.startsWith('pair.diff.'))
    return <section key={pid} className="pair" aria-label={pid}>
      <header><b>{pid}</b><span>Distance in standard deviations <b className="num">{fmt((L ?? R)!.fields['pair.distance'])}</b></span>
        {diffs.map(k => <span key={k} className="ink2">{k.slice(10)} left minus right <b className="num">{fmt(L!.fields[k])}{units[k.slice(10)] ? ` ${units[k.slice(10)]}` : ''}</b></span>)}</header>
      <div className="two">{[L, R].map((s, i) => s && <div key={s.id}><div className="side">{i ? 'Right' : 'Left'}</div>
        <Tile s={s} shown={shown} units={units} selected={selected === s.id} onSelect={() => onSelect(s.id)} /></div>)}</div>
    </section>
  })}{note}</main>
}
