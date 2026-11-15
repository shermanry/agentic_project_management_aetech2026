/* YBuild front end: the AeroGraph design (aero.css) on the live north star API.
   No build step. Five pages by hash: #overview #client #pm #pilot #data. Add ?presenter for the demo controls.
   Everything shown comes from GET /api/state; the page re-reads it whenever /api/events says something changed. */
(() => {
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const PRESENTER = new URLSearchParams(location.search).has('presenter');
const TABS = [['overview', 'Overview'], ['client', 'Client'], ['pm', 'PM'], ['pilot', 'Expert']];   // the Parking lot tab is now the + Add drawer (drop files anywhere)
const CRUMB = {overview: 'Overview', client: 'Client view', pm: 'Knowledge canvas', pilot: 'Expert view'};

/* The design groups nodes by domain; the back end types them by lifecycle (decision, blocker, ...).
   Both are shown: the type is the card's "kind", the domain is worked out from tags and wording. */
const CATS = {
  requirements: {label: 'Requirements', c: '#7F88D9', k: ['client', 'scope', 'rfi', 'deliverable', 'requirement', 'proceed', 'estimate', 'brief', 'contract']},
  site:         {label: 'Site',         c: '#57A8A4', k: ['site', 'facade', 'tower', 'roof', 'elevation', 'building', 'mullion', 'podium']},
  regulatory:   {label: 'Regulatory',   c: '#BD7EC8', k: ['permit', 'regulation', 'rule', 'faa', 'tfr', 'airspace', 'laanc', 'dhs', 'nypd', 'approval', 'authorization', 'register']},
  weather:      {label: 'Weather',      c: '#67A6DB', k: ['weather', 'wind', 'forecast', 'storm', 'gust', 'rain']},
  safety:       {label: 'Safety',       c: '#E5A368', k: ['safety', 'risk', 'hazard', 'insurance', 'maintenance', 'crew', 'interference']},
  technical:    {label: 'Technical',    c: '#6E8DDD', k: ['drone', 'equipment', 'gps', 'photogrammetry', 'metadata', 'sensor', 'camera', 'compass', 'model', 'flight-plan']},
  schedule:     {label: 'Schedule',     c: '#D78091', k: ['schedule', 'flight', 'date', 'thursday', 'deadline', 'window', 'week']},
};
const CAT_ORDER = Object.keys(CATS);
const UNCL = '#8FA3B8';
const TYPE_CAT = {constraint: 'safety', data_feed: 'technical', deliverable: 'requirements', blocker: 'safety', document: 'requirements',
                  entity: 'site', event: 'schedule', discovery: 'site', decision: 'schedule'};
const TYPE_LABEL = {decision: 'Decision', discovery: 'Discovery', event: 'Event', data_feed: 'Live feed', deliverable: 'Deliverable',
                    blocker: 'Blocker', constraint: 'Constraint', document: 'Document', entity: 'Entity'};
const TYPE_ICON = {decision: '◆', discovery: '✦', event: '◷', data_feed: '≋', deliverable: '▣', blocker: '⊘', constraint: '⊟', document: '▤', entity: '●'};
const FLAG = {at_risk: 'At risk', blocked: 'Blocked', reopened: 'Decide again'};
/* Wires run from what something rests on to what rests on it, left to right. */
const REVERSED = new Set(['depends_on', 'derived_from', 'about', 'supersedes', 'part_of']);
const VERB = {depends_on: ['rests on', 'feeds'], derived_from: ['derived from', 'source of'], about: ['about', 'context for'],
              supersedes: ['replaces', 'replaced by'], blocks: ['blocks', 'blocked by'], evidence_for: ['evidence for', 'evidence'],
              similar_to: ['similar to', 'similar to'], part_of: ['part of', 'includes']};
const LEVEL = {red: '#c8452f', amber: '#e0a13a', none: '#ffffff'};
const LEVEL_WORD = {red: 'At risk or blocked', amber: 'Being looked at', none: 'Nothing open'};
const CW = 202, CH = 114, COL = 318, ROW = CH + 46;

let S = null;            // last /api/state
let D = null;            // derived from S
let live = false, dirty = false;
const ui = {tab: 'overview', sel: null, mode: 'tree', off: new Set(), q: '', view: null, pos: {}, ask: {}, who: 'Mary', adding: false,
            search: null, link: null, detail: {}, busy: false, intake: false, feed: null, picked: new Set(), batch: null, batchErr: {}, addMenu: false, jobs: []};
try { ui.who = localStorage.getItem('yb.who') || 'Mary'; } catch {}

/* ------------------------------------------------------------------ data */
/* Reached as /p/<project id>/app/ when another project is opened through one shared link: every request then
   carries that prefix, and the app passes it on to that project's copy. */
const BASE = (location.pathname.match(/^\/p\/[^/]+/) || [''])[0];
async function api(path, opt) {
  const r = await fetch(BASE + path, opt);
  if (!r.ok) {
    let m = r.statusText;
    try { const j = await r.json(); m = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(m);
  }
  return r.json();
}
const post = (path, body) => api(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body || {})});

function catOf(n) {
  const tags = (n.tags || []).join(' ').toLowerCase(), title = (n.title || '').toLowerCase(), sum = (n.summary || '').toLowerCase();
  let best = null, score = 0;
  for (const id of CAT_ORDER) {
    let s = 0;
    for (const k of CATS[id].k) { if (tags.includes(k)) s += 3; if (title.includes(k)) s += 2; if (sum.includes(k)) s += .5; }
    if (s > score) { score = s; best = id; }
  }
  return best || TYPE_CAT[n.type] || null;
}

function derive() {
  const byId = {}, cat = {}, deg = {}, cause = {}, hist = {};
  for (const n of S.nodes) { byId[n.id] = n; cat[n.id] = catOf(n); deg[n.id] = 0; }
  const flow = [];
  for (const e of S.edges) {
    if (!byId[e.src] || !byId[e.dst]) continue;
    deg[e.src]++; deg[e.dst]++;
    if (e.type === 'similar_to') continue;
    flow.push(REVERSED.has(e.type) ? {a: e.dst, b: e.src, e} : {a: e.src, b: e.dst, e});
  }
  const events = [...S.events].sort((x, y) => x.seq - y.seq);
  for (const ev of events) {
    const fx = effectsOf(ev.payload);
    for (const f of fx) {
      (hist[f.node_id] ||= []).push({ev, f});
      if (/clear/i.test(f.change || '')) delete cause[f.node_id]; else cause[f.node_id] = {why: f.why, change: f.change, ev};
    }
    const own = ev.payload && (ev.payload.node_id || ev.payload.source_node);
    if (own && byId[own]) (hist[own] ||= []).push({ev, f: null});
  }
  const flagged = S.nodes.filter(n => FLAG[n.status]);
  const open = S.items.filter(i => ['processing', 'refining', 'ready', 'failed'].includes(i.status));
  D = {byId, cat, deg, flow, cause, hist, flagged, open, loose: S.nodes.filter(n => !deg[n.id]), ready: open.filter(i => i.status === 'ready'), events};
}
const effectsOf = p => !p ? [] : Array.isArray(p.effects) ? p.effects : (p.effects && Array.isArray(p.effects.effects) ? p.effects.effects : []);
const tone = n => n.status === 'blocked' ? 'bad' : FLAG[n.status] || ['waiting', 'changed'].includes(n.status) ? 'warn'
  : ['decided', 'active', 'healthy', 'placed', 'scheduled', 'done', 'resolved', 'approved'].includes(n.status) ? 'ok' : 'muted';
const statusLabel = n => FLAG[n.status] || String(n.status || n.state || '').replace(/_/g, ' ');
const when = t => { const d = new Date(t * 1000), now = Date.now(), m = Math.round((now - d) / 60000);
  return m < 1 ? 'just now' : m < 60 ? m + ' min ago' : m < 1440 ? Math.round(m / 60) + ' h ago' : d.toLocaleDateString('en-US', {month: 'short', day: 'numeric'}); };
const itemTitle = it => (it.proposal && it.proposal.title) || it.label || 'Untitled';
const nodeBtn = (id, text) => `<button data-act="sel" data-id="${esc(id)}">${esc(text ?? (D.byId[id] ? D.byId[id].title : id))}</button>`;

let refreshing = null, again = false;
async function refresh() {
  if (refreshing) { again = true; return refreshing; }
  refreshing = (async () => {
    try { S = await api('/api/state'); derive(); if (ui.sel && !D.byId[ui.sel]) ui.sel = null; ui.detail = {}; safeRender(); if (ui.sel && ui.tab === 'pm') loadDetail(ui.sel); }
    catch (e) { if (!S) $('#root').innerHTML = `<div class="app light"><main class="ed-page"><header class="ov-hero"><h1 class="ed-display md">Not connected</h1><p class="ed-lede">${esc(e.message)}. Start the north star app, then reload.</p></header></main></div>`; }
    finally { refreshing = null; if (again) { again = false; refresh(); } }
  })();
  return refreshing;
}
function safeRender() {            // do not wipe a field someone is typing in
  const a = document.activeElement;
  if (a && /INPUT|TEXTAREA/.test(a.tagName) && a.value && a.type !== 'file') { dirty = true; return; }
  render();
}
document.addEventListener('focusout', () => { if (dirty) setTimeout(() => { if (dirty) safeRender(); }, 150); });

function toast(m) { const t = $('#toast'); t.textContent = m; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 4200); }

