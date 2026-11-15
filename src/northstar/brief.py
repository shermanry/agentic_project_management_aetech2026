"""Draft design brief (Markdown) written from the live project record. Plain templating, no model call,
so it is instant and says only what the record says. Mirrors the sections of the UI/UX design's brief."""
from __future__ import annotations

import re
import time

from store import Store

TYPE_LABEL = {"constraint": "Limits and rules", "blocker": "Blockers", "discovery": "Findings"}
OPEN_BLOCKER = ("open", "waiting")


def _status(n: dict) -> str:
    return str(n.get("status") or n.get("state") or "").replace("_", " ")


def build(store: Store, parts: list[dict]) -> dict:
    nodes, edges, flags, items = store.nodes(), store.edges(), store.flags(), store.items()
    by_id = {n["id"]: n for n in nodes}
    project = store.project
    of = lambda *types: [n for n in nodes if n["type"] in types]
    line = lambda n: f"- **{n['title']}** ({_status(n)}{', owner ' + n['owner'] if n.get('owner') else ''}): {n.get('summary') or 'No summary recorded.'}"

    def rels(n: dict, limit: int = 4) -> list[str]:
        out = []
        for e in edges:
            if e["src"] == n["id"] and e["dst"] in by_id:
                out.append(f"  - {e['type'].replace('_', ' ')} *{by_id[e['dst']]['title']}*" + (f": {e['reason']}" if e.get("reason") else "")
                           + (" (suggested by the agent, accepted)" if e.get("origin") == "agent" else ""))
        return out[:limit]

    part_ids = {p["id"] for p in parts}
    site = [n for n in of("entity") if n["id"] not in part_ids and not ({"equipment", "drone"} & set(n.get("tags") or []))]
    equipment = [n for n in of("entity") if {"equipment", "drone"} & set(n.get("tags") or [])]
    deliverables, decisions, events = of("deliverable"), of("decision"), of("event")
    waiting = [i for i in items if i["status"] == "ready"]

    out: list[str] = [f"# Design brief (draft): {project['name']}", "",
                      f"Project {project['id']} · generated {time.strftime('%Y-%m-%d')} from {len(nodes)} nodes and {len(edges)} links in the project record.", "",
                      "> **Draft written from the project record as it stands.** It repeats what the record says and does not check it. "
                      f"{len({f['node_id'] for f in flags})} item(s) are currently flagged; see section 7 before relying on anything here.", ""]

    out += ["## 1. Project objective"]
    out += [f"- **{n['title']}**: {n.get('summary') or ''}" for n in deliverables] or ["- No deliverable is recorded yet, so the objective is not stated in the record."]
    scope = [n for n in decisions if {"scope", "client", "notice"} & set(n.get("tags") or []) or re.search(r"notice to proceed|scope", n["title"], re.I)]
    out += [line(n) for n in scope] + [""]

    out += ["## 2. Client and source requirements"]
    docs = of("document")
    for n in docs:
        out += [line(n)] + rels(n)
    if not docs:
        out += ["- No source documents are in the record yet."]
    out += [""]

    out += ["## 3. Geometry and site information"]
    out += [line(n) for n in site] or ["- No site information recorded."]
    if parts:
        out += ["", "Building parts:"]
        for p in parts:
            linked = ", ".join(l["title"] for l in p["linked"][:5]) or "nothing linked yet"
            state = {"red": "at risk or blocked", "amber": "being looked at", "none": "nothing open"}[p["level"]]
            out += [f"- **{p['title']}** ({state}): {p.get('summary') or ''} Related: {linked}."]
    out += [""]

    out += ["## 4. Constraints by category"]
    any_c = False
    for t, label in TYPE_LABEL.items():
        group = [n for n in of(t) if not (t == "blocker" and n["status"] in ("done", "resolved"))]
        if not group:
            continue
        any_c = True
        out += [f"### {label}"]
        for n in group:
            out += [line(n)] + rels(n)
    if not any_c:
        out += ["- No constraints, blockers or findings are recorded."]
    out += [""]

    out += ["## 5. Preliminary technical approach"]
    out += [line(n) for n in events] + [line(n) for n in decisions if n not in scope] + [line(n) for n in equipment]
    if not (events or decisions or equipment):
        out += ["- No flights, decisions or equipment are recorded yet."]
    out += [""]

    out += ["## 6. Deliverables"]
    out += [line(n) for n in deliverables] or ["- None recorded."]
    out += [""]

    out += ["## 7. Outstanding verifications"]
    seen, todo = set(), []
    for f in flags:
        n = by_id.get(f["node_id"])
        if n and n["id"] not in seen:
            seen.add(n["id"])
            todo.append(f"- [ ] **{n['title']}** is {f['status'].replace('_', ' ')}{' (owner: ' + n['owner'] + ')' if n.get('owner') else ''}: {f['reason']}")
    for n in of("blocker"):
        if n["id"] not in seen and n["status"] in OPEN_BLOCKER:
            todo.append(f"- [ ] **{n['title']}** is still {_status(n)}{' (owner: ' + n['owner'] + ')' if n.get('owner') else ''}.")
    for i in waiting:
        todo.append(f"- [ ] Review proposed addition: {(i.get('proposal') or {}).get('title') or i['label']}")
    out += todo or ["- Nothing is flagged, blocked or waiting for review."]
    out += ["", "---", "*Draft generated by YBuild from the live project record. Not an operational document; verify before use.*"]

    md = "\n".join(l for i, l in enumerate(out) if not (l == "" and i and out[i - 1] == ""))
    slug = re.sub(r"[^a-z0-9]+", "-", project["name"].lower()).strip("-")
    return {"markdown": md, "filename": f"{slug}-design-brief-draft.md", "nodes": len(nodes), "links": len(edges),
            "flagged": len({f['node_id'] for f in flags}), "generated_at": time.time()}
