/* twin.js: digital twin for the aerial AM project, shown inside the app's own Client and PM views.
   Loaded after app.js. It only appears when the record holds an aerial AM project (a BuilDrone node),
   so other projects (East Tower) look exactly as before.
   Client: the shell as built so far, how far along, one sentence, three milestones.
   PM: a "Twin" mode next to Tree / Freeform / Decisions with the model, a layer-by-layer simulation,
   the release gate at each moment and links into the record (they open the node in the inspector).
   Data: models/aerial-am-twin.json (72 layers with deviation and drone, and the build story). */
(() => {
  const N = 72, H = 2.4, DZ = H / N, TOL = 5;
  const TW = {data: null, frames: [], f: 0, playing: false, timer: null, pmOn: false, speed: 1, dwell: 0, gl: false};
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  // app.js keeps its state private, so the twin reads the same API itself and watches #root for each re-render.
  const BASE = location.pathname.replace(/\/app\/.*$/, '');          // '' locally, '/p/<project>' through the shared link
  let S = null;
  const getState = async () => { try { S = await fetch(BASE + '/api/state', {cache: 'no-store'}).then(r => r.json()); } catch (e) {} };
  const tab = () => { const a = document.querySelector('#root > .app'); if (!a || a.classList.contains('ob-gate')) return null; const m = a.className.match(/\btab-(\w+)/); return m && m[1]; };
  const isAero = () => S && S.nodes && S.nodes.some(n => /buildrone/i.test(n.title));
  const nodeId = re => { const n = S.nodes.find(x => re.test(x.title)); return n && n.id; };
  const loadScript = src => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; document.head.appendChild(s); });

  /* ------------------------------------------------------------ the build, frame by frame */
  function buildFrames() {
    const F = [{printed: 0, current: null, kind: 'design'}, {printed: 0, current: null, kind: 'dry'}];
    for (let L = 1; L <= N; L++) {
      if (L === 23) F.push({printed: 22, current: 23, hold: 'wind'});
      if (L === 41) F.push({printed: 40, current: 41, hold: 'cold'});
      F.push({printed: L, current: L});
    }
    F.push({printed: N, current: null, kind: 'done'});
    TW.frames = F;
    TW.f = F.findIndex(x => x.printed === 31 && !x.hold);
  }
  const day = p => p <= 18 ? 1 : p <= 40 ? 2 : 3;
  function info(fr) {
    const st = TW.data.steps, p = fr.printed, lay = fr.current ? TW.data.layers[fr.current - 1] : null;
    const base = {gate: 'GO', gateWhy: 'Scan within 5 mm, wind under limit, cartridge and battery ready.', links: [/release next layer/i, /layer scan feed/i, /^tolerance/i]};
    if (fr.kind === 'design') return {...base, ...st[0], gate: 'GATE', gateWhy: 'Design freeze: approve the sliced twin before any flight.', links: [/digital twin/i, /toolpath/i, /payload/i]};
    if (fr.kind === 'dry') return {...base, ...st[1], gate: 'GATE', gateWhy: 'Safety gate: the light-trace flight must clear the site.', links: [/dry run/i, /flight approval/i, /wind limit/i]};
    if (fr.kind === 'done') return {...base, ...st[7], gate: 'DONE', gateWhy: 'Final scan accepted. Layers 16–18 noted in the record.', links: [/final laser scan/i, /printed shell/i]};
    if (fr.hold === 'wind') return {...base, ...st[4], gate: 'HOLD', gateWhy: 'Wind above the 6 m/s printing limit. The loaded cartridge passes its open time.', links: [/wind limit/i, /wind and temperature/i, /open time/i]};
    if (fr.hold === 'cold') return {...base, ...st[6], gate: 'HOLD', gateWhy: 'Cold morning: layer 40 has not cured enough to carry layer 41.', links: [/open time/i, /crew/i, /wind and temperature/i]};
    if (p >= 16 && p <= 18) return {...base, ...st[3], gate: 'ADJUST', gateWhy: `Layer ${p} is ${lay.dev} mm off: over the 5 mm tolerance. The twin is updated to v5.`, links: [/^tolerance/i, /layer scan feed/i, /digital twin/i]};
    if (p === 31) return {...base, ...st[5], gate: 'GO', gateWhy: 'BuilDrone 2 grounded. BuilDrone 1 prints alone, refilling between layers.', links: [/buildrone 2/i, /telemetry/i, /buildrone 1/i]};
    if (p <= 15) return {...base, k: 'Day 1', t: `Build day 1: layer ${p} of 72`, client: `${p} of 72 layers done. On track.`, pm: st[2].pm, expert: `Layer ${p}: ${lay.dev} mm from the twin, printed by ${lay.drone}.`};
    if (p <= 30) return {...base, k: 'Day 2', t: `Build day 2: layer ${p} of 72`, client: `${p} of 72 layers done. On track.`, pm: 'Twin v5 in use. Each layer is released after its scan.', expert: `Layer ${p}: ${lay.dev} mm, ${lay.drone}.`};
    if (p <= 40) return {...base, k: 'Day 2', t: `Build day 2: layer ${p} of 72`, client: `${p} of 72 layers done. Slower today, still inside the plan.`, pm: 'One drone printing: about half the speed until BuilDrone 2 is back.', expert: `Layer ${p}: ${lay.dev} mm, BuilDrone 1 only.`, links: [/release next layer/i, /buildrone 1/i, /crew/i]};
    return {...base, k: 'Day 3', t: `Build day 3: layer ${p} of 72`, client: `${p} of 72 layers done. On track to finish today.`, pm: 'Both drones back. Each layer is released after its scan.', expert: `Layer ${p}: ${lay.dev} mm, ${lay.drone}.`};
  }

  /* ------------------------------------------------------------ 3D */
  let renderer, scene, camera, controls, canvas, pmG, clG, rings = [], drones = [], arrow, t = 0, clientKey = -1;
  const radius = i => { const tt = i / (N - 1); return .62 - .32 * Math.pow(tt, 1.6); };
  function ringGeo(i, drift) {
    const pts = [], r = radius(i), z = i * DZ + DZ / 2;
    for (let s = 0; s <= 96; s++) { const a = s / 96 * Math.PI * 2, b = drift * Math.pow(Math.max(0, Math.sin(a)), 2); pts.push(new THREE.Vector3((r + b) * Math.cos(a), z, (r + b) * Math.sin(a))); }
    return new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, true), 96, .008, 5, true);
  }
  function drone(col) {
    const d = new THREE.Group();
    d.add(new THREE.Mesh(new THREE.BoxGeometry(.12, .035, .12), new THREE.MeshStandardMaterial({color: col})));
    [[1, 1], [1, -1], [-1, 1], [-1, -1]].forEach(([a, b]) => { const p = new THREE.Mesh(new THREE.CylinderGeometry(.045, .045, .005, 16), new THREE.MeshStandardMaterial({color: 0x9b9b98})); p.position.set(a * .09, .022, b * .09); d.add(p); });
    return d;
  }
  function init3D() {
    canvas = document.createElement('canvas'); canvas.className = 'tw-canvas';
    try {
      renderer = new THREE.WebGLRenderer({canvas, antialias: true, alpha: true}); renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      scene = new THREE.Scene(); camera = new THREE.PerspectiveCamera(32, 1, .01, 100);
      controls = new THREE.OrbitControls(camera, canvas); controls.enableDamping = true; controls.target.set(0, 1.05, 0); camera.position.set(3.6, 2.5, 4.2);
      scene.add(new THREE.AmbientLight(0xffffff, .8)); const dl = new THREE.DirectionalLight(0xffffff, .55); dl.position.set(3, 6, 4); scene.add(dl);
      const base = new THREE.Mesh(new THREE.CircleGeometry(1.5, 64), new THREE.MeshBasicMaterial({color: 0xe2e2df})); base.rotation.x = -Math.PI / 2; scene.add(base);
      pmG = new THREE.Group(); clG = new THREE.Group(); scene.add(pmG, clG);
      for (let i = 0; i < N; i++) {
        const lay = TW.data.layers[i], bad = lay && !lay.ok;
        const m = new THREE.Mesh(ringGeo(i, 0), new THREE.MeshStandardMaterial({color: 0xb8b8b4, roughness: .7, transparent: true}));
        m.userData = {plain: m.geometry, drift: bad ? ringGeo(i, lay.dev / 1000 * 4) : null, bad};
        pmG.add(m); rings.push(m);
      }
      [0x0a0a0a, 0x6b6b6b, 0x2e7d4f].forEach((c, k) => { const d = drone(c); d.userData = {k}; pmG.add(d); drones.push(d); });
      arrow = new THREE.ArrowHelper(new THREE.Vector3(-1, 0, 0), new THREE.Vector3(1.6, 1, 0), .8, 0xc8452f, .14, .08); pmG.add(arrow);
      TW.gl = true;
    } catch (e) { TW.gl = false; }
    (function loop() {
      requestAnimationFrame(loop);
      if (!TW.gl || !canvas.isConnected) return;
      t += .016; const fr = TW.frames[TW.f];
      if (pmG.visible) drones.forEach(d => {
        const k = d.userData.k, L = fr.current || Math.max(fr.printed, 6), z = (L - 1) * DZ + .3 + k * .14, r = radius(L - 1) + .35 + k * .1;
        const sp = fr.hold ? 0 : (k === 2 ? -.4 : .8), a = (k === 1 ? Math.PI : k === 2 ? 1 : 0) + t * sp;
        d.position.set(Math.cos(a) * r, z, Math.sin(a) * r);
      });
      controls.update(); renderer.render(scene, camera);
    })();
  }
  function update3D() {
    if (!TW.gl) return;
    const fr = TW.frames[TW.f];
    rings.forEach((m, i) => {
      const L = i + 1, u = m.userData, mat = m.material;
      let col = 0xb8b8b4, op = .28, glow = 0, geo = u.plain;
      if (fr.kind === 'dry' && L <= 6) { col = 0x2e7d4f; op = 1; glow = .5; }
      else if (L <= fr.printed) { op = 1; if (u.bad) { col = 0xc8452f; geo = u.drift; } else col = 0x8a8a86; }
      else if (L === fr.current) { col = fr.hold ? 0xc8452f : 0xb4541a; op = 1; glow = .5; }
      m.geometry = geo; mat.color.setHex(col); mat.opacity = op; mat.emissive.setHex(glow ? col : 0); mat.emissiveIntensity = glow;
    });
    const flying = !fr.kind || fr.kind === 'dry', bd2out = fr.printed >= 31 && fr.printed <= 40;
    drones[0].visible = flying; drones[1].visible = flying && !bd2out; drones[2].visible = flying;
    arrow.visible = fr.hold === 'wind';
    if (clG.visible) buildClient();
  }
  function buildClient() {
    const p = TW.frames[TW.f].printed; if (p === clientKey) return; clientKey = p;
    while (clG.children.length) { const c = clG.children.pop(); c.geometry && c.geometry.dispose(); }
    const prof = (to, inset) => { const a = []; for (let i = 0; i <= to; i++) a.push(new THREE.Vector2(radius(Math.min(i, N - 1)) - inset, i * DZ)); return a; };
    const ghost = new THREE.Mesh(new THREE.LatheGeometry(prof(N, 0), 72), new THREE.MeshStandardMaterial({color: 0xb8b8b4, transparent: true, opacity: .16, side: THREE.DoubleSide, depthWrite: false}));
    clG.add(ghost);
    if (p > 0) {
      const outer = prof(p, 0), inner = prof(p, .035).reverse(), pts = outer.concat(inner, [outer[0]]);
      clG.add(new THREE.Mesh(new THREE.LatheGeometry(pts, 96), new THREE.MeshStandardMaterial({color: 0x9a9a96, roughness: .85, side: THREE.DoubleSide})));
    }
  }
  function attach(stage, mode) {
    if (!TW.gl) { stage.innerHTML = '<p class="ed-empty" style="padding:24px">The 3D view needs WebGL.</p>'; return; }
    if (canvas.parentNode !== stage) stage.prepend(canvas);
    pmG.visible = mode === 'pm'; clG.visible = mode === 'client'; controls.autoRotate = mode === 'client'; controls.autoRotateSpeed = .6;
    clientKey = -1; update3D();
    requestAnimationFrame(() => { const w = stage.clientWidth, h = stage.clientHeight; if (w && h) { renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); } });
  }

  /* ------------------------------------------------------------ Client: super simple */
  let clientEl;
  function clientHTML() {
    const fr = TW.frames[TW.f], I = info(fr), p = fr.printed, pct = Math.round(p / N * 100);
    const printing = p > 0 && fr.kind !== 'done', done = fr.kind === 'done';
    return `<div class="tw-cgrid"><div class="tw-stage tw-cstage"></div>
      <div class="tw-cread"><div><span class="ed-num">${pct}%</span><span class="ed-meta" style="display:block;margin-top:6px">built</span></div>
        <p class="ed-lede" style="max-width:22ch">${esc(I.client)}</p>
        <ol class="tw-miles"><li class="done">Designed</li><li class="${done ? 'done' : printing ? 'now' : ''}">${printing ? `Printing · day ${day(p)} of 3` : 'Printing'}</li><li class="${done ? 'done' : ''}">Handed over</li></ol></div></div>`;
  }
  function mountClient() {
    const hero = document.querySelector('#root .ov-hero'); if (!hero) return;
    if (!clientEl) { clientEl = document.createElement('section'); clientEl.className = 'ed-section tw-client'; }
    clientEl.innerHTML = `<div class="ed-label"><span class="ed-meta">Today</span><h2>Your shell</h2><span class="ed-meta" style="text-transform:none;letter-spacing:0;line-height:1.4">Printed in place by drones, layer by layer.</span></div><div class="ed-body">${clientHTML()}</div>`;
    hero.after(clientEl);
    attach(clientEl.querySelector('.tw-cstage'), 'client');
  }

  /* ------------------------------------------------------------ PM: model + simulation */
  let pmEl;
  function stripSVG(fr) {
    const w = 720, h = 70, bw = w / N, max = 8, y = v => h - 14 - v / max * (h - 22);
    const bars = TW.data.layers.map((l, i) => { const L = i + 1, on = L <= fr.printed, cur = L === fr.current;
      return `<rect data-tw-layer="${L}" x="${i * bw + .5}" y="${y(l.dev)}" width="${bw - 1}" height="${h - 14 - y(l.dev)}" fill="${cur ? '#b4541a' : !on ? '#e2e2df' : l.ok ? '#8a8a86' : '#c8452f'}" style="cursor:pointer"><title>Layer ${L}: ${l.dev} mm · ${l.drone}</title></rect>`; }).join('');
    return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="tw-strip-svg">${bars}
      <line x1="0" x2="${w}" y1="${y(TOL)}" y2="${y(TOL)}" stroke="#c8452f" stroke-dasharray="4 4" stroke-width="1"/>
      <text x="${w - 4}" y="${y(TOL) - 4}" text-anchor="end" font-size="10" fill="#c8452f">5 mm tolerance</text>
      ${[1, 18, 40, 72].map(L => `<text x="${(L - .5) * bw}" y="${h - 2}" text-anchor="middle" font-size="10" fill="#9b9b98">${L}</text>`).join('')}</svg>`;
  }
  function pmReadHTML() {
    const fr = TW.frames[TW.f], I = info(fr), lay = fr.current ? TW.data.layers[fr.current - 1] : null;
    const links = (I.links || []).map(re => { const id = nodeId(re), n = id && S.nodes.find(x => x.id === id); return n ? `<button class="tw-node" data-act="sel" data-id="${n.id}">${esc(n.title)}</button>` : ''; }).join('');
    const bd2out = fr.printed >= 31 && fr.printed <= 40;
    const cell = (k, v, cls) => `<div class="tw-cell ${cls || ''}"><span class="ed-meta">${k}</span><b>${v}</b></div>`;
    return `<div class="tw-cells">
        ${cell('Release next layer', I.gate, I.gate === 'HOLD' ? 'bad' : I.gate === 'ADJUST' ? 'warn' : '')}
        ${cell('Layer', fr.current ? `${fr.current} / ${N}` : fr.kind === 'done' ? `${N} / ${N}` : '— / ' + N)}
        ${cell('Day', fr.printed ? `${day(fr.current || fr.printed)} of 3` : 'Before build')}
        ${cell('Deviation', lay ? `${lay.dev} mm` : '—', lay && !lay.ok ? 'bad' : '')}
        ${cell('Printing', fr.kind ? (fr.kind === 'dry' ? 'Light trace' : '—') : fr.hold ? 'Paused' : lay ? lay.drone.replace('BuilDrone', 'BD') : '—')}
        ${cell('Drones up', fr.kind && fr.kind !== 'dry' ? '0' : bd2out ? '2 of 3' : '3 of 3', bd2out ? 'warn' : '')}</div>
      <h3 class="tw-title">${esc(I.t)}</h3>
      <p class="tw-why">${esc(I.gateWhy)}</p>
      <div class="tw-roles"><div><span class="ed-meta">PM</span><p>${esc(I.pm)}</p></div><div><span class="ed-meta">Expert</span><p>${esc(I.expert)}</p></div></div>
      ${links ? `<div class="tw-links"><span class="ed-meta">In the record</span>${links}</div>` : ''}`;
  }
  function pmHTML() {
    const fr = TW.frames[TW.f], steps = TW.data.steps;
    const stepIdx = [0, 1, TW.frames.findIndex(x => x.printed === 15 && !x.hold), TW.frames.findIndex(x => x.printed === 18), TW.frames.findIndex(x => x.hold === 'wind'),
      TW.frames.findIndex(x => x.printed === 31 && !x.hold), TW.frames.findIndex(x => x.hold === 'cold'), TW.frames.length - 1];
    return `<div class="tw-pmgrid">
      <div class="tw-left">
        <div class="tw-stage tw-pmstage"><span class="tw-hint">Drag to orbit · scroll to zoom</span>
          <div class="tw-key"><span><i style="background:#8a8a86"></i>Printed</span><span><i style="background:#c8452f"></i>Out of tolerance / hold</span><span><i style="background:#b4541a"></i>Printing now</span><span><i style="background:#cfcfcb"></i>Planned</span><span><i style="background:#2e7d4f"></i>ScanDrone</span></div></div>
        <div class="tw-ctl">
          <button class="tw-btn" data-tw="play">${TW.playing ? '❚❚ Pause' : '▶ Play the build'}</button>
          <button class="tw-btn" data-tw="prev" aria-label="Previous">◂</button><button class="tw-btn" data-tw="next" aria-label="Next">▸</button>
          <input type="range" class="tw-range" min="0" max="${TW.frames.length - 1}" value="${TW.f}" aria-label="Moment in the build">
          <div class="seg sm">${[1, 4].map(s => `<button class="${TW.speed === s ? 'on' : ''}" data-tw="speed" data-s="${s}">${s}×</button>`).join('')}</div>
        </div>
        <div class="tw-steps">${steps.map((s, i) => `<button data-tw="go" data-f="${stepIdx[i]}" class="${TW.f === stepIdx[i] ? 'on' : ''}">${esc(s.k)}</button>`).join('')}</div>
        <div class="tw-strip"><span class="ed-meta">Scan deviation per layer · click a layer to jump</span>${stripSVG(fr)}</div>
      </div>
      <div class="tw-read">${pmReadHTML()}</div></div>`;
  }
  function mountPM() {
    const tb = document.querySelector('#root .pm-toolbar'); if (!tb) return;
    const seg = tb.querySelector('.seg');
    if (seg && !seg.querySelector('[data-tw="mode"]')) seg.insertAdjacentHTML('beforeend', `<button data-tw="mode">Twin</button>`);
    if (!TW.pmOn) return;
    seg.querySelectorAll('button').forEach(b => b.classList.toggle('on', b.dataset.tw === 'mode'));
    const mi = tb.querySelector('.mode-info'); if (mi) mi.textContent = 'The shell as the record describes it, layer by layer. Press Play to run the build.';
    const main = tb.parentNode; main.querySelectorAll(':scope > .chips, :scope > .canvas-wrap').forEach(e => e.style.display = 'none');
    if (!pmEl) { pmEl = document.createElement('div'); pmEl.className = 'tw-pm'; }
    pmEl.innerHTML = pmHTML(); tb.after(pmEl);
    attach(pmEl.querySelector('.tw-pmstage'), 'pm');
  }
  function refreshPanels() {   // a frame change: update text in place, keep the canvas
    const fr = TW.frames[TW.f];
    if (pmEl && pmEl.isConnected) {
      pmEl.querySelector('.tw-read').innerHTML = pmReadHTML();
      pmEl.querySelector('.tw-strip').innerHTML = `<span class="ed-meta">Scan deviation per layer · click a layer to jump</span>${stripSVG(fr)}`;
      const r = pmEl.querySelector('.tw-range'); if (r && document.activeElement !== r) r.value = TW.f;
      pmEl.querySelectorAll('.tw-steps button').forEach(b => b.classList.toggle('on', +b.dataset.f === TW.f));
      const pb = pmEl.querySelector('[data-tw="play"]'); if (pb) pb.textContent = TW.playing ? '❚❚ Pause' : '▶ Play the build';
    }
    if (clientEl && clientEl.isConnected) clientEl.querySelector('.tw-cread').innerHTML = new DOMParser().parseFromString(clientHTML(), 'text/html').querySelector('.tw-cread').innerHTML;
    update3D();
  }
  function setFrame(i) { TW.f = Math.max(0, Math.min(TW.frames.length - 1, i)); refreshPanels(); }
  function play(on) {
    TW.playing = on; clearInterval(TW.timer);
    if (on) { if (TW.f >= TW.frames.length - 1) TW.f = 0; TW.timer = setInterval(() => {
      if (TW.frames[TW.f].hold && TW.dwell < 5) { TW.dwell++; return; } TW.dwell = 0;
      if (TW.f >= TW.frames.length - 1) { play(false); refreshPanels(); return; } setFrame(TW.f + 1); }, 420 / TW.speed); }
    refreshPanels();
  }

  /* ------------------------------------------------------------ wiring into the app */
  document.addEventListener('click', e => {
    if (e.target.closest('[data-act="mode"]')) TW.pmOn = false;           // Tree / Freeform / Decisions leave the twin
    const b = e.target.closest('[data-tw], [data-tw-layer]'); if (!b) return;
    if (b.dataset.twLayer) { const L = +b.dataset.twLayer; setFrame(TW.frames.findIndex(x => x.printed === L && !x.hold)); return; }
    const a = b.dataset.tw;
    if (a === 'mode') { TW.pmOn = true; mountPM(); }
    else if (a === 'play') play(!TW.playing);
    else if (a === 'prev') { play(false); setFrame(TW.f - 1); }
    else if (a === 'next') { play(false); setFrame(TW.f + 1); }
    else if (a === 'go') { play(false); setFrame(+b.dataset.f); }
    else if (a === 'speed') { TW.speed = +b.dataset.s; b.parentNode.querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b)); if (TW.playing) play(true); }
  }, true);
  document.addEventListener('input', e => { if (e.target.classList && e.target.classList.contains('tw-range')) { play(false); setFrame(+e.target.value); } });
  addEventListener('resize', () => { const st = canvas && canvas.parentNode; if (st && TW.gl) { renderer.setSize(st.clientWidth, st.clientHeight, false); camera.aspect = st.clientWidth / st.clientHeight; camera.updateProjectionMatrix(); } });

  function after() {
    if (!TW.data || !isAero()) return;
    const t = tab();
    try { if (t === 'client') mountClient(); else if (t === 'pm') mountPM(); } catch (e) { console.error('twin', e); }
  }
  const root = document.getElementById('root');
  if (root) new MutationObserver(after).observe(root, {childList: true});      // app.js replaced the page: put the twin back
  setInterval(() => getState(), 20000);

  document.head.insertAdjacentHTML('beforeend', `<style>
    .tw-stage{position:relative;background:var(--tile);overflow:hidden}
    .tw-stage .tw-canvas{position:absolute;inset:0;display:block;width:100%;height:100%}
    .tw-cgrid{display:grid;grid-template-columns:minmax(0,3fr) minmax(220px,2fr);gap:32px;align-items:center}
    .tw-cstage{height:clamp(300px,38vw,480px)}
    .tw-cread{display:flex;flex-direction:column;gap:22px}
    .tw-miles{list-style:none;margin:0;padding:0;border-top:1px solid var(--ink)}
    .tw-miles li{display:flex;align-items:center;gap:12px;padding:12px 0;border-bottom:1px solid var(--hair);font-size:17px;color:var(--ink-3)}
    .tw-miles li:before{content:"";width:12px;height:12px;border-radius:50%;border:1px solid var(--ink-3);flex:none}
    .tw-miles li.done{color:var(--ink)}.tw-miles li.done:before{background:var(--ink);border-color:var(--ink)}
    .tw-miles li.now{color:var(--ink)}.tw-miles li.now:before{border-color:#b4541a;background:linear-gradient(90deg,#b4541a 50%,transparent 50%)}
    .tw-pm{flex:1;min-height:0;overflow:auto;padding:14px 16px 24px max(var(--gutter),env(safe-area-inset-left,0px));border-top:1px solid var(--hair)}
    .tw-pmgrid{display:grid;grid-template-columns:minmax(0,1fr) minmax(260px,340px);gap:24px;align-items:start}
    .tw-pmstage{height:clamp(320px,52vh,560px)}
    .tw-hint{position:absolute;z-index:1;right:12px;top:10px;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)}
    .tw-key{position:absolute;z-index:1;left:12px;bottom:10px;display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px;color:var(--ink-2);background:#ffffffd9;padding:6px 10px}
    .tw-key i{display:inline-block;width:14px;height:3px;vertical-align:middle;margin-right:6px}
    .tw-ctl{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-top:12px}
    .tw-btn{border:0;background:none;font-size:15px;padding:6px 0;cursor:pointer;box-shadow:inset 0 -1px 0 var(--ink);white-space:nowrap}
    .tw-btn[data-tw="play"]{background:var(--ink);color:#fff;padding:8px 16px;box-shadow:none}
    .light .tw-btn[data-tw="play"]{color:#fff}
    .tw-range{flex:1 1 200px;accent-color:#0a0a0a}
    .tw-steps{display:flex;flex-wrap:wrap;border-top:1px solid var(--hair);margin-top:12px}
    .tw-steps button{flex:1 1 90px;border:0;background:none;text-align:left;padding:9px 8px 9px 0;font-size:13px;color:var(--ink-3);cursor:pointer;border-bottom:1px solid var(--hair)}
    .tw-steps button.on,.tw-steps button:hover{color:var(--ink)}.tw-steps button.on{box-shadow:inset 0 -2px 0 var(--ink)}
    .tw-strip{margin-top:16px}.tw-strip-svg{display:block;width:100%;height:84px;margin-top:6px}
    .tw-read{display:flex;flex-direction:column;gap:14px}
    .tw-cells{display:grid;grid-template-columns:1fr 1fr;column-gap:16px;border-top:1px solid var(--ink)}
    .tw-cell{display:flex;flex-direction:column;gap:4px;padding:10px 0;border-bottom:1px solid var(--hair)}
    .tw-cell b{font-weight:400;font-size:22px;letter-spacing:-.02em}
    .tw-cell.bad b{color:#c8452f}.tw-cell.warn b{color:#b4541a}
    .tw-cell:first-child{grid-column:1/-1}.tw-cell:first-child b{font-size:34px}
    .tw-title{font-size:24px;line-height:1.1}
    .tw-why{margin:0;font-size:15px;line-height:1.45;padding-left:12px;border-left:2px solid #b4541a}
    .tw-roles{display:flex;flex-direction:column;gap:10px}.tw-roles p{margin:4px 0 0;font-size:15px;line-height:1.45}
    .tw-links{display:flex;flex-direction:column;align-items:flex-start;gap:2px;border-top:1px solid var(--hair);padding-top:10px}
    .tw-node{border:0;background:none;padding:6px 0;font-size:15px;cursor:pointer;box-shadow:inset 0 -1px 0 var(--ink);text-align:left}
    @media(max-width:1100px){.tw-pmgrid,.tw-cgrid{grid-template-columns:1fr}}
  </style>`);

  (async () => {
    try {
      TW.data = await fetch('models/aerial-am-twin.json', {cache: 'no-store'}).then(r => r.json());
      buildFrames();
      if (!window.THREE) await loadScript('https://cdn.jsdelivr.net/npm/three@0.128.0/build/three.min.js');
      if (!THREE.OrbitControls) await loadScript('https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js');
      init3D();
    } catch (e) { console.warn('twin: not available', e); TW.data = TW.data && TW.frames.length ? TW.data : null; }
    await getState(); after();
  })();
})();