/* ------------------------------------------------------------------ shell */
function render() {
  dirty = false;
  if (!S) return;
  const y = window.scrollY, gate = UIX.gated(), tab = gate ? 'overview' : ui.tab;   // UIX: until the survey is answered it is the only page
  const counts = {pm: D.flagged.length};
  secN = 0;
  UIX.sync(S, D);
  const page = UIX.page(tab) || {overview, client, pm, pilot}[tab]();   // UIX: onboarding can stand in for the Overview
  $('#root').innerHTML = `<div class="app light tab-${tab} view-${tab === 'pm' ? 'pm' : 'monitor'} ${UIX.inNet() ? 'net-on' : ''} ${gate ? 'ob-gate' : ''}">
  <header class="topbar">
    <a class="brand" href="#overview" style="text-decoration:none;display:flex;align-items:center;gap:14px">
      <img src="logo.png" alt="YBuild" style="height:26px;width:auto;display:block">
      <span class="brand-sub" style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Decision record</span>
    </a>
    <nav class="crumbs"><span>Projects</span><span class="sl">›</span><b>${esc(S.project.name)}</b><span class="sl">›</span><span>${CRUMB[tab]}</span></nav>
    <nav class="seg views">${TABS.map(([id, l]) => `<button class="${id === tab ? 'on' : ''}" data-act="tab" data-id="${id}">${l}${counts[id] ? `<sup class="tab-count">${counts[id]}</sup>` : ''}</button>`).join('')}</nav>
    <div class="status-area">
      ${projectMenu()}
      <div class="add-wrap"><button class="add-btn" data-act="addmenu" aria-haspopup="menu" aria-expanded="${ui.addMenu ? 'true' : 'false'}">+ Add${D.open.length ? `<sup class="tab-count">${D.open.length}</sup>` : ''} <span class="caret">▾</span></button>
        ${ui.addMenu ? `<div class="add-menu${ui.addLeft ? ' from-left' : ''}" role="menu">
          <button role="menuitem" data-act="pickfiles"><b>Files</b><small>One or more files from this computer</small></button>
          <button role="menuitem" data-act="pickdir"><b>A folder</b><small>Every file inside becomes its own item</small></button>
          <button role="menuitem" data-act="drive"><b>Google Drive folder</b><small>Paste a link to a shared folder</small></button>
          <button role="menuitem" data-act="intake"><b>A note</b><small>Type or paste text</small></button>
          <button role="menuitem" data-act="intake" class="sep"><b>Waiting to be placed${D.open.length ? ` · ${D.open.length}` : ''}</b><small>Review what has been read</small></button>
        </div>` : ''}</div>
      <span class="live ${live ? '' : 'off'}" id="live"><i></i>${live ? 'Live' : 'Offline'}</span>
      <label class="who">As <select data-change="who">${S.people.filter(p => p.role !== 'client').map(p => `<option ${p.name === ui.who ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>
      <div class="clock"><span class="clock-t" id="clock">${clock()}</span><span class="clock-z">New York</span></div>
    </div>
  </header>
  ${PRESENTER ? presenterBar() : ''}
  ${page}
  ${intakeDrawer()}
  ${UIX.modal()}
  </div>`;
  if (tab === 'pm') mountCanvas(); else window.scrollTo(0, y);
  UIX.afterRender();
}
const clock = () => new Date().toLocaleTimeString('en-US', {timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false});
setInterval(() => { const c = $('#clock'); if (c) c.textContent = clock(); }, 20000);

/* Example projects each run as their own copy of the app (Ryan/northstar/projects.json). The menu jumps to the
   same tab of another one; a project that is not running is listed but cannot be picked. */
let P = [];
async function loadProjects() { try { P = (await api('/api/projects')).projects || []; } catch { P = []; } }
function projectMenu() {      // in the status area: the design hides the breadcrumb, so the menu sits beside "As"
  if (!P.length) return '';
  return `<label class="who">Project <select class="proj" data-change="project" aria-label="Switch project" title="Switch to another project, or add a new one">${P.map(p =>
    `<option value="${esc(p.id)}" ${p.current ? 'selected' : ''} ${p.current || p.running || p.available ? '' : 'disabled'}>${esc(p.name)}${p.current || p.running ? '' : p.available ? ' · stopped, pick to start' : ' · not installed'}</option>`).join('')}
    <option value="__new">+ Add new project…</option></select></label>`;
}
/* Each project is its own copy of the app on its own port. On the host computer switching opens that port; through
   a shared link (no port in the address) it opens /p/<project id>/app/, which the app passes on to that copy. */
const viaSharedLink = () => !!BASE || (!location.port && !/^(localhost|127\.0\.0\.1)$/.test(location.hostname));
function openProject(p) {
  location.href = viaSharedLink() ? `/p/${encodeURIComponent(p.id)}/app/${location.search}${location.hash}`
    : `${location.protocol}//${location.hostname}:${p.port}/app/${location.search}${location.hash}`;
}
async function pickProject(sel) {
  const v = sel.value, cur = P.find(p => p.current); sel.value = cur ? cur.id : '';        // the menu shows the current project until the switch happens
  try {
    if (v === '__new') {
      const name = (prompt('Name of the new project', '') || '').trim(); if (!name) return;
      toast(`Creating “${name}”…`);
      const p = await post('/api/projects', {name, by: ui.who}); await loadProjects(); render(); openProject(p);
    } else {
      const p = P.find(x => x.id === v); if (!p || p.current) return;
      if (!p.running) { toast(`Starting “${p.name}”…`); await post(`/api/projects/${p.id}/start`); await loadProjects(); }
      openProject(p);
    }
  } catch (err) { toast(err.message); }
}

function presenterBar() {
  const sc = (S.feeds && S.feeds.scenarios) || [];
  const names = Array.isArray(sc) ? sc.map(x => x.id || x) : Object.keys(sc);
  const r = S.replay || {}, cap = r.caption || {};
  return `<div class="presenter"><b>Presenter</b>
    <button data-act="goto" data-id="start" title="Empty project">⏮ Empty</button><button data-act="goto" data-id="setup" title="Project as planned, before the story">Set up</button>
    <button data-act="replay" data-id="back">◂ Back</button><button data-act="replay" data-id="forward">Forward ▸</button>
    <span class="dim">${r.pos ?? 0} of ${r.total ?? 0}</span>
    <span style="flex:1 1 260px;min-width:0"><b style="text-transform:none;letter-spacing:0;font-size:13px">${esc(cap.title || '')}</b> <span class="dim">${esc(cap.story || '')}</span>${r.error ? ` <span class="flag bad">${esc(r.error)}</span>` : ''}</span>
    <select data-change="inject"><option value="">Simulate a change…</option>${names.map(n => `<option value="${esc(n)}">${esc(String(n).replace(/_/g, ' '))}</option>`).join('')}</select>
    <button data-act="feedsrun" title="Poll every live feed now">Check feeds</button>
    <button data-act="reset">Reset</button></div>`;
}

/* ------------------------------------------------------------------ building (state.parts: a level rolled up from the nodes linked to each part) */
function buildingSVG(only) {
  const parts = {}; for (const p of S.parts || []) parts[p.part] = p;
  const fill = k => { const p = parts[k]; if (!p) return '#f4f4f2'; if (only && only !== k) return '#ececea'; return LEVEL[p.level] || '#fff'; };
  const g = (k, shape) => { const p = parts[k]; return `<g ${p ? `data-act="sel" data-id="${p.id}" style="cursor:pointer"` : ''}><title>${esc(p ? `${p.title}: ${LEVEL_WORD[p.level]}` : k)}</title>${shape.replace('/>', ` fill="${fill(k)}" stroke="#0a0a0a" stroke-width="1.2" stroke-linejoin="round"/>`)}</g>`; };
  const lines = []; for (let y = 96; y < 250; y += 14) lines.push(`<path d="M60 ${y + 8}L120 ${y + 20}L180 ${y + 8}" fill="none" stroke="#0a0a0a" stroke-opacity=".13"/>`);
  return `<svg viewBox="0 0 240 320" role="img" aria-label="Building, coloured by what is open on each part" style="display:block;width:100%;height:100%">
    ${g('roof', '<path d="M60 44L120 32L180 44L120 56Z"/>')}
    ${g('upper', '<path d="M60 44L120 56L180 44L180 100L120 112L60 100Z"/>')}
    ${g('north', '<path d="M60 100L120 112L120 262L60 250Z"/>')}
    ${g('east', '<path d="M120 112L180 100L180 250L120 262Z"/>')}
    ${g('entrance', '<path d="M40 252L120 268L200 252L200 280L120 296L40 280Z"/>')}
    <path d="M120 56V112" stroke="#0a0a0a" stroke-opacity=".3"/>${lines.join('')}</svg>`;
}
function partTiles() {
  const ps = S.parts || [];
  if (!ps.length) return `<p class="ed-empty">No building parts are in the record yet.</p>`;
  return `<div class="ed-tiles">${ps.map(p => `<button class="ed-tile" data-act="sel" data-id="${p.id}"><span class="frame" style="display:block;padding:10px">${buildingSVG(p.part)}</span>
    <span class="t" style="font-size:15px">${esc(p.title)}</span><span class="ed-meta ${p.level === 'red' ? 'flag bad' : p.level === 'amber' ? 'flag' : ''}">${p.open ? `${p.open} open` : 'Nothing open'} · ${p.linked.length} linked</span></button>`).join('')}</div>
    <div class="ed-key"><span><i class="ed-glyph" style="background:${LEVEL.red};border-color:${LEVEL.red}"></i>At risk or blocked</span><span><i class="ed-glyph" style="background:${LEVEL.amber};border-color:${LEVEL.amber}"></i>Being looked at</span><span><i class="ed-glyph"></i>Nothing open</span></div>`;
}
function partRows(plain) {
  return (S.parts || []).map(p => { const open = p.linked.filter(l => l.rank);
    return `<li class="ed-row"><span class="t"><i class="ed-glyph" style="background:${LEVEL[p.level]};border-color:${p.level === 'none' ? 'var(--ink)' : LEVEL[p.level]}"></i>${esc(p.title)}</span>
      <span class="side"><span class="ed-meta ${p.level === 'red' ? 'flag bad' : p.level === 'amber' ? 'flag' : ''}">${esc(LEVEL_WORD[p.level])}</span></span>
      ${p.summary ? `<span class="sub">${esc(p.summary)}</span>` : ''}
      ${open.length ? `<ul class="fx">${open.map(l => `<li><span class="chg">${esc(plain ? 'Being looked at' : FLAG[l.status] || l.status)}</span>${plain ? `<span>${esc(l.title)}</span>` : nodeBtn(l.id, l.title)}<span class="y">${esc(l.reason)}</span></li>`).join('')}</ul>` : ''}</li>`; }).join('');
}

/* ------------------------------------------------------------------ rules (the analysis loop: runs only when a person asks) */
function rulesBlock() {
  const rules = S.rules || [], prop = rules.filter(r => r.status === 'proposed'), act = rules.filter(r => r.status === 'active');
  const running = (S.analysis && S.analysis.running) || ui.busy === 'rules';
  const row = r => `<li class="ed-row"><span class="t">${esc(r.name)}</span><span class="side"><span class="ed-meta ${r.status === 'proposed' ? 'flag' : ''}">${r.status === 'proposed' ? 'Suggested' : 'Active'}</span>
      ${r.status === 'proposed' ? `<button class="ed-link plain" data-act="rule" data-id="${esc(r.id)}" data-what="approve">Approve</button><button class="ed-link dim" data-act="rule" data-id="${esc(r.id)}" data-what="dismiss">Dismiss</button>`
        : `<button class="ed-link dim" data-act="rule" data-id="${esc(r.id)}" data-what="dismiss">Retire</button>`}</span>
      <span class="sub">${esc(r.describe || '')}</span>${r.why ? `<span class="sub"><span class="ed-meta">Why</span> ${esc(r.why)}</span>` : ''}</li>`;
  return `${prop.length || act.length ? `<ul class="ed-rows">${[...prop, ...act].map(row).join('')}</ul>` : `<p class="ed-empty">No rules yet. Rules decide what else gets flagged when something is accepted or a feed changes.</p>`}
    <div style="margin-top:22px;display:flex;gap:20px;align-items:center;flex-wrap:wrap"><button class="ed-cta" data-act="suggest" ${running ? 'disabled' : ''}>${running ? 'Reading the record…' : 'Suggest rules'}</button>
    <span class="ed-meta" style="text-transform:none;letter-spacing:0;max-width:60ch;line-height:1.4">Reads this project's graph and history with ${esc((S.analysis && S.analysis.model) || 'the analysis model')} and proposes up to three rules. About a minute. Nothing changes until a rule is approved.</span></div>`;
}

/* ------------------------------------------------------------------ shared pieces */
function fxList(fx, max = 6) {
  if (!fx.length) return '';
  return `<ul class="fx">${fx.slice(0, max).map(f => `<li><span class="chg">${esc(f.change)}</span>${nodeBtn(f.node_id, f.title)}<span class="y">${esc(f.why || '')}</span></li>`).join('')}${fx.length > max ? `<li class="y">and ${fx.length - max} more</li>` : ''}</ul>`;
}
function itemRow(it, full) {
  const p = it.proposal;
  if (it.status === 'processing' || it.status === 'refining' || !p)
    return `<li class="ed-row pk-row"><span class="t">${esc(itemTitle(it))}</span><span class="side">${it.status === 'failed'
      ? `<span class="flag bad">${esc(it.error || 'Could not be read')}</span><button class="ed-link dim" data-act="dismiss" data-id="${it.id}">Remove</button>`
      : `<span class="reading">Reading and placing</span>`}</span></li>`;
  const links = (p.links || []).map(l => `${(VERB[l.type] || [l.type])[0]} “${D.byId[l.target] ? D.byId[l.target].title : l.target}”`);
  const fx = effectsOf(p);
  return `<li class="ed-row pk-row"><span class="t"><label class="pk-pick"><input type="checkbox" data-pick="${it.id}" ${ui.picked.has(it.id) ? 'checked' : ''} ${ui.batch ? 'disabled' : ''} aria-label="Select ${esc(p.title)}"></label>${esc(p.title)}</span>
    ${ui.batchErr[it.id] ? `<span class="sub"><span class="flag bad">Not placed: ${esc(ui.batchErr[it.id])}</span></span>` : ''}
    <span class="side"><span class="pk-sg"><span class="ed-meta">→</span><b>${esc(TYPE_LABEL[p.type] || p.type)}</b><span class="ed-meta">${Math.round((p.confidence || 0) * 100)}%</span>
      <span class="ed-meta links">${esc(links.join(' · ') || 'no links proposed')}</span></span>
      <button class="ed-link plain" data-act="accept" data-id="${it.id}">Accept</button><button class="ed-link dim" data-act="dismiss" data-id="${it.id}">Dismiss</button></span>
    ${full && p.summary ? `<span class="sub">${esc(p.summary)}</span>` : ''}
    ${((it.source && it.source.answers) || []).map(x => `<span class="sub dim">${esc(x.by || 'Someone')} answered: ${esc(x.a)}</span>`).join('')}
    ${p.missing_details ? `<span class="sub"><span class="open-q" style="display:block">Jev asks: ${esc(p.missing_details)}</span></span>
      <form class="sub" data-answer="${it.id}" style="display:flex;gap:16px;align-items:baseline;flex-wrap:wrap"><input name="a" placeholder="Answer here. It is read again with what you say, and the links can change." autocomplete="off" style="border:0;border-bottom:1px solid var(--hair);background:none;padding:6px 0;flex:1 1 320px;max-width:620px;font-size:14px"><button class="ed-link plain">Answer and read again</button></form>` : ''}
    ${fx.length ? `<span class="sub ed-meta" style="margin-top:6px">If accepted, this would change</span>${fxList(fx, full ? 8 : 3)}` : full ? `<span class="sub">Accepting this changes nothing else.</span>` : ''}
    ${full ? `<span class="sub"><input data-reason="${it.id}" placeholder="Reason for accepting (kept in the record)" style="border:0;border-bottom:1px solid var(--hair);background:none;padding:6px 0;width:min(100%,520px);font-size:14px"></span>` : ''}
  </li>`;
}
/* Batch accept: a folder can leave dozens of items waiting. Tick some, or take all of them (or only the ones the
   agent is confident about), and they are approved one after another with each item's own proposal. */
const CONFIDENT = 0.7;
const readyItems = () => D.open.filter(i => i.proposal && !['processing', 'refining', 'failed'].includes(i.status));
function batchBar() {
  const b = ui.batch, ready = readyItems();
  if (b) return `<div class="batch-bar" data-batchbar="1" role="status"><span class="reading">${b.kind === 'accept' ? 'Placing' : 'Dismissing'} ${Math.min(b.done + 1, b.total)} / ${b.total}…</span>${b.failed ? `<span class="flag bad">${b.failed} failed</span>` : ''}</div>`;
  if (ready.length < 2) return '<div data-batchbar="1" hidden></div>';
  const picked = ready.filter(i => ui.picked.has(i.id)).length, conf = ready.filter(i => (i.proposal.confidence || 0) >= CONFIDENT).length;
  return `<div class="batch-bar" data-batchbar="1"><label class="pk-pick"><input type="checkbox" data-pickall="1" ${picked === ready.length ? 'checked' : ''}>Select all</label>
    ${picked ? `<button class="ed-link plain" data-act="batch" data-id="accept" data-what="picked">Accept selected · ${picked}</button><button class="ed-link dim" data-act="batch" data-id="dismiss" data-what="picked">Dismiss selected</button>`
      : `<button class="ed-link plain" data-act="batch" data-id="accept" data-what="all">Accept all · ${ready.length}</button>${conf && conf < ready.length ? `<button class="ed-link plain" data-act="batch" data-id="accept" data-what="conf" title="Proposals the agent is at least ${CONFIDENT * 100}% sure of">Accept confident · ${conf}</button>` : ''}`}</div>`;
}
const paintBatch = () => document.querySelectorAll('[data-batchbar]').forEach(el => { el.outerHTML = batchBar(); });   // in place: a full render would lose the list's scroll position
async function batchRun(kind, what) {
  if (ui.batch) return;
  const ready = readyItems();
  const items = what === 'picked' ? ready.filter(i => ui.picked.has(i.id)) : what === 'conf' ? ready.filter(i => (i.proposal.confidence || 0) >= CONFIDENT) : ready;
  if (!items.length) return;
  if (kind === 'accept' && items.length > 20 && !confirm(`Accept ${items.length} items? Each is added to the record where the agent proposed, with the changes it listed.`)) return;
  if (kind === 'dismiss' && items.length > 5 && !confirm(`Dismiss ${items.length} items? They are removed from the list and not added to the record.`)) return;
  const jobs = items.map(it => { const r = document.querySelector(`[data-reason="${it.id}"]`), p = it.proposal;          // same payload as accept(), taken before anything re-renders
    return {id: it.id, path: `/api/items/${it.id}/${kind === 'accept' ? 'approve' : 'dismiss'}`,
            body: kind === 'accept' ? {type: p.type, title: p.title, links: p.links || [], by: ui.who, reason: r ? r.value.trim() : ''} : {by: ui.who, reason: ''}}; });
  const b = ui.batch = {kind, done: 0, total: jobs.length, failed: 0}; ui.batchErr = {};
  document.querySelectorAll('[data-pick]').forEach(c => { c.disabled = true; }); paintBatch();
  for (const j of jobs) {                    // one at a time, in list order (oldest first), so the record reads in order
    try { await post(j.path, j.body); }
    catch (e) { b.failed++; ui.batchErr[j.id] = e.message || 'failed'; }
    b.done++; paintBatch();
  }
  ui.batch = null; ui.picked.clear(); dirty = false;
  await refresh(); render();                 // once, at the end
  const ok = b.total - b.failed;
  toast(`${kind === 'accept' ? 'Placed' : 'Dismissed'} ${ok}${b.failed ? `, ${b.failed} failed` : ''}.${b.failed ? ' The failed ones are still in the list with the reason.' : ''}`);
}
function flaggedRow(n) {
  const c = D.cause[n.id];
  return `<button class="ed-row" data-act="sel" data-id="${n.id}"><span class="t">${esc(n.title)}</span>
    <span class="side"><span class="ed-meta flag ${n.status === 'blocked' ? 'bad' : ''}">${esc(FLAG[n.status])}</span><span class="ed-meta">${esc(TYPE_LABEL[n.type] || n.type)} · ${esc(n.owner || '')}</span><span class="go">→</span></span>
    ${c ? `<span class="sub">${esc(c.why || '')} <span class="dim">Because: ${esc(c.ev.title)}</span></span>` : ''}</button>`;
}
function eventRow(ev, filter) {
  let fx = effectsOf(ev.payload); if (filter) fx = fx.filter(filter);
  return `<li class="ed-row"><span class="t">${esc(ev.title)}</span><span class="side"><span class="ed-meta">${esc(ev.actor || '')} · ${when(ev.at)}</span></span>
    ${ev.reason ? `<span class="sub">${esc(ev.reason)}${ev.payload && ev.payload.url ? ` <a href="${esc(ev.payload.url)}" target="_blank" rel="noopener">source</a>` : ''}</span>` : ''}${fxList(fx)}</li>`;
}
function askBlock(key, placeholder, big) {
  const a = ui.ask[key] || {};
  let out = '';
  if (a.loading) out = `<div class="answer"><span class="reading">Reading the record</span></div>`;
  else if (a.err) out = `<div class="answer"><span class="flag bad">${esc(a.err)}</span></div>`;
  else if (a.res) {
    const text = esc(a.res.answer || '').replace(/\[(\d+)\]/g, '<sup>[$1]</sup>').replace(/\n+/g, '</p><p>');
    out = `<div class="answer"><p>${text}</p>${(a.res.citations || []).length ? `<ul class="cites">${a.res.citations.map(c =>
      `<li><button data-act="sel" data-id="${esc(c.node_id)}"><sup>[${c.n}]</sup> <b>${esc(c.title)}</b>${c.locator ? ` <span class="dim">${esc(c.locator)}</span>` : ''}</button>${c.quote ? `<q>${esc(c.quote)}</q>` : ''}</li>`).join('')}</ul>` : ''}</div>`;
  }
  const form = big
    ? `<form class="ask-big" data-ask="${esc(key)}"><div class="ed-search" style="flex:1 1 320px"><input name="q" placeholder="${esc(placeholder)}" value="${esc(a.q || '')}" autocomplete="off"></div><button class="ed-cta">Ask</button></form>`
    : `<form class="ask" data-ask="${esc(key)}"><input name="q" placeholder="${esc(placeholder)}" value="${esc(a.q || '')}" autocomplete="off"><button class="btn sm primary">Ask</button></form>`;
  return form + (out ? (big ? `<div class="ask-out">${out}</div>` : out) : '');
}
let secN = 0;
const section = (no, title, body, note) => `<section class="ed-section"><div class="ed-label"><span class="ed-meta">${String(++secN).padStart(2, '0')}</span><h2>${title}</h2>${note ? `<span class="ed-meta" style="text-transform:none;letter-spacing:0;line-height:1.4">${note}</span>` : ''}</div><div class="ed-body">${body}</div></section>`;
const foot = () => `<footer class="ed-foot"><span class="ed-meta">${esc(S.project.name)} · ${S.nodes.length} nodes · ${S.edges.length} links</span><span class="ed-meta">${esc((S.config && S.config.jev_model) || '')}</span></footer>`;

/* ------------------------------------------------------------------ overview */
function overview() {
  const last = [...D.events].reverse().find(e => effectsOf(e.payload).length);
  const again = D.flagged.filter(n => n.type === 'decision').length;
  const lede = D.flagged.length
    ? `${D.flagged.length} ${D.flagged.length === 1 ? 'thing needs' : 'things need'} another look${again ? `, ${again} of them ${again === 1 ? 'a decision' : 'decisions'} already made` : ''}.${last ? ` Latest cause: ${last.title}.` : ''}`
    : S.nodes.length ? 'Nothing is flagged. Every decision still rests on what it was decided on.' : 'An empty project. Add the first thing with + Add, or press Forward in the presenter bar.';
  const recent = [...D.events].reverse().filter(e => e.kind !== 'project.seeded').slice(0, 6);
  const feeds = feedDays();
  return `<main class="ed-page">
  <header class="ov-hero"><span class="ed-meta">${esc(S.project.id)} · Living decision record</span>
    <h1 class="ed-display">${esc(S.project.name)}</h1>
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:44ch">${esc(lede)}</p><button class="ed-link" data-act="tab" data-id="pm">Open the knowledge canvas</button></div></header>
  ${UIX.startStrip()}
  <section class="ed-nums">
    <div><span class="ed-num">${S.nodes.length}</span><span class="ed-meta">Nodes</span></div>
    <div><span class="ed-num">${S.edges.length}</span><span class="ed-meta">Links</span></div>
    <div><span class="ed-num">${D.open.length}</span><span class="ed-meta">To review</span></div>
    <div><span class="ed-num">${D.flagged.length}</span><span class="ed-meta">Need another look</span></div>
  </section>
  ${section('01', 'Review', D.open.length ? `${batchBar()}<ul class="ed-rows">${D.open.map(i => itemRow(i, false)).join('')}</ul>` : `<p class="ed-empty">Nothing is waiting. Drop a file anywhere, or press + Add, and it will be read, placed and shown here before anything changes.</p>`, 'New information, placed by the agent. Nothing joins the record until someone accepts it.')}
  ${section('02', 'Another look', D.flagged.length ? `<div class="ed-rows">${D.flagged.map(flaggedRow).join('')}</div>` : `<p class="ed-empty">No decision, deliverable or event is at risk.</p>`, 'What a change put at risk, blocked or re-opened, and why.')}
  ${section('03', 'Building', partTiles(), 'Each part lights up from what is open on the things linked to it.')}
  ${section('03', 'What changed', recent.length ? `<ul class="ed-rows">${recent.map(e => eventRow(e)).join('')}</ul>` : `<p class="ed-empty">No changes since the project was set up.</p>`)}
  ${section('04', 'Ask the record', askBlock('project', 'Why is Thursday’s flight at risk?', true), 'Answers come only from the record and cite the nodes they rest on.')}
  ${section('05', 'Project map', `<div class="ed-cols">${CAT_ORDER.map(c => { const ns = S.nodes.filter(n => D.cat[n.id] === c);
      return `<div class="ed-col"><span class="ed-meta">${CATS[c].label} · ${ns.length}</span>${ns.map(n => `<button class="ed-item" data-act="sel" data-id="${n.id}"><span class="t">${esc(n.title)}</span><span class="ed-meta ${FLAG[n.status] ? 'flag' : ''}">${esc(TYPE_LABEL[n.type] || n.type)} · ${esc(statusLabel(n))}</span></button>`).join('')}</div>`; }).join('')}</div>`)}
  ${section('06', 'Live feeds', feeds.html, 'Monitors that watch the outside world and raise a change when it touches the record.')}
  ${section('07', 'Rules', rulesBlock(), 'What the record has learned to watch for. Suggested by the analysis loop, approved by a person.')}
  ${UIX.retake()}
  ${foot()}</main>`;
}
function feedDays() {
  const mons = (S.feeds && S.feeds.monitors) || {}, by = {};
  for (const [name, m] of Object.entries(mons)) (by[m.feed] ||= []).push({name, ...m});
  const keys = Object.keys(by);
  if (!keys.length) return {html: `<p class="ed-empty">No live feeds are running.</p>${feedAdd()}`};
  const html = `<div class="ed-week" style="grid-template-columns:repeat(${Math.min(keys.length, 7)},minmax(0,1fr))">${keys.map(k => {
    const node = S.nodes.find(n => n.ref === k), ok = by[k].every(m => m.ok), flagged = node && (FLAG[node.status] || node.status === 'changed');
    const lastRun = Math.max(...by[k].map(m => m.last_run || 0));
    return `<div class="ed-day"><span class="ed-meta">${by[k].length} monitor${by[k].length > 1 ? 's' : ''}</span><b style="font-size:clamp(17px,1.6vw,24px);line-height:1.1">${esc(node ? node.title.replace(/ feed.*$/i, '') : k)}</b>
      <span class="ed-glyph ${!ok ? 'bad' : flagged ? 'warn' : 'ok'}"></span><small>${!ok ? esc(by[k].find(m => !m.ok).error || 'Not reachable') : flagged ? 'Raised a change' : 'No change'}${lastRun ? '<br>checked ' + when(lastRun) : ''}</small></div>`; }).join('')}</div>
    <div class="ed-key"><span><i class="ed-glyph ok"></i>No change</span><span><i class="ed-glyph warn"></i>Raised a change</span><span><i class="ed-glyph bad"></i>Not reachable</span></div>${feedAdd()}`;
  return {html};
}
/* Add live feed: a person picks what to watch, where, when and within which limits, and what depends on it.
   POST /api/feeds creates the feed node, links it, starts its monitors and takes the first reading. */
const FEED_LIMITS = {max_wind_mph: 'Max wind (mph)', max_gust_mph: 'Max gust (mph)', max_precip_prob: 'Max chance of rain (%)'};
function feedAdd() {
  const F = S.feeds || {}, kinds = F.kinds || [], mine = F.custom || [];
  if (!kinds.length) return '';
  const list = mine.length ? `<ul class="ed-rows feed-mine">${mine.map(c => `<li class="ed-row" style="cursor:default"><span class="t">${esc(c.title)}</span>
      <span class="ed-meta">${esc(c.place || '')}${c.flight_window && c.flight_window.start ? ' · ' + esc(c.flight_window.start) + ' to ' + esc(c.flight_window.end) : ''}</span>
      <span><button class="ed-link plain" data-act="sel" data-id="${esc(c.node_id)}">Open</button> <button class="ed-link dim" data-act="feedremove" data-id="${esc(c.node_id)}">Remove</button></span></li>`).join('')}</ul>` : '';
  const f = ui.feed;
  if (!f) return `${list}<div class="feed-add"><button class="ed-link" data-act="feedform">+ Add live feed</button></div>`;
  const k = kinds.find(x => x.id === f.kind) || kinds[0], d = F.defaults || {limits: {}}, w = (F.site && F.site.flight_window) || {};
  const place = /place/.test(k.needs), win = /window/.test(k.needs);
  const targets = S.nodes.filter(n => ['event', 'deliverable', 'decision'].includes(n.type));
  const val = n => esc(f[n] ?? '');
  return `${list}<form class="feed-form" data-feedform="1">
    <div class="feed-head"><span class="ed-meta">Add live feed</span><button type="button" class="ed-link dim" data-act="feedform">Cancel</button></div>
    <label>What to watch<select name="kind">${kinds.map(x => `<option value="${esc(x.id)}" ${x.id === k.id ? 'selected' : ''}>${esc(x.label)}</option>`).join('')}</select></label>
    <label>Name<input name="title" value="${val('title')}" placeholder="Named for you if left empty" autocomplete="off"></label>
    ${place ? `<label>Place (NYC address)<input name="address" value="${val('address')}" placeholder="${esc(d.place || 'The project site')} (project site)" autocomplete="off"></label>` : ''}
    ${win ? `<div class="feed-pair"><label>From<input type="date" name="start" value="${esc(f.start ?? w.start ?? '')}"></label><label>To<input type="date" name="end" value="${esc(f.end ?? w.end ?? '')}"></label></div>` : ''}
    ${k.limits.some(l => FEED_LIMITS[l]) ? `<div class="feed-pair">${k.limits.filter(l => FEED_LIMITS[l]).map(l => `<label>${FEED_LIMITS[l]}<input type="number" min="1" step="1" name="${l}" value="${val(l)}" placeholder="${esc(d.limits[l] ?? '')}"></label>`).join('')}</div>` : ''}
    <label>What depends on it<select name="depends"><option value="">Nothing yet (link it later on the canvas)</option>${targets.map(n => `<option value="${esc(n.id)}" ${f.depends === n.id ? 'selected' : ''}>${esc(n.title)}</option>`).join('')}</select></label>
    <div class="feed-head"><small class="dim">When it reports a change, whatever depends on it is flagged.</small><button class="ed-cta" ${f.busy ? 'disabled' : ''}>${f.busy ? 'Adding…' : 'Add feed'}</button></div></form>`;
}
async function addFeed() {
  const f = ui.feed; if (!f || f.busy) return;
  const limits = {}; for (const l of Object.keys(FEED_LIMITS)) if (f[l]) limits[l] = +f[l];
  f.busy = true; render(); toast('Adding the feed and taking a first reading…');
  try {
    const out = await post('/api/feeds', {kind: f.kind, title: f.title || '', address: f.address || '', window: {start: f.start || '', end: f.end || ''},
                                         limits, depends: f.depends ? [f.depends] : [], by: ui.who});
    const bad = Object.values(out.first_reading || {}).find(r => !r.ok);
    ui.feed = null; toast(`Added “${out.title}”. ${bad ? 'Its source did not answer: ' + (bad.error || 'not reachable') : 'Its source answered; changes from now on are flagged.'}`);
  } catch (err) { f.busy = false; toast(err.message); }
  await refresh(); render();
}

/* ------------------------------------------------------------------ + Add drawer (was the Parking lot tab)
   Files can be dropped anywhere on the page. Everything goes through POST /api/intake, which uses the converter
   (Minh/converter) to read the file, then waits here until someone accepts where it belongs. */
/* On the PM tab, adding something does not leave the page: what was sent shows right under the note field, first as
   being read, then with its suggested effects, and it is accepted or dismissed there. */
const inPlace = () => ui.tab === 'pm';
function reviewHere() {
  if (!D.open.length) return '';
  return `<div class="review-here" aria-label="Waiting for your review">${batchBar()}<ul class="ed-rows">${D.open.map(i => itemRow(i, true)).join('')}</ul></div>`;
}
/* Items with no connections (a project loaded all at once, or approved before the rest existed): say so on the
   canvas and offer to find them. Jev takes the items oldest first and links each to what came before it. */
function linkUp() {
  if (S.linking) return '<span class="link-up busy" role="status"><i></i>Finding connections\u2026 links appear as they are found</span>';
  const n = D.loose.length;
  if (!n || S.nodes.length < 2) return '';
  return `<span class="link-up"><b>${n}</b> ${n === 1 ? 'item has' : 'items have'} no connections <button class="ed-link plain" data-act="relink">Find connections</button></span>`;
}
function intakeDrawer() {
  return `${ui.intake ? '<div class="intake-scrim" data-act="intake"></div>' : ''}
  <aside class="intake ${ui.intake ? 'open' : ''}" aria-label="Add to project" ${ui.intake ? '' : 'aria-hidden="true"'}>
    <header><div><span class="ed-meta">Add to project</span><h2>Drop files anywhere</h2></div><button class="icon-btn" data-act="intake" aria-label="Close">×</button></header>
    <p class="intake-status on"><i></i>An email, a site note, a permit, a photo. It is read, a place is proposed with what it would change, and you decide.</p>
    <div class="intake-drop" id="drop"><span class="intake-pick"><button class="ed-cta" data-act="pickfiles">Choose files</button><button class="ed-link plain" data-act="pickdir">or a folder</button></span>
      <form class="pk-note" data-note="1"><input name="text" placeholder="or paste a note" autocomplete="off"><button class="ed-link plain">Add</button></form>
      ${S.config && S.config.folders ? `<form class="pk-note" data-drive="1"><input name="source" id="drive-src" placeholder="or a Google Drive folder link (shared with anyone with the link)" autocomplete="off"><button class="ed-link plain">Add folder</button></form>` : ''}</div>
    ${folderJobs()}
    <div class="intake-list"><span class="ed-meta">Waiting to be placed · ${D.open.length}</span>
      ${D.open.length ? `${batchBar()}<ul class="ed-rows">${D.open.map(i => itemRow(i, true)).join('')}</ul>` : '<p class="ed-empty">Nothing waiting. Everything is placed in the record.</p>'}</div>
  </aside>`;
}

/* ------------------------------------------------------------------ pilot */
function upstream(id) {
  const seen = new Set(), out = [];
  (function walk(x, d) { for (const f of D.flow) if (f.b === x && !seen.has(f.a) && f.e.type !== 'about') { seen.add(f.a); out.push({id: f.a, d, via: f.e.type}); if (d < 3) walk(f.a, d + 1); } })(id, 1);
  return out;
}
function pilot() {
  const net3d = UIX.pilotPage(); if (net3d) return net3d;     // UIX: the design's Pilot tab is the 3D knowledge network
  const flights = S.nodes.filter(n => n.type === 'event');
  const f = flights.find(n => FLAG[n.status]) || flights[0];
  if (!f) return `<main class="ed-page"><header class="ov-hero"><span class="ed-meta">Pilot brief</span><h1 class="ed-display md">No flight yet</h1><p class="ed-lede">Add a flight with + Add and its brief appears here.</p></header></main>`;
  const up = upstream(f.id).map(u => ({...u, n: D.byId[u.id]}));
  const bad = up.filter(u => u.n.status === 'blocked' || u.n.type === 'blocker' && !['resolved', 'done'].includes(u.n.status));
  const word = f.status === 'blocked' || bad.length ? 'No-go' : FLAG[f.status] ? 'At risk' : 'Go';
  const c = D.cause[f.id];
  const limits = S.nodes.filter(n => n.type === 'constraint');
  const feedEv = [...D.events].reverse().filter(e => /^feed\./.test(e.kind)).slice(0, 4);
  const row = u => { const n = u.n, t = tone(n), cz = FLAG[n.status] && D.cause[n.id];
    return `<button class="ed-row" data-act="sel" data-id="${n.id}"><span class="t"><i class="ed-glyph ${t === 'bad' ? 'bad' : t === 'warn' ? 'warn' : 'ok'}"></i>${esc(n.title)}</span>
      <span class="side"><span class="ed-meta ${FLAG[n.status] ? 'flag' : ''}">${esc(statusLabel(n))}</span><span class="ed-meta">${esc(TYPE_LABEL[n.type] || n.type)} · ${esc(n.owner || '')}</span><span class="go">→</span></span>
      ${cz ? `<span class="sub">${esc(cz.why)}</span>` : ''}</button>`; };
  return `<main class="ed-page">
  <header class="ov-hero"><span class="ed-meta">Pilot brief · ${esc(f.title)}</span><h1 class="ed-display md ${word !== 'Go' ? 'flag' + (word === 'No-go' ? ' bad' : '') : ''}">${word}</h1>
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:48ch">${esc(c ? `${c.why} Because: ${c.ev.title}.` : word === 'Go' ? 'Everything this flight rests on is in place.' : f.summary || '')}</p>
    <button class="ed-link" data-act="sel" data-id="${f.id}">See it on the canvas</button>${UIX.netLink()}</div></header>
  <section class="ed-nums">
    <div><span class="ed-num">${up.length}</span><span class="ed-meta">Things it rests on</span></div>
    <div><span class="ed-num">${up.filter(u => FLAG[u.n.status]).length}</span><span class="ed-meta">Flagged</span></div>
    <div><span class="ed-num">${bad.length}</span><span class="ed-meta">Blocking</span></div>
    <div><span class="ed-num">${limits.length}</span><span class="ed-meta">Limits</span></div>
  </section>
  ${section('01', 'Before you fly', up.length ? `<div class="ed-rows">${up.sort((a, b) => (FLAG[b.n.status] ? 1 : 0) - (FLAG[a.n.status] ? 1 : 0) || a.d - b.d).map(row).join('')}</div>` : `<p class="ed-empty">This flight does not rest on anything in the record yet.</p>`, 'Everything this flight rests on, flagged first.')}
  ${section('02', 'Limits', limits.length ? `<div class="ed-rows">${limits.map(n => row({n})).join('')}</div>` : `<p class="ed-empty">No limits recorded.</p>`)}
  ${section('03', 'From the feeds', (feedEv.length ? `<ul class="ed-rows">${feedEv.map(e => eventRow(e)).join('')}</ul>` : `<p class="ed-empty">The feeds have raised nothing.</p>`) + `<div style="margin-top:28px">${feedDays().html}</div>`)}
  ${section('04', 'Report from the field', `<div class="pk-drop"><form class="pk-note" data-note="1" style="flex:1 1 320px"><input name="text" placeholder="What did you see on site?" autocomplete="off" style="flex:1"><button class="ed-link plain">Add</button></form></div>`, 'A remark is enough. It is read, placed and sent for review.')}
  ${foot()}</main>`;
}

/* ------------------------------------------------------------------ client */
function client() {
  const dels = S.nodes.filter(n => n.type === 'deliverable'), decs = S.nodes.filter(n => n.type === 'decision');
  const show = new Set(['deliverable', 'event', 'decision']);
  const onTrack = dels.filter(n => !FLAG[n.status]).length;
  const changes = [...D.events].reverse().filter(e => effectsOf(e.payload).some(f => D.byId[f.node_id] && show.has(D.byId[f.node_id].type))).slice(0, 5);
  const lede = dels.length ? `${onTrack} of ${dels.length} deliverable${dels.length > 1 ? 's are' : ' is'} on track.${changes[0] && onTrack < dels.length ? ` The rest are being looked at again after: ${changes[0].title}.` : ''}` : 'No deliverables are recorded yet.';
  const row = n => { const c = FLAG[n.status] && D.cause[n.id];
    return `<li class="ed-row"><span class="t">${esc(n.title)}</span><span class="side"><span class="ed-meta ${FLAG[n.status] ? 'flag' : ''}">${esc(FLAG[n.status] ? (n.type === 'decision' ? 'Being reconsidered' : 'Being looked at again') : statusLabel(n))}</span></span>
      ${n.summary ? `<span class="sub">${esc(n.summary)}</span>` : ''}${c ? `<span class="sub flag">${esc(c.why)}</span>` : ''}</li>`; };
  return `<main class="ed-page">
  <header class="ov-hero"><span class="ed-meta">Client view · read only</span><h1 class="ed-display md">${esc(S.project.name)}</h1>
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:46ch">${esc(lede)}</p>${UIX.briefButton()}</div></header>
  ${(S.parts || []).length ? section('01', 'Your building', `<div style="display:grid;grid-template-columns:minmax(180px,1fr) minmax(0,2fr);gap:32px;align-items:start"><div class="ed-figure"><div class="frame" style="aspect-ratio:3/4;padding:18px">${buildingSVG()}</div></div><ul class="ed-rows">${partRows(true)}</ul></div>`, 'Each part of the building, and whether anything about it is being looked at again.') : ''}
  ${section('01', 'Your deliverables', dels.length ? `<ul class="ed-rows">${dels.map(row).join('')}</ul>` : `<p class="ed-empty">None yet.</p>`)}
  ${section('02', 'What changed', changes.length ? `<ul class="ed-rows">${changes.map(e => eventRow(e, f => D.byId[f.node_id] && show.has(D.byId[f.node_id].type))).join('')}</ul>` : `<p class="ed-empty">Nothing has changed that affects you.</p>`, 'Only changes that touch a deliverable, a flight or a decision.')}
  ${section('03', 'Decisions on record', decs.length ? `<ul class="ed-rows">${decs.map(row).join('')}</ul>` : `<p class="ed-empty">No decisions recorded.</p>`)}
  ${section('04', 'Ask', askBlock('client', 'When will the facade model be ready?', true), 'Answers come only from the project record.')}
  ${foot()}</main>`;
}

/* ------------------------------------------------------------------ knowledge canvas */
const visible = () => S.nodes.filter(n => !ui.off.has(D.cat[n.id] || 'none'));
function layout(mode, nodes) {
  const ids = new Set(nodes.map(n => n.id)), pos = {}, groups = [], labels = [];
  const ci = n => { const i = CAT_ORDER.indexOf(D.cat[n.id]); return i < 0 ? 99 : i; };
  const flow = D.flow.filter(f => ids.has(f.a) && ids.has(f.b));
  if (mode === 'free') {
    let x = 60;
    for (const c of [...CAT_ORDER, null]) {
      const ns = nodes.filter(n => (D.cat[n.id] || null) === c); if (!ns.length) continue;
      ns.forEach((n, i) => pos[n.id] = {x, y: 80 + i * (CH + 18)});
      groups.push({x: x - 20, y: 40, w: CW + 40, h: ns.length * (CH + 18) + 42, c: c ? CATS[c].c : UNCL, label: c ? CATS[c].label : 'Unclassified', dashed: !c});
      x += CW + 64;
    }
  } else if (mode === 'dec') {
    const dec = nodes.filter(n => n.type === 'decision'), dset = new Set(dec.map(n => n.id));
    const feed = nodes.filter(n => !dset.has(n.id) && flow.some(f => f.a === n.id && dset.has(f.b))), fset = new Set(feed.map(n => n.id));
    const outp = nodes.filter(n => !dset.has(n.id) && !fset.has(n.id) && flow.some(f => f.b === n.id && (dset.has(f.a) || fset.has(f.a)))), oset = new Set(outp.map(n => n.id));
    const rest = nodes.filter(n => !dset.has(n.id) && !fset.has(n.id) && !oset.has(n.id));
    [[feed, 'What they rest on'], [dec, 'Decisions'], [outp, 'What they affect'], [rest, 'Not tied to a decision']].forEach(([ns, label], k) => {
      const x = 60 + k * 380; ns.sort((a, b) => ci(a) - ci(b)).forEach((n, i) => pos[n.id] = {x, y: 90 + i * ROW});
      if (ns.length) labels.push({x, y: 54, label});
    });
  } else {
    const layer = {}, preds = {};
    for (const f of flow) (preds[f.b] ||= []).push(f.a);
    const depth = (id, stack) => { if (layer[id] != null) return layer[id]; if (stack.has(id)) return 0; stack.add(id);
      const l = (preds[id] || []).reduce((m, p) => Math.max(m, depth(p, stack) + 1), 0); stack.delete(id); return layer[id] = l; };
    nodes.forEach(n => depth(n.id, new Set()));
    const cols = []; nodes.forEach(n => (cols[layer[n.id]] ||= []).push(n));
    const idx = {};
    cols.forEach((col, L) => { if (!col) return;
      col.sort((a, b) => ci(a) - ci(b));
      if (L > 0) { const bc = n => { const p = (preds[n.id] || []).filter(p => idx[p] != null); return p.length ? p.reduce((s, x) => s + idx[x], 0) / p.length : 1e3 + ci(n); };
        col.sort((a, b) => bc(a) - bc(b)); }
      col.forEach((n, i) => idx[n.id] = i); });
    const tall = Math.max(...cols.filter(Boolean).map(c => c.length));
    cols.forEach((col, L) => col && col.forEach((n, i) => pos[n.id] = {x: 60 + L * COL, y: 60 + (tall - col.length) * ROW / 2 + i * ROW}));
  }
  return {pos, groups, labels};
}
let L = null;   // current layout
function pm() {
  const nodes = visible();
  L = layout(ui.mode, nodes);
  const moved = ui.pos[ui.mode] || {};
  for (const id in moved) if (L.pos[id]) L.pos[id] = moved[id];
  const sel = ui.sel, near = new Set(sel ? [sel] : []);
  if (sel) for (const f of D.flow) { if (f.a === sel) near.add(f.b); if (f.b === sel) near.add(f.a); }
  const q = ui.q.trim().toLowerCase(), hits = UIX.hits() || (ui.search && ui.search.res ? new Set(ui.search.res.results.map(r => r.node.id)) : null), hit = n => hits ? hits.has(n.id) : !q || (n.title + ' ' + (n.summary || '') + ' ' + (n.tags || []).join(' ') + ' ' + n.type).toLowerCase().includes(q);
  const cards = nodes.map(n => { const p = L.pos[n.id], c = D.cat[n.id], fl = FLAG[n.status], cz = fl && D.cause[n.id];
    return `<div class="card ${sel === n.id ? 'sel' : ''} ${(sel && !near.has(n.id)) || !hit(n) ? 'fade' : ''} ${c ? '' : 'uncl'} ${fl ? 'flagged' + (n.status === 'blocked' ? ' bad' : '') : ''}" data-card="${n.id}" style="left:${p.x}px;top:${p.y}px;--cat:${c ? CATS[c].c : UNCL}">
      <i class="port in"></i><i class="port out"></i>
      <div class="card-top"><span class="ico">${TYPE_ICON[n.type] || '•'}</span><span class="kind">${esc(TYPE_LABEL[n.type] || n.type)}</span>${n.data && n.data.item_id ? '<span class="badge t-ai">AI placed</span>' : ''}</div>
      <div class="card-title">${esc(n.title)}</div>
      <div class="${cz ? 'why' : 'card-sub'}">${esc(cz ? cz.why : n.summary || '')}</div>
      <div class="card-foot"><span class="badge t-${tone(n)}">${esc(statusLabel(n))}</span><span class="links">⇄ ${D.deg[n.id]}</span></div></div>`; }).join('');
  const modeInfo = {tree: 'Left to right: what each thing rests on, then what rests on it.', free: 'Grouped by domain. Drag cards anywhere.', dec: 'Each decision between what it rests on and what it affects.'}[ui.mode];
  return `<div class="pm"><div class="pm-main">
    <div class="pm-search pm-add" style="padding-top:18px">${UIX.askBar('pm')}
      <button class="ed-cta" data-act="adding">${ui.adding ? 'Close' : '+ Add to record'}</button></div>
    ${ui.adding ? `<form class="pm-add" data-note="1"><input name="text" placeholder="Type a note, a finding or a change. It is read and proposed, not added directly." autocomplete="off" autofocus><button class="ed-link plain">Send for review</button></form>` : ''}
    ${reviewHere()}
    <div class="pm-toolbar"><div class="seg sm">${[['tree', 'Tree'], ['free', 'Freeform'], ['dec', 'Decisions']].map(([m, l]) => `<button class="${ui.mode === m ? 'on' : ''}" data-act="mode" data-id="${m}">${l}</button>`).join('')}</div><span class="mode-info dim">${modeInfo}</span>${linkUp()}</div>
    <div class="chips">${CAT_ORDER.map(c => `<button class="fchip ${ui.off.has(c) ? '' : 'on'}" style="--c:${CATS[c].c}" data-act="cat" data-id="${c}"><i style="width:8px;height:8px;border-radius:50%;background:${CATS[c].c};display:inline-block"></i>${CATS[c].label} <span>${S.nodes.filter(n => D.cat[n.id] === c).length}</span></button>`).join('')}</div>
    <div class="canvas-wrap" id="wrap"><div class="layer" id="layer">
      ${L.groups.map(g => `<div class="gh-group ${g.dashed ? 'dashed' : ''}" style="left:${g.x}px;top:${g.y}px;width:${g.w}px;height:${g.h}px;--c:${g.c}"><span>${esc(g.label)}</span></div>`).join('')}
      ${L.labels.map(g => `<div class="group-label" style="left:${g.x}px;top:${g.y}px">${esc(g.label)}</div>`).join('')}
      <svg class="edges" id="edges" width="1" height="1" style="overflow:visible"></svg>${cards}</div>
      <div class="zoombar"><button data-act="zoom" data-id="out">−</button><span id="zoom" style="min-width:44px;text-align:center;font-size:12px">100%</span><button data-act="zoom" data-id="in">+</button><button data-act="zoom" data-id="fit">Fit</button><button data-act="zoom" data-id="arrange">Auto-arrange</button></div>
      <div class="legend-box"><div class="wire-key"><span class="k-app">Link in the record</span><span class="k-acc">Proposed by the agent, accepted</span></div><div class="ed-meta" style="margin-top:6px;text-transform:none;letter-spacing:0">Drag from a card’s black dot to another card to connect them.</div></div>
    </div></div>
    <aside class="pm-side">${inspector()}</aside></div>`;
}
function drawEdges() {
  const svg = $('#edges'); if (!svg || !L) return;
  const sel = ui.sel;
  svg.innerHTML = D.flow.filter(f => L.pos[f.a] && L.pos[f.b]).map(f => {
    const a = L.pos[f.a], b = L.pos[f.b], x1 = a.x + CW, y1 = a.y + CH / 2, x2 = b.x, y2 = b.y + CH / 2, d = Math.max(60, Math.abs(x2 - x1) / 2);
    const hot = sel && (f.a === sel || f.b === sel);
    return `<g class="edge ${hot ? 'hot' : sel ? 'dim' : ''} ${f.e.origin && f.e.origin !== 'user' && f.e.origin !== 'manual' && f.e.origin !== 'seed' ? 'acc' : ''}"><path d="M${x1} ${y1} C${x1 + d} ${y1},${x2 - d} ${y2},${x2} ${y2}"/>${hot ? `<text x="${(x1 + x2) / 2}" y="${(y1 + y2) / 2 - 6}" text-anchor="middle" style="stroke:#fff;fill:var(--ink)">${esc(f.e.type.replace(/_/g, ' '))}</text>` : ''}</g>`; }).join('');
}
function applyView() { const v = ui.view, l = $('#layer'); if (!l || !v) return; l.style.transform = `translate(${v.x}px,${v.y}px) scale(${v.k})`; const z = $('#zoom'); if (z) z.textContent = Math.round(v.k * 100) + '%'; }
function fit() {
  const w = $('#wrap'); if (!w || !L) return;
  const ps = Object.values(L.pos); if (!ps.length) { ui.view = {x: 0, y: 0, k: 1}; return applyView(); }
  const x0 = Math.min(...ps.map(p => p.x)) - 40, y0 = Math.min(...ps.map(p => p.y)) - 50, x1 = Math.max(...ps.map(p => p.x)) + CW + 40, y1 = Math.max(...ps.map(p => p.y)) + CH + 110;
  const k = Math.max(.3, Math.min(1, w.clientWidth / (x1 - x0), w.clientHeight / (y1 - y0)));
  ui.view = {k, x: (w.clientWidth - (x1 - x0) * k) / 2 - x0 * k, y: (w.clientHeight - (y1 - y0) * k) / 2 - y0 * k};
  applyView();
}
function zoomAt(f, cx, cy) { const v = ui.view, k = Math.max(.3, Math.min(2, v.k * f)); v.x = cx - (cx - v.x) * k / v.k; v.y = cy - (cy - v.y) * k / v.k; v.k = k; applyView(); }
function mountCanvas() {
  const w = $('#wrap'); if (!w) return;
  drawEdges(); if (!ui.view) fit(); else applyView();
  w.addEventListener('wheel', e => { e.preventDefault(); const r = w.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.1 : 1 / 1.1, e.clientX - r.left, e.clientY - r.top); }, {passive: false});
  w.addEventListener('pointerdown', e => {
    if (e.target.closest('.zoombar,.legend-box')) return;
    const port = e.target.closest('.port.out');
    if (port) return linkDrag(e, w, port.closest('[data-card]').dataset.card);
    const card = e.target.closest('[data-card]'), id = card && card.dataset.card, sx = e.clientX, sy = e.clientY;
    const start = id ? {...L.pos[id]} : {x: ui.view.x, y: ui.view.y}; let moved = false;
    w.setPointerCapture(e.pointerId);
    const move = ev => { const dx = ev.clientX - sx, dy = ev.clientY - sy; if (!moved && Math.hypot(dx, dy) < 4) return; moved = true;
      if (id) { const p = L.pos[id] = {x: start.x + dx / ui.view.k, y: start.y + dy / ui.view.k}; card.style.left = p.x + 'px'; card.style.top = p.y + 'px'; (ui.pos[ui.mode] ||= {})[id] = p; drawEdges(); }
      else { ui.view.x = start.x + dx; ui.view.y = start.y + dy; applyView(); } };
    const up = () => { w.removeEventListener('pointermove', move); w.removeEventListener('pointerup', up); w.removeEventListener('pointercancel', up);
      if (!moved) { ui.sel = id || null; ui.link = null; render(); if (id) loadDetail(id); } };
    w.addEventListener('pointermove', move); w.addEventListener('pointerup', up); w.addEventListener('pointercancel', up);
  });
}

