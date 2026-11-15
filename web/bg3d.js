/* Client tab backdrop: the building as linework, slowly orbiting behind the page.
   The lines come from the team's Rhino model (models/rector.bin + .json, made by Ryan/tools/rhino_linework.py).
   Decoration only: it never takes clicks, stops when the tab is not showing, and stands still if the
   system asks for reduced motion. Uses the same three.js build as the Expert tab's 3D network. */
(() => {
'use strict';
const MODEL = 'models/rector';
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
  let at = 0;
  for (const g of meta.groups) {
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.BufferAttribute(pos.subarray(at * 6, (at + g.segments) * 6), 3)); at += g.segments;
    spin.add(new T.LineSegments(geo, new T.LineBasicMaterial({color: 0x0a0a0a, transparent: true, opacity: g.name === 'main' ? 0.2 : 0.1})));
  }
  const h = meta.size[2];
  camera = new T.PerspectiveCamera(30, 1, 1, 5000);
  camera.position.set(0, h * 0.95, h * 3.1); camera.lookAt(0, h * 0.45, 0);
  renderer = new T.WebGLRenderer({antialias: true, alpha: true});
  renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
  host.appendChild(renderer.domElement);
  size();
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
  angle += Math.min(0.1, (t - last) / 1000) * 0.07; last = t;     // about one turn every 90 seconds
  draw(); raf = requestAnimationFrame(tick);
}
function sync() {
  const on = showing();
  if (on && !host) { host = document.createElement('div'); host.id = 'client-bg'; host.setAttribute('aria-hidden', 'true'); document.body.appendChild(host); }
  if (host) host.classList.toggle('on', on);
  if (!on) { if (raf) { cancelAnimationFrame(raf); raf = 0; } return; }
  if (!renderer) { loading = loading || load().then(sync).catch(() => { if (host) host.remove(); host = null; clearInterval(timer); }); return; }
  draw();
  if (!still && !raf) { last = performance.now(); raf = requestAnimationFrame(tick); }
}
window.addEventListener('resize', size);
window.addEventListener('hashchange', () => setTimeout(sync, 0));
document.addEventListener('visibilitychange', sync);
const timer = setInterval(sync, 700);     // the page re-renders itself; this keeps the backdrop in step with it
sync();
})();
