/** A recording (#23, lab/recording.py) played as one timeline: its first video and TRIBE v2 stream in the brain player,
 * its audio on the same clock, and one lane per stream (tables one lane per column, events as ticks). */
import { useEffect, useState } from 'react'
import { ClipBrain, type Lane } from './brain3d'

type Stream = { name: string; kind: 'video' | 'tribe' | 'audio' | 'table' | 'events'; file: string; start_s?: number; time_column?: string; label_column?: string }
type Manifest = { format: string; title?: string; duration_s?: number; streams: Stream[] }

function csv(text: string): string[][] {
  const rows: string[][] = []; let row: string[] = [], cell = '', q = false
  for (let i = 0; i < text.length; i++) { const c = text[i]
    if (q) { if (c === '"' && text[i + 1] === '"') { cell += '"'; i++ } else if (c === '"') q = false; else cell += c }
    else if (c === '"') q = true; else if (c === ',') { row.push(cell); cell = '' } else if (c === '\n' || c === '\r') { if (c === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = '' }
    else cell += c }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  return rows.filter(r => r.some(x => x !== ''))
}

async function peaks(url: string): Promise<{ values: number[]; dur: number }> {
  const buf = await (await fetch(url)).arrayBuffer(); const ctx = new AudioContext()
  try { const a = await ctx.decodeAudioData(buf); const ch = a.getChannelData(0); const n = 300; const step = Math.max(1, Math.floor(ch.length / n)); const values: number[] = []
    for (let i = 0; i < n && i * step < ch.length; i++) { let m = 0; for (let j = i * step; j < Math.min(ch.length, (i + 1) * step); j++) m = Math.max(m, Math.abs(ch[j])); values.push(m) }
    return { values, dur: a.duration } } finally { ctx.close() }
}

export function RecordingView({ manifestUrl }: { manifestUrl: string }) {
  const base = manifestUrl.slice(0, manifestUrl.lastIndexOf('/') + 1)
  const [rec, setRec] = useState<{ m: Manifest; lanes: Lane[] } | null>(null); const [err, setErr] = useState<string | null>(null)
  useEffect(() => {
    let live = true; setRec(null); setErr(null)
    ;(async () => {
      const man: Manifest = await (await fetch(manifestUrl)).json(); if (!live) return
      const lane = async (s: Stream): Promise<Lane[]> => {   // every stream read at once; the player draws once, with all its lanes (#30)
        const url = base + s.file.split('/').map(encodeURIComponent).join('/'); const start = s.start_s ?? 0
        if (s.kind === 'video') return [{ name: s.name, start, dur: man.duration_s }]
        if (s.kind === 'audio') { try { const p = await peaks(url); return [{ name: s.name, start, values: p.values, times: p.values.map((_, i) => i * p.dur / p.values.length) }] } catch { return [{ name: s.name, start }] } }
        if (s.kind === 'table' || s.kind === 'events') {
          const rows = csv(await (await fetch(url)).text()); const head = rows[0] ?? []; const ti = Math.max(0, head.indexOf(s.time_column ?? 't')); const body = rows.slice(1)
          const times = body.map(r => Number(r[ti]))
          if (s.kind === 'events') { const li = head.indexOf(s.label_column ?? 'label'); return [{ name: s.name, start, ticks: true, times, labels: li >= 0 ? body.map(r => r[li]) : undefined }] }
          return head.flatMap((h, ci) => ci !== ti ? [{ name: `${s.name}: ${h}`, start, times, values: body.map(r => Number(r[ci])) }] : [])
        }
        return []
      }
      const read = await Promise.all(man.streams.map(lane)); const out: Lane[] = []
      read.forEach((ls, i) => { for (const l of ls) if (man.streams[i].kind !== 'table' || out.length < 12) out.push(l) })   // a table adds columns while fewer than 12 lanes
      if (live) setRec({ m: man, lanes: out })
    })().catch(e => live && setErr(String(e)))
    return () => { live = false }
  }, [manifestUrl])
  if (err) return <div className="ink2">This recording could not be read: {err}</div>
  if (!rec) return <div className="clipbrain skel" role="status" aria-label="Reading the recording">   {/* the player's shape, its place held */}
    <div className="twoup"><div className="skelblock" style={{ aspectRatio: '832 / 480' }} /><div className="skelblock" style={{ aspectRatio: '4 / 3', marginBottom: 96 }} /></div>
    <div className="skelblock" style={{ height: 38 }} /></div>
  const { m, lanes } = rec
  const file = (k: Stream['kind']) => { const s = m.streams.find(x => x.kind === k); return s ? base + s.file.split('/').map(encodeURIComponent).join('/') : null }
  return <ClipBrain clip={file('video')} predsUrl={file('tribe')} audio={file('audio')} lanes={lanes} />
}
