"""Linked folders: point the converter at ONE root folder and it converts everything inside.

    root = local / network path   (C:\\Projects\\Pier54, \\\\server\\share\\Pier54, /mnt/projects/pier54)
         | Google Drive folder link (https://drive.google.com/drive/folders/<id>)

    every file    -> one package (node), like a drop: local extraction, plus the AI reading if mode="agent"
    every folder  -> one "folder" package that `contains` its files and subfolders (they are `part_of` it),
                     so the folder tree itself is the first skeleton of the data tree. Containment only:
                     the converter still doesn't judge what relates to what.
    every package -> source.uri = where the original lives (path or Drive link), source.folder, source.modified_at

Re-running is safe: files whose content was already converted are skipped (same bytes = same package id).
watch=True keeps polling for new or changed files. forward_url (optional) posts every file to another intake,
e.g. Ryan's north-star app: http://<host>:<port>/api/intake.

Google Drive: with GOOGLE_API_KEY (or GDRIVE_API_KEY) in .env, folders shared "anyone with the link" are listed
through the Drive API (no size limit, Google Docs/Sheets/Slides exported to docx/xlsx/pdf). Without a key, public
folders are read with gdown (max 50 files per folder). Private folders need a key / service account: not built.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable

from .core import SCHEMA_VERSION, now_iso, sha256_file
from .engine import _INDEX_LOCK, _update_index_unlocked, convert_file

SKIP_NAMES = {"thumbs.db", "desktop.ini", ".ds_store", "icon\r"}
SKIP_PREFIXES = ("~$", ".", "._")
DRIVE_FOLDER_RE = re.compile(r"drive\.google\.com/(?:drive/(?:u/\d+/)?folders/|open\?id=|embeddedfolderview\?id=)([A-Za-z0-9_-]{10,})")
DRIVE_API = "https://www.googleapis.com/drive/v3"
GOOGLE_EXPORT = {  # native Google files -> something the converter reads
    "application/vnd.google-apps.document": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "application/vnd.google-apps.spreadsheet": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
    "application/vnd.google-apps.drawing": ("image/png", ".png"),
}


def max_bytes() -> int:
    return int(float(os.environ.get("CONVERTER_LINK_MAX_MB", "500")) * 1_000_000)


# ---------------------------------------------------------------- entries
@dataclass
class Entry:
    rel: str                      # path inside the root, posix style, e.g. "02_Drawings/Facade/A-201.pdf"
    uri: str                      # where the original lives
    size: int | None
    modified: str | None
    key: str                      # changes when the file changes (for watch mode)
    fetch: Callable[[Path], Path]  # returns a local path to read (downloads into the given temp dir if needed)

    @property
    def name(self) -> str:
        return PurePosixPath(self.rel).name

    @property
    def folder(self) -> str:
        p = str(PurePosixPath(self.rel).parent)
        return "" if p == "." else p


def classify(source: str) -> str | None:
    """'local', 'gdrive' or None if this isn't something we can link."""
    s = source.strip().strip('"')
    if DRIVE_FOLDER_RE.search(s):
        return "gdrive"
    try:
        return "local" if s and Path(s).expanduser().is_dir() else None
    except OSError:
        return None


def _skip(name: str) -> bool:
    return name.lower() in SKIP_NAMES or name.startswith(SKIP_PREFIXES)


def list_local(root: Path) -> list[Entry]:
    out = []
    for p in sorted(root.rglob("*")):
        rel_parts = p.relative_to(root).parts
        if not p.is_file() or any(_skip(part) for part in rel_parts):
            continue
        st = p.stat()
        out.append(Entry(rel="/".join(rel_parts), uri=str(p), size=st.st_size,
                         modified=time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
                         key=f"{p}|{st.st_size}|{int(st.st_mtime)}", fetch=lambda _tmp, p=p: p))
    return out


def _drive_key() -> str | None:
    return os.environ.get("GOOGLE_API_KEY") or os.environ.get("GDRIVE_API_KEY")


def _http_json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "UEP-converter/0.1"}), timeout=60) as r:
        return json.loads(r.read())


