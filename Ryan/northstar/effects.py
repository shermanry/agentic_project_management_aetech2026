"""Dry run: what would change if a proposed node and its links were approved? Nothing is saved here.

Rules are plain code for the MVP (the plan is JSON rules written by the analysis loop). Each effect carries
the reason and the chain of nodes that led to it, so the UI can explain itself.

  blocker  -blocks/about-> T   : T becomes "blocked"; everything that depends on T (transitively) is "at risk"
  discovery -about/blocks-> T  : T needs review (a decision is re-opened); dependents are at risk or re-opened.
                                 'about' an entity, document or feed is context only: no status change
  constraint -about-> T        : T must be re-checked against the constraint
  anything  -supersedes-> T    : T is resolved; the flags T raised are cleared unless another open item still raises them
  anything  -evidence_for-> T  : adds evidence to T, no status change

On top of these, approved JSON rules (proposed by the user-triggered analysis loop, analysis.py) are applied
after the built-in ones. Rule shape (stored in the `rules` table, kept in ACTIVE_RULES):

  {"id": "rule_ab12", "name": "...", "why": "...",
   "when": {"new_type": "blocker" | "any", "link_types": ["about", "blocks"],
            "target_type": "entity" | "any", "target_tags_any": ["equipment"]},
   "then": {"flag": "target" | "dependents" | "neighbours",
            "only_types": ["deliverable"], "only_tags_any": ["permit"],
            "change": "needs update", "new_status": "at_risk" | "reopened" | "blocked" | null}}
"""
from __future__ import annotations

MAX_DEPTH = 3
ACTIVE_RULES: list[dict] = []          # approved rules; refreshed by the app from the store
RULE_STATUSES = ("at_risk", "reopened", "blocked", None)


def _tags(n: dict) -> set[str]:
    return {t.lower() for t in (n.get("tags") or [])}


def _matches(n: dict, types: list[str] | str | None, tags_any: list[str] | None) -> bool:
    if types and types != "any":
        if n["type"] not in ([types] if isinstance(types, str) else types):
            return False
    if tags_any and not (_tags(n) & {t.lower() for t in tags_any}):
        return False
    return True


def rule_hits(rule: dict, node_type: str, links: list[dict], nodes: list[dict], edges: list[dict]) -> list[tuple[dict, dict]]:
    """(matched link target, node to flag) pairs this rule produces for a proposed node and its links."""
    by_id = {n["id"]: n for n in nodes}
    w, t = rule.get("when", {}), rule.get("then", {})
    if w.get("new_type", "any") not in ("any", node_type):
        return []
    out = []
    for l in links:
        tgt = by_id.get(l.get("target"))
        if not tgt or (w.get("link_types") and l.get("type") not in w["link_types"]):
            continue
        if not _matches(tgt, w.get("target_type"), w.get("target_tags_any")):
            continue
        flag = t.get("flag", "target")
        if flag == "target":
            cands = [tgt["id"]]
        elif flag == "dependents":
            cands = _dependents(tgt["id"], edges)
        else:  # neighbours: anything linked to the target either way
            cands = [e["src"] for e in edges if e["dst"] == tgt["id"]] + [e["dst"] for e in edges if e["src"] == tgt["id"]]
        for cid in dict.fromkeys(cands):
            c = by_id.get(cid)
            if c and _matches(c, t.get("only_types"), t.get("only_tags_any")):
                out.append((tgt, c))
    return out


def describe(rule: dict) -> str:
    """Plain-language 'when ... then ...' for a rule (also stored as rules.when_expr)."""
    w, t = rule.get("when", {}), rule.get("then", {})
    a = lambda word: ("an " if word[:1] in "aeiou" else "a ") + word.replace("_", " ")
    new = "anything" if w.get("new_type", "any") == "any" else a(w["new_type"])
    tgt = "a node" if w.get("target_type", "any") == "any" else a(w["target_type"])
    if w.get("target_tags_any"):
        tgt += f" tagged {' or '.join(w['target_tags_any'])}"
    via = f" ({' / '.join(w['link_types'])})" if w.get("link_types") else ""
    who = {"target": "that node", "dependents": "whatever depends on it", "neighbours": "whatever is linked to it"}[t.get("flag", "target")]
    if t.get("only_types"):
        who += f", if it is {' or '.join(a(x) for x in t['only_types'])}"
    if t.get("only_tags_any"):
        who += f" tagged {' or '.join(t['only_tags_any'])}"
    return f"When {new} is linked to {tgt}{via}, mark {who} as “{t.get('change', 'check')}”."


