/* Simulaxon demo page: the typed lede, reveals, sticky columns that follow their text, the benchmark bars and the
   sideways traverse. Vanilla, no build. Scroll is the only clock for everything except the one-time typing. */
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Typed lede: once, at load; the whole line at once under reduced motion.
const typed = document.querySelector("[data-typed]");
if (typed) {
  const full = typed.dataset.typed, caret = typed.nextElementSibling;
  if (reduced) { typed.textContent = full; caret?.classList.add("done"); }
  else {
    let i = 0;
    const id = setInterval(() => { typed.textContent = full.slice(0, ++i); if (i >= full.length) { clearInterval(id); setTimeout(() => caret?.classList.add("done"), 1400); } }, 1000 / 40);
  }
}

// Reveals, and the benchmark bars growing to their values when seen.
const seen = new IntersectionObserver(es => es.forEach(e => {
  if (!e.isIntersecting) return;
  e.target.classList.add("in");
  e.target.querySelectorAll("[data-w]").forEach(b => { b.style.width = b.dataset.w; });
}), { threshold: 0.3 });
document.querySelectorAll(".reveal, .bars").forEach(el => seen.observe(el));

// Sticky columns: the frame shown is the last station whose top has passed 55% of the window.
const groups = Array.from(document.querySelectorAll(".stations")).map(g => ({
  stations: Array.from(g.querySelectorAll(".station")),
  frames: Array.from(g.querySelectorAll(".frames > *")),
  ticks: g.querySelector(".ticks"),
}));
for (const g of groups) if (g.ticks) g.frames.forEach(() => g.ticks.appendChild(document.createElement("i")));

// The traverse: vertical scroll through the tall track moves the strip sideways.
const track = document.querySelector(".traverse"), strip = track?.querySelector(".strip"), dots = track?.querySelector(".dots");
if (dots && strip) Array.from(strip.children).forEach(() => dots.appendChild(document.createElement("i")));

function frame() {
  const cut = innerHeight * 0.55;
  for (const g of groups) {
    let on = 0;
    g.stations.forEach((s, i) => { if (s.getBoundingClientRect().top <= cut) on = i; });
    g.stations.forEach((s, i) => s.classList.toggle("on", i === on));
    g.frames.forEach((f, i) => f.classList.toggle("on", i === on));
    if (g.ticks) Array.from(g.ticks.children).forEach((t, i) => t.classList.toggle("on", i === on));
  }
  if (track && strip && innerWidth > 820) {
    const r = track.getBoundingClientRect(), travel = track.offsetHeight - innerHeight;
    const p = Math.min(1, Math.max(0, -r.top / travel)), shift = Math.max(0, strip.scrollWidth - innerWidth);
    strip.style.transform = `translateX(${(-p * shift).toFixed(1)}px)`;
    const n = strip.children.length;
    Array.from(dots.children).forEach((d, i) => d.classList.toggle("on", i === Math.min(n - 1, Math.floor(p * n))));
  }
}
let queued = false;
addEventListener("scroll", () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; frame(); }); }, { passive: true });
addEventListener("resize", frame);
frame();
