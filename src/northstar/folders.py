"""Add a whole folder at once: every file inside becomes its own intake item, read and proposed like a single drop.

Built on Minh's linked folders (src/converter/sources.py): the same listing of a local/network folder or a Google
Drive folder link, the same skip rules (system, lock, backup and temp files) and the same size limit. Here the files
go into this app's intake instead of the converter's own library, so a person still approves where each one goes.

Google Drive: the folder must be shared "anyone with the link". With GOOGLE_API_KEY (or GDRIVE_API_KEY) in .env there
is no size limit; without it gdown reads up to 50 files per folder.
Settings: FOLDER_MAX_FILES (default 40 files per folder; each file costs one Jev call).
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pipeline  # noqa: F401  (puts Minh's converter on the import path)

try:
    from converter import sources
except Exception:   # the converter's dependencies are not installed
    sources = None


def max_files() -> int:
    return int(os.environ.get("FOLDER_MAX_FILES", "40"))


@dataclass
class Job:
    source: str
    kind: str                      # local | gdrive
    author: str
    note: str = ""
    id: str = field(default_factory=lambda: "fold_" + uuid.uuid4().hex[:8])
    root_name: str = ""
    status: str = "listing"        # listing | running | done | stopped | error
    total: int = 0                 # files that will be added
    found: int = 0                 # files in the folder
    done: int = 0
    failed: int = 0
    already: int = 0               # added earlier from this folder, not added again
    over_limit: int = 0            # left out because of FOLDER_MAX_FILES
    items: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


JOBS: dict[str, Job] = {}
_SEEN: set[str] = set()           # files already added since this server started (same file, unchanged)


def available() -> bool:
    return sources is not None


def start(source: str, author: str, note: str, add_file: Callable[[Path, str, str, str, dict], str]) -> Job:
    """add_file(path, filename, note, author, extra_source) -> item id: copies the file and starts reading it."""
    if sources is None:
        raise RuntimeError("The converter is not installed here (see src/converter/requirements.txt)")
    source = source.strip().strip('"')
    kind = sources.classify(source)
    if not kind:
        raise ValueError("Not a folder I can reach. Give a Google Drive folder link, or the path of a folder on this machine.")
    if kind == "local":
        source = str(Path(source).expanduser().resolve())
    job = Job(source=source, kind=kind, author=author, note=note.strip())
    JOBS[job.id] = job
    threading.Thread(target=_run, args=(job, add_file), daemon=True, name=job.id).start()
    return job


def stop(job_id: str) -> Job | None:
    job = JOBS.get(job_id)
    if job:
        job._stop.set()
    return job


def _run(job: Job, add_file: Callable) -> None:
    try:
        if job.kind == "local":
            root = Path(job.source)
            job.root_name, entries = root.name or str(root), sources.list_local(root)
        else:
            job.root_name, entries = sources.list_drive(job.source)
        job.found = len(entries)
        fresh = [e for e in entries if f"{job.source}|{e.key}" not in _SEEN]
        job.already = len(entries) - len(fresh)
        todo = fresh[:max_files()]
        job.over_limit = len(fresh) - len(todo)
        job.total = len(todo)
        job.status = "running"
        for e in todo:
            if job._stop.is_set():
                break
            _one(job, e, add_file)
        job.status = "stopped" if job._stop.is_set() else "done"
    except Exception as ex:
        job.status = "error"
        if job.kind == "gdrive":   # the usual cause; the library's own message is long
            job.errors.append('Google Drive would not list that folder. Share it as "Anyone with the link" and try again.'
                              + ("" if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GDRIVE_API_KEY")
                                 else " Folders with more than 50 files also need GOOGLE_API_KEY in .env."))
        else:
            job.errors.append(str(ex)[:300])


def _one(job: Job, e, add_file: Callable) -> None:
    where = "/".join(x for x in (job.root_name, e.folder) if x)
    note = f'From the folder "{where}"' + (" on Google Drive." if job.kind == "gdrive" else ".")
    if job.note:
        note += " " + job.note
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        try:
            if e.size and e.size > sources.max_bytes():
                raise RuntimeError(f"larger than {sources.max_bytes() // 1_000_000} MB, left out")
            path = e.fetch(Path(td))
            item_id = add_file(Path(path), e.name, note, job.author, {"uri": e.uri, "folder": where, "via": job.kind, "modified_at": e.modified})
            _SEEN.add(f"{job.source}|{e.key}")
            job.items.append(item_id)
            job.done += 1
        except Exception as ex:
            job.failed += 1
            job.errors.append(f"{e.rel}: {str(ex)[:200]}")