function inspector() {
  if (ui.link) return linkPanel();
  const n = ui.sel && D.byId[ui.sel];
  if (!n && ui.search) return searchPanel();
  if (!n) return `<div class="inspector"><div class="ins-head"><div class="ins-kicker"><span class="dim">Knowledge canvas</span></div><h3 class="ins-title">${esc(S.project.name)}</h3>
      <div class="ins-badges"><span class="badge t-info">${S.nodes.length} nodes</span> <span class="badge t-info">${S.edges.length} links</span> <span class="badge t-warn">${D.flagged.length} flagged</span></div></div>
    <section class="ins-sec"><h4>Start here</h4><p>Select a card to see what it rests on, what it affects and why it changed.</p></section>
    ${D.flagged.length ? `<section class="ins-sec"><h4>Need another look</h4><ul class="rels">${D.flagged.map(f => `<li><button data-act="sel" data-id="${f.id}"><span class="rel-verb flag">${esc(FLAG[f.status])}</span><span class="rel-t">${esc(f.title)}</span></button></li>`).join('')}</ul></section>` : ''}
    <section class="ins-sec"><h4>Ask the record</h4>${askBlock('project', 'Why is the permit at risk?')}</section></div>`;
  const c = D.cat[n.id], cz = FLAG[n.status] && D.cause[n.id];
  const ins = D.flow.filter(f => f.b === n.id), outs = D.flow.filter(f => f.a === n.id);
  const rel = (f, other, dir) => { const o = D.byId[other], v = VERB[f.e.type] || [f.e.type, f.e.type], fwd = REVERSED.has(f.e.type) ? dir === 'in' : dir === 'out';
    return `<li><button data-act="sel" data-id="${o.id}" title="${esc(f.e.reason || '')}"><span class="rel-verb">${esc(fwd ? v[0] : v[1])}</span><span class="rel-t">${esc(o.title)}${FLAG[o.status] ? ` <span class="flag">· ${esc(FLAG[o.status])}</span>` : ''}</span></button></li>`; };
  const hist = (D.hist[n.id] || []).slice().reverse().slice(0, 6);
  const canResolve = ['blocker', 'discovery', 'constraint'].includes(n.type) && !['resolved', 'done'].includes(n.status);
  const src = n.data && n.data.source;
  return `<div class="inspector"><div class="ins-head">
      <div class="ins-kicker"><i style="width:8px;height:8px;border-radius:50%;background:${c ? CATS[c].c : UNCL};display:inline-block"></i><span>${c ? CATS[c].label : 'Unclassified'}</span><span class="dim">· ${esc(TYPE_LABEL[n.type] || n.type)}</span></div>
      <h3 class="ins-title">${esc(n.title)}</h3>
      <div class="ins-badges"><span class="badge t-${tone(n)}">${esc(statusLabel(n))}</span>${n.data && n.data.item_id ? ' <span class="badge t-ai">AI placed, human approved</span>' : ''}</div></div>
    ${cz ? `<section class="ins-sec"><h4>Why it needs another look</h4><div class="open-q">${esc(cz.why)}<small>Because: ${esc(cz.ev.title)} · ${esc(cz.ev.actor || '')}, ${when(cz.ev.at)}</small></div></section>` : ''}
    ${n.summary ? `<section class="ins-sec"><h4>What this is</h4><p>${esc(n.summary)}</p></section>` : ''}
    <section class="ins-sec"><dl class="specs"><dt>Owner</dt><dd>${esc(n.owner || 'Unassigned')}</dd><dt>State</dt><dd>${esc(String(n.state || '').replace(/_/g, ' '))}</dd>
      ${src ? `<dt>Source</dt><dd>${esc(src)}${n.data.added_by ? ' · ' + esc(n.data.added_by) : ''}</dd>` : ''}${n.data && n.data.when ? `<dt>When</dt><dd>${esc(n.data.when)}</dd>` : ''}
      <dt>Added</dt><dd>${n.created_at ? when(n.created_at) : ''}</dd>${(n.tags || []).length ? `<dt>Tags</dt><dd>${esc(n.tags.join(', '))}</dd>` : ''}</dl></section>
    ${detailBlock(n.id)}
    ${ins.length ? `<section class="ins-sec"><h4>Rests on · ${ins.length}</h4><ul class="rels">${ins.map(f => rel(f, f.a, 'in')).join('')}</ul></section>` : ''}
    ${outs.length ? `<section class="ins-sec"><h4>Affects · ${outs.length}</h4><ul class="rels">${outs.map(f => rel(f, f.b, 'out')).join('')}</ul></section>` : ''}
    ${hist.length ? `<section class="ins-sec"><h4>History</h4><ul class="hist">${hist.map(h => `<li>${h.f ? `<b>${esc(h.f.change)}</b> · ` : ''}${esc(h.ev.title)}<small>${esc(h.ev.actor || '')} · ${when(h.ev.at)}</small></li>`).join('')}</ul></section>` : ''}
    ${canResolve ? `<section class="ins-sec ai-box"><h4>Resolve</h4><form class="ask" data-resolve="${n.id}"><input name="reason" placeholder="What settled it?" autocomplete="off"><button class="btn sm primary">Mark resolved</button></form></section>` : ''}
    <section class="ins-sec"><h4>Ask about this node</h4>${askBlock(n.id, 'Why does this matter?')}</section></div>`;
}

