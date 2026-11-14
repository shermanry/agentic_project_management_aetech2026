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

import effects
import livefeeds
import pipeline
import seed
from replay import Replay
from store import EDGE_TYPES, IMPORTANCE, NODE_TYPES, Store, new_id, now

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NORTHSTAR_DATA", HERE / "data"))
UPLOADS, PACKAGES = DATA / "uploads", DATA / "packages"
for d in (UPLOADS, PACKAGES):
    d.mkdir(parents=True, exist_ok=True)

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
    if store.empty():
        _seed_warning = await asyncio.to_thread(pipeline.seed_graph, store)
    replay = Replay(store, DATA, PACKAGES, notify, _approve)
    feeds = livefeeds.LiveFeeds(store, notify, submit_text, DATA)
    if os.environ.get("FEEDS_ENABLED", "1").lower() not in ("0", "false", "no"):
        feeds.start()   # polls weather, airspace, rules, city events on their cadences
    threading.Thread(target=pipeline.warm_up, args=(DATA / "warmup",), daemon=True).start()
    for it in store.items():  # anything interrupted by a restart
        if it["status"] in ("processing", "refining"):
            it.update(status="failed", error="interrupted by a restart; add it again")
            store.put_item(it)


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
    return {"project": seed.PROJECT, "people": seed.PEOPLE, "node_types": NODE_TYPES, "edge_types": EDGE_TYPES,
            "nodes": store.nodes(), "edges": store.edges(), "items": [_public_item(i) for i in store.items()],
            "events": store.events(), "replay": replay.status(), "config": {**pipeline.available(), "seed_warning": _seed_warning},
            "feeds": feeds.snapshot() if feeds else None}


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
    return effects.compute(p.type, p.title or it["proposal"]["title"], _checked(p), store.nodes(), store.edges())


def _approve(it: dict, type_: str, title: str, links: list[dict], by: str, reason: str, quiet: bool = False) -> dict:
    """Turn a reviewed proposal into a node, edges, an approval, an event and attention flags."""
    prop, src, item_id = it["proposal"], it["source"], it["id"]
    fx = effects.compute(type_, title, links, store.nodes(), store.edges())
    edited = type_ != prop["type"] or {(l["target"], l["type"]) for l in links} != {(l["target"], l["type"]) for l in prop["links"]}
    node = {"type": type_, "title": title, "summary": prop["summary"], "owner": it.get("author"), "tags": prop["tags"],
            "importance": IMPORTANCE.get(prop["importance"]), "text": src.get("text") or src.get("note") or prop["summary"],
            "metadata": {"package_id": prop.get("package_id"), "kind": prop.get("kind")},
            "data": {"item_id": item_id, "package_id": prop.get("package_id"), "source": src.get("filename") or "message",
                     "added_by": it.get("author")}}
    node_id, seq = store.approve_placement(it, node, links, fx, by, reason, edited)
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
    await asyncio.to_thread(store.reset)
    replay.restart()
    _seed_warning = await asyncio.to_thread(pipeline.seed_graph, store)
    if feeds:
        await asyncio.to_thread(feeds.ensure_nodes)
    notify({"type": "graph", "reset": True})
    return {"ok": True, "warning": _seed_warning}


app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
