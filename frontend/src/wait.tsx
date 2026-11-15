/** Waiting without flashes (#30, after Emil Kowalski's skills): nothing shows for a wait under 300 ms, and a longer one
 * shows a still skeleton shaped like the content it stands for, never a bare spinner that replaces the panel.
 * The 300 ms is in styles.css (.skel, .wait, .spin), so every waiting state follows one rule. */

/** A still placeholder in the content's shape: a heading's lines, then blocks for the cards or figures that follow. */
export function Skeleton({ lines = 2, blocks = [220], label = 'Loading' }: { lines?: number; blocks?: number[]; label?: string }) {
  return <div className="skel" role="status" aria-label={label} aria-busy="true">
    {Array.from({ length: lines }, (_, i) => <div key={`l${i}`} className="skelline" style={{ width: `${i === lines - 1 && lines > 1 ? 55 : 92}%` }} />)}
    {blocks.map((h, i) => <div key={`b${i}`} className="skelblock" style={{ height: h }} />)}
  </div>
}
