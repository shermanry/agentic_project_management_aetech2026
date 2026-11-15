"""The analysis loop, run only when a person asks for it ("Suggest rules").

It reads the project graph and its decision history, asks an Opus-class model what the built-in rules
missed, and returns at most a few JSON rules. Each proposal is validated, dry-run against what already
happened in this project ("would have flagged X when Y was added"), and stored as `proposed`. Nothing
changes until a person approves a rule; approved rules join effects.py's checks from then on.

Never scheduled, never triggered by events: see agent-architecture.md, section 5.
Settings: ANALYSIS_MODEL (default anthropic/claude-opus-5.5 via OpenRouter).
"""
from __future__ import annotations

import json
import os
import uuid

import effects
import llm
from store import EDGE_TYPES, NODE_TYPES

PACK = "facade-survey-nyc"
MAX_RULES = 3
FLAGS = ("target", "dependents", "neighbours")


def model() -> str:
    return os.environ.get("ANALYSIS_MODEL", "anthropic/claude-opus-5.5")


def load_active(store) -> int:
    """Refresh the rules effects.py applies. Returns how many are active."""
    effects.ACTIVE_RULES = [{"id": r["id"], "name": r["name"], "why": r["why"], "when": r["when"], "then": r["then"]}
                            for r in store.rules(("active",))]
    return len(effects.ACTIVE_RULES)


# ---------------------------------------------------------------- context for the model
def _context(store) -> dict:
    nodes, edges = store.nodes(), store.edges()
    title = {n["id"]: n["title"] for n in nodes}
    events = list(reversed(store.events(limit=120)))   # oldest first reads like a story
    history = []
    for e in events:
        p = e["payload"] or {}
        row = {"id": e["seq"], "actor": e["actor"], "what": e["kind"], "title": e["title"]}
        if e.get("reason"):
            row["reason"] = e["reason"][:300]
        if p.get("effects"):
            row["changed"] = [f"{f['title']} -> {f['change']}" for f in p["effects"]][:8]
        if p.get("links"):
            row["linked_to"] = [f"{l['type']} {title.get(l['target'], l['target'])}" for l in p["links"]][:6]
        history.append(row)
    tags = sorted({t for n in nodes for t in (n.get("tags") or [])})
    return {
        "nodes": [{"id": n["id"], "type": n["type"], "title": n["title"], "tags": n.get("tags") or [],
                   "status": n["status"], "owner": n.get("owner"), "summary": (n.get("summary") or "")[:220]} for n in nodes],
        "edges": [f"{title.get(e['src'], e['src'])} -[{e['type']}]-> {title.get(e['dst'], e['dst'])}" for e in edges],
        "history": history,
        "tags_in_use": tags,
        "existing_rules": [{"name": r["name"], "status": r["status"], "rule": r["describe"]} for r in store.rules()],
    }


SYSTEM = f"""You are the analysis loop of a project-management system for drone survey projects (facade inspection in NYC).
The project is a graph of typed nodes and edges. When a new node is approved with links, plain-code rules decide what
else changes ("effects"). Your job: study the graph and its decision history, find where people learned something late,
had to chase something by hand, or where a change should have flagged another node but did not, and propose AT MOST
{MAX_RULES} new rules that would have caught it earlier. Fewer, sharper rules beat many weak ones. Propose none if
nothing is justified.

Built-in rules (already applied, do not duplicate):
{effects.__doc__.split('On top of these')[0].split('so the UI can explain itself.')[1].strip()}

A rule you propose is JSON with this exact shape:
{{"name": "short imperative name",
  "why": "one sentence a pilot or PM would agree with",
  "evidence": [history ids or node ids that show the need],
  "would_have_caught": "one sentence: what in this project's history it would have flagged, and how much earlier",
  "when": {{"new_type": one of {NODE_TYPES + ['any']},
           "link_types": subset of {EDGE_TYPES},
           "target_type": one of {NODE_TYPES + ['any']},
           "target_tags_any": [tags from tags_in_use, optional]}},
  "then": {{"flag": "target" | "dependents" | "neighbours",
           "only_types": [node types, optional], "only_tags_any": [tags, optional],
           "change": "2-3 word label, e.g. needs amendment",
           "new_status": "at_risk" | "reopened" | "blocked" | null}}}}

Meaning: when a newly approved node of type `new_type` is linked (via one of `link_types`) to a node matching
`target_type`/`target_tags_any`, mark `flag` (the target itself, the nodes that depend on it, or every node linked to it),
filtered by `only_types`/`only_tags_any`, with `change`. Use only node types, edge types and tags that exist.
Do not repeat an existing rule, including dismissed ones.

Return ONLY: {{"observations": ["2-4 short findings about this project"], "rules": [ ... ]}}"""


