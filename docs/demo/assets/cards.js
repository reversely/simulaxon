/* The film's cards (~/Repos/film/videos/simulaxon-demo/index.html), live on the page: the same markup, eases and
   timings, each a paused GSAP timeline that plays when its card scrolls into view and replays when it comes back. */
(() => {
  if (!window.gsap) return;
  gsap.registerPlugin(ScrollTrigger);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const local = (root, el, fx = 0.5, fy = 0.5) => { const R = root.getBoundingClientRect(), b = el.getBoundingClientRect(); return { x: b.left - R.left + b.width * fx, y: b.top - R.top + b.height * fy }; };
  const press = (tl, cursor, t) => tl.fromTo(cursor, { scale: 1 }, { scale: 0.86, duration: 0.07, yoyo: true, repeat: 1, transformOrigin: '3px 2px' }, t);
  const rise = (tl, root, t) => {
    tl.fromTo(root.querySelector('.fc-card'), { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out' }, t);
    tl.fromTo(root.querySelectorAll('.fc-sheet'), { y: 60, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out', stagger: -0.05 }, t + 0.05);
  };

  // Scan cost: the cursor drags participants from 1 to 20; the total rolls with it ($710 an hour).
  function cost(root) {
    const tl = gsap.timeline({ paused: true }), cursor = root.querySelector('.fc-cursor');
    const track = root.querySelector('.fc-track'), knob = root.querySelector('.fc-knob'), fill = root.querySelector('.fc-fill');
    const nEl = root.querySelector('[data-n]'), totalEl = root.querySelector('[data-total]');
    const n = { v: 1 };
    const paint = () => { const W = track.getBoundingClientRect().width, p = (n.v - 1) / 19, people = Math.round(n.v);
      nEl.textContent = people; totalEl.textContent = '$' + (people * 710).toLocaleString('en-US'); gsap.set(fill, { scaleX: p }); gsap.set(knob, { x: p * W }); };
    rise(tl, root, 0);
    tl.call(() => { n.v = 1; paint(); }, null, 0);
    tl.add(() => {}, 0.6);
    const k = () => local(root, knob);
    tl.fromTo(cursor, { opacity: 0, x: () => k().x + 220, y: () => k().y + 150 }, { opacity: 1, x: () => k().x - 4, y: () => k().y - 2, duration: 0.6, ease: 'power2.inOut' }, 0.6);
    press(tl, cursor, 1.22);
    tl.fromTo(n, { v: 1 }, { v: 20, duration: 1.8, ease: 'power1.inOut', onUpdate: paint }, 1.3);
    tl.to(cursor, { x: () => k().x - 4 + track.getBoundingClientRect().width, duration: 1.8, ease: 'power1.inOut' }, 1.3);
    press(tl, cursor, 3.12);
    tl.to(cursor, { x: '+=120', y: '+=100', opacity: 0, duration: 0.6, ease: 'power2.in' }, 3.9);
    paint();
    return tl;
  }

  // Adapter: one click fits; the adapter's bar rolls to 0.407 beside TRIBE v2's 0.257, under the 0.675 ceiling.
  function adapter(root) {
    const tl = gsap.timeline({ paused: true }), cursor = root.querySelector('.fc-cursor'), btn = root.querySelector('.fc-btn');
    const [b0, b1, b2] = root.querySelectorAll('.fc-btn span'), fit = root.querySelector('[data-fit]'), fitN = root.querySelector('[data-fit-n]'), chip = root.querySelector('.fc-chip');
    gsap.set(root.querySelector('[data-tribe]'), { scaleX: 0.257 });
    rise(tl, root, 0);
    tl.set([b1, b2, chip], { opacity: 0 }, 0); tl.set(b0, { opacity: 1 }, 0); tl.set(fit, { scaleX: 0 }, 0); tl.call(() => { fitN.textContent = '0.000'; }, null, 0);
    const b = () => local(root, btn, 0.35, 0.6);
    tl.fromTo(cursor, { opacity: 0, x: () => b().x + 200, y: () => b().y + 180 }, { opacity: 1, x: () => b().x, y: () => b().y, duration: 0.7, ease: 'power2.inOut' }, 0.6);
    press(tl, cursor, 1.32);
    tl.fromTo(btn, { scale: 1 }, { scale: 0.97, duration: 0.08, yoyo: true, repeat: 1 }, 1.32);
    tl.to(b0, { opacity: 0, duration: 0.1 }, 1.4); tl.to(b1, { opacity: 1, duration: 0.1 }, 1.4);
    tl.to(b1, { opacity: 0, duration: 0.1 }, 2.7); tl.to(b2, { opacity: 1, duration: 0.1 }, 2.7);
    const f = { v: 0 };
    tl.fromTo(f, { v: 0 }, { v: 0.407, duration: 1.0, ease: 'power2.out', onUpdate() { fitN.textContent = f.v.toFixed(3); gsap.set(fit, { scaleX: f.v }); } }, 2.5);
    tl.to(chip, { opacity: 1, duration: 0.3 }, 3.5);
    tl.to(cursor, { x: '+=140', y: '+=120', opacity: 0, duration: 0.6, ease: 'power2.in' }, 3.9);
    return tl;
  }

  // Two workstations: each message travels its route, and the round's files land on VAST.
  function workstations(root) {
    const tl = gsap.timeline({ paused: true }), dot = root.querySelector('.fc-dot');
    const pt = (sel, fx = 0.5, fy = 0.5) => { const p = local(root, root.querySelector(sel), fx, fy); return { x: p.x - 7, y: p.y - 7 }; };
    tl.fromTo(root.querySelectorAll('.fc-ws, .fc-vast'), { y: 50, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out', stagger: 0.08 }, 0);
    tl.set(root.querySelectorAll('.fc-svc, .fc-vast'), { borderColor: '#3a352f' }, 0);
    const hop = (from, to, t, tag, dur = 0.7) => {
      tl.fromTo(dot, { x: () => from().x, y: () => from().y, opacity: 1 }, { x: () => to().x, y: () => to().y, opacity: 1, duration: dur, ease: 'power2.inOut', immediateRender: false }, t);
      const tg = root.querySelector(tag);
      tl.fromTo(tg, { x: () => (from().x + to().x) / 2 - 70, y: () => Math.min(from().y, to().y) - 30, opacity: 0 }, { opacity: 1, duration: 0.2, immediateRender: false }, t);
      tl.to(tg, { opacity: 0, duration: 0.2 }, t + dur + 0.25);
    };
    hop(() => ({ x: -60, y: pt('[data-svc=nem]').y }), () => pt('[data-svc=nem]', 0.04), 0.9, '[data-tag="1"]');
    tl.to('[data-svc=nem]', { borderColor: '#b5de2b', duration: 0.2 }, 1.5);
    hop(() => pt('[data-svc=app]', 0.96), () => pt('[data-svc=isaac]', 0.04), 1.9, '[data-tag="2"]');
    tl.to(root.querySelector('[data-svc=isaac]'), { borderColor: '#b5de2b', duration: 0.2 }, 2.65);
    tl.to(root.querySelector('[data-svc=cosmos]'), { borderColor: '#b5de2b', duration: 0.2 }, 3.05);
    tl.to(root.querySelector('[data-svc=tribe]'), { borderColor: '#b5de2b', duration: 0.2 }, 3.45);
    hop(() => pt('[data-svc=tribe]', 0.04), () => pt('[data-svc=nem]', 0.96), 4.1, '[data-tag="3"]', 0.8);
    hop(() => pt('[data-svc=tribe]', 0.5, 1), () => pt('.fc-vast', 0.7, 0.2), 5.1, '[data-tag="4"]', 0.6);
    tl.to(root.querySelector('.fc-vast'), { borderColor: '#b5de2b', duration: 0.2 }, 5.7);
    tl.to(dot, { opacity: 0, duration: 0.2 }, 5.8);
    return tl;
  }

  const builders = { cost, adapter, workstations };
  document.querySelectorAll('[data-card]').forEach(root => {
    const tl = builders[root.dataset.card](root);
    if (reduced) { tl.progress(1); return; }
    ScrollTrigger.create({ trigger: root, start: 'top 75%', end: 'bottom 15%', onEnter: () => tl.restart(), onEnterBack: () => tl.restart() });
  });
})();