def _download(url: str, dest: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "UEP-converter/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest


def list_drive(link: str) -> tuple[str, list[Entry]]:
    """Returns (root folder name, entries)."""
    folder_id = DRIVE_FOLDER_RE.search(link).group(1)
    key = _drive_key()
    if key:
        return _list_drive_api(folder_id, key)
    return _list_drive_gdown(link, folder_id)


def _list_drive_api(folder_id: str, key: str) -> tuple[str, list[Entry]]:
    common = f"key={key}&supportsAllDrives=true"
    try:
        root = _http_json(f"{DRIVE_API}/files/{folder_id}?fields=name&{common}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google Drive refused the folder (HTTP {e.code}). Is it shared 'anyone with the link'?") from None
    entries: list[Entry] = []

    def walk(fid: str, prefix: str):
        token = ""
        while True:
            q = urllib.parse.quote(f"'{fid}' in parents and trashed=false")
            data = _http_json(f"{DRIVE_API}/files?q={q}&pageSize=1000&includeItemsFromAllDrives=true&{common}"
                              f"&fields=nextPageToken,files(id,name,mimeType,size,modifiedTime,webViewLink)"
                              + (f"&pageToken={token}" if token else ""))
            for f in data.get("files", []):
                name, mime = f["name"], f["mimeType"]
                if _skip(name):
                    continue
                if mime == "application/vnd.google-apps.folder":
                    walk(f["id"], f"{prefix}{name}/")
                    continue
                if mime.startswith("application/vnd.google-apps") and mime not in GOOGLE_EXPORT:
                    continue  # forms, sites, shortcuts…
                if mime in GOOGLE_EXPORT:
                    exp_mime, ext = GOOGLE_EXPORT[mime]
                    url = f"{DRIVE_API}/files/{f['id']}/export?mimeType={urllib.parse.quote(exp_mime)}&key={key}"
                    name = name if name.lower().endswith(ext) else name + ext
                else:
                    url = f"{DRIVE_API}/files/{f['id']}?alt=media&{common}"
                entries.append(Entry(rel=f"{prefix}{name}", uri=f.get("webViewLink") or f"https://drive.google.com/file/d/{f['id']}/view",
                                     size=int(f["size"]) if f.get("size") else None, modified=f.get("modifiedTime"),
                                     key=f"{f['id']}|{f.get('modifiedTime')}",
                                     fetch=lambda tmp, url=url, name=name: _download(url, tmp / Path(name).name)))
            token = data.get("nextPageToken")
            if not token:
                break

    walk(folder_id, "")
    return root.get("name") or folder_id, entries


def _list_drive_gdown(link: str, folder_id: str) -> tuple[str, list[Entry]]:
    try:
        import gdown
    except ImportError:
        raise RuntimeError("Reading Google Drive needs GOOGLE_API_KEY in .env or `pip install gdown`") from None
    url = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        items = gdown.download_folder(url=url, skip_download=True, quiet=True, use_cookies=False)
    except Exception as e:
        msg = str(e).splitlines()[0][:200]
        if "50" in msg or "maximum" in msg.lower():
            msg += ". Add GOOGLE_API_KEY to .env to read large Drive folders."
        raise RuntimeError(f"Could not read the Drive folder: {msg}. Is it shared 'anyone with the link'?") from None
    if not items:
        raise RuntimeError("The Drive folder is empty or not shared 'anyone with the link'.")
    parts0 = [PurePosixPath(str(i.path).replace("\\", "/")).parts for i in items]
    root_name = parts0[0][0] if parts0 and len(parts0[0]) > 1 and all(p and p[0] == parts0[0][0] for p in parts0) else folder_id
    entries = []
    for it, parts in zip(items, parts0):
        rel_parts = parts[1:] if parts and parts[0] == root_name else parts
        if not rel_parts or any(_skip(p) for p in rel_parts):
            continue
        rel = "/".join(rel_parts)

        def fetch(tmp: Path, fid=it.id, name=rel_parts[-1]) -> Path:
            dest = tmp / name
            gdown.download(id=fid, output=str(dest), quiet=True, use_cookies=False)
            if not dest.exists():
                raise RuntimeError(f"download failed for {name}")
            return dest
        entries.append(Entry(rel=rel, uri=f"https://drive.google.com/file/d/{it.id}/view", size=None, modified=None,
                             key=it.id, fetch=fetch))
    return root_name, entries


# ---------------------------------------------------------------- jobs
@dataclass
class Job:
    source: str
    kind: str
    mode: str = "agent"            # "agent" = local + AI reading, "local" = local extraction only
    watch: bool = False
    forward_url: str | None = None
    prompt: str = ""
    id: str = field(default_factory=lambda: "link_" + uuid.uuid4().hex[:8])
    root_name: str = ""
    status: str = "listing"        # listing | running | watching | done | stopped | error
    total: int = 0
    done: int = 0
    skipped: int = 0
    failed: int = 0
    cost: float = 0.0
    errors: list = field(default_factory=list)
    recent: list = field(default_factory=list)
    root_id: str | None = None
    started_at: str = field(default_factory=now_iso)
    finished_at: str | None = None
    seen: dict = field(default_factory=dict)          # entry key -> package id
    _stop: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_") and k != "seen"}


JOBS: dict[str, Job] = {}
_PID_LOCKS: dict[str, threading.Lock] = {}
_REG_LOCK = threading.Lock()


def _parent_dir(rel_dir: str) -> str:
    return "" if "/" not in rel_dir else str(PurePosixPath(rel_dir).parent)


def _all_dirs(entries: list[Entry]) -> set[str]:
    """Every folder in the tree, including the root ("") and folders that only hold subfolders."""
    dirs = {""}
    for e in entries:
        parts = PurePosixPath(e.rel).parts[:-1]
        dirs |= {"/".join(parts[:i]) for i in range(1, len(parts) + 1)}
    return dirs


def _folder_pid(job: Job, rel_dir: str) -> str:
    return "uep_" + hashlib.sha256(f"folder|{job.source}|{rel_dir}".encode()).hexdigest()[:12]


def _folder_uri(job: Job, rel_dir: str) -> str:
    if job.kind == "local":
        return str(Path(job.source) / rel_dir) if rel_dir else str(Path(job.source))
    return job.source  # Drive subfolder links aren't known without the API; point at the linked root


def start(out: Path, source: str, mode: str = "agent", watch: bool = False, forward_url: str | None = None,
          prompt: str = "", interval: int = 60) -> Job:
    source = source.strip().strip('"')
    kind = classify(source)
    if not kind:
        raise ValueError("Not a folder I can reach: give a local/network folder path or a Google Drive folder link")
    if kind == "local":
        source = str(Path(source).expanduser().resolve())
    job = Job(source=source, kind=kind, mode=mode if mode in ("agent", "local") else "agent", watch=watch,
              forward_url=forward_url or None, prompt=prompt or "")
    JOBS[job.id] = job
    threading.Thread(target=_run, args=(out, job, interval), daemon=True, name=job.id).start()
    return job


def stop(job_id: str) -> Job | None:
    job = JOBS.get(job_id)
    if job:
        job._stop.set()
    return job


def _run(out: Path, job: Job, interval: int) -> None:
    try:
        while True:
            _sync(out, job)
            if not job.watch or job._stop.is_set():
                break
            job.status = "watching"
            if job._stop.wait(interval):
                break
        job.status = "stopped" if job._stop.is_set() else "done"
    except Exception as e:
        job.status = "error"
        job.errors.append(f"{type(e).__name__}: {e}")
    job.finished_at = now_iso()
    _save_registry(out)


def _sync(out: Path, job: Job) -> None:
    job.status = "listing"
    if job.kind == "local":
        root = Path(job.source)
        job.root_name = root.name or str(root)
        entries = list_local(root)
    else:
        job.root_name, entries = list_drive(job.source)
    todo = [e for e in entries if e.key not in job.seen]
    job.total = len(job.seen) + len(todo)
    job.root_id = _folder_pid(job, "")
    dirs = _all_dirs(entries)
    for d in dirs:  # placeholder folder packages first, so files can point at them
        if not (out / _folder_pid(job, d) / "manifest.json").exists():
            _write_folder(out, job, d, entries)
    job.status = "running"
    workers = 2 if job.mode == "agent" else 4
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(lambda e: _one(out, job, e), todo))
    for d in sorted(dirs, key=lambda x: -x.count("/")):  # final folder packages with their children
        _write_folder(out, job, d, entries)
    _save_registry(out)