# ---------------------------------------------------------------- validation and dry run
def _clean(raw: dict, tags: set[str]) -> tuple[dict | None, str | None]:
    w, t = raw.get("when") or {}, raw.get("then") or {}
    if w.get("new_type", "any") not in NODE_TYPES + ["any"] or w.get("target_type", "any") not in NODE_TYPES + ["any"]:
        return None, "unknown node type"
    links = [l for l in (w.get("link_types") or []) if l in EDGE_TYPES]
    if w.get("link_types") and not links:
        return None, "unknown edge type"
    if t.get("flag", "target") not in FLAGS:
        return None, "bad flag"
    status = t.get("new_status")
    if status not in effects.RULE_STATUSES:
        return None, f"bad status {status!r}"
    only_types = [x for x in (t.get("only_types") or []) if x in NODE_TYPES]
    keep_tags = lambda xs: [x for x in (xs or []) if x.lower() in tags]
    rule = {"id": "rule_" + uuid.uuid4().hex[:6], "name": str(raw.get("name") or "Unnamed rule")[:80],
            "why": str(raw.get("why") or "")[:300],
            "when": {"new_type": w.get("new_type", "any"), "link_types": links,
                     "target_type": w.get("target_type", "any"), "target_tags_any": keep_tags(w.get("target_tags_any"))},
            "then": {"flag": t.get("flag", "target"), "only_types": only_types, "only_tags_any": keep_tags(t.get("only_tags_any")),
                     "change": str(t.get("change") or "check")[:40], "new_status": status}}
    return rule, None


def dry_run(rule: dict, store) -> list[dict]:
    """Replay every node already in the graph as if it were being added now: what would this rule have flagged
    that the built-in rules did not?"""
    nodes, edges = store.nodes(), store.edges()
    hits = []
    for n in nodes:
        links = [{"target": e["dst"], "type": e["type"]} for e in edges if e["src"] == n["id"]]
        if not links:
            continue
        others = [e for e in edges if e["src"] != n["id"]]
        builtin = {e["node_id"] for e in effects.compute(n["type"], n["title"], links, nodes, others, rules=[])["effects"]}
        for tgt, c in effects.rule_hits(rule, n["type"], links, nodes, others):
            if c["id"] != n["id"] and c["id"] not in builtin:
                hits.append({"when_added": n["title"], "via": tgt["title"], "would_flag": c["title"], "node_id": c["id"],
                             "change": rule["then"]["change"]})
    seen, out = set(), []
    for h in hits:
        k = (h["when_added"], h["would_flag"])
        if k not in seen:
            seen.add(k)
            out.append(h)
    return out[:12]


# ---------------------------------------------------------------- the run
def suggest(store, by: str) -> dict:
    """One analysis run, started by a person. Stores proposals; changes nothing else."""
    ctx = _context(store)
    run_id = store.start_run(by, model(), {"nodes": len(ctx["nodes"]), "events": len(ctx["history"])})
    try:
        data, info = llm.chat_json(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": "Project graph and history:\n" + json.dumps(ctx, ensure_ascii=False)}],
            model=model(), max_tokens=4000, timeout=240)
    except Exception as e:
        store.finish_run(run_id, False, str(e)[:500], {})
        raise
    tags = {t.lower() for t in ctx["tags_in_use"]}
    proposed, rejected = [], []
    for raw in (data.get("rules") or [])[:MAX_RULES]:
        rule, err = _clean(raw, tags)
        if err:
            rejected.append({"name": raw.get("name"), "reason": err})
            continue
        hits = dry_run(rule, store)
        meta = {"evidence": raw.get("evidence") or [], "would_have_caught": raw.get("would_have_caught", ""),
                "dry_run": hits, "run_id": run_id, "model": info.get("model"), "asked_by": by}
        store.put_rule(rule, PACK, effects.describe(rule), meta)
        proposed.append({**rule, "describe": effects.describe(rule), "meta": meta})
    usage = info.get("usage") or {}
    store.finish_run(run_id, True, None, usage)
    seq = store.log(by, "analysis.run", f"{by} asked the analysis loop for rule suggestions: {len(proposed)} proposed",
                    "; ".join(data.get("observations") or [])[:600],
                    {"run_id": run_id, "model": info.get("model"), "seconds": info.get("seconds"),
                     "rules": [r["id"] for r in proposed], "rejected": rejected})
    return {"run_id": run_id, "revision": seq, "observations": data.get("observations") or [], "rules": proposed,
            "rejected": rejected, "model": info.get("model"), "seconds": info.get("seconds"),
            "cost_usd": usage.get("cost")}
