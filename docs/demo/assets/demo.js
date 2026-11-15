/* Simulaxon demo page. From the Provinans case study: a fixed backdrop that crossfades to each chapter's tint, a
   grain over it, and scroll as the clock. From the HyperFrames film: every entrance and change eased with GSAP
   (power3.out rises, staggered sheets), and the brain areas drifting round the title. Plain script, no build. */
(() => {
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hasGsap = !!window.gsap;
  if (hasGsap) gsap.registerPlugin(ScrollTrigger);

  // Chapters' tints, all from the film's palette: warm charcoal, with one hue each at low strength.
  const DARK = { top: '#171614', bottom: '#100f0e', glow: 'rgba(243, 240, 234, 0.035)' };
  const BIOMES = { home: DARK, cost: DARK, develop: DARK, model: DARK, ciq: DARK, compute: DARK,
    paper: { top: '#f3f0ea', bottom: '#eeeae2', glow: 'rgba(255, 255, 255, 0)', light: true } };   // the one contrast block

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
  const AREAS = ['V1', 'MT', 'FFC', 'PH', 'STSv', 'V4', 'PGi', 'LO1', 'TE1a', 'V3A', 'RSC', 'PIT'];
    const host = document.querySelector('[data-glyphs]');
  if (host) {
    let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    AREAS.forEach((name, i) => {
      const s = document.createElement('span'); s.className = 'glyph'; s.textContent = name;
      const top = i % 2 ? 2 + rnd() * 12 : 84 + rnd() * 12;   // bands above and below the text, never across it
      s.style.left = (3 + Math.floor(i / 2) / 6 * 92 + rnd() * 3) + '%';   // evenly across each band, so no two names land together s.style.top = top + '%'; host.appendChild(s);
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
    else {
      // Hold the paragraph at its finished height while it types, so nothing below it moves.
      const box = typed.parentElement; typed.textContent = full; box.style.minHeight = box.offsetHeight + 'px'; typed.textContent = '';
      addEventListener('resize', () => { box.style.minHeight = ''; }, { once: true });
      let i = 0; const id = setInterval(() => { typed.textContent = full.slice(0, ++i); if (i >= full.length) { clearInterval(id); setTimeout(() => caret?.classList.add('done'), 1400); } }, 1000 / 40);
    }
  }

  // Entrances: the film's rise, played once as each block reaches the lower part of the window.
  if (hasGsap && !reduced) {
    document.querySelectorAll('.reveal').forEach(el => gsap.fromTo(el, { y: 40, opacity: 0 }, { y: 0, opacity: 1, duration: 0.7, ease: 'power3.out', scrollTrigger: { trigger: el, start: 'top 85%' } }));
    document.querySelectorAll('.bars').forEach(el => ScrollTrigger.create({ trigger: el, start: 'top 80%', once: true, onEnter: () =>
      el.querySelectorAll('[data-w]').forEach((b, i) => gsap.to(b, { width: b.dataset.w, duration: 1.1, ease: 'power3.out', delay: i * 0.12 })) }));
  } else document.querySelectorAll('[data-w]').forEach(b => { b.style.width = b.dataset.w; });

  // Sticky columns: the frame follows the station whose top has passed 55% of the window; frames change with the film's ease.
  const groups = Array.from(document.querySelectorAll('.stations')).map(g => ({ el: g, stations: [...g.querySelectorAll('.station')], frames: [...g.querySelectorAll('.frames > *')], ticks: g.querySelector('.ticks'), on: -1 }));
  for (const g of groups) if (g.ticks) (g.frames.length ? g.frames : g.stations).forEach(() => g.ticks.appendChild(document.createElement('i')));
  const show = (g, on) => {
    if (g.on === on) return; const was = g.on; g.on = on;
    g.stations.forEach((s, i) => s.classList.toggle('on', i === on));
    if (g.ticks) [...g.ticks.children].forEach((t, i) => t.classList.toggle('on', i === on));
    g.onStep?.(on);
    g.frames.forEach((f, i) => {
      if (!hasGsap || reduced) { f.style.opacity = i === on ? 1 : 0; return; }
      if (i === on) gsap.fromTo(f, { opacity: 0, y: 24, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: 'power3.out' });
      else if (i === was) gsap.to(f, { opacity: 0, y: -16, duration: 0.35, ease: 'power2.in' });
      else gsap.set(f, { opacity: 0 });
    });
  };

  // Runs on CIQ: the pinned deployment lights each step's services, and an arrowhead travels the round's route between them.
  // Points are in the diagram's own layout (offsets), so they hold when the diagram is scaled to fit the window.
  const arch = document.querySelector('[data-route]');
  if (arch) {
    const pin = arch.parentElement, dot = arch.querySelector('.ar-dot'), all = arch.querySelector('.ar-all'), done = arch.querySelector('.ar-done');
    const q = k => arch.querySelector(`[data-at="${k}"]`);
    const box = el => { let x = 0, y = 0; for (let e = el; e && e !== arch; e = e.offsetParent) { x += e.offsetLeft; y += e.offsetTop; } return { x, y, w: el.offsetWidth, h: el.offsetHeight }; };
    // x from one element (or the gap between the workstations), y from another.
    const pt = (xk, fx, yk = xk, fy = 0.5) => () => {
      const by = box(q(yk)), y = by.y + by.h * fy;
      if (xk === 'gap') { const a = box(q('ws1')), b = box(q('ws2')); return [(a.x + a.w + b.x) / 2, y]; }
      const bx = box(q(xk)); return [bx.x + bx.w * fx, y];
    };
    const STEPS = [
      { lit: ['app', 'nem'], via: [pt('app', 1, 'app', 0.3), pt('nem', 1, 'nem', 0.2)] },
      { lit: ['app', 'rs', 'ws2'], via: [pt('app', 1, 'app', 0.3), pt('gap', 0, 'app', 0.3), pt('gap', 0, 'isaac'), pt('rs', 0, 'isaac')] },
      { lit: ['isaac'], via: [pt('isaac', 0)] },
      { lit: ['cosmos'], via: [pt('cosmos', 0)] },
      { lit: ['tribe', 'vjepa'], via: [pt('tribe', 0)] },
      { lit: ['nem'], via: [pt('gap', 0, 'tribe'), pt('gap', 0, 'nem', 0.2), pt('nem', 1, 'nem', 0.2)] },
      { lit: ['app', 'fuzz'], via: [pt('app', 1, 'app', 0.3), pt('gap', 0, 'app', 0.3), pt('gap', 0, 'fuzz', 1)] },
      { lit: ['vast'], via: [pt('gap', 0, 'vast', 0)] },
    ];
    const via = STEPS.flatMap(s => s.via), ends = []; STEPS.reduce((n, s) => (ends.push(n + s.via.length - 1), n + s.via.length), 0);
    let pts = [], cum = [], cur = 0;
    const EASE = 'cubic-bezier(0.645, 0.045, 0.355, 1)';
    const angle = (i, dir) => { const j = i - dir; if (j < 0 || j >= pts.length) return dir > 0 ? 0 : 180; const a = pts[j], b = pts[i]; return Math.hypot(b[0] - a[0], b[1] - a[1]) < 0.5 ? angle(j, dir) : Math.atan2(b[1] - a[1], b[0] - a[0]) * 180 / Math.PI; };
    const at = (p, deg) => `translate(${p[0].toFixed(1)}px, ${p[1].toFixed(1)}px) rotate(${deg.toFixed(1)}deg)`;
    let heading = 0;
    const place = (p, deg = heading) => { heading = deg; dot.style.transform = at(p, deg); };
    const light = k => {
      const lit = new Set(STEPS[k].lit); arch.classList.add('routed');
      arch.querySelectorAll('[data-at]').forEach(el => { el.classList.toggle('on', lit.has(el.dataset.at)); el.classList.remove('held'); });
      arch.querySelectorAll('[data-at].on').forEach(el => { for (let p = el.parentElement.closest('[data-at]'); p; p = p.parentElement.closest('[data-at]')) p.classList.add('held'); });
    };
    function layout() {
      arch.style.transform = ''; arch.style.marginBottom = '';
      if (innerWidth > 820) {   // fit the whole diagram in the pinned column
        const room = pin.clientHeight - (pin.querySelector('.ticks')?.offsetHeight || 0) - 28, h = arch.offsetHeight, s = Math.min(1, room / h);
        if (s < 1) { arch.style.transform = `scale(${s.toFixed(3)})`; arch.style.marginBottom = `${(-(1 - s) * h).toFixed(1)}px`; }
      }
      pts = via.map(f => f()); cum = [0];
      for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]));
      const line = pts.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ');
      all.setAttribute('points', line); done.setAttribute('points', line);
      const L = cum[cum.length - 1]; done.style.transition = 'none'; done.style.strokeDasharray = `${L} ${L}`; done.style.strokeDashoffset = L - cum[ends[cur]];
      dot.getAnimations().forEach(a => a.cancel()); place(pts[ends[cur]], angle(ends[cur], 1));
    }
    function go(k) {
      const from = ends[cur], to = ends[k]; cur = k; light(k);
      const L = cum[cum.length - 1], dist = Math.abs(cum[to] - cum[from]);
      if (reduced || !dist) { done.style.transition = 'none'; done.style.strokeDashoffset = L - cum[to]; place(pts[to], angle(to, 1)); return; }
      const dur = Math.min(900, Math.max(320, dist * 2.2)), step = to > from ? 1 : -1, frames = [];
      for (let i = from; ; i += step) { const deg = i === from ? heading : angle(i, step); frames.push({ transform: at(pts[i], deg), offset: Math.abs(cum[i] - cum[from]) / dist }); if (i === to) break; }
      dot.getAnimations().forEach(a => a.cancel()); place(pts[to], angle(to, step));
      dot.animate(frames, { duration: dur, easing: EASE });
      done.style.transition = `stroke-dashoffset ${dur}ms ${EASE}`; done.style.strokeDashoffset = L - cum[to];
    }
    const g = groups.find(x => x.el === arch.closest('.stations'));
    if (g) g.onStep = k => go(Math.min(k, STEPS.length - 1));
    layout(); light(0);
    addEventListener('resize', layout);
    if ('fonts' in document) document.fonts.ready.then(layout);
    addEventListener('load', layout);
    // The chapter's clips play only while on screen, and not at all under reduced motion.
    const vids = [...document.querySelectorAll('.ciq video')];
    if (reduced) vids.forEach(v => { v.removeAttribute('autoplay'); v.pause(); v.controls = !v.closest('.crop'); });
    else { const vo = new IntersectionObserver(es => es.forEach(e => e.isIntersecting ? e.target.play().catch(() => {}) : e.target.pause())); vids.forEach(v => vo.observe(v)); }
  }

  // Develop the experiment: the section pins and vertical scroll moves the track sideways, one panel per step.
  const hs = document.querySelector('.hscroll');
  if (hs && hasGsap && !reduced) {
    const track = hs.querySelector('.hs-track'), ticks = [...hs.querySelectorAll('.hs-ticks i')], n = ticks.length;
    const mm = gsap.matchMedia();
    mm.add('(min-width: 821px)', () => {
      const dist = () => Math.max(0, track.scrollWidth - innerWidth);
      gsap.to(track, { x: () => -dist(), ease: 'none', scrollTrigger: { trigger: hs, pin: hs.querySelector('.hs-pin'), start: 'top top', end: () => '+=' + dist(), scrub: 0.6, invalidateOnRefresh: true,
        onUpdate: st => { const k = Math.round(st.progress * (n - 1)); ticks.forEach((t, i) => t.classList.toggle('on', i === k)); } } });
    });
    addEventListener('load', () => ScrollTrigger.refresh());
  }

  function frame() {
    const cut = innerHeight * 0.55;
    for (const g of groups) { let on = 0; g.stations.forEach((s, i) => { if (s.getBoundingClientRect().top <= cut) on = i; }); show(g, on); }
  }
  let queued = false;
  addEventListener('scroll', () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; frame(); }); }, { passive: true });
  addEventListener('resize', frame);
  frame();
})();