def _one(out: Path, job: Job, e: Entry) -> None:
    if job._stop.is_set():
        return
    parent = _folder_pid(job, e.folder)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        try:
            if e.size and e.size > max_bytes():
                raise RuntimeError(f"larger than {max_bytes() // 1_000_000} MB, skipped")
            path = e.fetch(Path(td))
            pid = "uep_" + sha256_file(path)[:12]
            lock = _PID_LOCKS.setdefault(pid, threading.Lock())
            with lock:
                existing = out / pid / "manifest.json"
                if existing.exists() and (job.mode == "local" or json.loads(existing.read_text(encoding="utf-8")).get("agent")):
                    _add_parent(out, pid, parent)  # same content already converted (maybe elsewhere): just link it here
                    job.seen[e.key] = pid
                    job.skipped += 1
                    return
                ctx = {"source_uri": e.uri, "folder": e.folder or None, "modified_at": e.modified, "channel": "linked folder",
                       "note": job.prompt or None}
                m = convert_file(path, out, original_name=e.name, context=ctx, _parent_id=parent)
                if job.mode == "agent":
                    from . import agent
                    try:
                        m = agent.understand(out, m["id"], job.prompt)
                        job.cost += ((m.get("agent") or {}).get("usage") or {}).get("cost") or 0
                    except Exception as ex:  # keep the local extraction; note the AI failure
                        job.errors.append(f"{e.rel}: AI reading failed: {str(ex)[:160]}")
                if job.forward_url:
                    try:
                        _forward(job.forward_url, path, e.name, job.prompt)
                    except Exception as ex:
                        job.errors.append(f"{e.rel}: forward failed: {str(ex)[:160]}")
            job.seen[e.key] = m["id"]
            job.done += 1
            job.recent = (job.recent + [{"id": m["id"], "rel": e.rel, "kind": m["kind"],
                                         "title": (m.get("agent") or {}).get("title") or m["title"]}])[-25:]
        except Exception as ex:
            job.failed += 1
            job.errors.append(f"{e.rel}: {type(ex).__name__}: {str(ex)[:200]}")


