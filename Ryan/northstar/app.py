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
import pipeline
import seed
from store import EDGE_TYPES, NODE_TYPES, Store, new_id, now

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("NORTHSTAR_DATA", HERE / "data"))
UPLOADS, PACKAGES = DATA / "uploads", DATA / "packages"
for d in (UPLOADS, PACKAGES):
    d.mkdir(parents=True, exist_ok=True)

store = Store(DATA / "northstar.db")
app = FastAPI(title="North star intake")
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
    global _loop, _seed_warning
    _loop = asyncio.get_running_loop()
    if store.empty():
        _seed_warning = await asyncio.to_thread(pipeline.seed_graph, store)
    threading.Thread(target=pipeline.warm_up, args=(DATA / "warmup",), daemon=True).start()
    for it in store.items():  # anything interrupted by a restart
        if it["status"] in ("processing", "refining"):
            it.update(status="failed", error="interrupted by a restart; add it again")
            store.put_item(it)


def _public_item(it: dict) -> dict:
    it = dict(it)
    if it.get("proposal"):
        it["proposal"] = {k: v for k, v in it["proposal"].items() if k != "vector"}
    if it.get("source"):
        it["source"] = {k: v for k, v in it["source"].items() if k != "path"}
    return it


@app.get("/api/state")
def state() -> dict:
    return {"project": seed.PROJECT, "people": seed.PEOPLE, "node_types": NODE_TYPES, "edge_types": EDGE_TYPES,
            "nodes": store.nodes(), "edges": store.edges(), "items": [_public_item(i) for i in store.items()],
            "events": store.events(), "config": {**pipeline.available(), "seed_warning": _seed_warning}}


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
        item_id = new_id("it")
        it = {"id": item_id, "status": "processing", "label": text[:70], "author": author,
              "source": {"kind": "text", "text": text}, "created_at": now()}
        store.put_item(it)
        created.append(item_id)
    for item_id in created:
        notify({"type": "item", "id": item_id, "status": "processing"})
        threading.Thread(target=pipeline.process, args=(item_id, store, PACKAGES, notify), daemon=True).start()
    return {"items": created}


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


@app.post("/api/items/{item_id}/approve")
def approve(item_id: str, p: Placement) -> dict:
    it = _ready_item(item_id)
    if it["status"] != "ready":
        raise HTTPException(409, "Still being read; approve when it's ready")
    prop, links = it["proposal"], _checked(p)
    title = p.title or prop["title"]
    fx = effects.compute(p.type, title, links, store.nodes(), store.edges())
    node_id = new_id("n")
    status = {"blocker": "open", "discovery": "new", "decision": "awaiting_inputs"}.get(p.type, "active")
    src = it["source"]
    store.put_node({"id": node_id, "type": p.type, "title": title, "summary": prop["summary"], "status": status,
                    "owner": it.get("author"), "tags": prop["tags"],
                    "data": {"importance": prop["importance"], "item_id": item_id, "package_id": prop.get("package_id"),
                             "source": src.get("filename") or "message", "added_by": it.get("author"),
                             "text": src.get("text") or src.get("note") or ""}},
                   vector=prop.get("vector"), vector_model=prop.get("vector_model"))
    for l in links:
        store.put_edge(node_id, l["target"], l["type"], l["reason"], l["confidence"], l["origin"])
    for e in fx["effects"]:
        if e["new_status"]:
            store.set_status(e["node_id"], e["new_status"])
    edited = p.type != prop["type"] or {(l["target"], l["type"]) for l in links} != {(l["target"], l["type"]) for l in prop["links"]}
    seq = store.log(p.by, "placement_approved", f"Added “{title}” as {p.type}", p.reason, {
        "node_id": node_id, "item_id": item_id, "source": src.get("filename") or "message", "added_by": it.get("author"),
        "proposed_by": prop.get("by"), "edited_by_user": edited,
        "links": [{"target": l["target"], "type": l["type"], "reason": l["reason"]} for l in links],
        "effects": [{"node_id": e["node_id"], "title": e["title"], "change": e["change"], "why": e["why"]} for e in fx["effects"]],
        "notify": fx["notify"]})
    it.update(status="approved")
    it["proposal"]["node_id"] = node_id
    store.put_item(it)
    notify({"type": "graph", "seq": seq, "node_id": node_id})
    return {"node_id": node_id, "effects": fx, "revision": seq}


class Dismiss(BaseModel):
    by: str = "Sam"
    reason: str = ""


@app.post("/api/items/{item_id}/dismiss")
def dismiss(item_id: str, d: Dismiss) -> dict:
    it = _ready_item(item_id)
    seq = store.log(d.by, "placement_dismissed", f"Dismissed “{it['proposal']['title'] if it.get('proposal') else it['label']}”",
                    d.reason, {"item_id": item_id})
    it.update(status="dismissed")
    store.put_item(it)
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
    with store.lock:
        for t in ("nodes", "edges", "items", "events"):
            store.db.execute(f"DELETE FROM {t}")
        store.db.commit()
    _seed_warning = await asyncio.to_thread(pipeline.seed_graph, store)
    notify({"type": "graph", "reset": True})
    return {"ok": True, "warning": _seed_warning}


app.mount("/", StaticFiles(directory=HERE / "static", html=True), name="static")
