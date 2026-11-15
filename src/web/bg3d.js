/* Client tab backdrop: the building as linework, slowly orbiting behind the page.
   An aerial AM project instead shows its shell being printed by the drones (models/aerial-am-shell).
   The lines come from the team's Rhino model (models/rector.bin + .json, made by src/tools/rhino_linework.py).
   Decoration only: it never takes clicks, stops when the tab is not showing, and stands still if the
   system asks for reduced motion. Uses the same three.js build as the Expert tab's 3D network. */
(() => {
'use strict';
// Each project can bring its own model; anything else gets the facade survey's building.
const MODELS = {'rooftop-shell': 'models/aerial-am-shell'};
const BASE = location.pathname.replace(/\/app\/.*$/, '');          // '' locally, '/p/<project>' through the shared link
let MODEL = null, picking = null;
async function pickModel() {
  try {
    const s = await fetch(BASE + '/api/state', {cache: 'no-store'}).then(r => r.json());
    if (MODELS[s.project.id]) return MODELS[s.project.id];
    if ((s.nodes || []).some(n => /buildrone/i.test(n.title))) return 'models/aerial-am-shell';   // an aerial AM record under another id
  } catch (e) {}
  return 'models/rector';
}
const still = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
let host = null, T = null, renderer = null, scene = null, camera = null, spin = null, loading = null, raf = 0, angle = 0.6, last = 0;

const showing = () => !!document.querySelector('.app.tab-client:not(.ob-gate)') && !document.querySelector('.intake.open');

async function load() {
  const [three, meta, buf] = await Promise.all([
    import('https://cdn.jsdelivr.net/npm/three@0.172.0/build/three.module.js'),
    fetch(MODEL + '.json').then(r => r.json()), fetch(MODEL + '.bin').then(r => r.arrayBuffer())]);
  T = three;
  const raw = new Int16Array(buf), pos = new Float32Array(raw.length);
  for (let i = 0; i < raw.length; i += 3) {            // Rhino is Z-up, the screen is Y-up
    pos[i] = raw[i] * meta.scale; pos[i + 1] = raw[i + 2] * meta.scale; pos[i + 2] = -raw[i + 1] * meta.scale; }
  scene = new T.Scene(); spin = new T.Group(); scene.add(spin);
  let at = 0, mainGeo = null;
  for (const g of meta.groups) {
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(pos.subarray(at * 6, (at + g.segments) * 6), 3)); at += g.segments;
    spin.add(new T.LineSegments(geo, new T.LineBasicMaterial({color: 0x0a0a0a, transparent: true, opacity: g.name === 'main' ? (meta.layers ? 0.45 : 0.2) : 0.1})));
    if (g.name === 'main') mainGeo = geo;
  }
  if (meta.layers) aerial(meta, mainGeo);
  const h = meta.size[2];
  camera = new T.PerspectiveCamera(30, 1, 1, 5000);
  camera.position.set(0, h * 0.95, h * 3.1); camera.lookAt(0, h * 0.45, 0);
  renderer = new T.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  host.appendChild(renderer.domElement);
  size();
}
/* Aerial AM project: the shell prints itself ring by ring while the drones work, on a loop.
   BuilDrone 1 and 2 take turns (one prints, the other refills at the pad), the ScanDrone circles above the
   newest layer. Same line style as the rest of the backdrop. */
let AER = null;
function droneLines(size) {
  const v = [], ring = (cx, cz, r) => { for (let i = 0; i < 16; i++) { const a = i / 16 * Math.PI * 2, b = (i + 1) / 16 * Math.PI * 2;
    v.push(cx + r * Math.cos(a), 0, cz + r * Math.sin(a), cx + r * Math.cos(b), 0, cz + r * Math.sin(b)); } };
  const d = size / 2;
  v.push(-d, 0, -d, d, 0, d, -d, 0, d, d, 0, -d);                                  // arms
  [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([x, z]) => ring(x * d, z * d, size * 0.28));   // rotors
  const b = size * 0.16; v.push(-b, -.01, -b, b, -.01, -b, b, -.01, -b, b, -.01, b, b, -.01, b, -b, -.01, b, -b, -.01, b, -b, -.01, -b);   // body
  v.push(0, -.01, 0, 0, -size * 0.45, 0);                                          // nozzle
  const g = new T.BufferGeometry(); g.setAttribute('position', new T.Float32BufferAttribute(v, 3)); return g;
}
function aerial(meta, mainGeo) {
  const L = meta.layers, mk = (op, size) => { const m = new T.LineSegments(droneLines(size), new T.LineBasicMaterial({color: 0x0a0a0a, transparent: true, opacity: op})); spin.add(m); return m; };
  AER = {L, geo: mainGeo, t: 0, drones: [mk(0.9, 0.26), mk(0.9, 0.26), mk(0.6, 0.2)], pad: [new T.Vector3(1.55, 0.35, 0.9), new T.Vector3(1.55, 0.35, -0.9)]};
  AER.drones[0].position.copy(AER.pad[0]); AER.drones[1].position.copy(AER.pad[1]); AER.drones[2].position.set(0.5, 2.8, 0);   // where they rest if motion is off
}
function aerialStep(dt) {
  const A = AER, L = A.L, cyc = 1.5, travel = 0.35;       // seconds per layer, of which the drone swap takes 0.35
  A.t = (A.t + dt) % (L.count * cyc + 4);                  // a short pause on the finished shell, then print again
  const k = Math.min(L.count, Math.floor(A.t / cyc)), f = A.t / cyc - k, done = k >= L.count;
  const p = done ? 0 : Math.max(0, (f * cyc - travel) / (cyc - travel));
  A.geo.setDrawRange(0, (k * L.ring + Math.floor(p * L.ring)) * 2);
  const r = i => L.r0 - L.dr * Math.pow(i / (L.count - 1), 1.6), y = i => i * L.dz + L.dz / 2;
  const i = Math.min(k, L.count - 1), a = p * Math.PI * 2, at = new T.Vector3(r(i) * Math.cos(a), y(i) + 0.17, -r(i) * Math.sin(a));
  const start = new T.Vector3(r(i), y(i) + 0.17, 0), bob = t => Math.sin(t * 3) * 0.02;
  A.drones.forEach((d, n) => {
    if (n === 2) { const s = -A.t * 0.5; d.position.set((r(i) + 0.45) * Math.cos(s), y(i) + 0.55, (r(i) + 0.45) * Math.sin(s)); return; }
    const printing = !done && k % 2 === n, wasPrinting = !done && k > 0 && (k - 1) % 2 === n, pad = A.pad[n].clone().setY(A.pad[n].y + bob(A.t + n));
    if (printing) d.position.copy(f * cyc < travel ? pad.lerp(start, f * cyc / travel) : at);
    else if (wasPrinting && f * cyc < travel) d.position.copy(start.clone().lerp(pad, f * cyc / travel));
    else d.position.copy(pad);
  });
}
function size() {
  if (!renderer) return;
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false); camera.aspect = w / h;
  if (w > 900) camera.setViewOffset(w, h, -w * 0.24, 0, w, h); else camera.clearViewOffset();   // on wide screens the building sits to the right of the text
  camera.updateProjectionMatrix(); draw();
}
function draw() { if (renderer) { spin.rotation.y = angle; renderer.render(scene, camera); } }
function tick(t) {
  raf = 0;
  if (!showing()) { sync(); return; }
  const dt = Math.min(0.1, (t - last) / 1000); last = t;
  angle += dt * 0.07;                                               // about one turn every 90 seconds
  if (AER) aerialStep(dt);
  draw(); raf = requestAnimationFrame(tick);
}
function sync() {
  const on = showing();
  if (on && !host) { host = document.createElement('div'); host.id = 'client-bg'; host.setAttribute('aria-hidden', 'true'); document.body.appendChild(host); }
  if (host) host.classList.toggle('on', on);
  if (!on) { if (raf) { cancelAnimationFrame(raf); raf = 0; } return; }
  if (!renderer) { if (!MODEL) { picking = picking || pickModel().then(m => { MODEL = m; sync(); }); return; } loading = loading || load().then(sync).catch(() => { if (host) host.remove(); host = null; clearInterval(timer); }); return; }
  draw();
  if (!still && !raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
}
window.addEventListener('resize', size);
window.addEventListener('hashchange', () => setTimeout(sync, 0));
document.addEventListener('visibilitychange', sync);
const timer = setInterval(sync, 700);     // the page re-renders itself; this keeps the backdrop in step with it
sync();
})();
