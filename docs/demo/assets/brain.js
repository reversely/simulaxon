/* The app's brain view (frontend/src/brain3d.tsx), ported to plain JavaScript for the demo page: fsaverage5 in
   WebGL2, coloured per vertex by TRIBE v2's prediction second by second, turning slowly, with the clip on one clock.
   Colours follow the app: a single map normalised at its 1st and 99th percentiles, coloured above 0.6 of that range. */
(() => {
  const b64 = s => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u.buffer; };

  function normals(pos, faces) {
    const out = new Float32Array(pos.length);
    for (let f = 0; f < faces.length; f += 3) {
      const a = faces[f] * 3, b = faces[f + 1] * 3, c = faces[f + 2] * 3;
      const ux = pos[b] - pos[a], uy = pos[b + 1] - pos[a + 1], uz = pos[b + 2] - pos[a + 2];
      const vx = pos[c] - pos[a], vy = pos[c + 1] - pos[a + 1], vz = pos[c + 2] - pos[a + 2];
      const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
      for (const i of [a, b, c]) { out[i] += nx; out[i + 1] += ny; out[i + 2] += nz; }
    }
    for (let i = 0; i < out.length; i += 3) { const l = Math.hypot(out[i], out[i + 1], out[i + 2]) || 1; out[i] /= l; out[i + 1] /= l; out[i + 2] /= l; }
    return out;
  }

  function parseMesh(buf) {
    const dv = new DataView(buf), hl = dv.getUint32(0, true);
    const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, hl))), base = 4 + hl;
    const arr = k => { const a = head.arrays[k], len = a.shape.reduce((x, y) => x * y, 1);
      return a.dtype === 'i2' ? new Int16Array(buf, base + a.offset, len) : a.dtype === 'u2' ? new Uint16Array(buf, base + a.offset, len) : new Uint8Array(buf, base + a.offset, len); };
    const mm = a => Float32Array.from(a, v => v / head.scale);
    const pial = mm(arr('pial')), infl = mm(arr('infl')), faces = new Uint16Array(arr('faces'));
    let radius = 0;
    for (let i = 0; i < pial.length; i += 3) radius = Math.max(radius, Math.hypot(pial[i], pial[i + 1], pial[i + 2]), Math.hypot(infl[i], infl[i + 1], infl[i + 2]));
    return { n: head.n, pial, infl, nPial: normals(pial, faces), nInfl: normals(infl, faces), sulc: Float32Array.from(arr('sulc'), v => v / 255), faces, radius };
  }

  let F16 = null;
  function f16() {
    if (F16) return F16; F16 = new Float32Array(65536);
    for (let h = 0; h < 65536; h++) { const s = h & 0x8000 ? -1 : 1, e = (h >> 10) & 31, f = h & 1023;
      F16[h] = e === 0 ? s * 2 ** -14 * (f / 1024) : e === 31 ? (f ? NaN : s * Infinity) : s * 2 ** (e - 15) * (1 + f / 1024); }
    return F16;
  }
  function parseNpy(buf) {
    const u8 = new Uint8Array(buf), dv = new DataView(buf), major = u8[6];
    const hl = major === 1 ? dv.getUint16(8, true) : dv.getUint32(8, true), off = major === 1 ? 10 : 12;
    const header = new TextDecoder().decode(u8.subarray(off, off + hl));
    const descr = /'descr':\s*'([^']+)'/.exec(header)[1];
    const shape = /'shape':\s*\(([^)]*)\)/.exec(header)[1].split(',').map(x => x.trim()).filter(Boolean).map(Number);
    const n = shape.reduce((a, b) => a * b, 1), start = off + hl;
    let data;
    if (descr === '<f2') { const t = f16(), h = new Uint16Array(buf.slice(start, start + 2 * n)); data = new Float32Array(n); for (let i = 0; i < n; i++) data[i] = t[h[i]]; }
    else if (descr === '<f4') data = new Float32Array(buf.slice(start, start + 4 * n));
    else data = Float32Array.from(new Float64Array(buf.slice(start, start + 8 * n)));
    const s = Array.from(data.filter(Number.isFinite)).sort((a, b) => a - b), q = p => s[Math.round(p * (s.length - 1))];
    return { rows: shape[0], n: shape[1], data, lo: q(0.01), hi: q(0.99) };
  }

  const RAMPS = { single: [[0, '#2a2b2e'], [0.45, '#b3261e'], [0.75, '#ff8c1a'], [1, '#fff2a8']],
    signed: [[0, '#4fd0ff'], [0.3, '#1a6bb0'], [0.5, '#2a2b2e'], [0.7, '#b3261e'], [1, '#ffd23f']] };   // the app's legend ramps
  function rampPixels(stops) {
    const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)), px = new Uint8Array(256 * 4);
    for (let i = 0; i < 256; i++) { const x = i / 255; let j = 0; while (j < stops.length - 2 && x > stops[j + 1][0]) j++;
      const [x0, c0] = stops[j], [x1, c1] = stops[j + 1], t = Math.min(1, Math.max(0, (x - x0) / (x1 - x0))), a = rgb(c0), b = rgb(c1);
      for (let c = 0; c < 3; c++) px[i * 4 + c] = Math.round(a[c] + (b[c] - a[c]) * t); px[i * 4 + 3] = 255; }
    return px;
  }

  const VS = `#version 300 es
in vec3 aPial; in vec3 aInfl; in vec3 aNPial; in vec3 aNInfl; in float aSulc; in float aVal;
uniform mat4 uProj; uniform mat4 uView; uniform float uMix;
out vec3 vN; out float vSulc; out float vVal;
void main() { vec3 p = mix(aPial, aInfl, uMix); vN = mat3(uView) * normalize(mix(aNPial, aNInfl, uMix)); vSulc = aSulc; vVal = aVal; gl_Position = uProj * uView * vec4(p, 1.0); }`;
  const FS = `#version 300 es
precision highp float;
in vec3 vN; in float vSulc; in float vVal; uniform sampler2D uRamp; uniform int uSigned; out vec4 o;
void main() {
  vec3 n = normalize(vN); if (!gl_FrontFacing) n = -n;
  float light = 0.38 + 0.62 * max(dot(n, normalize(vec3(0.25, 0.35, 1.0))), 0.0);
  vec3 base = vec3(mix(0.74, 0.36, vSulc));
  float c; float a;
  if (uSigned == 1) { c = 0.5 + 0.5 * clamp(vVal, -1.0, 1.0); a = clamp(abs(vVal) / 0.35 - 0.15, 0.0, 1.0); }
  else { c = clamp((vVal - 0.6) / 0.4, 0.0, 1.0); a = clamp(c / 0.2, 0.0, 1.0); }
  o = vec4(mix(base, texture(uRamp, vec2(c, 0.5)).rgb, a) * light, 1.0);
}`;
  function persp(fovy, aspect, near, far) { const f = 1 / Math.tan(fovy / 2), nf = 1 / (near - far);
    return new Float32Array([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0]); }
  function lookAt(e, up) {
    const l = Math.hypot(...e), z = e.map(v => v / l);
    const xr = [up[1] * z[2] - up[2] * z[1], up[2] * z[0] - up[0] * z[2], up[0] * z[1] - up[1] * z[0]], xl = Math.hypot(...xr) || 1, x = xr.map(v => v / xl);
    const y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]], d = a => -(a[0] * e[0] + a[1] * e[1] + a[2] * e[2]);
    return new Float32Array([x[0], y[0], z[0], 0, x[1], y[1], z[1], 0, x[2], y[2], z[2], 0, d(x), d(y), d(z), 1]);
  }

  class Brain {
    constructor(canvas, mesh, signed = false) {
      this.signed = signed;
      const gl = canvas.getContext('webgl2', { antialias: true, alpha: true, premultipliedAlpha: false });
      if (!gl) throw new Error('WebGL2 is off in this browser');
      this.gl = gl; this.canvas = canvas; this.mesh = mesh; this.mix = 0.5; this.yaw = 160; this.pitch = 16;
      const sh = (t, s) => { const x = gl.createShader(t); gl.shaderSource(x, s); gl.compileShader(x); if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
      const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p); this.prog = p;
      const attr = (name, data, size, usage = gl.STATIC_DRAW) => { const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, usage);
        const loc = gl.getAttribLocation(p, name); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, size, gl.FLOAT, false, 0, 0); return b; };
      this.vao = gl.createVertexArray(); gl.bindVertexArray(this.vao);
      attr('aPial', mesh.pial, 3); attr('aInfl', mesh.infl, 3); attr('aNPial', mesh.nPial, 3); attr('aNInfl', mesh.nInfl, 3); attr('aSulc', mesh.sulc, 1);
      this.vals = new Float32Array(mesh.n); this.val = attr('aVal', this.vals, 1, gl.DYNAMIC_DRAW);
      const ib = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ib); gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.faces, gl.STATIC_DRAW); gl.bindVertexArray(null);
      this.ramp = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, this.ramp); gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, rampPixels(RAMPS[signed ? 'signed' : 'single']));
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    }
    show(preds, t) {   // one moment of a prediction, rows interpolated at t seconds
      const r = Math.min(preds.rows - 1, Math.max(0, t)), i0 = Math.floor(r), i1 = Math.min(preds.rows - 1, i0 + 1), f = r - i0, span = preds.hi - preds.lo || 1;
      for (let v = 0; v < preds.n; v++) { const x = preds.data[i0 * preds.n + v] * (1 - f) + preds.data[i1 * preds.n + v] * f; this.vals[v] = Number.isFinite(x) ? Math.min(1, Math.max(0, (x - preds.lo) / span)) : 0; }
      const gl = this.gl; gl.bindBuffer(gl.ARRAY_BUFFER, this.val); gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.vals);
    }
    showMap(values, vmax) {   // one signed map, scaled by vmax as the app scales a contrast
      for (let v = 0; v < values.length; v++) this.vals[v] = Number.isFinite(values[v]) ? values[v] / vmax : 0;
      const gl = this.gl; gl.bindBuffer(gl.ARRAY_BUFFER, this.val); gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.vals);
    }
    draw() {
      const gl = this.gl, c = this.canvas, dpr = Math.min(2, devicePixelRatio || 1);
      const w = Math.max(1, Math.round(c.clientWidth * dpr)), h = Math.max(1, Math.round(c.clientHeight * dpr)); if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
      gl.viewport(0, 0, w, h); gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT); gl.enable(gl.DEPTH_TEST);
      const R = this.mesh.radius * 1.05, fov = 0.5, dist = R / Math.sin(fov / 2) * (w < h ? h / w : 1) * 0.8;
      const y = this.yaw * Math.PI / 180, p = this.pitch * Math.PI / 180;
      const view = lookAt([dist * Math.cos(p) * Math.cos(y), dist * Math.cos(p) * Math.sin(y), dist * Math.sin(p)], [0, 0, 1]);
      const proj = persp(fov, w / h, Math.max(1, dist - R * 1.6), dist + R * 1.6);
      gl.useProgram(this.prog); gl.bindVertexArray(this.vao);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.prog, 'uProj'), false, proj); gl.uniformMatrix4fv(gl.getUniformLocation(this.prog, 'uView'), false, view);
      gl.uniform1f(gl.getUniformLocation(this.prog, 'uMix'), this.mix); gl.uniform1i(gl.getUniformLocation(this.prog, 'uSigned'), this.signed ? 1 : 0);
      gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.ramp); gl.uniform1i(gl.getUniformLocation(this.prog, 'uRamp'), 0);
      gl.drawElements(gl.TRIANGLES, this.mesh.faces.length, gl.UNSIGNED_SHORT, 0); gl.bindVertexArray(null);
    }
  }

  const npy1 = s => { const p = parseNpy(b64(s)); return p.data; };   // a single map of 20,484 values

  // The adapter's map, large: where on the cortex each model predicts measured fMRI. Buttons switch the map.
  function maps() {
    const host = document.querySelector('[data-brain-map]'); if (!host || !window.BRAIN_DATA) return;
    let brain; try { brain = new Brain(host.querySelector('canvas'), mesh(), true); } catch (e) { host.classList.add('nogl'); return; }
    const M = { adapter_r: [npy1(BRAIN_DATA.adapter_r), 0.8], tribe_v2_r: [npy1(BRAIN_DATA.tribe_v2_r), 0.8], gain: [npy1(BRAIN_DATA.gain), 0.4] };
    const legend = host.querySelector('[data-legend]');
    const pick = k => { brain.showMap(...M[k]); host.querySelectorAll('[data-map]').forEach(b => b.classList.toggle('on', b.dataset.map === k));
      if (legend) legend.textContent = k === 'gain' ? '−0.4 to +0.4: where the adapter beats TRIBE v2 (red) or trails it (blue)' : 'r −0.8 to +0.8 against measured fMRI, per brain area'; };
    host.querySelectorAll('[data-map]').forEach(b => b.addEventListener('click', () => pick(b.dataset.map)));
    pick('adapter_r'); brain.mix = 0.75; brain.pitch = 12;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const tick = now => { if (!reduced) brain.yaw = 180 + 40 * Math.sin(now / 6000); brain.draw(); requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
  }

  let MESH = null; const mesh = () => (MESH ??= parseMesh(b64(BRAIN_DATA.mesh)));

  // The hero: a trial's clip and the brain on one clock. Buttons switch between the trials.
  function hero() {
    const host = document.querySelector('[data-brain]'); if (!host || !window.BRAIN_DATA) return;
    const canvas = host.querySelector('canvas'), video = host.querySelector('video'), clock = host.querySelector('[data-clock]'), phase = host.querySelector('[data-phase]');
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let brain;
    try { brain = new Brain(canvas, mesh()); } catch (e) { host.classList.add('nogl'); return; }
    const preds = { isaac: parseNpy(b64(BRAIN_DATA.isaac)), cosmos: parseNpy(b64(BRAIN_DATA.cosmos)) };
    const trials = { isaac: 'assets/brain/isaac.mp4', cosmos: 'assets/brain/cosmos.mp4' };
    let cur = 'isaac';
    const pick = k => { cur = k; video.src = trials[k]; video.currentTime = 0; video.play().catch(() => {});
      host.querySelectorAll('[data-trial]').forEach(b => b.classList.toggle('on', b.dataset.trial === k)); };
    host.querySelectorAll('[data-trial]').forEach(b => b.addEventListener('click', () => pick(b.dataset.trial)));
    pick(cur);
    const tick = now => {
      const t = video.currentTime || 0; brain.show(preds[cur], t);
      if (!reduced) brain.yaw = 160 + 22 * Math.sin(now / 5200);
      brain.draw();
      if (clock) clock.textContent = `${t.toFixed(1)} s`;
      if (phase) phase.textContent = t < 4 ? 'Render on screen' : 'Rest: the screen is grey';
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  const start = () => { hero(); maps(); };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
