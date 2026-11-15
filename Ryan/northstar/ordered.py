"""Files that arrive together are added one at a time, oldest first, with Jev at each step.

Why: a proposal can only link to what is already in the graph. When a folder of files was read all at once
against an empty project, every file found nothing to link to and the graph came out as loose nodes.

How: every incoming file goes into one lane. The lane gathers files that arrive close together (a multi-file
drop, a dropped folder, a linked folder). A file on its own is handled as before: it is read and waits for
review. Two or more are a batch: they are sorted by the file's own date, then by name (A01, A02, … A10),
and for each one in turn it is read, Jev proposes its type and links against the graph as it stands at that
moment, and it is added before the next one is read. So file 7 can link to files 1 to 6.

Each automatic addition is recorded in the history like any other, with its position in the batch as the reason.
Set INTAKE_ORDERED=0 to go back to reading everything in parallel and reviewing each proposal.
"""
from __future__ import annotations

import os
import queue
import re
import threading
import time
import traceback
from datetime import datetime

SETTLE_S = float(os.environ.get("INTAKE_SETTLE_S", "2.5"))        # quiet time that ends a batch
SETTLE_FOLDER_S = float(os.environ.get("INTAKE_SETTLE_FOLDER_S", "12"))   # linked folders fetch file by file
MAX_GATHER_S = 90.0


def enabled() -> bool:
    return os.environ.get("INTAKE_ORDERED", "1").lower() not in ("0", "false", "no")


def natural(name: str) -> list:
    """Sort key that puts A2 before A10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name or "")]


def to_ts(value) -> float | None:
    """A file date from the browser (milliseconds), a folder listing (ISO text) or already in seconds."""
    if value in (None, "", 0, "0"):
        return None
    try:
        v = float(value)
        return v / 1000 if v > 1e11 else v
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def in_order(items: list[dict]) -> list[dict]:
    """Oldest first by the file's own date (to the second), then by name. If any date is missing, by name only."""
    dated = all((i.get("source") or {}).get("created_ts") for i in items)
    name = lambda i: natural((i.get("source") or {}).get("filename") or i.get("label") or "")
    return sorted(items, key=lambda i: ((int(i["source"]["created_ts"]) if dated else 0), name(i)))


class Lane:
    def __init__(self, store, read_one, approve, start_single, notify):
        self.store, self.read_one, self.approve, self.start_single, self.notify = store, read_one, approve, start_single, notify
        self.q: queue.Queue = queue.Queue()
        self.busy = False
        threading.Thread(target=self._run, daemon=True).start()

    def add(self, item_id: str, from_folder: bool = False) -> None:
        self.q.put((item_id, from_folder))

    def _run(self) -> None:
        while True:
            item_id, slow = self.q.get()
            burst, window, stop = [item_id], (SETTLE_FOLDER_S if slow else SETTLE_S), time.time() + MAX_GATHER_S
            while time.time() < stop:
                try:
                    nxt, s = self.q.get(timeout=window)
                except queue.Empty:
                    break
                burst.append(nxt)
                if s:
                    window = SETTLE_FOLDER_S
            try:
                if len(burst) == 1:
                    self.start_single(burst[0])          # one file: read it and let a person review it, as before
                else:
                    self.busy = True
                    self._batch(burst)
            except Exception:
                traceback.print_exc()
            finally:
                self.busy = False

    def _batch(self, ids: list[str]) -> None:
        items = in_order([i for i in (self.store.item(x) for x in ids) if i])
        n = len(items)
        for k, it in enumerate(items, 1):
            try:
                self.read_one(it["id"])                  # convert, match, Jev: against the graph as it stands now
                cur = self.store.item(it["id"])
                if cur and cur["status"] == "ready":
                    p = cur["proposal"]
                    self.approve(cur, p["type"], p["title"], p["links"], cur.get("author") or "someone",
                                 f"Added automatically, in order of creation ({k} of {n}).")
            except Exception:
                traceback.print_exc()
        self.notify({"type": "batch", "added": n})