/* ---- node detail (GET /api/nodes/{id}): source, what it flagged, the passages it was read from */
async function loadDetail(id) {
  if (!id || ui.detail[id]) return;
  try { ui.detail[id] = await api('/api/nodes/' + id + '?limit=3'); if (ui.sel === id && (ui.tab === 'pm' || UIX.inNet()) && !ui.link) safeRender(); } catch {}
}
function detailBlock(id) {
  const d = ui.detail[id]; if (!d) return '';
  const raised = (d.raised || []).filter(r => r.id !== id), ps = (d.passages && d.passages.items) || [];
  const loc = p => { const o = p.pointer || {}; return Object.entries(o).filter(([, v]) => v != null && typeof v !== 'object').map(([k, v]) => `${k} ${v}`).join(' · '); };
  return `${raised.length ? `<section class="ins-sec"><h4>It flagged · ${raised.length}</h4><ul class="rels">${raised.map(r => `<li><button data-act="sel" data-id="${r.id}"><span class="rel-verb flag">${esc(FLAG[r.status] || r.status)}</span><span class="rel-t">${esc(r.title)}</span></button></li>`).join('')}</ul></section>` : ''}
    ${ps.length ? `<section class="ins-sec"><h4>Read from · ${d.passages.total} passage${d.passages.total > 1 ? 's' : ''}${d.source && d.source.name ? ' · ' + esc(d.source.name) : ''}</h4><ul class="hist">${ps.map(p => `<li>${esc(String(p.text || '').slice(0, 260))}${String(p.text || '').length > 260 ? '…' : ''}<small>${esc([p.role, p.modality, loc(p)].filter(Boolean).join(' · '))}</small></li>`).join('')}</ul></section>` : ''}`;
}

