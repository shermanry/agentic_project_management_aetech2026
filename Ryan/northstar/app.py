"""North star MVP: add something -> the system proposes where it goes -> explore the effects -> approve.

Run:  uvicorn app:app --port 8100      (from Ryan/northstar, with the repo-root .env filled in)
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analysis
import effects
import livefeeds
import links
import pipeline
import qa
import seed
from replay import Replay
from store import EDGE_TYPES, IMPORTANCE, NODE_TYPES, Store, new_id, now

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NORTHSTAR_DATA", HERE / "data"))
UPLOADS, PACKAGES = DATA / "uploads", DATA / "packages"
for d in (UPLOADS, PACKAGES):
    d.mkdir(parents=True, exist_ok=True)

# "project" = the working app (default). "demo" = the presentation app: its own database, with the replay controls.
MODE = os.environ.get("NORTHSTAR_MODE", "project").lower()
DEMO_URL = os.environ.get("DEMO_URL", "http://localhost:8200")
store = Store(os.environ.get("DATABASE_URL", "postgresql://drone:drone@localhost:5433/drone"), seed.PROJECT)
app = FastAPI(title="North star intake")
replay: Replay = None  # type: ignore  (created at startup, once notify works)
feeds: livefeeds.LiveFeeds | None = None
_subscribers: list[asyncio.Queue] = []
_loop: asyncio.AbstractEventLoop | None = None
_seed_warning: str | None = None


def notify(msg: dict) -> None:
    """Thread-safe push to every open browser (server-sent events)."""
    if _loop is None:
        return
    for q in list(_subscribers):
        _loop.call_soon_threadsafe(q.put_nowait, msg)


@app.on_event("startup")
async def _startup() -> None:
    global _loop, _seed_warning, replay, feeds
    _loop = asyncio.get_running_loop()
    feeds = livefeeds.LiveFeeds(store, notify, submit_text, DATA)
    replay = Replay(store, DATA, PACKAGES, notify, _approve, feeds, enabled=MODE == "demo")
    if MODE == "demo":                                     # presentation app: the replay drives the graph
        feeds.gate = lambda: not replay.in_setup()         # no feed nodes while the replay is still adding the project's own
        if store.empty() and replay.fresh:
            await asyncio.to_thread(replay.goto, "setup")
    else:                                                  # working project: no replay; feeds only in the full example
        feeds.gate = lambda: replay.template == "full"
        if store.empty() and replay.fresh:
            await asyncio.to_thread(replay.start_project, "starter")
    _seed_warning = replay.warning
    await asyncio.to_thread(replay.ensure_setup_nodes)     # e.g. building parts added to the seed after this project was set up
    await asyncio.to_thread(store.sweep)
    await asyncio.to_thread(analysis.load_active, store)   # approved rules from earlier analysis runs
    if os.environ.get("FEEDS_ENABLED", "1").lower() not in ("0", "false", "no"):
        feeds.start()   # polls weather, airspace, rules, city events on their cadences
    threading.Thread(target=pipeline.warm_up, args=(DATA / "warmup",), daemon=True).start()
    threading.Thread(target=pipeline.index_missing, args=(store, PACKAGES, notify), daemon=True).start()
    for it in store.items():  # anything interrupted by a restart
        if it["status"] in ("processing", "refining"):
            it.update(status="failed", error="interrupted by a restart; add it again")
            store.put_item(it)


_RANK = {"blocked": 3, "at_risk": 3, "reopened": 2, "open": 1}


def parts_rollup(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Each building part with the state of everything linked to it. A part has no status of its own: it is red
    when something about it is blocked or at risk, amber when a decision about it is re-opened or there is an
    open finding or blocker about it. This is what lets a picture of the building light up from the graph."""
    by_id = {n["id"]: n for n in nodes}
    out = []
    for p in nodes:
        if "building-part" not in (p.get("tags") or []):
            continue
        linked, seen = [], set()
        for e in edges:
            other = e["src"] if e["dst"] == p["id"] else e["dst"] if e["src"] == p["id"] else None
            n = by_id.get(other) if other else None
            if not n or n["id"] in seen or e["type"] == "part_of":
                continue
            seen.add(n["id"])
            status = n["status"]
            open_finding = n["type"] in ("discovery", "blocker") and n.get("state") in ("new", "open", "waiting")
            rank = _RANK.get(status, 0) or (1 if open_finding else 0)
            linked.append({"id": n["id"], "title": n["title"], "type": n["type"], "status": status, "link": e["type"],
                           "reason": e.get("reason") or "", "rank": rank})
        own = _RANK.get(p["status"], 0)
        worst = max([own] + [l["rank"] for l in linked])
        linked.sort(key=lambda l: (-l["rank"], l["title"]))
        out.append({"id": p["id"], "ref": p.get("ref"), "part": (p.get("data") or {}).get("part"), "title": p["title"],
                    "summary": p["summary"], "level": "red" if worst >= 3 else "amber" if worst >= 1 else "none",
                    "open": sum(1 for l in linked if l["rank"]), "linked": linked})
    return out