def _add_parent(out: Path, pid: str, parent: str) -> None:
    p = out / pid / "manifest.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    ids = m.setdefault("metadata", {}).setdefault("parent_ids", [])
    if parent in ids:
        return
    ids.append(parent)
    m["metadata"]["parent_id"] = ids[0]
    m["links"] = [l for l in m.get("links", []) if l["type"] != "part_of"] + [{"type": "part_of", "target": t} for t in ids]
    p.write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    with _INDEX_LOCK:
        _update_index_unlocked(out, m)


def _write_folder(out: Path, job: Job, rel_dir: str, entries: list[Entry]) -> None:
    """A 'folder' package: what's in it, and contains/part_of links. Pure structure, no judgement."""
    pid = _folder_pid(job, rel_dir)
    d = out / pid
    d.mkdir(parents=True, exist_ok=True)
    sub = sorted(x for x in _all_dirs(entries) if x and _parent_dir(x) == rel_dir)
    files = [e for e in entries if e.folder == rel_dir]
    file_ids = [job.seen[e.key] for e in files if e.key in job.seen]
    child_ids = [_folder_pid(job, s) for s in sub] + file_ids
    name = PurePosixPath(rel_dir).name if rel_dir else job.root_name
    parent = None if not rel_dir else _folder_pid(job, _parent_dir(rel_dir))
    kinds = Counter(Path(e.name).suffix.lower() or "(none)" for e in files)
    listing = [f"{PurePosixPath(s).name}/" for s in sub] + [e.name for e in files]
    desc = (f"Folder '{rel_dir or job.root_name}' in the linked source {job.source}: {len(files)} file(s), "
            f"{len(sub)} subfolder(s).")
    summary = f"{name}\n{desc}\nContents: " + ", ".join(listing[:200]) + (" …" if len(listing) > 200 else "")
    manifest = {
        "schema": SCHEMA_VERSION, "id": pid, "kind": "folder", "title": name, "description": desc,
        "source": {"filename": name, "extension": "", "mime": None, "size_bytes": sum(e.size or 0 for e in files),
                   "sha256": None, "aliases": [name], "ingested_at": now_iso(), "uri": _folder_uri(job, rel_dir),
                   "folder": _parent_dir(rel_dir) or None},
        "modalities": ["text"], "tags": {"values": ["kind:folder", "modality:text"], "suggested_by": "rules"},
        "context": {"channel": "linked folder", **({"note": job.prompt} if job.prompt else {})},
        "metadata": {"linked_root": job.source, "link_job": job.id, "path": rel_dir or "/", "files": len(files),
                     "subfolders": len(sub), "file_types": dict(kinds), "entities": {},
                     **({"parent_ids": [parent], "parent_id": parent} if parent else {})},
        "thumbnail": None, "chunk_count": 1, "children": child_ids,
        "links": ([{"type": "part_of", "target": parent}] if parent else []) + [{"type": "contains", "target": c} for c in child_ids],
        "warnings": [],
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    chunk = {"id": f"{pid}:0000", "package_id": pid, "index": 0, "modality": "text", "text": summary, "asset": None,
             "mime": None, "role": "summary", "locator": {"path": rel_dir or "/"}, "meta": {}}
    (d / "chunks.jsonl").write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    with _INDEX_LOCK:
        _update_index_unlocked(out, manifest)


def _forward(url: str, path: Path, name: str, note: str) -> None:
    """POST one file to another intake (multipart: files, text, author), e.g. Ryan's /api/intake."""
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in (("text", note or ""), ("author", "Linked folder")):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n".encode() + path.read_bytes() + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as r:
        r.read()


def _save_registry(out: Path) -> None:
    """Keep a record of linked roots next to the library (what was linked, when, results)."""
    with _REG_LOCK:
        p = out / "links.json"
        reg = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        for j in JOBS.values():
            reg[j.id] = {k: v for k, v in j.public().items() if k not in ("recent",)}
        p.write_text(json.dumps(reg, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
