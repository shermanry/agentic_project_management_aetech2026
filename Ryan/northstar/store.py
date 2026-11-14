"""SQLite store: nodes, edges, intake items (proposals) and an append-only event log.

Every change to the graph is written to `events` first-class, so the decision history, a replay and the
stream the UI listens to all come from one table. Swappable for Postgres later: nothing outside this file
touches SQL.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

NODE_TYPES = ["decision", "discovery", "event", "data_feed", "deliverable", "blocker", "constraint", "document", "entity"]
EDGE_TYPES = ["depends_on", "blocks", "about", "evidence_for", "supersedes", "derived_from", "similar_to"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (id TEXT PRIMARY KEY, type TEXT, title TEXT, summary TEXT, status TEXT, owner TEXT,
  tags TEXT, data TEXT, vector TEXT, vector_model TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS edges (id TEXT PRIMARY KEY, src TEXT, dst TEXT, type TEXT, reason TEXT, confidence REAL,
  origin TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, status TEXT, label TEXT, author TEXT, source TEXT,
  proposal TEXT, timings TEXT, error TEXT, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY AUTOINCREMENT, at REAL, actor TEXT, kind TEXT, title TEXT,
  reason TEXT, payload TEXT);
"""


def now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(_SCHEMA)
            self.db.commit()

    # ---- helpers
    def _rows(self, sql: str, args=()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def _exec(self, sql: str, args=()) -> None:
        with self.lock:
            self.db.execute(sql, args)
            self.db.commit()

    @staticmethod
    def _node(r: dict, with_vector: bool = False) -> dict:
        n = {**r, "tags": json.loads(r["tags"] or "[]"), "data": json.loads(r["data"] or "{}")}
        vec = n.pop("vector", None)
        if with_vector:
            n["vector"] = json.loads(vec) if vec else None
        return n

    # ---- nodes / edges
    def nodes(self, with_vectors: bool = False) -> list[dict]:
        return [self._node(r, with_vectors) for r in self._rows("SELECT * FROM nodes ORDER BY created_at")]

    def node(self, node_id: str) -> dict | None:
        rows = self._rows("SELECT * FROM nodes WHERE id=?", (node_id,))
        return self._node(rows[0]) if rows else None

    def put_node(self, n: dict, vector: list[float] | None = None, vector_model: str | None = None) -> None:
        self._exec("INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            n["id"], n["type"], n["title"], n.get("summary", ""), n.get("status", "active"), n.get("owner"),
            json.dumps(n.get("tags", [])), json.dumps(n.get("data", {})),
            json.dumps(vector) if vector else None, vector_model, n.get("created_at", now())))

    def set_status(self, node_id: str, status: str) -> None:
        self._exec("UPDATE nodes SET status=? WHERE id=?", (status, node_id))

    def edges(self) -> list[dict]:
        return self._rows("SELECT * FROM edges ORDER BY created_at")

    def put_edge(self, src: str, dst: str, type_: str, reason: str = "", confidence: float = 1.0, origin: str = "seed") -> str:
        eid = new_id("e")
        self._exec("INSERT INTO edges VALUES (?,?,?,?,?,?,?,?)", (eid, src, dst, type_, reason, confidence, origin, now()))
        return eid

    # ---- intake items
    def items(self) -> list[dict]:
        out = []
        for r in self._rows("SELECT * FROM items ORDER BY created_at DESC"):
            for k in ("source", "proposal", "timings"):
                r[k] = json.loads(r[k]) if r[k] else None
            out.append(r)
        return out

    def item(self, item_id: str) -> dict | None:
        return next((i for i in self.items() if i["id"] == item_id), None)

    def put_item(self, it: dict) -> None:
        self._exec("INSERT OR REPLACE INTO items VALUES (?,?,?,?,?,?,?,?,?,?)", (
            it["id"], it["status"], it["label"], it.get("author"), json.dumps(it.get("source")),
            json.dumps(it.get("proposal")), json.dumps(it.get("timings")), it.get("error"),
            it.get("created_at", now()), now()))

    # ---- event log (the revision history)
    def log(self, actor: str, kind: str, title: str, reason: str = "", payload: dict | None = None) -> int:
        with self.lock:
            cur = self.db.execute("INSERT INTO events (at, actor, kind, title, reason, payload) VALUES (?,?,?,?,?,?)",
                                  (now(), actor, kind, title, reason, json.dumps(payload or {})))
            self.db.commit()
            return cur.lastrowid

    def events(self, limit: int = 200) -> list[dict]:
        rows = self._rows("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,))
        for r in rows:
            r["payload"] = json.loads(r["payload"] or "{}")
        return rows

    def empty(self) -> bool:
        return not self._rows("SELECT id FROM nodes LIMIT 1")