@app.get("/api/parts")
def parts() -> dict:
    """Building parts, each with a level (red / amber / none) rolled up from the nodes linked to it."""
    return {"parts": parts_rollup(store.nodes(), store.edges())}


def _public_item(it: dict) -> dict:
    it = dict(it)
    if it.get("proposal"):
        it["proposal"] = {k: v for k, v in it["proposal"].items() if k != "vector"}
        if it.get("node_id"):
            it["proposal"]["node_id"] = it["node_id"]
    if it.get("source"):
        it["source"] = {k: v for k, v in it["source"].items() if k != "path"}
    return it


@app.get("/api/state")
def state() -> dict:
    nodes, edges = store.nodes(), store.edges()
    return {"project": seed.PROJECT, "people": seed.PEOPLE, "node_types": NODE_TYPES, "edge_types": EDGE_TYPES,
            "nodes": nodes, "edges": edges, "parts": parts_rollup(nodes, edges), "items": [_public_item(i) for i in store.items()],
            "events": store.events(), "replay": replay.status(),
            "config": {**pipeline.available(), "seed_warning": _seed_warning, "mode": MODE, "demo_url": DEMO_URL if MODE != "demo" else None},
            "feeds": feeds.snapshot() if feeds else None, "rules": store.rules(),
            "analysis": {"model": analysis.model(), "running": _analysis_running.is_set()}}


# ---------------------------------------------------------------- analysis loop: only when a person asks
_analysis_running = threading.Event()


class RuleAction(BaseModel):
    by: str = "Sam"
    reason: str = ""


@app.get("/api/rules")
def rules_list() -> dict:
    return {"rules": store.rules(), "model": analysis.model(), "running": _analysis_running.is_set()}


@app.post("/api/rules/suggest")
async def rules_suggest(a: RuleAction) -> dict:
    """Run the analysis loop once over this project's graph and history. Proposes rules; changes nothing else."""
    if _analysis_running.is_set():
        raise HTTPException(409, "An analysis run is already in progress")
    _analysis_running.set()
    notify({"type": "analysis", "status": "running", "by": a.by})
    try:
        out = await asyncio.to_thread(analysis.suggest, store, a.by)
    except Exception as e:
        notify({"type": "analysis", "status": "failed"})
        raise HTTPException(502, f"Analysis failed: {e}")
    finally:
        _analysis_running.clear()
    notify({"type": "graph", "seq": out["revision"]})
    return out


def _rule_status(rule_id: str, status: str, a: RuleAction) -> dict:
    try:
        seq = store.set_rule_status(rule_id, status, a.by, a.reason)
    except KeyError:
        raise HTTPException(404, "No such rule")
    active = analysis.load_active(store)
    notify({"type": "graph", "seq": seq})
    return {"revision": seq, "active_rules": active}


