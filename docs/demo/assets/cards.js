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

  // Scan time: the cursor drags participants from 1 to 20; the scanner hours roll with it (one hour each).
  function cost(root) {
    const tl = gsap.timeline({ paused: true }), cursor = root.querySelector('.fc-cursor');
    const track = root.querySelector('.fc-track'), knob = root.querySelector('.fc-knob'), fill = root.querySelector('.fc-fill');
    const nEl = root.querySelector('[data-n]'), totalEl = root.querySelector('[data-total]');
    const n = { v: 1 };
    const paint = () => { const W = track.getBoundingClientRect().width, p = (n.v - 1) / 19, people = Math.round(n.v);
      nEl.textContent = people; totalEl.textContent = people + ' h'; gsap.set(fill, { scaleX: p }); gsap.set(knob, { x: p * W }); };
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

  // Adapter: one click fits; bars are shares of the 0.675 noise ceiling, the adapter's rolling to 60% beside TRIBE v2's 38%.
  function adapter(root) {
    const tl = gsap.timeline({ paused: true }), cursor = root.querySelector('.fc-cursor'), btn = root.querySelector('.fc-btn');
    const [b0, b1, b2] = root.querySelectorAll('.fc-btn span'), fit = root.querySelector('[data-fit]'), fitN = root.querySelector('[data-fit-n]'), chip = root.querySelector('.fc-chip');
    const CEIL = 0.675;
    gsap.set(root.querySelector('[data-tribe]'), { scaleX: 0.257 / CEIL });
    rise(tl, root, 0);
    tl.set([b1, b2, chip], { opacity: 0 }, 0); tl.set(b0, { opacity: 1 }, 0); tl.set(fit, { scaleX: 0 }, 0); tl.call(() => { fitN.textContent = '0%'; }, null, 0);
    const b = () => local(root, btn, 0.35, 0.6);
    tl.fromTo(cursor, { opacity: 0, x: () => b().x + 200, y: () => b().y + 180 }, { opacity: 1, x: () => b().x, y: () => b().y, duration: 0.7, ease: 'power2.inOut' }, 0.6);
    press(tl, cursor, 1.32);
    tl.fromTo(btn, { scale: 1 }, { scale: 0.97, duration: 0.08, yoyo: true, repeat: 1 }, 1.32);
    tl.to(b0, { opacity: 0, duration: 0.1 }, 1.4); tl.to(b1, { opacity: 1, duration: 0.1 }, 1.4);
    tl.to(b1, { opacity: 0, duration: 0.1 }, 2.7); tl.to(b2, { opacity: 1, duration: 0.1 }, 2.7);
    const f = { v: 0 };
    tl.fromTo(f, { v: 0 }, { v: 0.407, duration: 1.0, ease: 'power2.out', onUpdate() { fitN.textContent = Math.round(100 * f.v / CEIL) + '%'; gsap.set(fit, { scaleX: f.v / CEIL }); } }, 2.5);
    tl.to(chip, { opacity: 1, duration: 0.3 }, 3.5);
    tl.to(cursor, { x: '+=140', y: '+=120', opacity: 0, duration: 0.6, ease: 'power2.in' }, 3.9);
    return tl;
  }

  const builders = { cost, adapter };
  document.querySelectorAll('[data-card]').forEach(root => {
    const tl = builders[root.dataset.card](root);
    if (reduced) { tl.progress(1); return; }
    ScrollTrigger.create({ trigger: root, start: 'top 75%', end: 'bottom 15%', onEnter: () => tl.restart(), onEnterBack: () => tl.restart() });
  });
})();