/* ---- hybrid search (GET /api/search): meaning and keywords, no model call */
async function search(q) {
  ui.q = q; q = q.trim();
  if (!q) { ui.search = null; return render(); }
  ui.search = {q, loading: true}; ui.sel = null; ui.link = null; render();
  try { ui.search = {q, res: await api(`/api/search?q=${encodeURIComponent(q)}&k=8&passages=1`)}; } catch (e) { ui.search = {q, err: e.message}; }
  render();
}
function searchPanel() {
  const s = ui.search, rs = (s.res && s.res.results) || [];
  const snip = p => esc(p.snippet || p.text || '').replace(/\[\[(.+?)\]\]/g, '<mark>$1</mark>');
  return `<div class="inspector"><div class="ins-head"><div class="ins-kicker"><span class="dim">Search${s.res ? ' · ' + esc(s.res.mode === 'hybrid' ? 'meaning and keywords' : s.res.mode) : ''}</span></div><h3 class="ins-title">“${esc(s.q)}”</h3>
      <div class="ins-badges"><span class="badge t-info">${s.loading ? 'Searching' : rs.length + ' found'}</span> <button class="ed-link dim" data-act="clearsearch">Clear</button></div></div>
    ${s.err ? `<section class="ins-sec"><span class="flag bad">${esc(s.err)}</span></section>` : ''}
    ${rs.map(r => `<section class="ins-sec"><ul class="rels"><li><button data-act="sel" data-id="${r.node.id}"><span class="rel-verb">${esc(TYPE_LABEL[r.node.type] || r.node.type)}</span><span class="rel-t">${esc(r.node.title)}${FLAG[r.node.status] ? ` <span class="flag">· ${esc(FLAG[r.node.status])}</span>` : ''}</span></button></li></ul>
      ${r.passages[0] ? `<p style="font-size:13px;color:var(--ink-2);margin-top:6px">${snip(r.passages[0])}</p>` : ''}<small class="dim">matched by ${esc((r.matched || []).join(' and '))}</small></section>`).join('')}
    ${!s.loading && !rs.length && !s.err ? `<section class="ins-sec"><p>Nothing in the record matches.</p></section>` : ''}</div>`;
}