@app.post("/api/rules/{rule_id}/approve")
def rule_approve(rule_id: str, a: RuleAction) -> dict:
    """Make a proposed rule live: from now on it joins the effects checks for every approval and live feed."""
    return _rule_status(rule_id, "active", a)


@app.post("/api/rules/{rule_id}/dismiss")
def rule_dismiss(rule_id: str, a: RuleAction) -> dict:
    """Dismiss a proposal, or retire an active rule."""
    return _rule_status(rule_id, "retired", a)


@app.get("/api/feeds")
def feeds_status() -> dict:
    """Live data monitors: site, last and next run per monitor, errors, demo scenarios."""
    return feeds.snapshot()


@app.post("/api/feeds/run")
async def feeds_run(only: str = "") -> dict:
    """Run monitors now (all, or a comma-separated list) instead of waiting for their cadence."""
    names = [n.strip() for n in only.split(",") if n.strip()] or None
    bad = [n for n in names or [] if n not in feeds.monitors]
    if bad:
        raise HTTPException(400, f"unknown monitors {bad}; choose from {sorted(feeds.monitors)}")
    return await asyncio.to_thread(feeds.run, names)


@app.post("/api/feeds/inject/{scenario}")
async def feeds_inject(scenario: str) -> dict:
    """Demo: feed a canned change through the real path (e.g. thursday_unflyable, tfr_over_site, rule_change)."""
    try:
        return await asyncio.to_thread(feeds.inject, scenario)
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.get("/api/events")
async def events() -> StreamingResponse:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)

    async def gen():
        try:
            yield "retry: 2000\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=20)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if q in _subscribers:
                _subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/intake")
async def intake(text: str = Form(""), author: str = Form("Sam"), files: list[UploadFile] = File(default=[])) -> dict:
    """A drop, a paste or a chat message. Each file becomes one item; text alone becomes one item;
    text sent with files is attached to them as the user's note."""
    text = text.strip()
    created = []
    real = [f for f in files if f.filename]
    if not real and not text:
        raise HTTPException(400, "Nothing to add: send text, files, or both")
    for f in real:
        item_id = new_id("it")
        dest = UPLOADS / f"{item_id}_{Path(f.filename).name}"
        with dest.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        it = {"id": item_id, "status": "processing", "label": f.filename, "author": author,
              "source": {"kind": "file", "filename": f.filename, "path": str(dest), "note": text}, "created_at": now()}
        store.put_item(it)
        created.append(item_id)
    if not real:
        created.append(_new_text_item(text, author))
    for item_id in created:
        _start_processing(item_id)
    return {"items": created}


def _new_text_item(text: str, author: str) -> str:
    item_id = new_id("it")
    store.put_item({"id": item_id, "status": "processing", "label": text.splitlines()[0][:70], "author": author,
                    "source": {"kind": "text", "text": text}, "created_at": now()})
    return item_id


def _start_processing(item_id: str) -> None:
    notify({"type": "item", "id": item_id, "status": "processing"})
    threading.Thread(target=pipeline.process, args=(item_id, store, PACKAGES, notify), daemon=True).start()


def submit_text(text: str, author: str) -> str:
    """Text intake from code (live feeds): same path as typing into the chat box."""
    item_id = _new_text_item(text, author)
    _start_processing(item_id)
    return item_id


class Link(BaseModel):
    target: str
    type: str
    reason: str = ""
    confidence: float = 1.0
    origin: str = "user"


class Placement(BaseModel):
    type: str
    title: str | None = None
    links: list[Link] = []
    by: str = "Sam"
    reason: str = ""


def _ready_item(item_id: str) -> dict:
    it = store.item(item_id)
    if not it:
        raise HTTPException(404, "No such item")
    if it["status"] not in ("ready", "refining"):
        raise HTTPException(409, f"Item is {it['status']}, not open for review")
    return it