def _dependents(target: str, edges: list[dict]) -> list[str]:
    """Nodes X where X depends_on target, or target blocks X."""
    out = [e["src"] for e in edges if e["type"] == "depends_on" and e["dst"] == target]
    out += [e["dst"] for e in edges if e["type"] == "blocks" and e["src"] == target]
    return out


def compute(node_type: str, title: str, links: list[dict], nodes: list[dict], edges: list[dict],
            caused: dict[str, list[str]] | None = None, rules: list[dict] | None = None) -> dict:
    """`caused` maps a source node id to the node ids it currently flags (open attention items)."""
    caused = caused or {}
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
            if lt == "about" and t["type"] in ("entity", "document", "data_feed"):
                add(t["id"], "new information", None, f"“{title}” is about it.", [t["id"]])   # context, not a risk
            elif t["type"] == "decision":
                add(t["id"], "re-open", "reopened", f"“{title}” may invalidate it.", [t["id"]])
                ripple(t["id"], f"“{title}”", "may change")
            else:
                add(t["id"], "needs review", "at_risk", f"“{title}” may invalidate it.", [t["id"]])
                ripple(t["id"], f"“{title}”", "may change")
        elif node_type == "constraint" and lt in ("about", "blocks"):
            add(t["id"], "re-check", "at_risk", f"Must be checked against “{title}”.", [t["id"]])
            ripple(t["id"], f"“{title}”", "constrains")
        elif lt == "supersedes":
            # Superseding a blocker, discovery or constraint resolves it: the flags it raised are cleared,
            # unless another open item is still flagging the same node.
            add(t["id"], "resolved", "superseded", f"“{title}” resolves or replaces it.", [t["id"]])
            for nid in caused.get(t["id"], []):
                others = [by_id[s]["title"] for s, touched in caused.items() if s != t["id"] and nid in touched and s in by_id]
                if others:
                    add(nid, "still flagged", None, f"Also flagged by “{others[0]}”.", [t["id"], nid])
                else:
                    add(nid, "cleared", None, f"It was only flagged because of “{t['title']}”.", [t["id"], nid])
                    seen[nid]["clears"] = True
        elif lt == "blocks":
            add(t["id"], "blocked", "blocked", f"“{title}” blocks it.", [t["id"]])
            ripple(t["id"], f"“{title}”", "changes")
        elif lt == "evidence_for":
            add(t["id"], "new evidence", None, f"“{title}” is added as evidence.", [t["id"]])

    # approved rules from the analysis loop, after the built-in ones
    for rule in (ACTIVE_RULES if rules is None else rules):
        then = rule.get("then", {})
        for tgt, c in rule_hits(rule, node_type, links, nodes, edges):
            if c["id"] in seen:
                continue
            add(c["id"], then.get("change", "check"), then.get("new_status"),
                f"Rule “{rule.get('name', rule['id'])}”: {rule.get('why', '')}", [tgt["id"], c["id"]])
            seen[c["id"]]["rule_id"] = rule["id"]

    notify = sorted({e["owner"] for e in effects if e.get("owner") and e["new_status"]})
    order = {"blocked": 0, "at risk": 1, "re-open": 2, "needs review": 3, "needs update": 4, "re-check": 5, "resolved": 6, "cleared": 7}
    effects.sort(key=lambda e: order.get(e["change"], 9))
    worst = ("red" if any(e["new_status"] in ("blocked", "at_risk") for e in effects)
             else "green" if any(e.get("clears") for e in effects) else ("amber" if effects else "none"))
    return {"effects": effects, "notify": notify, "level": worst}
