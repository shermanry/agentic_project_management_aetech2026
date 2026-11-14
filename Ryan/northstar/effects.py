"""Dry run: what would change if a proposed node and its links were approved? Nothing is saved here.

Rules are plain code for the MVP (the plan is JSON rules written by the analysis loop). Each effect carries
the reason and the chain of nodes that led to it, so the UI can explain itself.

  blocker  -blocks/about-> T   : T becomes "blocked"; everything that depends on T (transitively) is "at risk"
  discovery -about/blocks-> T  : T needs review; decided decisions downstream are re-opened; events at risk
  constraint -about-> T        : T must be re-checked against the constraint
  decision  -supersedes-> T    : T is superseded
  anything  -evidence_for-> T  : adds evidence to T, no status change
"""
from __future__ import annotations

MAX_DEPTH = 3


def _dependents(target: str, edges: list[dict]) -> list[str]:
    """Nodes X where X depends_on target, or target blocks X."""
    out = [e["src"] for e in edges if e["type"] == "depends_on" and e["dst"] == target]
    out += [e["dst"] for e in edges if e["type"] == "blocks" and e["src"] == target]
    return out


def compute(node_type: str, title: str, links: list[dict], nodes: list[dict], edges: list[dict]) -> dict:
    by_id = {n["id"]: n for n in nodes}
    effects: list[dict] = []
    seen: dict[str, dict] = {}

    def add(node_id: str, change: str, new_status: str | None, why: str, chain: list[str]):
        n = by_id.get(node_id)
        if not n or node_id in seen:
            return
        e = {"node_id": node_id, "title": n["title"], "type": n["type"], "owner": n.get("owner"),
             "change": change, "new_status": new_status, "why": why, "chain": chain}
        seen[node_id] = e
        effects.append(e)

    def ripple(start: str, origin_title: str, verb: str):
        frontier, depth = [(start, [start])], 0
        while frontier and depth < MAX_DEPTH:
            nxt = []
            for nid, chain in frontier:
                for dep in _dependents(nid, edges):
                    d = by_id.get(dep)
                    if not d or dep in seen:
                        continue
                    via = by_id[nid]["title"]
                    if d["type"] == "decision" and d.get("status") in ("decided", "active"):
                        add(dep, "re-open", "reopened", f"It was decided assuming “{via}” was fine; {origin_title} {verb} that.", chain + [dep])
                    elif d["type"] == "event":
                        add(dep, "at risk", "at_risk", f"It depends on “{via}”.", chain + [dep])
                    elif d["type"] in ("deliverable", "blocker"):
                        add(dep, "needs update", "at_risk", f"It depends on “{via}”.", chain + [dep])
                    else:
                        add(dep, "check", None, f"It depends on “{via}”.", chain + [dep])
                    nxt.append((dep, chain + [dep]))
            frontier, depth = nxt, depth + 1

    for l in links:
        t = by_id.get(l.get("target"))
        if not t:
            continue
        lt = l.get("type")
        if node_type == "blocker" and lt in ("blocks", "about"):
            add(t["id"], "blocked", "blocked", f"“{title}” blocks it.", [t["id"]])
            ripple(t["id"], f"“{title}”", "changes")
        elif node_type == "discovery" and lt in ("blocks", "about"):
            add(t["id"], "needs review", "at_risk", f"“{title}” may invalidate it.", [t["id"]])
            ripple(t["id"], f"“{title}”", "may change")
        elif node_type == "constraint" and lt in ("about", "blocks"):
            add(t["id"], "re-check", "at_risk", f"Must be checked against “{title}”.", [t["id"]])
            ripple(t["id"], f"“{title}”", "constrains")
        elif lt == "supersedes":
            add(t["id"], "superseded", "superseded", f"Replaced by “{title}”.", [t["id"]])
        elif lt == "blocks":
            add(t["id"], "blocked", "blocked", f"“{title}” blocks it.", [t["id"]])
            ripple(t["id"], f"“{title}”", "changes")
        elif lt == "evidence_for":
            add(t["id"], "new evidence", None, f"“{title}” is added as evidence.", [t["id"]])

    notify = sorted({e["owner"] for e in effects if e.get("owner") and e["new_status"]})
    order = {"blocked": 0, "at risk": 1, "re-open": 2, "needs review": 3, "needs update": 4, "re-check": 5}
    effects.sort(key=lambda e: order.get(e["change"], 9))
    worst = "red" if any(e["new_status"] in ("blocked", "at_risk") for e in effects) else ("amber" if effects else "none")
    return {"effects": effects, "notify": notify, "level": worst}
