import type { ReactNode } from 'react'

// Long ids and file paths may wrap only after / # _ , so a line never splits a word. Elements that wrapped "anywhere"
// broke "app_table.json" into "app_table.jso" and "n", and tile ids at random characters (2026-11-14).
export const brk = (v: string): ReactNode => v.split(/(?<=[/#_])/).flatMap((part, i) => i ? [<wbr key={i} />, part] : [part])
