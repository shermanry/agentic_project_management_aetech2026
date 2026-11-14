/* YBuild front end: the AeroGraph design (aero.css) on the live north star API.
   No build step. Five pages by hash: #overview #client #pm #pilot #data. Add ?presenter for the demo controls.
   Everything shown comes from GET /api/state; the page re-reads it whenever /api/events says something changed. */
(() => {
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const PRESENTER = new URLSearchParams(location.search).has('presenter');
const TABS = [['overview', 'Overview'], ['client', 'Client'], ['pm', 'PM'], ['pilot', 'Pilot'], ['data', 'Parking lot']];
const CRUMB = {overview: 'Overview', client: 'Client view', pm: 'Knowledge canvas', pilot: 'Pilot brief', data: 'Parking lot'};

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
const REVERSED = new Set(['depends_on', 'derived_from', 'about', 'supersedes']);
const VERB = {depends_on: ['rests on', 'feeds'], derived_from: ['derived from', 'source of'], about: ['about', 'context for'],
              supersedes: ['replaces', 'replaced by'], blocks: ['blocks', 'blocked by'], evidence_for: ['evidence for', 'evidence'],
              similar_to: ['similar to', 'similar to']};
const CW = 202, CH = 114, COL = 318, ROW = CH + 46;

let S = null;            // last /api/state
let D = null;            // derived from S
let live = false, dirty = false;
const ui = {tab: 'overview', sel: null, mode: 'tree', off: new Set(), q: '', view: null, pos: {}, ask: {}, who: 'Mary', adding: false};
try { ui.who = localStorage.getItem('yb.who') || 'Mary'; } catch {}

/* ------------------------------------------------------------------ data */
async function api(path, opt) {
  const r = await fetch(path, opt);
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
  D = {byId, cat, deg, flow, cause, hist, flagged, open, ready: open.filter(i => i.status === 'ready'), events};
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
    try { S = await api('/api/state'); derive(); if (ui.sel && !D.byId[ui.sel]) ui.sel = null; safeRender(); }
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
  const y = window.scrollY, tab = ui.tab;
  const counts = {data: D.open.length, pm: D.flagged.length};
  const page = {overview, client, pm, pilot, data: parking}[tab]();
  $('#root').innerHTML = `<div class="app light tab-${tab} view-${tab === 'pm' ? 'pm' : 'monitor'}">
  <header class="topbar">
    <a class="brand" href="#overview" style="text-decoration:none;display:flex;align-items:center;gap:14px">
      <img src="logo.png" alt="YBuild" style="height:26px;width:auto;display:block">
      <span class="brand-sub" style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-3)">Decision record</span>
    </a>
    <nav class="crumbs"><span>Projects</span><span class="sl">›</span><b>${esc(S.project.name)}</b><span class="sl">›</span><span>${CRUMB[tab]}</span></nav>
    <nav class="seg views">${TABS.map(([id, l]) => `<button class="${id === tab ? 'on' : ''}" data-act="tab" data-id="${id}">${l}${counts[id] ? `<sup class="tab-count">${counts[id]}</sup>` : ''}</button>`).join('')}</nav>
    <div class="status-area">
      <span class="live ${live ? '' : 'off'}" id="live"><i></i>${live ? 'Live' : 'Offline'}</span>
      <label class="who">As <select data-change="who">${S.people.filter(p => p.role !== 'client').map(p => `<option ${p.name === ui.who ? 'selected' : ''}>${esc(p.name)}</option>`).join('')}</select></label>
      <div class="clock"><span class="clock-t" id="clock">${clock()}</span><span class="clock-z">New York</span></div>
    </div>
  </header>
  ${PRESENTER ? presenterBar() : ''}
  ${page}
  </div>`;
  if (tab === 'pm') mountCanvas(); else window.scrollTo(0, y);
}
const clock = () => new Date().toLocaleTimeString('en-US', {timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false});
setInterval(() => { const c = $('#clock'); if (c) c.textContent = clock(); }, 20000);

function presenterBar() {
  const sc = (S.feeds && S.feeds.scenarios) || {};
  const names = Array.isArray(sc) ? sc.map(s => s.id || s) : Object.keys(sc);
  const r = S.replay || {};
  return `<div class="presenter"><b>Presenter</b>
    <select data-change="inject"><option value="">Simulate a change…</option>${names.map(n => `<option value="${esc(n)}">${esc(String(n).replace(/_/g, ' '))}</option>`).join('')}</select>
    <button data-act="replay" data-id="back">◂ Back</button><button data-act="replay" data-id="forward">Forward ▸</button>
    <span class="dim">Story step ${r.cursor ?? 0} of ${(r.steps || []).length}${r.phase && r.phase !== 'idle' ? ' · ' + esc(r.phase) : ''}</span>
    <button data-act="reset" style="margin-left:auto">Reset project</button></div>`;
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
  return `<li class="ed-row pk-row"><span class="t">${esc(p.title)}</span>
    <span class="side"><span class="pk-sg"><span class="ed-meta">→</span><b>${esc(TYPE_LABEL[p.type] || p.type)}</b><span class="ed-meta">${Math.round((p.confidence || 0) * 100)}%</span>
      <span class="ed-meta links">${esc(links.join(' · ') || 'no links proposed')}</span></span>
      <button class="ed-link plain" data-act="accept" data-id="${it.id}">Accept</button><button class="ed-link dim" data-act="dismiss" data-id="${it.id}">Dismiss</button></span>
    ${full && p.summary ? `<span class="sub">${esc(p.summary)}</span>` : ''}
    ${fx.length ? `<span class="sub ed-meta" style="margin-top:6px">If accepted, this would change</span>${fxList(fx, full ? 8 : 3)}` : full ? `<span class="sub">Accepting this changes nothing else.</span>` : ''}
    ${full ? `<span class="sub"><input data-reason="${it.id}" placeholder="Reason for accepting (kept in the record)" style="border:0;border-bottom:1px solid var(--hair);background:none;padding:6px 0;width:min(100%,520px);font-size:14px"></span>` : ''}
  </li>`;
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
const section = (no, title, body, note) => `<section class="ed-section"><div class="ed-label"><span class="ed-meta">${no}</span><h2>${title}</h2>${note ? `<span class="ed-meta" style="text-transform:none;letter-spacing:0;line-height:1.4">${note}</span>` : ''}</div><div class="ed-body">${body}</div></section>`;
const foot = () => `<footer class="ed-foot"><span class="ed-meta">${esc(S.project.name)} · ${S.nodes.length} nodes · ${S.edges.length} links</span><span class="ed-meta">${esc((S.config && S.config.jev_model) || '')}</span></footer>`;

/* ------------------------------------------------------------------ overview */
function overview() {
  const last = [...D.events].reverse().find(e => effectsOf(e.payload).length);
  const again = D.flagged.filter(n => n.type === 'decision').length;
  const lede = D.flagged.length
    ? `${D.flagged.length} ${D.flagged.length === 1 ? 'thing needs' : 'things need'} another look${again ? `, ${again} of them ${again === 1 ? 'a decision' : 'decisions'} already made` : ''}.${last ? ` Latest cause: ${last.title}.` : ''}`
    : 'Nothing is flagged. Every decision still rests on what it was decided on.';
  const recent = [...D.events].reverse().filter(e => e.kind !== 'project.seeded').slice(0, 6);
  const feeds = feedDays();
  return `<main class="ed-page">
  <header class="ov-hero"><span class="ed-meta">${esc(S.project.id)} · Living decision record</span>
    <h1 class="ed-display">${esc(S.project.name)}</h1>
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:44ch">${esc(lede)}</p><button class="ed-link" data-act="tab" data-id="pm">Open the knowledge canvas</button></div></header>
  <section class="ed-nums">
    <div><span class="ed-num">${S.nodes.length}</span><span class="ed-meta">Nodes</span></div>
    <div><span class="ed-num">${S.edges.length}</span><span class="ed-meta">Links</span></div>
    <div><span class="ed-num">${D.open.length}</span><span class="ed-meta">To review</span></div>
    <div><span class="ed-num">${D.flagged.length}</span><span class="ed-meta">Need another look</span></div>
  </section>
  ${section('01', 'Review', D.open.length ? `<ul class="ed-rows">${D.open.map(i => itemRow(i, false)).join('')}</ul>` : `<p class="ed-empty">Nothing is waiting. Drop a file or a note in the parking lot and it will be read, placed and shown here before anything changes.</p>`, 'New information, placed by the agent. Nothing joins the record until someone accepts it.')}
  ${section('02', 'Another look', D.flagged.length ? `<div class="ed-rows">${D.flagged.map(flaggedRow).join('')}</div>` : `<p class="ed-empty">No decision, deliverable or event is at risk.</p>`, 'What a change put at risk, blocked or re-opened, and why.')}
  ${section('03', 'What changed', recent.length ? `<ul class="ed-rows">${recent.map(e => eventRow(e)).join('')}</ul>` : `<p class="ed-empty">No changes since the project was set up.</p>`)}
  ${section('04', 'Ask the record', askBlock('project', 'Why is Thursday’s flight at risk?', true), 'Answers come only from the record and cite the nodes they rest on.')}
  ${section('05', 'Project map', `<div class="ed-cols">${CAT_ORDER.map(c => { const ns = S.nodes.filter(n => D.cat[n.id] === c);
      return `<div class="ed-col"><span class="ed-meta">${CATS[c].label} · ${ns.length}</span>${ns.map(n => `<button class="ed-item" data-act="sel" data-id="${n.id}"><span class="t">${esc(n.title)}</span><span class="ed-meta ${FLAG[n.status] ? 'flag' : ''}">${esc(TYPE_LABEL[n.type] || n.type)} · ${esc(statusLabel(n))}</span></button>`).join('')}</div>`; }).join('')}</div>`)}
  ${section('06', 'Live feeds', feeds.html, 'Monitors that watch the outside world and raise a change when it touches the record.')}
  ${foot()}</main>`;
}
function feedDays() {
  const mons = (S.feeds && S.feeds.monitors) || {}, by = {};
  for (const [name, m] of Object.entries(mons)) (by[m.feed] ||= []).push({name, ...m});
  const keys = Object.keys(by);
  if (!keys.length) return {html: `<p class="ed-empty">No live feeds are running.</p>`};
  const html = `<div class="ed-week" style="grid-template-columns:repeat(${Math.min(keys.length, 7)},minmax(0,1fr))">${keys.map(k => {
    const node = S.nodes.find(n => n.ref === k), ok = by[k].every(m => m.ok), flagged = node && (FLAG[node.status] || node.status === 'changed');
    const lastRun = Math.max(...by[k].map(m => m.last_run || 0));
    return `<div class="ed-day"><span class="ed-meta">${by[k].length} monitor${by[k].length > 1 ? 's' : ''}</span><b style="font-size:clamp(17px,1.6vw,24px);line-height:1.1">${esc(node ? node.title.replace(/ feed.*$/i, '') : k)}</b>
      <span class="ed-glyph ${!ok ? 'bad' : flagged ? 'warn' : 'ok'}"></span><small>${!ok ? esc(by[k].find(m => !m.ok).error || 'Not reachable') : flagged ? 'Raised a change' : 'No change'}${lastRun ? '<br>checked ' + when(lastRun) : ''}</small></div>`; }).join('')}</div>
    <div class="ed-key"><span><i class="ed-glyph ok"></i>No change</span><span><i class="ed-glyph warn"></i>Raised a change</span><span><i class="ed-glyph bad"></i>Not reachable</span></div>`;
  return {html};
}

/* ------------------------------------------------------------------ parking lot */
function parking() {
  const done = S.items.filter(i => i.status === 'approved').slice(0, 12);
  return `<main class="ed-page">
  <header class="ov-hero"><span class="ed-meta">Intake · ${D.open.length} parked</span><h1 class="ed-display md">Parking lot</h1>
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:46ch">Drop anything here: an email, a site note, a permit, a photo. The agent reads it, proposes where it belongs and shows what it would change. You decide.</p></div></header>
  <div class="pk-drop" id="drop"><span class="big">Drop files here</span><button class="ed-link" data-act="browse">Browse</button><input type="file" id="file" multiple>
    <form class="pk-note" data-note="1" style="flex:1 1 320px"><input name="text" placeholder="or paste a note" autocomplete="off" style="flex:1"><button class="ed-link plain">Add</button></form></div>
  ${section('01', 'Parked', D.open.length ? `<ul class="ed-rows">${D.open.map(i => itemRow(i, true)).join('')}</ul>` : `<p class="ed-empty">Nothing parked.</p>`, 'Proposed, not yet part of the record.')}
  ${section('02', 'In the record', done.length ? `<div class="ed-rows">${done.map(i => `<button class="ed-row" ${i.node_id ? `data-act="sel" data-id="${i.node_id}"` : ''}><span class="t">${esc(itemTitle(i))}</span><span class="side"><span class="ed-meta">${esc(TYPE_LABEL[i.proposal && i.proposal.type] || '')} · added by ${esc(i.author || '')}</span><span class="go">→</span></span></button>`).join('')}</div>` : `<p class="ed-empty">Nothing has been accepted from the parking lot yet.</p>`)}
  ${foot()}</main>`;
}

/* ------------------------------------------------------------------ pilot */
function upstream(id) {
  const seen = new Set(), out = [];
  (function walk(x, d) { for (const f of D.flow) if (f.b === x && !seen.has(f.a) && f.e.type !== 'about') { seen.add(f.a); out.push({id: f.a, d, via: f.e.type}); if (d < 3) walk(f.a, d + 1); } })(id, 1);
  return out;
}
function pilot() {
  const flights = S.nodes.filter(n => n.type === 'event');
  const f = flights.find(n => FLAG[n.status]) || flights[0];
  if (!f) return `<main class="ed-page"><header class="ov-hero"><span class="ed-meta">Pilot brief</span><h1 class="ed-display md">No flight yet</h1><p class="ed-lede">Add a flight in the parking lot and its brief appears here.</p></header></main>`;
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
    <button class="ed-link" data-act="sel" data-id="${f.id}">See it on the canvas</button></div></header>
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
    <div class="ov-hero-foot"><p class="ed-lede" style="max-width:46ch">${esc(lede)}</p></div></header>
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
  const q = ui.q.trim().toLowerCase(), hit = n => !q || (n.title + ' ' + (n.summary || '') + ' ' + (n.tags || []).join(' ') + ' ' + n.type).toLowerCase().includes(q);
  const cards = nodes.map(n => { const p = L.pos[n.id], c = D.cat[n.id], fl = FLAG[n.status], cz = fl && D.cause[n.id];
    return `<div class="card ${sel === n.id ? 'sel' : ''} ${(sel && !near.has(n.id)) || !hit(n) ? 'fade' : ''} ${c ? '' : 'uncl'} ${fl ? 'flagged' + (n.status === 'blocked' ? ' bad' : '') : ''}" data-card="${n.id}" style="left:${p.x}px;top:${p.y}px;--cat:${c ? CATS[c].c : UNCL}">
      <i class="port in"></i><i class="port out"></i>
      <div class="card-top"><span class="ico">${TYPE_ICON[n.type] || '•'}</span><span class="kind">${esc(TYPE_LABEL[n.type] || n.type)}</span>${n.data && n.data.item_id ? '<span class="badge t-ai">AI placed</span>' : ''}</div>
      <div class="card-title">${esc(n.title)}</div>
      <div class="${cz ? 'why' : 'card-sub'}">${esc(cz ? cz.why : n.summary || '')}</div>
      <div class="card-foot"><span class="badge t-${tone(n)}">${esc(statusLabel(n))}</span><span class="links">⇄ ${D.deg[n.id]}</span></div></div>`; }).join('');
  const modeInfo = {tree: 'Left to right: what each thing rests on, then what rests on it.', free: 'Grouped by domain. Drag cards anywhere.', dec: 'Each decision between what it rests on and what it affects.'}[ui.mode];
  return `<div class="pm"><div class="pm-main">
    <div class="pm-search pm-add" style="padding-top:18px"><form class="ed-search" data-search="1" style="flex:1 1 320px"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="11" cy="11" r="7"/><path d="M16.5 16.5L21 21"/></svg><input type="search" name="q" placeholder="Search the record" value="${esc(ui.q)}" autocomplete="off"></form>
      <button class="ed-cta" data-act="adding">${ui.adding ? 'Close' : '+ Add to record'}</button></div>
    ${ui.adding ? `<form class="pm-add" data-note="1"><input name="text" placeholder="Type a note, a finding or a change. It is read and proposed, not added directly." autocomplete="off" autofocus><button class="ed-link plain">Send for review</button></form>` : ''}
    <div class="pm-toolbar"><div class="seg sm">${[['tree', 'Tree'], ['free', 'Freeform'], ['dec', 'Decisions']].map(([m, l]) => `<button class="${ui.mode === m ? 'on' : ''}" data-act="mode" data-id="${m}">${l}</button>`).join('')}</div><span class="mode-info dim">${modeInfo}</span></div>
    <div class="chips">${CAT_ORDER.map(c => `<button class="fchip ${ui.off.has(c) ? '' : 'on'}" style="--c:${CATS[c].c}" data-act="cat" data-id="${c}"><i style="width:8px;height:8px;border-radius:50%;background:${CATS[c].c};display:inline-block"></i>${CATS[c].label} <span>${S.nodes.filter(n => D.cat[n.id] === c).length}</span></button>`).join('')}</div>
    <div class="canvas-wrap" id="wrap"><div class="layer" id="layer">
      ${L.groups.map(g => `<div class="gh-group ${g.dashed ? 'dashed' : ''}" style="left:${g.x}px;top:${g.y}px;width:${g.w}px;height:${g.h}px;--c:${g.c}"><span>${esc(g.label)}</span></div>`).join('')}
      ${L.labels.map(g => `<div class="group-label" style="left:${g.x}px;top:${g.y}px">${esc(g.label)}</div>`).join('')}
      <svg class="edges" id="edges" width="1" height="1" style="overflow:visible"></svg>${cards}</div>
      <div class="zoombar"><button data-act="zoom" data-id="out">−</button><span id="zoom" style="min-width:44px;text-align:center;font-size:12px">100%</span><button data-act="zoom" data-id="in">+</button><button data-act="zoom" data-id="fit">Fit</button><button data-act="zoom" data-id="arrange">Auto-arrange</button></div>
      <div class="legend-box"><div class="wire-key"><span class="k-app">Link in the record</span><span class="k-acc">Proposed by the agent, accepted</span></div></div>
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
    const card = e.target.closest('[data-card]'), id = card && card.dataset.card, sx = e.clientX, sy = e.clientY;
    const start = id ? {...L.pos[id]} : {x: ui.view.x, y: ui.view.y}; let moved = false;
    w.setPointerCapture(e.pointerId);
    const move = ev => { const dx = ev.clientX - sx, dy = ev.clientY - sy; if (!moved && Math.hypot(dx, dy) < 4) return; moved = true;
      if (id) { const p = L.pos[id] = {x: start.x + dx / ui.view.k, y: start.y + dy / ui.view.k}; card.style.left = p.x + 'px'; card.style.top = p.y + 'px'; (ui.pos[ui.mode] ||= {})[id] = p; drawEdges(); }
      else { ui.view.x = start.x + dx; ui.view.y = start.y + dy; applyView(); } };
    const up = () => { w.removeEventListener('pointermove', move); w.removeEventListener('pointerup', up); w.removeEventListener('pointercancel', up);
      if (!moved) { ui.sel = id || null; render(); } };
    w.addEventListener('pointermove', move); w.addEventListener('pointerup', up); w.addEventListener('pointercancel', up);
  });
}

function inspector() {
  const n = ui.sel && D.byId[ui.sel];
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
    ${ins.length ? `<section class="ins-sec"><h4>Rests on · ${ins.length}</h4><ul class="rels">${ins.map(f => rel(f, f.a, 'in')).join('')}</ul></section>` : ''}
    ${outs.length ? `<section class="ins-sec"><h4>Affects · ${outs.length}</h4><ul class="rels">${outs.map(f => rel(f, f.b, 'out')).join('')}</ul></section>` : ''}
    ${hist.length ? `<section class="ins-sec"><h4>History</h4><ul class="hist">${hist.map(h => `<li>${h.f ? `<b>${esc(h.f.change)}</b> · ` : ''}${esc(h.ev.title)}<small>${esc(h.ev.actor || '')} · ${when(h.ev.at)}</small></li>`).join('')}</ul></section>` : ''}
    ${canResolve ? `<section class="ins-sec ai-box"><h4>Resolve</h4><form class="ask" data-resolve="${n.id}"><input name="reason" placeholder="What settled it?" autocomplete="off"><button class="btn sm primary">Mark resolved</button></form></section>` : ''}
    <section class="ins-sec"><h4>Ask about this node</h4>${askBlock(n.id, 'Why does this matter?')}</section></div>`;
}

/* ------------------------------------------------------------------ actions */
async function intake(text, files) {
  const fd = new FormData(); fd.append('text', text || ''); fd.append('author', ui.who);
  for (const f of files || []) fd.append('files', f);
  try { await api('/api/intake', {method: 'POST', body: fd}); toast('Reading it now. It will appear under Parked for review.'); ui.adding = false; await refresh(); }
  catch (e) { toast(e.message); }
}
async function accept(id) {
  const it = S.items.find(i => i.id === id); if (!it || !it.proposal) return;
  const r = document.querySelector(`[data-reason="${id}"]`), p = it.proposal;
  try { const out = await post(`/api/items/${id}/approve`, {type: p.type, title: p.title, links: p.links || [], by: ui.who, reason: r ? r.value.trim() : ''});
    const n = effectsOf(out).length; toast(`Added to the record${n ? `. ${n} thing${n > 1 ? 's' : ''} flagged for another look.` : '.'}`); dirty = false; await refresh(); render(); }
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
  const b = e.target.closest('[data-act]'); if (!b) return;
  const act = b.dataset.act, id = b.dataset.id;
  if (act === 'tab') { location.hash = id; }
  else if (act === 'sel') { ui.sel = id; if (ui.tab !== 'pm') location.hash = 'pm'; else render(); }
  else if (act === 'mode') { ui.mode = id; ui.view = null; render(); }
  else if (act === 'cat') { ui.off.has(id) ? ui.off.delete(id) : ui.off.add(id); ui.view = null; render(); }
  else if (act === 'adding') { ui.adding = !ui.adding; ui.view = null; render(); }
  else if (act === 'zoom') { const w = $('#wrap');
    if (id === 'fit') fit(); else if (id === 'arrange') { delete ui.pos[ui.mode]; ui.view = null; render(); } else zoomAt(id === 'in' ? 1.2 : 1 / 1.2, w.clientWidth / 2, w.clientHeight / 2); }
  else if (act === 'accept') { b.disabled = true; accept(id); }
  else if (act === 'dismiss') { try { await post(`/api/items/${id}/dismiss`, {by: ui.who, reason: ''}); dirty = false; await refresh(); render(); } catch (err) { toast(err.message); } }
  else if (act === 'browse') { e.preventDefault(); $('#file').click(); }
  else if (act === 'replay') { b.disabled = true; try { await post('/api/replay/' + id); } catch (err) { toast(err.message); } await refresh(); render(); }
  else if (act === 'reset') { if (confirm('Reset the project to its starting state? Everything added since is removed.')) { try { await post('/api/reset'); ui.sel = null; ui.view = null; } catch (err) { toast(err.message); } await refresh(); render(); } }
});
document.addEventListener('submit', async e => {
  const f = e.target; e.preventDefault();
  if (f.dataset.ask != null) ask(f.dataset.ask, f.q.value.trim());
  else if (f.dataset.note) { const t = f.text.value.trim(); if (t) { f.text.value = ''; intake(t); } }
  else if (f.dataset.search) { ui.q = f.q.value; render(); }
  else if (f.dataset.resolve) { try { await post(`/api/nodes/${f.dataset.resolve}/resolve`, {by: ui.who, reason: f.reason.value.trim()}); f.reason.value = ''; toast('Marked resolved. The flags it raised are cleared.'); await refresh(); render(); } catch (err) { toast(err.message); } }
});
document.addEventListener('input', e => {
  if (e.target.closest('[data-search]')) { ui.q = e.target.value; const q = ui.q.trim().toLowerCase();
    document.querySelectorAll('[data-card]').forEach(c => { const n = D.byId[c.dataset.card]; c.classList.toggle('fade', !!q && !(n.title + ' ' + (n.summary || '') + ' ' + (n.tags || []).join(' ') + ' ' + n.type).toLowerCase().includes(q)); }); }
});
document.addEventListener('change', async e => {
  const t = e.target;
  if (t.id === 'file' && t.files.length) intake('', [...t.files]);
  else if (t.dataset.change === 'who') { ui.who = t.value; try { localStorage.setItem('yb.who', ui.who); } catch {} }
  else if (t.dataset.change === 'inject' && t.value) { try { await post('/api/feeds/inject/' + t.value); toast('Simulated: ' + t.value.replace(/_/g, ' ')); } catch (err) { toast(err.message); } await refresh(); render(); }
});
document.addEventListener('dragover', e => { const d = $('#drop'); if (d) { e.preventDefault(); d.classList.add('over'); } });
document.addEventListener('dragleave', e => { const d = $('#drop'); if (d && !e.relatedTarget) d.classList.remove('over'); });
document.addEventListener('drop', e => { const d = $('#drop'); if (!d) return; e.preventDefault(); d.classList.remove('over'); if (e.dataTransfer.files.length) intake('', [...e.dataTransfer.files]); });

function route() { const h = location.hash.replace('#', ''); ui.tab = TABS.some(t => t[0] === h) ? h : 'overview'; ui.view = null; if (S) { render(); if (ui.tab !== 'pm') window.scrollTo(0, 0); } }
window.addEventListener('hashchange', route);
window.addEventListener('resize', () => { if (ui.tab === 'pm' && S) fit(); });

const es = new EventSource('/api/events');
const setLive = v => { live = v; const l = $('#live'); if (l) { l.classList.toggle('off', !v); l.lastChild.textContent = v ? 'Live' : 'Offline'; } };
es.onopen = () => setLive(true); es.onerror = () => setLive(false);
let deb; es.onmessage = () => { clearTimeout(deb); deb = setTimeout(refresh, 150); };
setInterval(refresh, 20000);
route(); refresh();
})();
