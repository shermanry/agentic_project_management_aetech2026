"""Dispatch: picks a handler by file extension, runs it, writes the package and
updates the library index. Handlers can spawn child packages (email attachments,
files inside a zip) via `convert_child`."""
from __future__ import annotations

import json
import tempfile
import threading
import traceback
from pathlib import Path
from typing import Callable

from .core import Chunk, Package, now_iso
from .tagging import keyword_tags, needs_decision
from .entities import extract as extract_entities

Handler = Callable[[Package, "Context"], None]
_REGISTRY: dict[str, tuple[str, Handler]] = {}


def register(kind: str, *extensions: str):
    def deco(fn: Handler) -> Handler:
        for ext in extensions:
            _REGISTRY[ext.lower()] = (kind, fn)
        return fn
    return deco


def supported_extensions() -> dict[str, str]:
    _load_handlers()
    return {ext: kind for ext, (kind, _) in sorted(_REGISTRY.items())}


class Context:
    def __init__(self, out_root: Path, depth: int = 0, parent_id: str | None = None, context: dict | None = None):
        self.out_root = Path(out_root)
        self.depth = depth
        self.parent_id = parent_id
        self.context = context or {}

    def convert_child(self, data: bytes, filename: str, parent: Package) -> dict | None:
        """Convert an embedded file (attachment, zip member) into its own package."""
        if self.depth >= 3:
            parent.warnings.append(f"skipped nested file {filename}: max depth reached")
            return None
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            p = Path(td) / Path(filename).name
            p.write_bytes(data)
            # attachments inherit who sent them and the message they came with
            inherited = {k: v for k, v in parent.context.items() if k in ("author", "author_role", "channel", "date", "note")}
            m = convert_file(p, self.out_root, original_name=filename, context=inherited,
                             _depth=self.depth + 1, _parent_id=parent.id)
        parent.children.append(m["id"])
        return m


_loaded = False


def _load_handlers() -> None:
    global _loaded
    if not _loaded:
        from . import handlers  # noqa: F401  (registers via decorators)
        _loaded = True


def convert_file(path: str | Path, out_root: str | Path, original_name: str | None = None,
                 context: dict | None = None, _depth: int = 0, _parent_id: str | None = None) -> dict:
    """context (all optional): note, author, author_role, channel, date, intent, refers_to."""
    _load_handlers()
    path, out_root = Path(path), Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    name = original_name or path.name
    ext = Path(name).suffix.lower()
    pkg = Package(path, out_root, original_name=name, context=context)
    kind, handler = _REGISTRY.get(ext, ("unknown", None))
    pkg.kind = kind
    ctx = Context(out_root, _depth, _parent_id, pkg.context)
    if handler is None:
        from .handlers.fallback import convert_unknown
        handler = convert_unknown
    try:
        handler(pkg, ctx)
    except Exception as e:  # keep partial results; never lose the file
        pkg.warnings.append(f"{type(e).__name__}: {e}")
        pkg.metadata["error_trace"] = traceback.format_exc(limit=4)
    _finalize(pkg, _parent_id)
    manifest = pkg.write()
    _update_index(out_root, manifest)
    return manifest


def _finalize(pkg: Package, parent_id: str | None) -> None:
    # the message/note that came with the file is its own chunk: often it IS the meaning
    if pkg.context.get("note") and not any(c.role == "context" for c in pkg.chunks):
        pkg.chunks.insert(0, Chunk("text", text=pkg.context_line(), role="context", meta={"source": "user"}))
    if pkg.context.get("author_role"):
        pkg.tags.add(f"from:{pkg.context['author_role'].lower().replace(' ', '-')}")
    if pkg.context.get("channel"):
        pkg.tags.add(f"channel:{pkg.context['channel'].lower()}")
    if not pkg.description:
        pkg.description = excerpt(pkg)
    # summary chunk first: a compact, embeddable statement of what this node is
    if pkg.description and not any(c.role == "summary" for c in pkg.chunks):
        pkg.chunks.insert(0, Chunk("text", text=f"{pkg.title}\n{pkg.description}", role="summary"))
    all_text = "\n".join(c.text or "" for c in pkg.chunks)
    pkg.tags |= keyword_tags(all_text + " " + pkg.title)
    pkg.tags.add(f"kind:{pkg.kind}")
    for m in pkg.modalities:
        pkg.tags.add(f"modality:{m}")
    pkg.metadata.setdefault("needs_decision_hint", needs_decision(all_text))
    pkg.metadata["entities"] = extract_entities(all_text + " " + pkg.title)
    if parent_id and parent_id not in pkg.parent_ids:
        pkg.parent_ids.append(parent_id)
    if pkg.parent_ids:
        pkg.metadata["parent_ids"] = pkg.parent_ids
        pkg.metadata["parent_id"] = pkg.parent_ids[0]
    _links(pkg)


def _links(pkg: Package) -> None:
    """Explicit, typed edges the graph can use directly (embedding-proximity edges come later)."""
    links = [{"type": "part_of", "target": p} for p in pkg.parent_ids]
    links += [{"type": "contains", "target": c} for c in pkg.children]
    marks = pkg.metadata.get("markup")
    for m in (marks if isinstance(marks, list) else [marks] if marks else []):
        if m.get("marks_up"):
            links.append({"type": "marks_up", "target": m["marks_up"]["package_id"],
                          "target_chunk": m["marks_up"].get("chunk_id"), "confidence": _conf(m["marks_up"])})
    if pkg.context.get("refers_to") and not any(l["target"] == pkg.context["refers_to"] for l in links):
        links.append({"type": "refers_to", "target": pkg.context["refers_to"], "confidence": 1.0})
    pkg.links = links


def _conf(m: dict) -> float:
    d = m.get("distance")
    return 1.0 if d is None else round(max(0.5, 1 - d / 32), 2)


def excerpt(pkg: Package, n: int = 300) -> str:
    """First meaningful body text (skipping chunks that only repeat the title)."""
    for c in pkg.chunks:
        if c.modality == "text" and c.text and c.role not in ("header", "summary"):
            t = c.text.strip()
            if t.lower().startswith(pkg.title.lower()):
                t = t[len(pkg.title):].strip()
            t = " ".join(t.split())
            if len(t) > 20:
                return t[:n] + ("…" if len(t) > n else "")
    return ""


_INDEX_LOCK = threading.Lock()


def _update_index(out_root: Path, manifest: dict) -> None:
    with _INDEX_LOCK:
        _update_index_unlocked(out_root, manifest)


def _update_index_unlocked(out_root: Path, manifest: dict) -> None:
    """library index: one line per package (latest wins on re-conversion)."""
    idx = out_root / "index.jsonl"
    rows = {}
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                rows[r["id"]] = r
    rows[manifest["id"]] = {
        "id": manifest["id"], "kind": manifest["kind"], "title": manifest["title"],
        "filename": manifest["source"]["filename"], "modalities": manifest["modalities"],
        "chunk_count": manifest["chunk_count"], "parent_id": manifest["metadata"].get("parent_id"),
        "author": manifest.get("context", {}).get("author"), "author_role": manifest.get("context", {}).get("author_role"),
        "children": manifest["children"], "links": manifest.get("links", []), "updated_at": now_iso(), "path": manifest["id"] + "/manifest.json",
    }
    idx.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows.values()), encoding="utf-8")
