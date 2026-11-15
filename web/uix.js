/* uix.js: the pieces of the UI/UX design (Leslie/) that the live page lacked, wired to the real API.
     1 Onboarding questionnaire on the Overview, the "Suggested for you" strip and the Retake button
     2 Ask bar on the PM and Pilot tabs: plain-language question, short answer, "Go to" buttons, highlights
     3 Design brief on the Client tab: preview, copy, download .md  (GET /api/brief)
     4 Pilot tab as the 3D knowledge network (three.js), with the flight brief one click away
   Markup, class names and wording follow the design's React components; app.js calls in at a few marked hooks.
   Load this file before app.js: it defines window.makeUIX, which app.js calls with its own helpers. */
window.makeUIX = ({ui, esc, $, api, post, render, toast, inspector, loadDetail, CATS, CAT_ORDER, UNCL, PRESENTER}) => {
  let S = null, D = null;      // app.js is a closed scope: it passes its helpers in here, and its state before every render (sync)
  const store = {get: k => { try { return JSON.parse(localStorage.getItem(k)); } catch { return null; } },
                 set: (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, JSON.stringify(v)); } catch {} }};

  /* ------------------------------------------------------------ 1 onboarding */
  const STEPS = [
    {key: 'role', q: 'What best describes you?', options: [
      ['client', 'Client', 'I want to follow the project and see what I am getting'],
      ['pm', 'Project manager', 'I keep the pieces moving and decide what happens next'],
      ['pilot', 'Pilot or specialist', 'I plan and carry out the technical work'],
      ['explore', 'Just looking', 'Show me around']]},
    {key: 'goal', q: 'What would you like to do first?', options: [
      ['building', 'See the building', 'Explore it part by part'],
      ['blocking', 'Find out what is holding things up', 'Open questions and things to check'],
      ['find', 'Find a piece of information', 'Ask a question in plain words'],
      ['add', 'Add something new', 'A file, an email, a note']]},
    {key: 'level', q: 'How well do you know this project?', options: [
      ['new', 'New to it', 'Keep it simple and guide me'],
      ['some', 'I know the basics', ''],
      ['expert', 'I know it well', 'Get out of my way']]},
  ];
  const ob = {saved: store.get('yb.onboarding'), step: 0, ans: {}, skipped: PRESENTER};
  function startFor(a) {
    if (a.goal === 'building') return {tab: 'client', label: 'Building explorer', why: 'See each part of the building and what is open on it.'};
    if (a.goal === 'add') return {tab: 'data', label: 'Parking lot', why: 'Drop files or paste notes. They get sorted into the project for you to approve.'};
    if (a.goal === 'blocking') return {tab: a.role === 'pilot' ? 'pilot' : 'pm', label: a.role === 'pilot' ? 'Knowledge network' : 'Project tree',
      why: 'We will ask the guide what is still open and show you where.', question: 'What still needs checking?'};
    if (a.role === 'client') return {tab: 'client', label: 'Building explorer', why: 'The simplest way in: explore the building, then draft a brief.'};
    if (a.role === 'pilot') return {tab: 'pilot', label: 'Knowledge network', why: 'Every piece of project knowledge in one view. Ask a question to find your way.'};
    return {tab: 'pm', label: 'Project tree', why: 'Everything laid out left to right. Ask a question in plain words to find things.'};
  }
  function onboarding() {
    const done = ob.step >= STEPS.length, st = STEPS[ob.step], start = done ? startFor(ob.ans) : null;
    return `<main class="ed-page ob">
      <header class="ob-top"><span class="ed-meta">${esc(S.project.name)} — ${done ? 'Ready' : `Question ${ob.step + 1} of ${STEPS.length}`}</span>
        <span class="ob-bar" aria-hidden="true">${STEPS.map((_, i) => `<i class="${i < ob.step ? 'on' : ''}"></i>`).join('')}</span>
        <button class="ed-link dim" data-uix="ob-skip">Skip</button></header>
      ${!done ? `<section class="ob-step"><h1 class="ed-display md">${esc(st.q)}</h1>
          <ul class="ed-rows ob-options">${st.options.map(([v, label, hint]) => `<li><button class="ed-row" data-uix="ob-pick" data-v="${v}"><span class="t">${esc(label)}${hint ? `<span class="ob-hint">${esc(hint)}</span>` : ''}</span><span class="side"><span class="go" aria-hidden="true">→</span></span></button></li>`).join('')}</ul>
          ${ob.step > 0 ? '<button class="ed-link dim" data-uix="ob-back">Back</button>' : ''}</section>`
        : `<section class="ob-step"><span class="ed-meta">Start here</span><h1 class="ed-display md">${esc(start.label)}</h1><p class="ed-lede">${esc(start.why)}</p>
          <div class="ob-actions"><button class="ed-cta" data-uix="ob-go">Take me there</button><button class="ed-link" data-uix="ob-stay">Show the overview first</button><button class="ed-link dim" data-uix="ob-again">Start again</button></div></section>`}
    </main>`;
  }
  /* app.js hook: a page that replaces the tab's normal one, or null */
  function page(tab) { return tab === 'overview' && !ob.saved && !ob.skipped ? onboarding() : null; }
  function startStrip() {
    const start = ob.saved ? startFor(ob.saved) : null;
    return `<div class="ov-start">${start
      ? `<span class="ed-meta">Suggested for you</span><button class="ed-link" data-uix="go-start">${esc(start.label)}</button><span class="why">${esc(start.why)}</span>`
      : `<span class="ed-meta">New here?</span><button class="ed-link" data-uix="ob-open">Answer 3 questions to find your start</button>`}</div>`;
  }
  function retake() {
    return `<section class="ov-retake"><p class="ed-lede">${ob.saved ? 'Changed role, or want a different starting point?' : 'Not sure where to begin?'}</p>
      <button class="ed-cta xl" data-uix="ob-retake">${ob.saved ? 'Retake questions' : 'Answer 3 questions'}</button></section>`;
  }
  function goTo(start) {
    location.hash = start.tab;
    if (start.tab === 'pilot') pilotMode = 'net';
    if (start.question) setTimeout(() => runGuide(start.question), 60);
  }

  /* ------------------------------------------------------------ 2 ask bar (guide) */
  const EXAMPLES = ["What's blocking the flight?", 'Are we allowed to fly here?', 'Who looks after safety?', 'What does the client get?'];
  let guide = null;      // {q, loading, answer, ids, err, answered}
  const lowerHit = (n, q) => (n.title + ' ' + (n.summary || '') + ' ' + (n.tags || []).join(' ') + ' ' + n.type).toLowerCase().includes(q);
  /* app.js hook: node ids to highlight, or null when no question is active */
  function hits() { return guide && !guide.loading && guide.ids && guide.ids.length ? new Set(guide.ids) : null; }
  async function runGuide(q) {
    q = (q || '').trim(); if (!q) return;
    ui.q = q; guide = {q, loading: true}; render();
    const [a, s] = await Promise.allSettled([post('/api/ask', {question: q}), api(`/api/search?q=${encodeURIComponent(q)}&k=5&passages=0`)]);
    if (!guide || guide.q !== q) return;
    const ids = [];
    if (a.status === 'fulfilled') for (const c of a.value.citations || []) if (D.byId[c.node_id] && !ids.includes(c.node_id)) ids.push(c.node_id);
    if (s.status === 'fulfilled' && ids.length < 5) for (const r of s.value.results || []) if (D.byId[r.node.id] && !ids.includes(r.node.id) && ids.length < 5) ids.push(r.node.id);
    guide = a.status === 'fulfilled'
      ? {q, ids: ids.slice(0, 5), answer: (a.value.answer || '').replace(/\s*\[[\d,\s]+\]/g, ''), answered: a.value.answered !== false, cited: (a.value.citations || []).length}
      : {q, ids: ids.slice(0, 5), err: a.reason.message};
    render(); if (ui.tab === 'pilot') net.refresh();
  }
  function clearGuide() { guide = null; ui.q = ''; ui.search = null; render(); if (ui.tab === 'pilot') net.refresh(); }
  function askBar(where) {
    const q = ui.q || '', typed = q.trim().toLowerCase(), h = hits();
    const shown = h ? h.size : typed ? S.nodes.filter(n => lowerHit(n, typed)).length : S.nodes.length;
    const active = !!typed;
    const chip = id => { const n = D.byId[id], c = D.cat[id];
      return `<button class="ask-chip ${ui.sel === id ? 'on' : ''}" data-act="sel" data-id="${esc(id)}"><i style="background:${c ? CATS[c].c : UNCL}"></i>${esc(n.title)}</button>`; };
    let below;
    if (guide && guide.loading) below = `<div class="ask-answer" aria-live="polite"><p class="reading">Reading the record</p></div>`;
    else if (guide && guide.err) below = `<div class="ask-answer" aria-live="polite"><p class="flag bad">${esc(guide.err)}</p></div>`;
    else if (guide) below = `<div class="ask-answer" aria-live="polite"><p title="${esc(guide.answer)}">${esc(guide.answer)}</p>
        <div class="ask-go">${guide.ids.length ? '<span class="ed-meta">Go to</span>' : ''}${guide.ids.map(chip).join('')}
          <span class="ed-meta note">Guide · answered from the record${guide.cited ? `, ${guide.cited} source${guide.cited > 1 ? 's' : ''}` : ''}</span></div></div>`;
    else below = `<div class="ask-try"><span class="ed-meta">Try</span>${EXAMPLES.map(x => `<button data-uix="try" data-q="${esc(x)}">${esc(x)}</button>`).join('')}</div>`;
    return `<div class="ask-wrap"><form class="ed-search" role="search" data-guide="${where}" ${where === 'pm' ? 'data-search="1"' : ''}>
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg>
        <input type="search" name="q" id="${where}-search" aria-label="Ask a question about the project" placeholder="Ask anything about the project" value="${esc(q)}" autocomplete="off">
        ${active ? `<span class="ed-meta count">${shown} of ${S.nodes.length}</span>` : ''}
        ${q ? '<button type="button" class="clear" aria-label="Clear question" data-uix="clear">×</button>' : ''}</form>${below}</div>`;
  }

  /* ------------------------------------------------------------ 3 design brief */
  let brief = null;     // {loading} | {data, copied} | {err}
  async function openBrief() {
    brief = {loading: true}; render();
    try { brief = {data: await api('/api/brief')}; } catch (e) { brief = {err: e.message}; }
    render();
  }
  function renderMd(md) {   // same tiny renderer as the design: headings, lists, bold/italic, quotes, checkboxes
    const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/\*(.+?)\*/g, '<i>$1</i>');
    const out = []; let list = 0;
    const close = to => { while (list > to) { out.push('</ul>'); list--; } };
    for (const raw of md.split('\n')) {
      const m = raw.match(/^(\s*)- (\[ \] )?(.*)$/);
      if (m) { const depth = m[1].length >= 2 ? 2 : 1; while (list < depth) { out.push('<ul>'); list++; } close(depth);
        out.push(`<li>${m[2] ? '<span class="cb"></span>' : ''}${inline(m[3])}</li>`); continue; }
      close(0);
      if (raw.startsWith('### ')) out.push(`<h4>${inline(raw.slice(4))}</h4>`);
      else if (raw.startsWith('## ')) out.push(`<h3>${inline(raw.slice(3))}</h3>`);
      else if (raw.startsWith('# ')) out.push(`<h2>${inline(raw.slice(2))}</h2>`);
      else if (raw.startsWith('> ')) out.push(`<blockquote>${inline(raw.slice(2))}</blockquote>`);
      else if (raw === '---') out.push('<hr/>');
      else if (raw.trim()) out.push(`<p>${inline(raw)}</p>`);
    }
    close(0); return out.join('');
  }
  /* app.js hook: appended after the page */
  function modal() {
    if (!brief) return '';
    const body = brief.loading ? '<article class="md"><p class="reading">Writing the brief from the record</p></article>'
      : brief.err ? `<article class="md"><p class="flag bad">${esc(brief.err)}</p></article>` : `<article class="md">${renderMd(brief.data.markdown)}</article>`;
    return `<div class="modal-back" data-uix="brief-close"><div class="modal" role="dialog" aria-label="Design brief draft" data-uix="noop">
      <header><div><div class="eyebrow">Generated from the project record</div><h2 class="modal-title">Design brief · draft</h2></div>
        <div class="modal-act">${brief.data ? `<button class="btn sm" data-uix="brief-copy">${brief.copied ? 'Copied' : 'Copy Markdown'}</button><button class="btn sm primary" data-uix="brief-dl">Download .md</button>` : ''}
          <button class="icon-btn" data-uix="brief-close" aria-label="Close">×</button></div></header>${body}</div></div>`;
  }
  const briefButton = () => '<button class="ed-cta" data-uix="brief">Generate design brief</button>';

  /* ------------------------------------------------------------ 4 Pilot: 3D knowledge network */
  let pilotMode = 'net';     // 'net' (the design's Pilot tab) or 'brief' (the go / no-go flight brief)
  const opt = {labels: true, focus: false, proposed: true, orbit: false};
  const neighbours = id => { const s = new Set([id]); for (const e of S.edges) { if (e.src === id) s.add(e.dst); if (e.dst === id) s.add(e.src); } return s; };
  function network() {
    const sel = ui.sel && D.byId[ui.sel] ? ui.sel : null;
    const toggles = [['labels', 'Labels'], ['focus', 'Focus neighborhood'], ['proposed', 'Proposed links'], ['orbit', 'Auto-orbit']];
    return `<div class="twin net">
      <div class="twin-canvas" id="net3d"></div>
      <div class="hud">
        <div class="hud-col left">
          <section class="glass"><div class="eyebrow">Pilot</div><h1 class="site-name">Knowledge network</h1>
            <p class="body dim">Grouped by category. Drag to orbit, scroll to zoom, click a node.</p>
            <div class="netstats"><div><b class="mono">${S.nodes.length}</b><span>nodes</span></div><div><b class="mono">${S.edges.length}</b><span>relationships</span></div><div><b class="mono">${D.ready.length}</b><span>proposed</span></div></div></section>
          <section class="glass"><div class="glass-h"><h2>Categories</h2></div>
            <div class="chips">${CAT_ORDER.map(c => `<button class="fchip ${ui.off.has(c) ? '' : 'on'}" style="--c:${CATS[c].c}" data-act="cat" data-id="${c}"><i style="width:8px;height:8px;border-radius:50%;background:${CATS[c].c};display:inline-block"></i>${CATS[c].label} <span class="dim">${S.nodes.filter(n => D.cat[n.id] === c).length}</span></button>`).join('')}</div></section>
          <section class="glass"><div class="glass-h"><h2>Links</h2></div><div class="edge-key"><span class="k-app">approved</span><span class="k-prop">proposed</span></div></section>
        </div>
        <div class="hud-top stack">
          <div class="glass net-search">${askBar('pilot')}</div>
          <div class="toolbar glass" role="toolbar" aria-label="Network view"><button class="btn sm" data-uix="net-reset">Reset view</button><span class="sep"></span>
            ${toggles.map(([k, l]) => `<label class="toggle ${opt[k] ? 'on' : ''}"><input type="checkbox" data-uix-toggle="${k}" ${opt[k] ? 'checked' : ''}>${l}</label>`).join('')}
            <span class="sep"></span><button class="btn sm" data-uix="pilot-brief">Flight brief</button></div>
        </div>
        <div class="hud-col right"><section class="glass">${sel
          ? inspector() + `<div class="ins-act" style="margin-top:10px"><button class="ed-link" data-uix="open-canvas">Open in canvas</button><button class="ed-link dim" data-uix="net-desel">Close</button></div>`
          : '<p class="body dim">Click a node to see its category, status, summary and connections.</p>'}</section></div>
      </div></div>`;
  }
  /* app.js hook */
  function pilotPage() { return pilotMode === 'net' ? network() : null; }
  const inNet = () => ui.tab === 'pilot' && pilotMode === 'net';

  const net = {T: null, loading: null, root: null, sig: '', raf: 0, meshes: {}, lines: [], chips: {}, tags: [], cam: null,
    home: {pos: [310, 250, 460], target: [45, 45, 0]},      // the design's camera, aimed a little higher so the graph sits below the ask bar
    async mount() {
      const host = $('#net3d'); if (!host) return;
      if (!net.root) { net.root = document.createElement('div'); net.root.id = 'net3d-root'; net.root.innerHTML = '<div class="net-msg">Loading the 3D view…</div>'; }
      host.appendChild(net.root);
      if (!net.T) {
        net.loading = net.loading || import('https://cdn.jsdelivr.net/npm/three@0.172.0/build/three.module.js').then(m => { net.T = m; net.init(); })
          .catch(() => { net.root.innerHTML = '<div class="net-msg">The 3D view needs the three.js library from the internet and could not load it.<br>Use Flight brief, or the PM tab, in the meantime.</div>'; });
        await net.loading; if (!net.T) return;
      }
      net.size(); net.refresh(); net.loop();
    },
    init() {
      const T = net.T; net.root.innerHTML = '';
      net.renderer = new T.WebGLRenderer({antialias: true}); net.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
      net.root.appendChild(net.renderer.domElement);
      net.labels = document.createElement('div'); net.labels.id = 'net3d-labels'; net.root.appendChild(net.labels);
      net.scene = new T.Scene(); net.scene.background = new T.Color('#ffffff'); net.scene.fog = new T.Fog('#ffffff', 500, 1100);
      net.scene.add(new T.AmbientLight(0xffffff, 1.6)); const pl = new T.PointLight(0xffffff, 1.2, 0, 0); pl.position.set(0, 300, 300); net.scene.add(pl);
      net.group = new T.Group(); net.scene.add(net.group);
      net.camera = new T.PerspectiveCamera(45, 1, 1, 4000); net.ray = new T.Raycaster();
      net.reset();
      const el = net.renderer.domElement; let drag = null;
      el.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY, moved: false}; el.setPointerCapture(e.pointerId); });
      el.addEventListener('pointermove', e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true; drag.x = e.clientX; drag.y = e.clientY;
        net.cam.theta -= dx * .006; net.cam.phi = Math.max(.15, Math.min(Math.PI - .15, net.cam.phi - dy * .006)); });
      el.addEventListener('pointerup', e => { const d = drag; drag = null; if (d && !d.moved) net.pick(e); });
      el.addEventListener('wheel', e => { e.preventDefault(); net.cam.r = Math.max(120, Math.min(1200, net.cam.r * (e.deltaY > 0 ? 1.1 : 1 / 1.1))); }, {passive: false});
      new ResizeObserver(() => net.size()).observe(net.root);
    },
    reset() { const T = net.T, p = new T.Vector3(...net.home.pos), t = new T.Vector3(...net.home.target), d = p.clone().sub(t);
      net.cam = {t, r: d.length(), theta: Math.atan2(d.x, d.z), phi: Math.acos(d.y / d.length())}; },
    size() { if (!net.renderer) return; const w = net.root.clientWidth || 1, h = net.root.clientHeight || 1; net.renderer.setSize(w, h, false); net.camera.aspect = w / h; net.camera.updateProjectionMatrix(); },
    place() {      // illustrative placement, as in the design: one cluster per category, nodes spread on a small shell
      const cats = [...CAT_ORDER, 'none'], pos = {}, centers = {};
      cats.forEach((c, i) => { const ns = S.nodes.filter(n => (D.cat[n.id] || 'none') === c); if (!ns.length) return;
        const a = i / cats.length * Math.PI * 2, ctr = c === 'none' ? [45, -15, 0] : [45 + Math.cos(a) * 185, -15 + (i % 2 ? 55 : -45), Math.sin(a) * 185];
        const rad = 26 + ns.length * 6; centers[c] = {ctr, count: ns.length};
        ns.forEach((n, k) => { const y = ns.length === 1 ? 0 : 1 - 2 * (k + .5) / ns.length, r = Math.sqrt(1 - y * y), th = k * 2.399963;
          pos[n.id] = [ctr[0] + Math.cos(th) * r * rad, ctr[1] + y * rad * .8, ctr[2] + Math.sin(th) * r * rad]; }); });
      return {pos, centers};
    },
    build() {
      const T = net.T, g = net.group; while (g.children.length) g.remove(g.children[0]);
      net.labels.innerHTML = ''; net.meshes = {}; net.lines = []; net.chips = {}; net.tags = [];
      const {pos, centers} = net.place(); net.pos = pos;
      for (const c in centers) { const {ctr, count} = centers[c], col = c === 'none' ? UNCL : CATS[c].c;
        const halo = new T.Mesh(new T.SphereGeometry(34 + count * 8, 24, 24), new T.MeshBasicMaterial({color: col, transparent: true, opacity: .07, depthWrite: false}));
        halo.position.set(...ctr); g.add(halo);
        const tag = document.createElement('div'); tag.className = 'cluster-tag'; tag.style.color = col; tag.textContent = c === 'none' ? 'Unclassified' : CATS[c].label;
        net.labels.appendChild(tag); net.tags.push({el: tag, p: new T.Vector3(ctr[0], ctr[1] - (40 + count * 8), ctr[2])}); }
      for (const e of S.edges) { if (!pos[e.src] || !pos[e.dst]) continue;
        const line = new T.Line(new T.BufferGeometry().setFromPoints([new T.Vector3(...pos[e.src]), new T.Vector3(...pos[e.dst])]), new T.LineBasicMaterial({color: 0x8c8c88, transparent: true, opacity: .6}));
        line.userData = e; g.add(line); net.lines.push(line); }
      for (const n of S.nodes) { const col = D.cat[n.id] ? CATS[D.cat[n.id]].c : UNCL, r = n.importance >= .75 ? 7 : n.importance >= .5 ? 5.5 : 4.5;
        const m = new T.Mesh(new T.SphereGeometry(r, 24, 24), new T.MeshStandardMaterial({color: col, emissive: col, emissiveIntensity: .35, transparent: true}));
        m.position.set(...pos[n.id]); m.userData = {id: n.id, r}; g.add(m); net.meshes[n.id] = m;
        const glow = new T.Mesh(new T.SphereGeometry(r * 2.1, 16, 16), new T.MeshBasicMaterial({color: col, transparent: true, opacity: .14, depthWrite: false})); m.add(glow); m.userData.glow = glow;
        const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'node-chip' + (D.cat[n.id] ? '' : ' uncl'); chip.dataset.id = n.id; chip.textContent = n.title;
        chip.onclick = ev => { ev.stopPropagation(); net.select(n.id); }; net.labels.appendChild(chip); net.chips[n.id] = {el: chip, p: m.position, dy: r + 8}; }
      net.ghosts = [];      // proposals waiting for review: a hollow node with dashed links to what it would touch
      for (const it of D.ready) { const links = ((it.proposal && it.proposal.links) || []).filter(l => pos[l.target]); if (!links.length) continue;
        const c = links.reduce((a, l) => a.map((v, i) => v + pos[l.target][i] / links.length), [0, 0, 0]), p = new T.Vector3(c[0] + 26, c[1] + 34, c[2] + 18);
        const m = new T.Mesh(new T.SphereGeometry(5, 12, 12), new T.MeshBasicMaterial({color: 0x8c8c88, wireframe: true})); m.position.copy(p); g.add(m);
        const objs = [m];
        for (const l of links) { const line = new T.Line(new T.BufferGeometry().setFromPoints([p, new T.Vector3(...pos[l.target])]), new T.LineDashedMaterial({color: 0x8c8c88, dashSize: 6, gapSize: 5, transparent: true, opacity: .6}));
          line.computeLineDistances(); g.add(line); objs.push(line); }
        const chip = document.createElement('button'); chip.type = 'button'; chip.className = 'node-chip ghost'; chip.textContent = (it.proposal.title || it.label) + ' · proposed';
        chip.onclick = () => { location.hash = 'data'; }; net.labels.appendChild(chip); const lab = {el: chip, p, dy: 13}; net.tags.push(lab); net.ghosts.push({objs, lab}); }
    },
    refresh() {        // rebuild when the graph changed, then restyle for selection, question and toggles
      if (!net.T || !net.root || !S) return;
      const sig = S.nodes.map(n => n.id + (D.cat[n.id] || '')).join() + '|' + S.edges.length + '|' + D.ready.map(i => i.id).join();
      if (sig !== net.sig) { net.sig = sig; net.build(); }
      const T = net.T, sel = ui.sel && net.meshes[ui.sel] ? ui.sel : null, near = sel ? neighbours(sel) : new Set(), h = hits(), q = !h && (ui.q || '').trim().toLowerCase();
      const dim = id => id !== sel && (ui.off.has(D.cat[id] || 'none') || (h && !h.has(id)) || (q && !lowerHit(D.byId[id], q)) || (opt.focus && sel && !near.has(id)));
      for (const id in net.meshes) { const m = net.meshes[id], off = dim(id), on = id === sel;
        m.material.opacity = off ? .18 : 1; m.userData.glow.material.opacity = off ? .02 : on ? .22 : .14; m.scale.setScalar(on ? 1.35 : 1);
        const c = net.chips[id].el; c.classList.toggle('on', on); c.classList.toggle('dim', !!off); c.style.display = opt.labels ? '' : 'none'; }
      for (const l of net.lines) { const e = l.userData, hot = sel && (e.src === sel || e.dst === sel), off = (opt.focus && sel && !hot) || dim(e.src) && dim(e.dst) || (h && !(h.has(e.src) && h.has(e.dst)));
        l.material.color.set(hot ? 0x0a0a0a : 0x8c8c88); l.material.opacity = off ? .08 : hot ? .95 : .6; }
      if (net.ring) { net.group.remove(net.ring); net.ring = null; }
      if (sel) { const m = net.meshes[sel], r = m.userData.r; net.ring = new T.Mesh(new T.RingGeometry(r * 2, r * 2.3, 48), new T.MeshBasicMaterial({color: 0x0a0a0a, side: T.DoubleSide, transparent: true, opacity: .8}));
        net.ring.rotation.x = Math.PI / 2; net.ring.position.copy(m.position); net.group.add(net.ring); }
      for (const gh of net.ghosts || []) { gh.objs.forEach(o => o.visible = opt.proposed); gh.lab.el.style.display = opt.proposed && opt.labels ? '' : 'none'; }
      net.tags.forEach(t => { if (!t.el.classList.contains('ghost')) t.el.style.display = opt.labels ? '' : 'none'; });
    },
    pick(e) { const T = net.T, b = net.renderer.domElement.getBoundingClientRect();
      net.ray.setFromCamera(new T.Vector2((e.clientX - b.left) / b.width * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1), net.camera);
      const hit = net.ray.intersectObjects(Object.values(net.meshes), false)[0]; net.select(hit ? hit.object.userData.id : null); },
    select(id) { ui.sel = id; ui.link = null; render(); if (id) loadDetail(id); },
    loop() { cancelAnimationFrame(net.raf);
      const tick = () => { if (!net.root.isConnected || !inNet()) return;
        const c = net.cam; if (opt.orbit) c.theta += .0025;
        net.camera.position.set(c.t.x + c.r * Math.sin(c.phi) * Math.sin(c.theta), c.t.y + c.r * Math.cos(c.phi), c.t.z + c.r * Math.sin(c.phi) * Math.cos(c.theta));
        net.camera.lookAt(c.t); net.renderer.render(net.scene, net.camera);
        const w = net.root.clientWidth, hh = net.root.clientHeight, v = new net.T.Vector3();
        const put = (el, p, dy) => { if (el.style.display === 'none') return; v.copy(p); v.y += dy || 0; v.project(net.camera);
          if (v.z > 1) { el.style.visibility = 'hidden'; return; } el.style.visibility = '';
          el.style.transform = `translate(-50%,-100%) translate(${((v.x + 1) / 2 * w).toFixed(1)}px,${((1 - v.y) / 2 * hh).toFixed(1)}px)`; };
        for (const id in net.chips) put(net.chips[id].el, net.chips[id].p, net.chips[id].dy);
        for (const t of net.tags) put(t.el, t.p, t.dy);
        net.raf = requestAnimationFrame(tick); };
      net.raf = requestAnimationFrame(tick); },
  };
  /* app.js hook: after every render */
  function afterRender() { if (inNet()) net.mount(); }

  /* ------------------------------------------------------------ events */
  document.addEventListener('click', async e => {
    const b = e.target.closest('[data-uix]'); if (!b) return;
    const a = b.dataset.uix;
    if (a === 'noop') { e.stopPropagation(); return; }
    if (a === 'ob-pick') { ob.ans[STEPS[ob.step].key] = b.dataset.v; ob.step++; render(); window.scrollTo(0, 0); }
    else if (a === 'ob-back') { ob.step = Math.max(0, ob.step - 1); render(); }
    else if (a === 'ob-again') { ob.step = 0; ob.ans = {}; render(); }
    else if (a === 'ob-skip') { ob.skipped = true; render(); }
    else if (a === 'ob-go' || a === 'ob-stay') { ob.saved = {...ob.ans}; store.set('yb.onboarding', ob.saved); const st = startFor(ob.saved); render(); if (a === 'ob-go') goTo(st); }
    else if (a === 'ob-open' || a === 'ob-retake') { ob.saved = null; store.set('yb.onboarding', null); ob.skipped = false; ob.step = 0; ob.ans = {}; render(); window.scrollTo({top: 0}); }
    else if (a === 'go-start') goTo(startFor(ob.saved));
    else if (a === 'try') runGuide(b.dataset.q);
    else if (a === 'clear') clearGuide();
    else if (a === 'brief') openBrief();
    else if (a === 'brief-close') { if (b.classList.contains('modal-back') && e.target.closest('.modal')) return; brief = null; render(); }
    else if (a === 'brief-copy') { try { await navigator.clipboard.writeText(brief.data.markdown); brief.copied = true; } catch { toast('Could not copy. Use Download instead.'); } render(); }
    else if (a === 'brief-dl') { const l = document.createElement('a'); l.href = URL.createObjectURL(new Blob([brief.data.markdown], {type: 'text/markdown'})); l.download = brief.data.filename; l.click(); }
    else if (a === 'net-reset') { if (net.T) net.reset(); }
    else if (a === 'net-desel') net.select(null);
    else if (a === 'open-canvas') { location.hash = 'pm'; }
    else if (a === 'pilot-brief') { pilotMode = 'brief'; render(); window.scrollTo(0, 0); }
    else if (a === 'pilot-net') { pilotMode = 'net'; render(); }
  });
  document.addEventListener('change', e => { const k = e.target.dataset && e.target.dataset.uixToggle; if (!k) return;
    opt[k] = e.target.checked; e.target.closest('.toggle').classList.toggle('on', opt[k]); net.refresh(); });
  document.addEventListener('submit', e => { const f = e.target; if (f.dataset.guide == null) return; e.preventDefault(); runGuide(f.q.value); });
  document.addEventListener('input', e => { const f = e.target.closest('[data-guide]'); if (!f) return;
    ui.q = e.target.value; if (guide && guide.q !== ui.q.trim()) guide = null; if (f.dataset.guide === 'pilot') net.refresh(); });
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && brief) { brief = null; render(); } });

  return {sync: (s, d) => { S = s; D = d; }, page, startStrip, retake, askBar, hits, modal, briefButton, pilotPage, afterRender, inNet,
          netLink: () => '<button class="ed-link" data-uix="pilot-net">Knowledge network</button>'};
};