def _checked(p: Placement) -> list[dict]:
    if p.type not in NODE_TYPES:
        raise HTTPException(400, f"type must be one of {NODE_TYPES}")
    ids = {n["id"] for n in store.nodes()}
    links = [l.model_dump() for l in p.links]
    for l in links:
        if l["target"] not in ids or l["type"] not in EDGE_TYPES:
            raise HTTPException(400, f"bad link: {l}")
    return links


@app.post("/api/items/{item_id}/preview")
def preview(item_id: str, p: Placement) -> dict:
    """Dry run of the effects for an edited placement. Saves nothing."""
    it = _ready_item(item_id)
    return effects.compute(p.type, p.title or it["proposal"]["title"], _checked(p), store.nodes(), store.edges(), store.caused())


def _approve(it: dict, type_: str, title: str, links: list[dict], by: str, reason: str, quiet: bool = False) -> dict:
    """Turn a reviewed proposal into a node, edges, an approval, an event and attention flags."""
    prop, src, item_id = it["proposal"], it["source"], it["id"]
    fx = effects.compute(type_, title, links, store.nodes(), store.edges(), store.caused())
    edited = type_ != prop["type"] or {(l["target"], l["type"]) for l in links} != {(l["target"], l["type"]) for l in prop["links"]}
    node = {"type": type_, "title": title, "summary": prop["summary"], "owner": it.get("author"), "tags": prop["tags"],
            "importance": IMPORTANCE.get(prop["importance"]), "text": src.get("text") or src.get("note") or prop["summary"],
            "metadata": {"package_id": prop.get("package_id"), "kind": prop.get("kind")},
            "data": {"item_id": item_id, "package_id": prop.get("package_id"), "source": src.get("filename") or "message",
                     "added_by": it.get("author")}}
    node_id, seq = store.approve_placement(it, node, links, fx, by, reason, edited)
    threading.Thread(target=pipeline.index_node, args=(store, node_id, PACKAGES, None if quiet else notify), daemon=True).start()
    if not quiet:
        notify({"type": "graph", "seq": seq, "node_id": node_id})
    return {"node_id": node_id, "effects": fx, "revision": seq}


@app.post("/api/items/{item_id}/approve")
def approve(item_id: str, p: Placement) -> dict:
    it = _ready_item(item_id)
    if it["status"] != "ready":
        raise HTTPException(409, "Still being read; approve when it's ready")
    title, links = p.title or it["proposal"]["title"], _checked(p)
    out = _approve(it, p.type, title, links, p.by, p.reason)
    if replay.item_id == item_id:            # approved by hand during a replay: that counts as the Forward press
        replay.approved_by_hand(it, p.type, title, links)
    return out


@app.post("/api/replay/forward")
def replay_forward() -> dict:
    try:
        return replay.forward()
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/project/new")
async def project_new(template: str = "starter") -> dict:
    """Working project only: wipe it and start again. template = empty | starter | full."""
    global _seed_warning
    if MODE == "demo":
        raise HTTPException(409, "This is the presentation app. Use Reset demo here; start projects in the working app.")
    try:
        out = await asyncio.to_thread(replay.start_project, template)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _seed_warning = replay.warning
    return out


@app.post("/api/replay/goto")
def replay_goto(to: str = "start") -> dict:
    """Jump the replay: to=start is the empty project, to=setup is the project set up before the story."""
    try:
        return replay.goto(to)
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/replay/back")
def replay_back() -> dict:
    try:
        return replay.back()
    except ValueError as e:
        raise HTTPException(409, str(e))


class Dismiss(BaseModel):
    by: str = "Sam"
    reason: str = ""


@app.post("/api/items/{item_id}/dismiss")
def dismiss(item_id: str, d: Dismiss) -> dict:
    it = _ready_item(item_id)
    seq = store.dismiss(it, d.by, d.reason)
    notify({"type": "graph", "seq": seq})
    return {"revision": seq}


class Question(BaseModel):
    question: str


