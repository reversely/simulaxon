// Line icons, one weight and size, drawn in the text colour so they follow the theme. An icon helps read a control; the
// word stays beside it, except where a standard symbol says it alone (Close), which then carries its name for screen readers.
const PATHS: Record<string, string> = {
  close: 'M6 6l12 12M18 6L6 18',
  plus: 'M12 5v14M5 12h14',
  chat: 'M5 4h14a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-9l-5 4v-4H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z',
  flask: 'M9 3h6M10 3v6l-5.4 9.2A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-2.8L14 9V3M7.2 15h9.6',
  template: 'M4 4h16v16H4zM4 9h16M10 9v11',
  play: 'M7 5l12 7-12 7z',
  stop: 'M7 7h10v10H7z',
  open: 'M7 17L17 7M9 7h8v8',
  upload: 'M12 15V4M7 9l5-5 5 5M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
  download: 'M12 4v11M7 10l5 5 5-5M4 20h16',
  send: 'M4 12L20 4l-6 16-3-7z M11 13l9-9',
  undo: 'M9 14L4 9l5-5M4 9h11a5 5 0 0 1 0 10h-3',
  code: 'M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14',
  expand: 'M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7',
  shrink: 'M4 10h6V4M20 14h-6v6M10 10L3 3M14 14l7 7',
  gauge: 'M4 15a8 8 0 0 1 16 0M12 15l4-4M12 15h.01',
  room: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12v9M12 12L4 7.5',
  samples: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  brain: 'M9 4a3 3 0 0 0-3 3 3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 3 3 2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM15 4a3 3 0 0 1 3 3 3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-3 3 2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
  search: 'M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13zM20 20l-4.8-4.8',
  table: 'M4 5h16v14H4zM4 10h16M4 15h16M10 5v14',
  findings: 'M5 20V11M12 20V4M19 20v-6',
  book: 'M5 4h8a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM16 7h3v13h-3',
  branch: 'M7 4v12M7 16a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM17 8c0 5-10 3-10 8',
  back: 'M19 12H5M11 6l-6 6 6 6',
  clock: 'M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM12 8v4l3 2',
  eye: 'M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  check: 'M5 12.5l4.5 4.5L19 7.5',
  pairs: 'M3 7h7v10H3zM14 7h7v10h-7zM10 12h4',
  leaveout: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM14 14l5 5M19 14l-5 5',
  funnel: 'M4 5h16l-6 7.5V18l-4 2v-7.5z',
  shuffle: 'M4 7h3l10 10h3M4 17h3L17 7h3M17 4l3 3-3 3M17 14l3 3-3 3',
}

export type IconName = keyof typeof PATHS

export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return <svg className="ico" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75"
    strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={PATHS[name]} /></svg>
}
