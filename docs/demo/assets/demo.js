/* Simulaxon demo page. From the Provinans case study: a fixed backdrop that crossfades to each chapter's tint, a
   grain over it, and scroll as the clock. From the HyperFrames film: every entrance and change eased with GSAP
   (power3.out rises, staggered sheets), and the brain areas drifting round the title. Plain script, no build. */
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hasGsap = !!window.gsap;
  if (hasGsap) gsap.registerPlugin(ScrollTrigger);

  // Chapters' tints, all from the film's palette: warm charcoal, with one hue each at low strength.
  const BIOMES = {
    home: { top: '#191714', bottom: '#0f0e0d', glow: 'rgba(181, 222, 43, 0.10)' },     // the accent
    cost: { top: '#1a1816', bottom: '#100f0d', glow: 'rgba(243, 240, 234, 0.07)' },    // ivory
    develop: { top: '#141719', bottom: '#0d0e0f', glow: 'rgba(46, 140, 176, 0.14)' },  // series two
    model: { top: '#1a1413', bottom: '#0f0d0c', glow: 'rgba(179, 38, 30, 0.14)' },     // the brain's ramp
    paper: { top: '#f3f0ea', bottom: '#e9e3d8', glow: 'rgba(127, 160, 28, 0.10)', light: true },   // the one ivory chapter
    ciq: { top: '#151813', bottom: '#0d0e0c', glow: 'rgba(127, 160, 28, 0.13)' },      // series one
    compute: { top: '#14161a', bottom: '#0d0e10', glow: 'rgba(46, 140, 176, 0.11)' },
  };
  const layers = [document.getElementById('backdrop-a'), document.getElementById('backdrop-b')];
  let front = 0, current = '';
  const paint = (el, b) => { el.style.setProperty('--l-top', b.top); el.style.setProperty('--l-bottom', b.bottom); el.style.setProperty('--l-glow', b.glow); };
  function biome(name) {
    if (name === current || !BIOMES[name]) return; current = name; const b = BIOMES[name];
    document.body.classList.toggle('light', !!b.light);
    front = 1 - front; paint(layers[front], b); layers[front].classList.add('active'); layers[1 - front].classList.remove('active');
  }
  paint(layers[0], BIOMES.home); layers[0].classList.add('active'); current = 'home';
  const bo = new IntersectionObserver(es => es.forEach(e => e.isIntersecting && biome(e.target.dataset.biome)), { rootMargin: '-45% 0px -45% 0px' });
  document.querySelectorAll('[data-biome]').forEach(s => bo.observe(s));

  // Brain areas drifting round the title, as on the film's title card. Seeded, so the layout is the same each load.
  const AREAS = ['V1', 'V2', 'V3', 'V4', 'MT', 'MST', 'FFC', 'PH', 'PHA1', 'VVC', 'STSv', 'PGi', 'TE1a', 'A5', '45', 'V4t', 'IPS1', 'LO1', 'LO2', 'V3A', 'V6', 'PIT', 'RSC', 'TPOJ1'];
  const HOT = new Set(['FFC', 'PH', 'MT']);
  const host = document.querySelector('[data-glyphs]');
  if (host) {
    let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    AREAS.forEach((name, i) => {
      const s = document.createElement('span'); s.className = 'glyph' + (HOT.has(name) ? ' hot' : ''); s.textContent = name;
      const top = i % 2 ? 2 + rnd() * 12 : 84 + rnd() * 12;   // bands above and below the text, never across it
      s.style.left = (3 + Math.floor(i / 2) / 12 * 92 + rnd() * 3) + '%';   // evenly across each band, so no two names land together s.style.top = top + '%'; host.appendChild(s);
      if (hasGsap && !reduced) {
        gsap.fromTo(s, { opacity: 0, y: 24 }, { opacity: 1, y: 0, duration: 1.4, ease: 'power3.out', delay: 0.1 + i * 0.05 });
        gsap.to(s, { x: (rnd() - 0.5) * 80, y: (rnd() - 0.5) * 16, duration: 9 + rnd() * 6, ease: 'sine.inOut', yoyo: true, repeat: -1, delay: 1.5 });
      }
    });
  }

  // Typed lede, once at load.
  const typed = document.querySelector('[data-typed]');
  if (typed) {
    const full = typed.dataset.typed, caret = typed.nextElementSibling;
    if (reduced) { typed.textContent = full; caret?.classList.add('done'); }
    else { let i = 0; const id = setInterval(() => { typed.textContent = full.slice(0, ++i); if (i >= full.length) { clearInterval(id); setTimeout(() => caret?.classList.add('done'), 1400); } }, 1000 / 40); }
  }

  // Entrances: the film's rise, played once as each block reaches the lower part of the window.
  if (hasGsap && !reduced) {
    document.querySelectorAll('.reveal').forEach(el => gsap.fromTo(el, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 85%' } }));
    document.querySelectorAll('.bars').forEach(el => ScrollTrigger.create({ trigger: el, start: 'top 80%', once: true, onEnter: () =>
      el.querySelectorAll('[data-w]').forEach((b, i) => gsap.to(b, { width: b.dataset.w, duration: 1.1, ease: 'power3.out', delay: i * 0.12 })) }));
  } else document.querySelectorAll('[data-w]').forEach(b => { b.style.width = b.dataset.w; });

  // Sticky columns: the frame follows the station whose top has passed 55% of the window; frames change with the film's ease.
  const groups = Array.from(document.querySelectorAll('.stations')).map(g => ({ stations: [...g.querySelectorAll('.station')], frames: [...g.querySelectorAll('.frames > *')], ticks: g.querySelector('.ticks'), on: -1 }));
  for (const g of groups) if (g.ticks) g.frames.forEach(() => g.ticks.appendChild(document.createElement('i')));
  const show = (g, on) => {
    if (g.on === on) return; const was = g.on; g.on = on;
    g.stations.forEach((s, i) => s.classList.toggle('on', i === on));
    if (g.ticks) [...g.ticks.children].forEach((t, i) => t.classList.toggle('on', i === on));
    g.frames.forEach((f, i) => {
      if (!hasGsap || reduced) { f.style.opacity = i === on ? 1 : 0; return; }
      if (i === on) gsap.fromTo(f, { opacity: 0, y: 24, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: 'power3.out' });
      else if (i === was) gsap.to(f, { opacity: 0, y: -16, duration: 0.35, ease: 'power2.in' });
      else gsap.set(f, { opacity: 0 });
    });
  };

  // The traverse: vertical scroll through the tall track moves the pipeline sideways.
  const track = document.querySelector('.traverse'), strip = track?.querySelector('.strip'), dots = track?.querySelector('.dots');
  if (dots && strip) [...strip.children].forEach(() => dots.appendChild(document.createElement('i')));

  function frame() {
    const cut = innerHeight * 0.55;
    for (const g of groups) { let on = 0; g.stations.forEach((s, i) => { if (s.getBoundingClientRect().top <= cut) on = i; }); show(g, on); }
    if (track && strip && innerWidth > 820) {
      const r = track.getBoundingClientRect(), travel = track.offsetHeight - innerHeight;
      const p = Math.min(1, Math.max(0, -r.top / travel)), shift = Math.max(0, strip.scrollWidth - innerWidth);
      strip.style.transform = `translateX(${(-p * shift).toFixed(1)}px)`;
      const n = strip.children.length; [...dots.children].forEach((d, i) => d.classList.toggle('on', i === Math.min(n - 1, Math.floor(p * n))));
    }
  }
  let queued = false;
  addEventListener('scroll', () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; frame(); }); }, { passive: true });
  addEventListener('resize', frame);
  frame();
})();