@app.post("/api/ask")
def ask(q: Question) -> dict:
    """Answer from the graph only, returning the passages and nodes the answer rests on."""
    text = q.question.strip()
    if not text:
        raise HTTPException(400, "Ask a question")
    try:
        return qa.ask(text[:1000], store)
    except Exception as e:
        raise HTTPException(502, f"Could not answer: {str(e)[:200]}")


def _csv(v: str) -> list[str]:
    return [x.strip() for x in v.split(",") if x.strip()]


@app.get("/api/search")
def search(q: str = "", type: str = "", owner: str = "", since: str = "", k: int = 10, passages: int = 3) -> dict:
    """Find nodes without calling a model. Combines meaning (embeddings) and keywords, with optional filters:
    type=decision,blocker  owner=Mary  since=2026-11-14. With no q it lists matching nodes, newest first."""
    t0 = now()
    k, passages = max(1, min(k, 50)), max(0, min(passages, 10))
    types = _csv(type)
    bad = [t for t in types if t not in NODE_TYPES]
    if bad:
        raise HTTPException(400, f"unknown type {bad}; use {NODE_TYPES}")
    nodes = {n["id"]: n for n in store.nodes()}
    brief = lambda n: {x: n[x] for x in ("id", "title", "type", "status", "state", "owner", "summary", "tags")}
    try:
        if not q.strip():
            ids = store.list_nodes(types, owner or None, since or None, k)
            return {"query": "", "mode": "list", "seconds": round(now() - t0, 3),
                    "results": [{"node": brief(nodes[i]), "score": None, "matched": [], "passages": []} for i in ids if i in nodes]}
        mode, vec, model = "hybrid", None, None
        try:
            vec, model = pipeline.embeddings.embed(q[:1000], kind="query")[0], pipeline.embeddings.model_id()
        except Exception:
            mode = "keyword"                                   # embedding server unreachable: keywords still work
        hits = store.search_hybrid(q[:1000], vec, model, k * 6, types, owner or None, since or None)
    except Exception as e:
        raise HTTPException(400, f"search failed: {str(e)[:160]}")
    grouped: dict[str, dict] = {}
    for h in hits:
        n = nodes.get(h["node_id"])
        if not n:
            continue
        g = grouped.setdefault(n["id"], {"node": brief(n), "score": 0.0, "matched": set(), "passages": []})
        g["score"] = max(g["score"], h["score"]) + (0.002 if g["passages"] else 0)      # more hits in one node nudges it up
        g["matched"].update(h["matched"])
        if len(g["passages"]) < passages:
            g["passages"].append({"kind": "summary" if h["role"] == "card" else "passage", "locator": h["pointer"] or {},
                                  "text": h["text"][:600], "snippet": h.get("snippet"), "matched": h["matched"],
                                  "similarity": round(h["sim"], 3) if h["sim"] is not None else None})
    results = sorted(grouped.values(), key=lambda g: g["score"], reverse=True)[:k]
    for g in results:
        g["matched"], g["score"] = sorted(g["matched"]), round(g["score"], 4)
    return {"query": q, "mode": mode, "results": results, "seconds": round(now() - t0, 3)}


@app.get("/api/nodes/{node_id}")
def node_detail(node_id: str, limit: int = 50, offset: int = 0) -> dict:
    """Everything about one node: text, source, its passages (paged), links both ways, open flags, what it has
    flagged on other nodes, and its history."""
    d = store.node_detail(node_id, max(1, min(limit, 200)), max(0, offset)) if node_id.isdigit() else None
    if not d:
        raise HTTPException(404, "No such node")
    return d


@app.get("/api/nodes/{node_id}/neighbours")
def neighbours(node_id: str, direction: str = "any", depth: int = 2) -> dict:
    """Walk outward from a node. direction=affects (what is hit if this changes), rests_on (what this depends on),
    or any. depth 1-6."""
    if direction not in ("affects", "rests_on", "any"):
        raise HTTPException(400, "direction must be affects, rests_on or any")
    if not node_id.isdigit() or not store.node(node_id):
        raise HTTPException(404, "No such node")
    depth = max(1, min(depth, 6))
    return {"node_id": node_id, "direction": direction, "depth": depth, "nodes": store.neighbours(node_id, direction, depth)}


