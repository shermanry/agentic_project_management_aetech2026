"""Link the nodes a project already has, in order of creation, with Jev at each step.

For projects whose files were all read at once and came out as loose nodes. Nodes are taken oldest first
(by source file name in natural order when the file dates were not kept, otherwise by when they were added).
For each one, Jev sees its text and the nodes that came BEFORE it, and proposes typed links with reasons.
Those links are added and recorded in the history. A node that already has outgoing links is left alone, so
running it twice changes nothing.

    POST /api/relink                       from the running app
    .venv/bin/python relink.py <project>   from a terminal, against that project's database
"""
from __future__ import annotations

import sys
import time
import traceback


def run(store, by: str = "Jev", notify=None, dry: bool = False, seen: dict | None = None) -> dict:
    import links as links_mod
    import ordered
    import pipeline
    emb = pipeline.embeddings
    nodes = store.nodes()
    items = {i["node_id"]: i for i in store.items() if i.get("node_id")}
    def key(n):
        it = items.get(n["id"]) or {}
        src = it.get("source") or {}
        return (0 if src.get("filename") else 1, ordered.natural(src.get("filename") or ""), n["created_at"])
    seq = sorted(nodes, key=key)
    has_out = {e["src"] for e in store.edges()}
    model = emb.model_id()
    out = {"nodes": len(seq), "looked_at": 0, "links": 0, "skipped": 0, "errors": 0, "added": [], "seconds": 0}
    t0 = time.time()
    for k, n in enumerate(seq):
        if k == 0:
            continue
        if n["id"] in has_out:
            out["skipped"] += 1
            continue
        if seen is not None and seen.get(n["id"]) == k:   # already compared with these same earlier nodes
            out["skipped"] += 1
            continue
        try:
            earlier = {x["id"] for x in seq[:k]}
            detail = store.node_detail(n["id"], limit=6) or {}
            text = "\n\n".join(p["text"] for p in (detail.get("passages") or {}).get("items", []))[:6000] or (detail.get("node") or {}).get("text") or ""
            card = f"{n['title']}. {n.get('summary', '')} Tags: {', '.join(n.get('tags') or [])}"
            sims = store.similar(emb.embed(card[:4000], kind="document")[0], model)
            low = (card + " " + text[:1500]).lower()
            cands = []
            for c in seq[:k]:
                names = [c["title"].lower()] + [a.lower() for a in (c.get("data") or {}).get("aliases", [])]
                cands.append({"id": c["id"], "type": c["type"], "title": c["title"], "summary": c.get("summary", ""), "status": c["status"],
                              "owner": c.get("owner"), "similarity": round(sims.get(c["id"], 0.0), 3),
                              "name_match": next((a for a in names if len(a) > 4 and a in low), None)})
            cands.sort(key=lambda c: (c["name_match"] is not None, c["similarity"]), reverse=True)
            material = {"kind": (n.get("data") or {}).get("source") and "document" or "note", "title": n["title"],
                        "description": n.get("summary", ""), "text": text, "image": None, "entities": {}, "warnings": []}
            prop, _info = pipeline._propose(material, "Already in the project. Say how it connects to the earlier items listed.",
                                            n.get("owner") or by, cands[:12])
            out["looked_at"] += 1
            if seen is not None:
                seen[n["id"]] = k
            for l in prop["links"]:
                if l["target"] not in earlier:
                    continue
                dst = next(x for x in seq if x["id"] == l["target"])
                if dry:
                    out["added"].append((n["title"], l["type"], dst["title"], l["reason"]))
                    out["links"] += 1
                    continue
                try:
                    fx = links_mod.edge_effects(n, dst, l["type"], store)
                    store.add_edge(n, dst, l["type"], l["reason"], l["confidence"], "jev", by, fx,
                                   {"suggested_by": "jev", "source": "linked in order of creation", "added_by": by})
                    out["links"] += 1
                    out["added"].append((n["title"], l["type"], dst["title"], l["reason"]))
                except ValueError:
                    pass                                   # that link already exists
            if notify and not dry:
                notify({"type": "graph", "relink": k})
        except Exception:
            out["errors"] += 1
            traceback.print_exc()
    out["seconds"] = round(time.time() - t0, 1)
    return out


if __name__ == "__main__":
    import os
    import projects
    if len(sys.argv) < 2:
        raise SystemExit("usage: relink.py <project id> [--dry]")
    for k_, v_ in projects.env(sys.argv[1]).items():      # that project's database and seed
        os.environ.setdefault(k_, v_)
    import seed
    from store import Store
    res = run(Store(os.environ["DATABASE_URL"], seed.PROJECT), dry="--dry" in sys.argv)
    for a, t, b, why in res["added"]:
        print(f"  {a[:44]:<44} {t:<13} {b[:40]:<40} | {why}")
    print({k_: v_ for k_, v_ in res.items() if k_ != "added"})