/* ---- connect two nodes (POST /api/edges/suggest, then POST /api/edges): suggestions come with their dry-run effects */
function linkDrag(e, w, from) {
  const svg = $('#edges'), a = L.pos[from], x1 = a.x + CW, y1 = a.y + CH / 2, r = w.getBoundingClientRect();
  const line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#0a0a0a'); line.setAttribute('stroke-width', '1.6'); line.setAttribute('stroke-dasharray', '6 5');
  svg.appendChild(line); w.setPointerCapture(e.pointerId);
  const move = ev => line.setAttribute('d', `M${x1} ${y1}L${(ev.clientX - r.left - ui.view.x) / ui.view.k} ${(ev.clientY - r.top - ui.view.y) / ui.view.k}`);
  const up = ev => { w.removeEventListener('pointermove', move); w.removeEventListener('pointerup', up); w.removeEventListener('pointercancel', up); line.remove();
    try { w.releasePointerCapture(ev.pointerId); } catch {}
    const el = document.elementFromPoint(ev.clientX, ev.clientY), c = el && el.closest('[data-card]');
    if (c && c.dataset.card !== from) connect(from, c.dataset.card); };
  w.addEventListener('pointermove', move); w.addEventListener('pointerup', up); w.addEventListener('pointercancel', up);
}
async function connect(a, b) {
  ui.link = {a, b, loading: true}; render();
  try { const res = await post('/api/edges/suggest', {source: a, target: b}); if (ui.link && ui.link.a === a && ui.link.b === b) ui.link = {a, b, res}; }
  catch (e) { if (ui.link) ui.link = {a, b, err: e.message}; }
  render();
}
async function addLink(body) {
  try { const out = await post('/api/edges', {...body, by: ui.who}); const n = effectsOf(out).length;
    toast(`Link added to the record${n ? `. ${n} thing${n > 1 ? 's' : ''} flagged for another look.` : '.'}`); ui.sel = ui.link ? ui.link.a : ui.sel; ui.link = null; dirty = false; await refresh(); render(); }
  catch (e) { toast(e.message); render(); }
}
function linkPanel() {
  const k = ui.link, A = D.byId[k.a], B = D.byId[k.b], res = k.res || {}, sg = res.suggestions || [];
  const t = id => esc(D.byId[id] ? D.byId[id].title : id);
  return `<div class="inspector"><div class="ins-head"><div class="ins-kicker"><span class="dim">Connect two nodes</span></div><h3 class="ins-title">${esc(A.title)} <span class="dim">and</span> ${esc(B.title)}</h3>
      <div class="ins-badges"><button class="ed-link dim" data-act="unlink">Cancel</button></div></div>
    ${(res.existing || []).length ? `<section class="ins-sec"><h4>Already linked</h4>${res.existing.map(x => `<p>${esc(String(x.type || '').replace(/_/g, ' '))}${x.reason ? ` <span class="dim">${esc(x.reason)}</span>` : ''}</p>`).join('')}</section>` : ''}
    <section class="ins-sec ai-box"><h4>Suggested links · need approval</h4>
      ${k.loading ? `<span class="reading">Working out how they relate</span>` : k.err ? `<span class="flag bad">${esc(k.err)}</span>` : sg.length ? sg.map((x, i) => { const fx = effectsOf(x);
        return `<div class="sugg"><b>${t(x.from)}</b> <i>${esc(String(x.type).replace(/_/g, ' '))}</i> <b>${t(x.to)}</b> <span class="dim">${Math.round((x.confidence || 0) * 100)}%</span><br>${esc(x.reason || '')}
          ${fx.length ? `<div style="margin-top:6px"><span class="ed-meta">If added, this would change</span>${fx.map(f => `<div><span class="flag">${esc(f.change)}</span> · ${esc(f.title)}</div>`).join('')}</div>` : `<div class="dim" style="margin-top:6px">Adding it changes nothing else.</div>`}
          <div class="sugg-act"><button class="btn sm primary" data-act="addlink" data-id="${i}">Accept link</button></div></div>`; }).join('')
        : `<p>${esc(res.note || res.error || 'No link suggested. Add one by hand below.')}</p>`}</section>
    <section class="ins-sec"><h4>Or say it yourself</h4><form data-manual="1" style="display:flex;flex-direction:column;gap:10px">
      <span><b>${esc(A.title)}</b></span>
      <select name="type" style="border:0;border-bottom:1px solid var(--hair);background:none;padding:6px 0">${(S.edge_types || []).map(x => `<option value="${esc(x)}">${esc(x.replace(/_/g, ' '))}</option>`).join('')}</select>
      <span><b>${esc(B.title)}</b></span>
      <div class="ask"><input name="reason" placeholder="Why? (kept with the link)" autocomplete="off"><button class="btn sm primary">Add link</button></div></form></section></div>`;
}

