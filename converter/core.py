"""Core data model for the Universal Embedding Package (UEP).

A package is one folder per source file:

    <package_id>/
        manifest.json   node-level metadata (what the graph team turns into a node)
        chunks.jsonl    one line per embeddable unit (text / image / audio / video)
        assets/         binary payloads referenced by chunks (png, wav, mp4 ...)

Every chunk carries a `text` field, even image/audio/video chunks (a caption or
context line), so a text-only embedder can still use the package while a
multimodal embedder can use the asset directly.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import mimetypes
import re
import shutil
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "uep/0.1"
TEXT_CHUNK_CHARS = 1500  # target size of a text chunk
TEXT_CHUNK_OVERLAP = 150


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def slug(s: str, n: int = 40) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")
    return s[:n] or "file"


@dataclass
class Chunk:
    modality: str                      # text | image | audio | video
    text: str | None = None            # content (text) or caption/context (media)
    asset: str | None = None           # relative path inside the package, e.g. assets/p001.png
    mime: str | None = None
    role: str = "body"                 # summary | context | header | body | table | snapshot | page | keyframe | segment | transcript
                                       # | attachment | markup | markup_region
    locator: dict[str, Any] = field(default_factory=dict)  # page / t_start / t_end / view / layer / sheet / slide
    meta: dict[str, Any] = field(default_factory=dict)


class Package:
    """Collects chunks + assets for one source file, then writes them to disk."""

    def __init__(self, source: Path, out_root: Path, original_name: str | None = None, context: dict | None = None):
        self.source = Path(source)
        self.out_root = Path(out_root)
        self.original_name = original_name or self.source.name
        # user-supplied context: note (the message that came with the file), author, author_role,
        # channel, date, intent ("markup" | "reference" | ...), refers_to (package id)
        self.context: dict[str, Any] = {k: v for k, v in (context or {}).items() if v not in (None, "")}
        self.sha256 = sha256_file(self.source)
        self.id = f"uep_{self.sha256[:12]}"
        self.dir = Path(out_root) / self.id
        self.assets_dir = self.dir / "assets"
        # Same bytes = same package id (dedup: an attachment that is also dropped on its own is one node).
        # Re-converting replaces the content but remembers every filename and parent it arrived through.
        self.aliases: list[str] = []
        self.parent_ids: list[str] = []
        prev = self.dir / "manifest.json"
        if prev.exists():
            try:
                old = json.loads(prev.read_text(encoding="utf-8"))
                self.aliases = old["source"].get("aliases", [old["source"]["filename"]])
                self.parent_ids = old["metadata"].get("parent_ids", [])
                # context given earlier (who sent it, the message) survives a plain re-conversion
                self.context = {**old.get("context", {}), **self.context}
            except Exception:
                pass
        if self.dir.exists():
            shutil.rmtree(self.dir)
        if self.original_name not in self.aliases:
            self.aliases.append(self.original_name)
        self.assets_dir.mkdir(parents=True)
        self.kind = "unknown"
        self.title = Path(self.original_name).stem
        self.description = ""
        self.metadata: dict[str, Any] = {}
        self.tags: set[str] = set()
        self.chunks: list[Chunk] = []
        self.children: list[str] = []
        self.links: list[dict] = []
        self.warnings: list[str] = []
        self._asset_names: set[str] = set()

    # ---------- building ----------
    def asset_path(self, name: str) -> tuple[Path, str]:
        """Reserve a unique asset filename; returns (absolute path, relative path)."""
        name = slug(name, 80)
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, "bin"
        candidate, i = f"{stem}.{ext}", 1
        while candidate in self._asset_names:
            i += 1
            candidate = f"{stem}_{i}.{ext}"
        self._asset_names.add(candidate)
        return self.assets_dir / candidate, f"assets/{candidate}"

    def add_asset_bytes(self, name: str, data: bytes) -> str:
        p, rel = self.asset_path(name)
        p.write_bytes(data)
        return rel

    def add(self, chunk: Chunk) -> Chunk:
        if chunk.asset and not chunk.mime:
            chunk.mime = mimetypes.guess_type(chunk.asset)[0]
        self.chunks.append(chunk)
        return chunk

    def add_text(self, text: str, role: str = "body", locator: dict | None = None, **meta) -> None:
        """Adds text, splitting long text into overlapping chunks on paragraph boundaries."""
        text = normalize_ws(text)
        if not text:
            return
        parts = split_text(text)
        for i, part in enumerate(parts):
            loc = dict(locator or {})
            if len(parts) > 1:
                loc["part"] = i + 1
                loc["parts"] = len(parts)
            self.add(Chunk("text", text=part, role=role, locator=loc, meta=dict(meta)))

    def add_image(self, rel_asset: str, caption: str, role: str = "snapshot", locator: dict | None = None, **meta) -> Chunk:
        from .markup import dhash_file
        meta = dict(meta)
        try:
            meta.setdefault("dhash", dhash_file(self.dir / rel_asset))  # lets other packages find "the same picture"
        except Exception:
            pass
        return self.add(Chunk("image", text=caption, asset=rel_asset, role=role, locator=locator or {}, meta=meta))

    # ---------- context ----------
    def who(self) -> str:
        c = self.context
        author, role = c.get("author"), c.get("author_role")
        if author and role:
            return f"{author} ({role})"
        return author or role or ""

    def context_line(self) -> str:
        """'From J. Smith (client) via Teams: "make the canopy lighter"' - appended to captions so
        every vector carries who asked for what, not just what the picture looks like."""
        c = self.context
        parts = []
        if self.who():
            parts.append(f"From {self.who()}")
        if c.get("channel"):
            parts.append(f"via {c['channel']}")
        if c.get("date"):
            parts.append(f"on {c['date']}")
        line = " ".join(parts)
        if c.get("note"):
            line = f'{line}: "{c["note"]}"' if line else f'Note: "{c["note"]}"'
        return line

    # ---------- output ----------
    @property
    def modalities(self) -> list[str]:
        order = ["text", "image", "audio", "video"]
        present = {c.modality for c in self.chunks}
        return [m for m in order if m in present]

    def manifest(self) -> dict[str, Any]:
        st = self.source.stat()
        thumb = next((c.asset for c in self.chunks if c.modality == "image"), None)
        return {
            "schema": SCHEMA_VERSION,
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "description": self.description,
            "source": {
                "filename": self.original_name,
                "extension": Path(self.original_name).suffix.lower(),
                "mime": mimetypes.guess_type(self.original_name)[0],
                "size_bytes": st.st_size,
                "sha256": self.sha256,
                "aliases": self.aliases,
                "ingested_at": now_iso(),
            },
            "modalities": self.modalities,
            "tags": {"values": sorted(self.tags), "suggested_by": "rules"},
            "context": self.context,
            "metadata": self.metadata,
            "thumbnail": thumb,
            "chunk_count": len(self.chunks),
            "children": self.children,
            "links": self.links,
            "warnings": self.warnings,
        }

    def write(self) -> dict[str, Any]:
        m = self.manifest()
        (self.dir / "manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        with open(self.dir / "chunks.jsonl", "w", encoding="utf-8") as f:
            for i, c in enumerate(self.chunks):
                row = {"id": f"{self.id}:{i:04d}", "package_id": self.id, "index": i, **asdict(c)}
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
        return m


# ---------- text helpers ----------
def normalize_ws(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_text(text: str, size: int = TEXT_CHUNK_CHARS, overlap: int = TEXT_CHUNK_OVERLAP) -> list[str]:
    if len(text) <= size:
        return [text]
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # break paragraphs that are themselves too long, on sentence boundaries
    pieces: list[str] = []
    for p in paras:
        if len(p) <= size:
            pieces.append(p)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", p)
        buf = ""
        for s in sentences:
            while len(s) > size:  # no sentence boundary at all: hard split
                pieces.append(s[:size]); s = s[size:]
            if len(buf) + len(s) + 1 > size and buf:
                pieces.append(buf); buf = s
            else:
                buf = f"{buf} {s}".strip()
        if buf:
            pieces.append(buf)
    chunks, buf = [], ""
    for p in pieces:
        if len(buf) + len(p) + 2 > size and buf:
            chunks.append(buf)
            tail = buf[-overlap:]
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            buf = f"{tail}\n\n{p}" if overlap else p
        else:
            buf = f"{buf}\n\n{p}" if buf else p
    if buf:
        chunks.append(buf)
    return chunks


def zip_package(pkg_dir: Path, zip_path: Path, include_children: bool = True) -> Path:
    """Zip a package folder, plus (recursively) the child packages it links to."""
    pkg_dir = Path(pkg_dir)
    root, todo, seen = pkg_dir.parent, [pkg_dir.name], set()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        while todo:
            pid = todo.pop()
            d = root / pid
            if pid in seen or not (d / "manifest.json").exists():
                continue
            seen.add(pid)
            for p in sorted(d.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(root))
            if include_children:
                todo += json.loads((d / "manifest.json").read_text(encoding="utf-8")).get("children", [])
    return zip_path