class EdgeIn(BaseModel):
    source: str                      # "from" node id
    target: str                      # "to" node id
    type: str = "about"
    reason: str = ""
    confidence: float = 1.0
    origin: str = "user"             # "jev" when a suggestion is accepted unchanged
    by: str = "Sam"


def _edge_nodes(e: EdgeIn, need_type: bool = True) -> tuple[dict, dict]:
    if need_type and e.type not in EDGE_TYPES:
        raise HTTPException(400, f"type must be one of {EDGE_TYPES}")
    if e.source == e.target:
        raise HTTPException(400, "Pick two different nodes")
    src, dst = (store.node(e.source) if e.source.isdigit() else None), (store.node(e.target) if e.target.isdigit() else None)
    if not src or not dst:
        raise HTTPException(404, "No such node")
    return src, dst


@app.post("/api/edges/suggest")
def edge_suggest(e: EdgeIn) -> dict:
    """The user dragged a line between two nodes: how might they be connected, and what would each link change?
    Saves nothing."""
    src, dst = _edge_nodes(e, need_type=False)
    return links.suggest(src["id"], dst["id"], store)


@app.post("/api/edges/preview")
def edge_preview(e: EdgeIn) -> dict:
    """Dry run of one specific link between two existing nodes. Saves nothing."""
    src, dst = _edge_nodes(e)
    return links.edge_effects(src, dst, e.type, store)


@app.post("/api/edges")
def edge_add(e: EdgeIn) -> dict:
    """Add a link between two existing nodes, apply its effects and record it in the history."""
    src, dst = _edge_nodes(e)
    fx = links.edge_effects(src, dst, e.type, store)
    try:
        seq = store.add_edge(src, dst, e.type, e.reason.strip()[:300], e.confidence, "jev" if e.origin == "jev" else "user", e.by, fx,
                             {"suggested_by": "jev" if e.origin == "jev" else None, "source": "drawn on the graph", "added_by": e.by})
    except ValueError as err:
        raise HTTPException(409, str(err))
    notify({"type": "graph", "seq": seq, "node_id": src["id"]})
    return {"revision": seq, "effects": fx}


@app.post("/api/nodes/{node_id}/resolve")
def resolve(node_id: str, d: Dismiss) -> dict:
    """Mark a blocker, discovery or constraint as resolved by hand. Clears the flags it raised."""
    n = store.node(node_id)
    if not n:
        raise HTTPException(404, "No such node")
    if n["type"] not in ("blocker", "discovery", "constraint"):
        raise HTTPException(400, "Only blockers, discoveries and constraints can be marked resolved")
    seq = store.resolve_node(node_id, d.by, d.reason)
    notify({"type": "graph", "seq": seq})
    return {"revision": seq}


@app.get("/api/items/{item_id}/image")
def item_image(item_id: str):
    it = store.item(item_id)
    src = (it or {}).get("source") or {}
    p = Path(src.get("path", ""))
    if it and p.is_file() and p.suffix.lower() in pipeline.IMAGE_EXT and UPLOADS in p.parents:
        return FileResponse(p)
    raise HTTPException(404, "No image for this item")


@app.post("/api/reset")
async def reset() -> dict:
    """Demo helper: wipe the graph and history, reload the example project."""
    global _seed_warning
    if MODE == "demo":
        await asyncio.to_thread(replay.goto, "setup")      # the project as planned, before the story steps
    else:
        await asyncio.to_thread(replay.start_project, replay.template)   # the working project, from its template again
    _seed_warning = replay.warning
    return {"ok": True, "warning": _seed_warning}


WEB = HERE.parent.parent / "web"            # the phased front end (repo root); this page stays as the graph and dev console
if WEB.is_dir():
    app.mount("/app", StaticFiles(directory=WEB, html=True), name="web")
app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