/* ------------------------------------------------------------------ actions */
/* Folders (Minh's converter work, wired into this intake). Three ways in:
   a folder picked or dropped here  -> each file is sent to POST /api/intake as its own item, with its folder as the note
   a Google Drive folder link       -> POST /api/intake/folder; the server lists and downloads it (Minh/converter/sources.py) */
const JUNK = /^(\.|~\$|thumbs\.db$|desktop\.ini$)|\.(3dmbak|bak|tmp|temp|rhl|swp|crdownload|part)$|~$/i;   // same skip rules as the converter
const relOf = f => f._rel || f.webkitRelativePath || '';
const folderOf = f => relOf(f).split('/').slice(0, -1).join('/');
function pick(dir) {                 // a file input outside #root, so a re-render cannot lose the choice
  const inp = document.createElement('input'); inp.type = 'file'; inp.multiple = true; inp.hidden = true;
  if (dir) inp.webkitdirectory = true;
  inp.onchange = () => { const fs = [...inp.files]; inp.remove(); if (!fs.length) return; dir || fs.some(folderOf) ? addFolder(fs) : intake('', fs); };
  document.body.appendChild(inp); inp.click();
}
async function filesFromDrop(dt) {   // a dropped folder arrives as a placeholder: open it and collect every file inside
  const entries = [...(dt.items || [])].filter(i => i.kind === 'file').map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.some(e => e.isDirectory)) return [...(dt.files || [])];
  const out = [];
  const walk = async (entry, prefix) => {
    if (entry.isFile) { const f = await new Promise((res, rej) => entry.file(res, rej)); f._rel = prefix + f.name; out.push(f); }
    else if (entry.isDirectory) { const reader = entry.createReader();
      for (;;) { const batch = await new Promise((res, rej) => reader.readEntries(res, rej)); if (!batch.length) break;
        for (const e of batch) await walk(e, prefix + entry.name + '/'); } }
  };
  for (const e of entries) await walk(e, '');
  return out;
}
async function addFolder(all, extraNote, quiet) {
  const max = (S.config && S.config.folder_max) || 40;
  let files = all.filter(f => !relOf(f).split('/').concat(f.name).some(part => JUNK.test(part)));
  if (!files.length) { toast('That folder has no files to add.'); return; }
  const roots = [...new Set(files.map(f => relOf(f).split('/')[0]).filter(Boolean))], name = roots.join(', ') || 'the folder';
  if (files.length > max && !confirm(`${name} has ${files.length} files. Add the first ${max}? Each one is read and proposed separately.`)) return;
  files = files.slice(0, max);
  const job = {id: 'up_' + Date.now(), local: true, root_name: name, kind: 'upload', status: 'running', total: files.length, done: 0, failed: 0, errors: []};
  ui.jobs.push(job); if (!quiet && !inPlace()) ui.intake = true; render();
  let i = 0;
  const worker = async () => { while (i < files.length && job.status === 'running') { const f = files[i++], dir = folderOf(f);
    const fd = new FormData(); fd.append('author', ui.who); fd.append('files', f, f.name); fd.append('modified', f.lastModified || '');   // the file's own date: a batch is added oldest first
    fd.append('text', [dir ? `From the folder "${dir}".` : '', extraNote || ''].filter(Boolean).join(' '));
    try { await api('/api/intake', {method: 'POST', body: fd}); job.done++; } catch (e) { job.failed++; job.errors.push(`${f.name}: ${e.message}`); }
    safeRender(); } };
  await Promise.all([worker(), worker()]);
  if (job.status === 'running') job.status = 'done';
  toast(`${job.done} file${job.done === 1 ? '' : 's'} from ${name} ${job.done === 1 ? 'is' : 'are'} being read${job.failed ? `; ${job.failed} could not be sent` : ''}.`);
  await refresh(); render();
}
async function addDrive(source) {
  const fd = new FormData(); fd.append('source', source); fd.append('author', ui.who);
  try { const j = await api('/api/intake/folder', {method: 'POST', body: fd}); ui.jobs.push(j); ui.intake = true; render(); pollJobs(); }
  catch (e) { toast(e.message); }
}
let jobTimer = null;
function pollJobs() {
  if (jobTimer) return;
  jobTimer = setInterval(async () => {
    const live = ui.jobs.filter(j => !j.local && ['listing', 'running'].includes(j.status));
    if (!live.length) { clearInterval(jobTimer); jobTimer = null; return; }
    for (const j of live) { try { Object.assign(j, await api(`/api/intake/folder/${j.id}`)); } catch { j.status = 'error'; j.errors = ['Lost contact with the server']; } }
    safeRender();
  }, 1500);
}
function folderJobs() {
  if (!ui.jobs.length) return '';
  const word = {listing: 'Reading the folder', running: 'Adding', done: 'Added', stopped: 'Stopped', error: 'Could not be read'};
  return `<div class="intake-list"><span class="ed-meta">Folders</span><ul class="ed-rows">${ui.jobs.slice().reverse().map(j => {
    const live = ['listing', 'running'].includes(j.status), extra = [j.failed ? `${j.failed} failed` : '', j.already ? `${j.already} added before` : '', j.over_limit ? `${j.over_limit} left out (limit ${(S.config && S.config.folder_max) || 40})` : ''].filter(Boolean).join(' · ');
    return `<li class="ed-row" style="cursor:default"><span class="t">${esc(j.root_name || j.source || 'Folder')}</span>
      <span class="ed-meta ${live ? 'reading' : ''}">${j.kind === 'gdrive' ? 'Google Drive · ' : ''}${word[j.status] || j.status}${j.status === 'listing' ? '' : ` · ${j.done} of ${j.total}`}${extra ? ' · ' + extra : ''}</span>
      <span>${live ? `<button class="ed-link dim" data-act="jobstop" data-id="${esc(j.id)}">Stop</button>` : `<button class="ed-link dim" data-act="jobclear" data-id="${esc(j.id)}">Clear</button>`}</span>
      ${(j.errors || []).length ? `<span class="sub">${esc(j.errors.slice(0, 3).join(' · '))}</span>` : ''}</li>`; }).join('')}</ul></div>`;
}
async function intake(text, files, quiet, onTitle) {      // quiet: stay in the 3D view; the item shows up under + Add
  const fd = new FormData(); fd.append('text', text || ''); fd.append('author', ui.who);
  for (const f of files || []) fd.append('files', f);
  fd.append('modified', [...(files || [])].map(f => f.lastModified || '').join(','));   // each file's own date: a batch is added oldest first
  try { await api('/api/intake', {method: 'POST', body: fd}); toast(quiet ? `Reading it now${onTitle ? `, in relation to ${onTitle}` : ''}. Open + Add to place it.` : inPlace() ? 'Reading it now. It appears under the note field to approve.' : 'Reading it now. It will appear under Waiting to be placed.'); ui.adding = inPlace() && ui.adding; if (!quiet && !inPlace()) ui.intake = true; await refresh(); render(); }
  catch (e) { toast(e.message); }
}
async function accept(id) {
  const it = S.items.find(i => i.id === id); if (!it || !it.proposal) return;
  const r = document.querySelector(`[data-reason="${id}"]`), p = it.proposal;
  try { const out = await post(`/api/items/${id}/approve`, {type: p.type, title: p.title, links: p.links || [], by: ui.who, reason: r ? r.value.trim() : ''});
    const n = effectsOf(out).length; toast(`Added to the record${n ? `. ${n} thing${n > 1 ? 's' : ''} flagged for another look.` : '.'}`); dirty = false; if (inPlace()) ui.view = null; await refresh(); render(); }
  catch (e) { toast(e.message); }
}
async function ask(key, q) {
  if (!q) return;
  const n = D.byId[key];
  ui.ask[key] = {q, loading: true}; render();
  try { ui.ask[key] = {q, res: await post('/api/ask', {question: n ? `About “${n.title}”: ${q}` : q})}; }
  catch (e) { ui.ask[key] = {q, err: e.message}; }
  render();
}
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]');
  if (ui.addMenu && !(b && b.dataset.act === 'addmenu')) { ui.addMenu = false; if (!b) { render(); return; } }   // any click closes the + Add menu
  if (!b) return;
  const act = b.dataset.act, id = b.dataset.id;
  if (act === 'addmenu') { ui.addMenu = !ui.addMenu; ui.addLeft = b.getBoundingClientRect().right < 300; render(); }   // near the left edge the menu opens rightwards
  else if (act === 'pickfiles') { e.preventDefault(); render(); pick(false); }
  else if (act === 'pickdir') { e.preventDefault(); render(); pick(true); }
  else if (act === 'drive') { ui.intake = true; render(); const d = $('#drive-src'); if (d) d.focus(); else toast('Folder links need the converter installed on the server.'); }
  else if (act === 'jobstop') { const j = ui.jobs.find(x => x.id === id); if (j) { if (j.local) j.status = 'stopped'; else { try { Object.assign(j, await post(`/api/intake/folder/${id}/stop`)); } catch (err) { toast(err.message); } } render(); } }
  else if (act === 'jobclear') { ui.jobs = ui.jobs.filter(x => x.id !== id); render(); }
  else if (act === 'relink') {
    try { await post('/api/relink', {by: 'Jev'}); S.linking = true; render(); toast('Jev is reading the items in order and linking each to what came before.'); }
    catch (err) { toast(/404|Not Found/i.test(String(err && err.message)) ? 'This project is running an older copy of the app. Restart it, then try again.' : (err && err.message) || 'Could not start'); refresh(); } }
  else if (act === 'tab') { location.hash = id; }
  else if (act === 'sel') { ui.sel = id; ui.link = null; if (UIX.inNet()) render(); else if (ui.tab !== 'pm') location.hash = 'pm'; else render(); loadDetail(id); }
  else if (act === 'unlink') { ui.link = null; render(); }
  else if (act === 'addlink') { const sg = ui.link && ui.link.res && ui.link.res.suggestions[+id]; if (sg) { b.disabled = true; addLink({source: sg.from, target: sg.to, type: sg.type, reason: sg.reason, confidence: sg.confidence, origin: 'jev'}); } }
  else if (act === 'clearsearch') { ui.search = null; ui.q = ''; render(); }
  else if (act === 'mode') { ui.mode = id; ui.view = null; render(); }
  else if (act === 'cat') { ui.off.has(id) ? ui.off.delete(id) : ui.off.add(id); ui.view = null; render(); }
  else if (act === 'intake') { ui.intake = !ui.intake; render(); }
  else if (act === 'adding') { ui.adding = !ui.adding; ui.view = null; render(); }
  else if (act === 'zoom') { const w = $('#wrap');
    if (id === 'fit') fit(); else if (id === 'arrange') { delete ui.pos[ui.mode]; ui.view = null; render(); } else zoomAt(id === 'in' ? 1.2 : 1 / 1.2, w.clientWidth / 2, w.clientHeight / 2); }
  else if (act === 'accept') { b.disabled = true; accept(id); }
  else if (act === 'batch') { batchRun(id, b.dataset.what); }
  else if (act === 'dismiss') { try { await post(`/api/items/${id}/dismiss`, {by: ui.who, reason: ''}); dirty = false; await refresh(); render(); } catch (err) { toast(err.message); } }
  else if (act === 'replay') { b.disabled = true; try { await post('/api/replay/' + id); } catch (err) { toast(err.message); } await refresh(); render(); }
  else if (act === 'goto') { b.disabled = true; try { await api('/api/replay/goto?to=' + id, {method: 'POST'}); ui.sel = null; ui.view = null; } catch (err) { toast(err.message); } await refresh(); render(); }
  else if (act === 'feedform') { ui.feed = ui.feed ? null : {kind: 'weather', depends: (S.nodes.find(n => n.type === 'event') || {}).id || ''}; render(); }
  else if (act === 'feedremove') { const c = ((S.feeds && S.feeds.custom) || []).find(x => x.node_id === id);
    if (c && confirm(`Remove “${c.title}”? Its links and open flags go with it; the history stays.`)) { try { await post(`/api/feeds/${id}/remove`, {by: ui.who, reason: ''}); if (ui.sel === id) ui.sel = null; toast('Feed removed.'); } catch (err) { toast(err.message); } await refresh(); render(); } }
  else if (act === 'feedsrun') { b.disabled = true; toast('Checking every live feed…'); try { await api('/api/feeds/run', {method: 'POST'}); toast('Feeds checked.'); } catch (err) { toast(err.message); } await refresh(); render(); }
  else if (act === 'rule') { const what = b.dataset.what; let reason = '';
    if (what === 'dismiss') { reason = prompt('Why? (kept in the record, and helps the next run)', ''); if (reason === null) return; }
    try { await post(`/api/rules/${encodeURIComponent(id)}/${what}`, {by: ui.who, reason}); toast(what === 'approve' ? 'Rule is live. It now joins every effects check.' : 'Rule removed.'); } catch (err) { toast(err.message); } await refresh(); render(); }
  else if (act === 'suggest') { if (!confirm('Run the analysis loop now?\n\nIt sends this project\u2019s graph and history to the analysis model and suggests up to 3 rules. It takes about a minute and costs roughly $0.10 to $0.30. Nothing changes until you approve a rule.')) return;
    ui.busy = 'rules'; render(); try { const out = await post('/api/rules/suggest', {by: ui.who}); const n = (out.rules || out.proposed || []).length; toast(n ? `${n} rule${n > 1 ? 's' : ''} suggested.` : 'Analysis finished.'); } catch (err) { toast(err.message); } ui.busy = false; await refresh(); render(); }
  else if (act === 'reset') { if (confirm('Reset the project to its starting state? Everything added since is removed.')) { try { await post('/api/reset'); ui.sel = null; ui.view = null; } catch (err) { toast(err.message); } await refresh(); render(); } }
});
document.addEventListener('submit', async e => {
  const f = e.target; e.preventDefault();
  if (f.dataset.ask != null) ask(f.dataset.ask, f.q.value.trim());
  else if (f.dataset.drive) { const v = f.source.value.trim(); if (v) { f.source.value = ''; addDrive(v); } }
  else if (f.dataset.answer) { const t = f.a.value.trim(); if (!t) return; f.a.value = '';
    try { await post(`/api/items/${f.dataset.answer}/answer`, {answer: t, by: ui.who}); toast('Reading it again with your answer.'); dirty = false; await refresh(); render(); } catch (err) { toast(err.message); } }
  else if (f.dataset.note) { const t = f.text.value.trim(); if (t) { f.text.value = ''; intake(t); } }
  else if (f.dataset.search) { search(f.q.value); }
  else if (f.dataset.feedform) { addFeed(); }
  else if (f.dataset.manual) { addLink({source: ui.link.a, target: ui.link.b, type: f.type.value, reason: f.reason.value.trim(), confidence: 1, origin: 'user'}); }
  else if (f.dataset.resolve) { try { await post(`/api/nodes/${f.dataset.resolve}/resolve`, {by: ui.who, reason: f.reason.value.trim()}); f.reason.value = ''; toast('Marked resolved. The flags it raised are cleared.'); await refresh(); render(); } catch (err) { toast(err.message); } }
});
document.addEventListener('input', e => {
  if (e.target.closest('[data-feedform]') && ui.feed && e.target.name) { ui.feed[e.target.name] = e.target.value; return; }   // kept across re-renders
  if (e.target.closest('[data-search]')) { ui.q = e.target.value; ui.search = null; const q = ui.q.trim().toLowerCase();
    document.querySelectorAll('[data-card]').forEach(c => { const n = D.byId[c.dataset.card]; c.classList.toggle('fade', !!q && !(n.title + ' ' + (n.summary || '') + ' ' + (n.tags || []).join(' ') + ' ' + n.type).toLowerCase().includes(q)); }); }
});
document.addEventListener('change', async e => {
  const t = e.target;
  if (t.dataset.pick || t.dataset.pickall) {     // ticks are kept in ui.picked; the bars are repainted in place
    if (t.dataset.pickall) { ui.picked = new Set(t.checked ? readyItems().map(i => i.id) : []); }
    else if (t.checked) ui.picked.add(t.dataset.pick); else ui.picked.delete(t.dataset.pick);
    document.querySelectorAll('[data-pick]').forEach(c => { c.checked = ui.picked.has(c.dataset.pick); });
    t.blur(); paintBatch(); return;
  }
  if (t.closest('[data-feedform]') && ui.feed && t.name) { ui.feed[t.name] = t.value; if (t.name === 'kind') render(); }
  else if (t.dataset.change === 'project') { pickProject(t); }
  else if (t.dataset.change === 'who') { ui.who = t.value; try { localStorage.setItem('yb.who', ui.who); } catch {} }
  else if (t.dataset.change === 'inject' && t.value) { try { await post('/api/feeds/inject/' + t.value); toast('Simulated: ' + t.value.replace(/_/g, ' ')); } catch (err) { toast(err.message); } await refresh(); render(); }
});
/* Drag and drop is native to the whole page: a file dropped on any tab is sent to intake.
   In the 3D knowledge network the scene stays visible: the nearest node becomes the drop target and the
   file is sent with that node named, so the proposal is made in relation to it. */
