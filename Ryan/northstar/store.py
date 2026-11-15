"""Postgres + pgvector store, on the team's shared schema (db/001_schema.sql, from Sharare's decision engine).

What goes where:
  nodes / node_versions / chunks   the graph of record; one 'card' chunk per node holds its pgvector embedding
  entity_aliases                   "drone 4a" -> Drone 4A (exact name matching)
  edges                            typed links with origin, confidence and reason
  approvals + events               every approval or dismissal; events is the append-only decision history
  attention_items                  what an approved item put at risk, blocked or re-opened
  intake_items (db/010)            items being processed or waiting for review (north star only)

Nothing outside this file touches SQL.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

NODE_TYPES = ["decision", "discovery", "event", "data_feed", "deliverable", "blocker", "constraint", "document", "entity"]
EDGE_TYPES = ["depends_on", "blocks", "about", "evidence_for", "supersedes", "derived_from", "similar_to", "part_of"]
IMPORTANCE = {"low": 0.25, "medium": 0.5, "high": 0.75, "critical": 1.0}
_EDGE_ORIGIN = {"jev": "agent", "seed": "user", "user": "user"}
_ATTENTION_TYPE = {"blocked": "blocker", "at_risk": "blocker", "reopened": "decision", "superseded": "decision"}
DB_DIR = Path(__file__).resolve().parent / "db"


def now() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _vec(v: list[float] | None) -> str | None:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]" if v else None


class Store:
    def __init__(self, url: str, project: dict):
        self.project = project
        self.pool = ConnectionPool(url, min_size=1, max_size=8, open=True,
                                   kwargs={"autocommit": True, "row_factory": dict_row})
        self.pool.wait(timeout=30)
        self._ensure_schema()
        self._states = {r["type"]: r["states"] for r in self._q("SELECT type, states FROM node_types")}

    # ---------------------------------------------------------------- plumbing
    def _q(self, sql: str, args=None) -> list[dict]:
        with self.pool.connection() as c:
            cur = c.execute(sql, args)
            return cur.fetchall() if cur.description else []

    def _ensure_schema(self) -> None:
        """Create the schema if this is an empty database (docker-entrypoint may already have done it)."""
        with self.pool.connection() as c:
            for table, f in (("nodes", "001_schema.sql"), ("intake_items", "010_northstar.sql")):
                if c.execute("SELECT to_regclass(%s) AS t", (f"public.{table}",)).fetchone()["t"] is None:
                    c.execute((DB_DIR / f).read_text())
            c.execute((DB_DIR / "020_search.sql").read_text())      # idempotent indexes
            c.execute("INSERT INTO projects (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                      (self.project["id"], self.project["name"]))

    def user(self, name: str | None) -> str:
        """Users table id for a display name; creates the user on first use."""
        name = (name or "someone").strip()
        fixed = {"system": ("svc_northstar", "North star", "service"), "jev": ("agent_jev", "Jev", "agent"),
                 "monitors": ("svc_monitors", "Monitors", "service"),
                 "analysis": ("agent_analysis", "Analysis loop", "agent")}
        uid, label, kind = fixed.get(name.lower(), ("u_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"), name, "human"))
        self._q("INSERT INTO users (id, name, kind) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING", (uid, label, kind))
        return uid

    # ---------------------------------------------------------------- read the graph
    def nodes(self) -> list[dict]:
        rows = self._q("""
            SELECT n.id::text AS id, n.ref, n.type, n.title, n.state, n.tags, n.data, n.importance,
                   extract(epoch FROM n.created_at)::float AS created_at, u.name AS owner, coalesce(h.summary, '') AS summary
            FROM nodes n LEFT JOIN users u ON u.id = n.owner_id LEFT JOIN node_head h ON h.node_id = n.id
            WHERE n.project_id = %s AND n.status = 'confirmed' ORDER BY n.id""", (self.project["id"],))
        aliases: dict[str, list[str]] = {}
        for r in self._q("SELECT entity_node_id::text AS id, alias FROM entity_aliases"):
            aliases.setdefault(r["id"], []).append(r["alias"])
        flags: dict[str, str] = {}
        for r in self._q("SELECT touches, matched_by FROM attention_items WHERE project_id = %s AND state = 'open' ORDER BY id",
                         (self.project["id"],)):
            status = next((m.split(":", 1)[1] for m in r["matched_by"] if m.startswith("effect:")), None)
            for nid in r["touches"]:
                if status:
                    flags[str(nid)] = status
        for n in rows:
            n["data"] = {**(n["data"] or {}), **({"aliases": aliases[n["id"]]} if n["id"] in aliases else {})}
            n["status"] = flags.get(n["id"], n["state"])   # what the UI shows: an open attention flag wins over the state
        return rows

    def node(self, node_id: str) -> dict | None:
        return next((n for n in self.nodes() if n["id"] == str(node_id)), None)

    def edges(self) -> list[dict]:
        return self._q("""SELECT id::text AS id, from_node::text AS src, to_node::text AS dst, type, reason, confidence, origin
                          FROM edges WHERE project_id = %s AND status = 'accepted' ORDER BY id""", (self.project["id"],))

    def similar(self, vector: list[float], model: str) -> dict[str, float]:
        """Cosine similarity of every node's card vector to `vector` (pgvector), within one embedding model."""
        rows = self._q("""
            SELECT h.node_id::text AS id, 1 - (c.embedding <=> %s::vector) AS sim
            FROM chunks c JOIN node_head h ON h.id = c.node_version_id JOIN nodes n ON n.id = h.node_id
            WHERE c.role = 'card' AND c.embedding IS NOT NULL AND c.embedding_model = %s
              AND n.project_id = %s AND n.status = 'confirmed'""", (_vec(vector), model, self.project["id"]))
        return {r["id"]: float(r["sim"]) for r in rows}

    # ---------------------------------------------------------------- passages for question answering
    def node_text(self, node_id: str) -> tuple[str, str]:
        r = self._q("SELECT coalesce(content_text, '') AS t, coalesce(summary, '') AS s FROM node_head WHERE node_id = %s", (int(node_id),))
        return (r[0]["t"], r[0]["s"]) if r else ("", "")

    def unindexed(self) -> list[str]:
        """Nodes that only have their card chunk: their document passages have not been embedded yet."""
        return [r["id"] for r in self._q("""
            SELECT n.id::text AS id FROM nodes n JOIN node_head h ON h.node_id = n.id
            WHERE n.project_id = %s AND n.status = 'confirmed'
              AND NOT EXISTS (SELECT 1 FROM chunks c WHERE c.node_version_id = h.id AND c.role <> 'card') ORDER BY n.id""",
            (self.project["id"],))]

    def add_chunks(self, node_id: str, rows: list[dict], vectors: list[list[float]], model: str) -> int:
        with self.pool.connection() as c, c.transaction():
            head = c.execute("SELECT id FROM node_head WHERE node_id = %s", (int(node_id),)).fetchone()
            if not head:
                return 0                                   # node went away meanwhile (replay rebuilt the graph)
            vid = head["id"]
            if c.execute("SELECT 1 FROM chunks WHERE node_version_id = %s AND role <> 'card' LIMIT 1", (vid,)).fetchone():
                return 0                                   # someone else indexed it meanwhile
            for i, (r, v) in enumerate(zip(rows, vectors), 1):
                c.execute("""INSERT INTO chunks (node_version_id, idx, modality, role, text, pointer, embedding, embedding_model, embedded_at)
                             VALUES (%s, %s, 'text', %s, %s, %s, %s::vector, %s, now())""",
                          (vid, i, r.get("role") or "body", r["text"], Jsonb(r.get("pointer") or {}), _vec(v), model))
        return len(rows)

    def search(self, vector: list[float], model: str, k: int) -> list[dict]:
        """Nearest chunks of any kind (node cards and document passages) to a query vector."""
        return self._q("""
            SELECT n.id::text AS node_id, c.role, c.text, c.pointer, 1 - (c.embedding <=> %s::vector) AS sim
            FROM chunks c JOIN node_head h ON h.id = c.node_version_id JOIN nodes n ON n.id = h.node_id
            WHERE c.embedding IS NOT NULL AND c.embedding_model = %s AND n.project_id = %s AND n.status = 'confirmed'
            ORDER BY c.embedding <=> %s::vector LIMIT %s""", (_vec(vector), model, self.project["id"], _vec(vector), k))

    # ---------------------------------------------------------------- hybrid search, node detail, neighbours
    _OR_QUERY = "replace(plainto_tsquery('english', %s)::text, '&', '|')::tsquery"      # any of the words, ranked

    def _node_filter(self, types, owner, since) -> tuple[str, list]:
        sql, args = "n.project_id = %s AND n.status = 'confirmed'", [self.project["id"]]
        if types:
            sql += " AND n.type = ANY (%s)"; args.append(list(types))
        if owner:
            sql += " AND n.owner_id IN (SELECT id FROM users WHERE lower(name) = lower(%s))"; args.append(owner)
        if since:
            sql += " AND n.created_at >= %s::timestamptz"; args.append(since)
        return sql, args

    def search_hybrid(self, text: str, vector: list[float] | None, model: str | None, k: int = 30,
                      types=None, owner: str | None = None, since: str | None = None) -> list[dict]:
        """Chunks ranked by meaning (pgvector) and by keywords (Postgres full-text), fused with reciprocal rank.
        Either side can be missing: no vector -> keywords only; no words that match -> meaning only."""
        where, wargs = self._node_filter(types, owner, since)
        base = "FROM chunks c JOIN node_head h ON h.id = c.node_version_id JOIN nodes n ON n.id = h.node_id WHERE " + where
        pool = max(k * 2, 40)
        hits: dict[int, dict] = {}
        if vector and model:
            for rank, r in enumerate(self._q(f"""
                    SELECT c.id, n.id::text AS node_id, c.role, c.text, c.pointer, 1 - (c.embedding <=> %s::vector) AS sim
                    {base} AND c.embedding IS NOT NULL AND c.embedding_model = %s
                    ORDER BY c.embedding <=> %s::vector LIMIT %s""", [_vec(vector), *wargs, model, _vec(vector), pool]), 1):
                hits[r["id"]] = {**r, "sim": float(r["sim"]), "kw": None, "snippet": None, "score": 1 / (60 + rank), "matched": ["meaning"]}
        if text.strip():
            for rank, r in enumerate(self._q(f"""
                    WITH q AS (SELECT {self._OR_QUERY} AS tsq)
                    SELECT c.id, n.id::text AS node_id, c.role, c.text, c.pointer,
                           ts_rank_cd(to_tsvector('english', c.text), q.tsq) AS kw,
                           ts_headline('english', c.text, q.tsq, 'MaxFragments=1,MaxWords=45,MinWords=20,StartSel=[[,StopSel=]]') AS snippet
                    {base.replace('FROM chunks c', 'FROM q, chunks c')} AND to_tsvector('english', c.text) @@ q.tsq
                    ORDER BY kw DESC LIMIT %s""", [text, *wargs, pool]), 1):
                h = hits.get(r["id"])
                if h:
                    h.update(kw=float(r["kw"]), snippet=r["snippet"], score=h["score"] + 1 / (60 + rank), matched=["meaning", "keyword"])
                else:
                    hits[r["id"]] = {**r, "sim": None, "kw": float(r["kw"]), "score": 1 / (60 + rank), "matched": ["keyword"]}
        return sorted(hits.values(), key=lambda h: h["score"], reverse=True)[:k]

    def list_nodes(self, types=None, owner=None, since=None, limit: int = 50) -> list[str]:
        where, wargs = self._node_filter(types, owner, since)
        return [r["id"] for r in self._q(f"SELECT n.id::text AS id FROM nodes n WHERE {where} ORDER BY n.created_at DESC LIMIT %s", [*wargs, limit])]

    def node_detail(self, node_id: str, limit: int = 50, offset: int = 0) -> dict | None:
        nodes = {n["id"]: n for n in self.nodes()}
        n = nodes.get(str(node_id))
        if not n:
            return None
        nid = int(node_id)
        brief = lambda i: {k: nodes[i][k] for k in ("id", "title", "type", "status", "owner")} if i in nodes else {"id": i}
        text, _ = self.node_text(node_id)
        total = self._q("""SELECT count(*) AS c FROM chunks c JOIN node_head h ON h.id = c.node_version_id
                           WHERE h.node_id = %s AND c.role <> 'card'""", (nid,))[0]["c"]
        passages = self._q("""SELECT c.idx, c.role, c.modality, c.text, c.pointer FROM chunks c JOIN node_head h ON h.id = c.node_version_id
                              WHERE h.node_id = %s AND c.role <> 'card' ORDER BY c.idx LIMIT %s OFFSET %s""", (nid, limit, offset))
        edges = self._q("""SELECT id::text AS id, from_node::text AS src, to_node::text AS dst, type, reason, confidence, origin
                           FROM edges WHERE status = 'accepted' AND (from_node = %s OR to_node = %s) ORDER BY id""", (nid, nid))
        history = self._q("""SELECT e.id AS seq, extract(epoch FROM e.at)::float AS at, u.name AS actor, e.verb AS kind, e.payload
                             FROM events e JOIN users u ON u.id = e.actor_id
                             WHERE e.project_id = %s AND (e.object_id = %s OR e.payload->>'node_id' = %s
                                   OR e.payload->'effects' @> %s::jsonb) ORDER BY e.id DESC LIMIT 50""",
                          (self.project["id"], nid, str(node_id), json.dumps([{"node_id": str(node_id)}])))
        for h in history:
            h["title"], h["reason"] = h["payload"].get("title", h["kind"]), h["payload"].get("reason", "")
        flags = [f for f in self.flags() if f["node_id"] == str(node_id)]
        raised = [{**brief(t), "because": n["title"]} for t in self.caused().get(str(node_id), [])]
        d = n.get("data") or {}
        return {"node": {**n, "text": text},
                "source": {"kind": "file" if d.get("package_id") else ("message" if d.get("source") == "message" else "seed"),
                           "name": d.get("source"), "added_by": d.get("added_by"), "package_id": d.get("package_id"), "item_id": d.get("item_id")},
                "passages": {"total": total, "offset": offset, "items": passages},
                "links_out": [{**e, "node": brief(e["dst"])} for e in edges if e["src"] == str(node_id)],
                "links_in": [{**e, "node": brief(e["src"])} for e in edges if e["dst"] == str(node_id)],
                "flags": flags, "raised": raised, "history": history}

    _STEPS = {   # (src, dst): following an edge from src reaches dst
        "affects": """SELECT to_node AS src, from_node AS dst, id, type FROM edges WHERE type = 'depends_on' AND status = 'accepted' AND project_id = %(p)s
                      UNION ALL SELECT from_node, to_node, id, type FROM edges WHERE type = 'blocks' AND status = 'accepted' AND project_id = %(p)s""",
        "rests_on": """SELECT from_node AS src, to_node AS dst, id, type FROM edges WHERE type = 'depends_on' AND status = 'accepted' AND project_id = %(p)s
                       UNION ALL SELECT to_node, from_node, id, type FROM edges WHERE type = 'blocks' AND status = 'accepted' AND project_id = %(p)s""",
        "any": """SELECT from_node AS src, to_node AS dst, id, type FROM edges WHERE status = 'accepted' AND project_id = %(p)s
                  UNION ALL SELECT to_node, from_node, id, type FROM edges WHERE status = 'accepted' AND project_id = %(p)s""",
    }

    def neighbours(self, node_id: str, direction: str = "any", depth: int = 2) -> list[dict]:
        """Walk the graph in the database (recursive query). affects = what would be hit if this changed;
        rests_on = what this depends on; any = plain neighbourhood. Returns each node once, at its shortest distance."""
        rows = self._q(f"""
            WITH RECURSIVE step AS ({self._STEPS[direction]}),
            walk(id, depth, via, edge_type, path) AS (
                SELECT %(id)s::bigint, 0, NULL::bigint, NULL::text, ARRAY[%(id)s::bigint]
                UNION ALL
                SELECT s.dst, w.depth + 1, w.id, s.type, w.path || s.dst
                FROM walk w JOIN step s ON s.src = w.id
                WHERE w.depth < %(depth)s AND NOT s.dst = ANY (w.path))
            SELECT DISTINCT ON (id) id::text AS id, depth, via::text AS via, edge_type, array_to_string(path, '>') AS path
            FROM walk WHERE depth > 0 ORDER BY id, depth""", {"p": self.project["id"], "id": int(node_id), "depth": depth})
        nodes = {n["id"]: n for n in self.nodes()}
        out = [{**{k: nodes[r["id"]][k] for k in ("id", "title", "type", "status", "owner")}, "depth": r["depth"], "via": r["via"],
                "edge_type": r["edge_type"], "path": r["path"].split(">")} for r in rows if r["id"] in nodes]
        return sorted(out, key=lambda r: (r["depth"], r["title"]))

    def flags(self) -> list[dict]:
        """Open attention flags, newest first: which node, what status, why, and which node caused it."""
        out = []
        for r in self._q("""SELECT a.touches, a.matched_by, a.reason, src.title AS source_title
                            FROM attention_items a LEFT JOIN events e ON e.id = a.event_id
                            LEFT JOIN nodes src ON src.id = e.object_id AND e.object_type = 'node'
                            WHERE a.project_id = %s AND a.state = 'open' ORDER BY a.id DESC""", (self.project["id"],)):
            status = next((m.split(":", 1)[1] for m in r["matched_by"] if m.startswith("effect:")), None)
            for nid in r["touches"]:
                if status:
                    out.append({"node_id": str(nid), "status": status, "reason": r["reason"], "source_title": r["source_title"]})
        return out

    def caused(self) -> dict[str, list[str]]:
        """source node id -> node ids it currently flags (open attention items raised when it was approved)."""
        out: dict[str, list[str]] = {}
        for r in self._q("""SELECT e.object_id::text AS source, a.touches FROM attention_items a JOIN events e ON e.id = a.event_id
                            WHERE a.project_id = %s AND a.state = 'open' AND e.object_id IS NOT NULL""", (self.project["id"],)):
            out.setdefault(r["source"], []).extend(str(t) for t in r["touches"])
        return out

    _RESOLVED_STATE = {"blocker": "done", "discovery": "absorbed", "constraint": "expired", "decision": "superseded"}

    def _resolve(self, c, node_id: int) -> list[int]:
        """Close every open flag this node raised and move it to its resolved state. Returns the node ids cleared."""
        rows = c.execute("""UPDATE attention_items SET state = 'done' WHERE state = 'open' AND event_id IN
                            (SELECT id FROM events WHERE object_type = 'node' AND object_id = %s) RETURNING touches""", (node_id,)).fetchall()
        c.execute("UPDATE attention_items SET state = 'done' WHERE state = 'open' AND %s = ANY (touches) AND 'effect:superseded' = ANY (matched_by)", (node_id,))
        typ = c.execute("SELECT type FROM nodes WHERE id = %s", (node_id,)).fetchone()
        if typ and typ["type"] in self._RESOLVED_STATE:
            c.execute("UPDATE nodes SET state = %s WHERE id = %s", (self._RESOLVED_STATE[typ["type"]], node_id))
        return sorted({t for r in rows for t in r["touches"]})

    def resolve_node(self, node_id: str, by: str, reason: str) -> int:
        """A person marks a blocker, discovery or constraint as resolved."""
        n = self.node(node_id)
        with self.pool.connection() as c, c.transaction():
            cleared = self._resolve(c, int(node_id))
            titles = {str(x["id"]): x["title"] for x in c.execute("SELECT id, title FROM nodes WHERE id = ANY (%s::bigint[])", (cleared,)).fetchall()}
            still = {str(t) for r in c.execute("SELECT touches FROM attention_items WHERE state = 'open' AND touches && %s::bigint[]", (cleared,)).fetchall() for t in r["touches"]}
            payload = {"title": f"Resolved “{n['title']}”", "reason": reason, "node_id": str(node_id),
                       "effects": [{"node_id": k, "title": v, "change": "still flagged" if k in still else "cleared"} for k, v in titles.items()]}
            return c.execute("""INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload)
                                VALUES (%s, %s, 'node.resolved', 'resolution', %s, %s) RETURNING id""",
                             (self.project["id"], self.user(by), int(node_id), Jsonb(payload))).fetchone()["id"]

    def sweep(self) -> None:
        """Repair older data: anything already superseded should not still be raising flags."""
        with self.pool.connection() as c, c.transaction():
            for r in c.execute("""SELECT DISTINCT unnest(touches) AS id FROM attention_items
                                  WHERE project_id = %s AND state = 'open' AND 'effect:superseded' = ANY (matched_by)""",
                               (self.project["id"],)).fetchall():
                self._resolve(c, r["id"])

    def empty(self) -> bool:
        return not self._q("SELECT 1 FROM nodes WHERE project_id = %s LIMIT 1", (self.project["id"],))

    # ---------------------------------------------------------------- write the graph
    def _insert_node(self, c, n: dict, vector, vector_model, created_by: str) -> int:
        state = n.get("state") or self._states[n["type"]][0]
        data = dict(n.get("data") or {})
        aliases = data.pop("aliases", [])
        node_id = c.execute("""
            INSERT INTO nodes (project_id, type, ref, title, status, state, owner_id, tags, data, importance, created_by)
            VALUES (%s, %s, %s, %s, 'confirmed', %s, %s, %s, %s, %s, %s) RETURNING id""",
            (self.project["id"], n["type"], n.get("ref"), n["title"], state, self.user(n["owner"]) if n.get("owner") else None,
             n.get("tags", []), Jsonb(data), n.get("importance"), created_by)).fetchone()["id"]
        version_id = c.execute("""
            INSERT INTO node_versions (node_id, version_no, content_text, summary, metadata, created_by, valid_at)
            VALUES (%s, 1, %s, %s, %s, %s, now()) RETURNING id""",
            (node_id, n.get("text") or n.get("summary", ""), n.get("summary", ""), Jsonb(n.get("metadata") or {}), created_by)).fetchone()["id"]
        card = f"{n['title']}. {n.get('summary', '')} Tags: {', '.join(n.get('tags', []))}"
        c.execute("""INSERT INTO chunks (node_version_id, idx, modality, role, text, embedding, embedding_model, embedded_at)
                     VALUES (%s, 0, 'text', 'card', %s, %s::vector, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE now() END)""",
                  (version_id, card, _vec(vector), vector_model if vector else None, _vec(vector)))
        for a in aliases:
            c.execute("INSERT INTO entity_aliases VALUES (%s, %s) ON CONFLICT DO NOTHING", (node_id, a.lower()))
        return node_id

    def _insert_edge(self, c, src, dst, type_, reason, confidence, origin, created_by) -> None:
        c.execute("""INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, 'accepted', %s) ON CONFLICT DO NOTHING""",
                  (self.project["id"], int(src), int(dst), type_, _EDGE_ORIGIN.get(origin, "user"),
                   max(0.0, min(1.0, float(confidence))), reason, created_by))

    def put_node(self, n: dict, vector=None, vector_model=None, created_by: str = "system") -> str:
        with self.pool.connection() as c, c.transaction():
            return str(self._insert_node(c, n, vector, vector_model, self.user(created_by)))

    def put_edge(self, src: str, dst: str, type_: str, reason: str = "", confidence: float = 1.0, origin: str = "seed") -> None:
        with self.pool.connection() as c:
            self._insert_edge(c, src, dst, type_, reason, confidence, origin, self.user("system"))

    def approve_placement(self, item: dict, node: dict, links: list[dict], fx: dict, by: str, reason: str, edited: bool) -> tuple[str, int]:
        """One transaction: node + version + card vector, edges, approval, event, attention flags."""
        uid, author = self.user(by), self.user(item.get("author"))
        prop = item["proposal"]
        with self.pool.connection() as c, c.transaction():
            node_id = self._insert_node(c, node, prop.get("vector"), prop.get("vector_model"), author)
            for l in links:
                self._insert_edge(c, node_id, l["target"], l["type"], l["reason"], l["confidence"], l["origin"],
                                  self.user("jev") if l["origin"] == "jev" else uid)
            approval_id = c.execute("""INSERT INTO approvals (project_id, subject_type, subject_id, verdict, reason, by_user, via)
                                       VALUES (%s, 'candidate', %s, %s, %s, %s, 'app') RETURNING id""",
                                    (self.project["id"], str(node_id), "edited" if edited else "approved", reason or None, uid)).fetchone()["id"]
            payload = {"title": f"Added “{node['title']}” as {node['type']}", "reason": reason, "node_id": str(node_id),
                       "item_id": item["id"], "approval_id": approval_id, "source": node["data"].get("source"),
                       "added_by": item.get("author"), "proposed_by": prop.get("by"), "edited_by_user": edited,
                       "links": [{"target": l["target"], "type": l["type"], "reason": l["reason"]} for l in links],
                       "effects": [{"node_id": e["node_id"], "title": e["title"], "change": e["change"], "why": e["why"]} for e in fx["effects"]],
                       "notify": fx["notify"]}
            event_id = c.execute("""INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload)
                                    VALUES (%s, %s, 'candidate.confirmed', 'node', %s, %s) RETURNING id""",
                                 (self.project["id"], uid, node_id, Jsonb(payload))).fetchone()["id"]
            for e in fx["effects"]:
                if e["new_status"] == "superseded":          # the new item resolves this one: clear what it flagged
                    self._resolve(c, int(e["node_id"]))
                    continue
                if not e["new_status"]:
                    continue
                c.execute("""INSERT INTO attention_items (project_id, event_id, type, touches, matched_by, reason, suggested_action, levels)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                          (self.project["id"], event_id, _ATTENTION_TYPE.get(e["new_status"], "fyi"), [int(e["node_id"])],
                           [f"effect:{e['new_status']}", "chain:" + ">".join(e["chain"])], e["why"], e["change"],
                           Jsonb({"pilot": "red", "pm": "red"} if e["new_status"] in ("blocked", "at_risk") else {"pilot": "amber", "pm": "amber"})))
            c.execute("UPDATE intake_items SET status = 'approved', node_id = %s, updated_at = now() WHERE id = %s", (node_id, item["id"]))
        return str(node_id), event_id

    def dismiss(self, item: dict, by: str, reason: str) -> int:
        uid = self.user(by)
        title = (item.get("proposal") or {}).get("title") or item["label"]
        with self.pool.connection() as c, c.transaction():
            approval_id = c.execute("""INSERT INTO approvals (project_id, subject_type, subject_id, verdict, reason, by_user, via)
                                       VALUES (%s, 'candidate', %s, 'dismissed', %s, %s, 'app') RETURNING id""",
                                    (self.project["id"], item["id"], reason or None, uid)).fetchone()["id"]
            event_id = c.execute("""INSERT INTO events (project_id, actor_id, verb, object_type, payload)
                                    VALUES (%s, %s, 'candidate.dismissed', 'intake_item', %s) RETURNING id""",
                                 (self.project["id"], uid, Jsonb({"title": f"Dismissed “{title}”", "reason": reason,
                                                                  "item_id": item["id"], "approval_id": approval_id}))).fetchone()["id"]
            c.execute("UPDATE intake_items SET status = 'dismissed', updated_at = now() WHERE id = %s", (item["id"],))
        return event_id

    # ---------------------------------------------------------------- live data feeds (livefeeds.py)
    def node_by_ref(self, ref: str) -> dict | None:
        return next((n for n in self.nodes() if n.get("ref") == ref), None)

    def set_state(self, node_id: str, state: str) -> None:
        self._q("UPDATE nodes SET state = %s WHERE id = %s AND state <> %s", (state, int(node_id), state))

    def register_source(self, node_id: str, connector: str, config: dict, cron: str) -> None:
        self._q("""INSERT INTO sources (node_id, connector, config, refresh_policy, cron) VALUES (%s, %s, %s, 'periodic', %s)
                   ON CONFLICT (node_id) DO UPDATE SET connector = EXCLUDED.connector, config = EXCLUDED.config, cron = EXCLUDED.cron""",
                (int(node_id), connector, Jsonb(config), cron))

    def feed_event(self, feed_id: str, verb: str, payload: dict, fx: dict | None, dedupe_key: str) -> int:
        """A monitor reported a change: reading + event, and (for bad news) attention flags on what it puts at risk.
        Any earlier open flags for the same real-world thing (dedupe_key) are closed first, so updates replace."""
        uid = self.user("monitors")
        with self.pool.connection() as c, c.transaction():
            c.execute("UPDATE sources SET last_captured_at = now() WHERE node_id = %s", (int(feed_id),))
            if c.execute("SELECT 1 FROM sources WHERE node_id = %s", (int(feed_id),)).fetchone():
                c.execute("INSERT INTO readings (source_node_id, ts, payload) VALUES (%s, clock_timestamp(), %s)",
                          (int(feed_id), Jsonb(payload)))
            c.execute("""UPDATE attention_items SET state = 'done' WHERE project_id = %s AND state = 'open'
                         AND %s = ANY(matched_by)""", (self.project["id"], f"feed:{dedupe_key}"))
            event_id = c.execute("""INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload)
                                    VALUES (%s, %s, %s, 'node', %s, %s) RETURNING id""",
                                 (self.project["id"], uid, verb, int(feed_id), Jsonb(payload))).fetchone()["id"]
            for e in (fx or {}).get("effects", []):
                if not e["new_status"]:
                    continue
                c.execute("""INSERT INTO attention_items (project_id, event_id, type, touches, matched_by, reason, suggested_action, levels, scores)
                             VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                          (self.project["id"], event_id, _ATTENTION_TYPE.get(e["new_status"], "discovery"), [int(e["node_id"])],
                           [f"effect:{e['new_status']}", f"feed:{dedupe_key}", "chain:" + ">".join(e["chain"])],
                           e["why"], e["change"],
                           Jsonb({"pilot": "red", "pm": "red", "client": "status_line"} if e["new_status"] in ("blocked", "at_risk")
                                 else {"pilot": "amber", "pm": "amber"}),
                           Jsonb({"confidence": payload.get("confidence", 0.9)})))
            open_flags = c.execute("""SELECT count(*) AS n FROM attention_items WHERE project_id = %s AND state = 'open'
                                      AND %s = ANY(touches) AND EXISTS (SELECT 1 FROM unnest(matched_by) m WHERE m LIKE 'feed:%%')""",
                                   (self.project["id"], int(feed_id))).fetchone()["n"]
            c.execute("UPDATE nodes SET state = %s WHERE id = %s",
                      ("changed" if open_flags else "healthy", int(feed_id)))
        return event_id

    # ---------------------------------------------------------------- rules (analysis.py, user-triggered)
    def rules(self, statuses: tuple[str, ...] = ("proposed", "active", "retired")) -> list[dict]:
        rows = self._q("""SELECT id, pack, applies_to, when_expr, then_actions, why, status, stats,
                                 extract(epoch FROM created_at)::float AS created_at FROM rules
                          WHERE status = ANY(%s) ORDER BY created_at DESC""", (list(statuses),))
        out = []
        for r in rows:
            meta = r["stats"] or {}
            out.append({"id": r["id"], "pack": r["pack"], "status": r["status"], "name": meta.get("name", r["id"]),
                        "why": r["why"], "describe": r["when_expr"], "when": r["applies_to"],
                        "then": (r["then_actions"] or [{}])[0], "meta": meta, "created_at": r["created_at"]})
        return out

    def put_rule(self, rule: dict, pack: str, describe: str, meta: dict) -> None:
        self._q("""INSERT INTO rules (id, pack, applies_to, when_expr, then_actions, why, written_by, status, stats)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, 'proposed', %s)""",
                (rule["id"], pack, Jsonb(rule["when"]), describe, Jsonb([rule["then"]]), rule["why"],
                 self.user("analysis"), Jsonb({"fired": 0, "acted_on": 0, "dismissed": 0, "name": rule["name"], **meta})))

    def set_rule_status(self, rule_id: str, status: str, by: str, reason: str) -> int:
        """Approve (active), dismiss or retire (retired) a rule; records an approval and an event."""
        uid = self.user(by)
        verdict = "approved" if status == "active" else "dismissed"
        with self.pool.connection() as c, c.transaction():
            r = c.execute("SELECT id, status, stats, when_expr FROM rules WHERE id = %s", (rule_id,)).fetchone()
            if r is None:
                raise KeyError(rule_id)
            c.execute("UPDATE rules SET status = %s WHERE id = %s", (status, rule_id))
            approval_id = c.execute("""INSERT INTO approvals (project_id, subject_type, subject_id, verdict, reason, by_user, via)
                                       VALUES (%s, 'rule', %s, %s, %s, %s, 'app') RETURNING id""",
                                    (self.project["id"], rule_id, verdict, reason or None, uid)).fetchone()["id"]
            name = (r["stats"] or {}).get("name", rule_id)
            verb = {"active": "rule.approved", "retired": "rule.retired" if r["status"] == "active" else "rule.dismissed"}[status]
            title = {"rule.approved": f"Approved rule “{name}”", "rule.retired": f"Retired rule “{name}”",
                     "rule.dismissed": f"Dismissed suggested rule “{name}”"}[verb]
            return c.execute("""INSERT INTO events (project_id, actor_id, verb, object_type, payload)
                                VALUES (%s, %s, %s, 'rule', %s) RETURNING id""",
                             (self.project["id"], uid, verb, Jsonb({"title": title, "reason": reason, "rule_id": rule_id,
                                                                    "rule": r["when_expr"], "approval_id": approval_id}))).fetchone()["id"]

    def start_run(self, by: str, model: str, params: dict) -> int:
        return self._q("""INSERT INTO runs (project_id, kind, name, actor_id, model, params)
                          VALUES (%s, 'analysis_loop', 'suggest_rules', %s, %s, %s) RETURNING id""",
                       (self.project["id"], self.user(by), model, Jsonb(params)))[0]["id"]

    def finish_run(self, run_id: int, ok: bool, error: str | None, usage: dict) -> None:
        self._q("""UPDATE runs SET status = %s, error = %s, tokens_in = %s, tokens_out = %s, cost_usd = %s, finished_at = now()
                   WHERE id = %s""",
                (("succeeded" if ok else "failed"), error, usage.get("prompt_tokens"), usage.get("completion_tokens"),
                 usage.get("cost"), run_id))

    # ---------------------------------------------------------------- intake items
    _ITEM = """SELECT id, status, label, author, source, proposal, timings, error, node_id::text AS node_id,
                      extract(epoch FROM created_at)::float AS created_at FROM intake_items"""

    def items(self) -> list[dict]:
        return self._q(self._ITEM + " WHERE project_id = %s ORDER BY created_at DESC", (self.project["id"],))

    def item(self, item_id: str) -> dict | None:
        rows = self._q(self._ITEM + " WHERE id = %s", (item_id,))
        return rows[0] if rows else None

    def put_item(self, it: dict) -> None:
        self._q("""INSERT INTO intake_items (id, project_id, status, label, author, source, proposal, timings, error)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, proposal = EXCLUDED.proposal,
                       timings = EXCLUDED.timings, error = EXCLUDED.error, updated_at = now()""",
                (it["id"], self.project["id"], it["status"], it["label"], it.get("author"), Jsonb(it.get("source") or {}),
                 Jsonb(it["proposal"]) if it.get("proposal") else None, Jsonb(it["timings"]) if it.get("timings") else None, it.get("error")))

    def delete_item(self, item_id: str) -> None:
        self._q("DELETE FROM intake_items WHERE id = %s AND node_id IS NULL", (item_id,))

    # ---------------------------------------------------------------- history
    def log(self, actor: str, verb: str, title: str, reason: str = "", payload: dict | None = None) -> int:
        return self._q("""INSERT INTO events (project_id, actor_id, verb, object_type, payload)
                          VALUES (%s, %s, %s, 'project', %s) RETURNING id""",
                       (self.project["id"], self.user(actor), verb, Jsonb({"title": title, "reason": reason, **(payload or {})})))[0]["id"]

    def events(self, limit: int = 200) -> list[dict]:
        rows = self._q("""SELECT e.id AS seq, extract(epoch FROM e.at)::float AS at, u.name AS actor, e.verb AS kind, e.payload
                          FROM events e JOIN users u ON u.id = e.actor_id WHERE e.project_id = %s ORDER BY e.id DESC LIMIT %s""",
                       (self.project["id"], limit))
        for r in rows:
            r["title"], r["reason"] = r["payload"].get("title", r["kind"]), r["payload"].get("reason", "")
        return rows

    def reset(self) -> None:
        """Demo helper. TRUNCATE (not DELETE) because events and versions are append-only by trigger."""
        self._q("TRUNCATE nodes, events, intake_items, approvals RESTART IDENTITY CASCADE")