let dragDepth = 0, dropOn = null;
const hasFiles = e => [...((e.dataTransfer && e.dataTransfer.types) || [])].includes('Files');
function veil(on) {
  let v = $('#veil');
  if (on && !v) { v = document.createElement('div'); v.id = 'veil'; v.className = 'drop-veil'; v.innerHTML = '<span class="ed-meta">Add to project</span><span class="big">Drop to add to the project</span>'; document.body.appendChild(v); }
  else if (!on && v) v.remove();
}
function dropBar(html, on) {
  let v = $('#dropbar');
  if (html == null) { if (v) v.remove(); return; }
  if (!v) { v = document.createElement('div'); v.id = 'dropbar'; document.body.appendChild(v); }
  v.className = 'drop-bar' + (on ? ' on' : ''); v.innerHTML = html;
}
function netTarget(e) {
  let best = null;
  document.querySelectorAll('#net3d-labels .node-chip[data-id]').forEach(el => { const r = el.getBoundingClientRect();
    const d = Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2 + 14)); if (d < 90 && (!best || d < best.d)) best = {id: el.dataset.id, d, el}; });
  return best;
}
function bldTarget(e) {                                    // Client tab: the part of the building under (or nearest to) the pointer
  const hit = e.target && e.target.closest && e.target.closest('.ed-figure svg g[data-id]');
  if (hit) return {id: hit.dataset.id, el: hit};
  let best = null;
  document.querySelectorAll('.ed-figure svg g[data-id]').forEach(el => { const r = el.getBoundingClientRect();
    const d = Math.hypot(e.clientX - (r.left + r.width / 2), e.clientY - (r.top + r.height / 2)); if (d < 110 && (!best || d < best.d)) best = {id: el.dataset.id, d, el}; });
  return best;
}
/* where a dragged file can be dropped onto one thing: a node in the 3D network, or a part of the building on the Client tab */
const dropSpot = () => UIX.inNet() ? 'net' : ui.tab === 'client' && !ui.intake && document.querySelector('.ed-figure svg g[data-id]') ? 'bld' : null;
function clearDropOn() { document.querySelectorAll('.drop-on').forEach(el => el.classList.remove('drop-on')); dropOn = null; }
const NET_HINT = 'Drop on a node to attach it there, or anywhere to add it';
const BLD_HINT = 'Drop on a part of the building to attach it there, or anywhere to add it';
document.addEventListener('dragenter', e => { if (!hasFiles(e)) return; dragDepth++; const spot = dropSpot(); if (spot) dropBar(spot === 'net' ? NET_HINT : BLD_HINT, false); else veil(true); });
document.addEventListener('dragover', e => { if (!hasFiles(e)) return; e.preventDefault();
  const spot = dropSpot(); if (!spot) return;
  const t = spot === 'net' ? netTarget(e) : bldTarget(e), id = t ? t.id : null;
  if (id !== dropOn) { clearDropOn(); dropOn = id; if (t) t.el.classList.add('drop-on');
    dropBar(t && D.byId[id] ? `Drop to attach to <b>${esc(D.byId[id].title)}</b>` : spot === 'net' ? NET_HINT : BLD_HINT, !!t); } });
document.addEventListener('dragleave', e => { if (!hasFiles(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) { veil(false); dropBar(null); clearDropOn(); } });
document.addEventListener('drop', e => { if (!hasFiles(e)) return; e.preventDefault(); dragDepth = 0; veil(false); dropBar(null);
  const on = dropOn && D.byId[dropOn], spot = dropSpot(); clearDropOn();
  const note = on ? (spot === 'bld' ? `Dropped onto "${on.title}" on the building. It relates to that part.` : `Dropped onto "${on.title}" in the knowledge network. It relates to that node.`) : '';
  filesFromDrop(e.dataTransfer).then(fs => { if (!fs.length) { toast('That folder is empty.'); return; }
    if (fs.some(folderOf)) addFolder(fs, note, !!spot); else intake(note, fs, !!spot, on ? on.title : ''); }).catch(err => toast(err.message)); });

function route() { const h = location.hash.replace('#', ''); if (h === 'data') ui.intake = true;   // old Parking lot links open the drawer
  ui.tab = TABS.some(t => t[0] === h) ? h : 'overview'; ui.view = null; if (S) { render(); if (ui.tab !== 'pm') window.scrollTo(0, 0); } }
window.addEventListener('hashchange', route);
window.addEventListener('resize', () => { if (ui.tab === 'pm' && S) fit(); });

const es = new EventSource(BASE + '/api/events');
const setLive = v => { live = v; const l = $('#live'); if (l) { l.classList.toggle('off', !v); l.lastChild.textContent = v ? 'Live' : 'Offline'; } };
es.onopen = () => setLive(true); es.onerror = () => setLive(false);
let deb; es.onmessage = e => {
  try { const m = JSON.parse(e.data); if (m.type === 'relinked') toast(m.failed ? 'Could not finish finding connections.' : m.links ? `Found ${m.links} connection${m.links === 1 ? '' : 's'}.` : 'Looked again; no further connections found.'); } catch (_) {} clearTimeout(deb); deb = setTimeout(refresh, 150); };
setInterval(refresh, 20000);
const UIX = window.makeUIX({ui, esc, $, api, post, render, toast, inspector, loadDetail, CATS, CAT_ORDER, UNCL, PRESENTER});   // the UI/UX design's additions (uix.js)
route(); loadProjects().then(() => { if (S) render(); }); refresh();
setInterval(() => loadProjects().then(() => { if (S && !dirty) safeRender(); }), 30000);
})();
