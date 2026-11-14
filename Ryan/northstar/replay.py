"""Replay mode: step forward and backward through the facade survey from the team's whiteboard.

Each scenario step is something that arrived during the real project. One press of Forward either brings the
next item in (it goes through the normal intake pipeline and shows as a proposed placement with its effects),
or approves the item that is waiting. One press of Back undoes exactly one Forward.

    cursor = 2k      k steps approved, nothing waiting
    cursor = 2k + 1  k steps approved, step k is proposed and waiting for approval

The first time a step runs it is live (Jev and embeddings). Its approved proposal is then cached in the data
folder, so going back and forward again is instant and identical. Back rebuilds the graph from the seed plus
the cached steps, because the event log is append-only.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import effects
import llm
import pipeline
from store import IMPORTANCE, Store, new_id

SCENARIO = [
    dict(id="scope", title="Notice to proceed", author="Mary", approver="Mary",
         text="Client email: notice to proceed. Scope is a drone facade inspection of East Tower, east and north "
              "elevations, to map the facade surfaces and estimate repair effort. They want the model before year end.",
         story="A year after the proposal, the client gives notice to proceed.", reason="Confirmed with the client by phone"),
    dict(id="site_visit", title="Site visit findings", author="Sam", approver="Sam",
         text="Site visit notes: strong compass interference next to the rooftop mechanical units on the east side, and "
              "weak GPS in the street canyon along the north elevation. Blind spots behind the fins. Flight plan v3 "
              "take-off spot needs to move to the podium roof.",
         story="The site visit turns up interference and blind spots that the flight plan has to absorb.",
         reason="Seen on site; will revise the flight path"),
    dict(id="insurance", title="Insurance will take 10 days", author="Mary", approver="Mary",
         text="Legal says the certificate of insurance for the permit will take 10 business days to issue.",
         story="The permit package waits on other people: legal, the property owner, each crew member.",
         reason="Legal confirmed by email"),
    dict(id="rule_change", title="Airspace approval moves to DHS", author="Sam", approver="Mary",
         text="City notice: for the duration of the FIFA games, airspace approval over lower Manhattan passes from the "
              "FAA to DHS. NYPD will not issue a take-off permit without the new DHS approval.",
         story="Two weeks after submitting, the team discovers the rules changed. In the real project this was found late, by accident.",
         reason="Checked with NYPD; package must be resubmitted"),
    dict(id="weather", title="Only one flyable day", author="Sam", approver="Sam",
         text="Forecast for the permit window: gusts of 28 mph on Thursday morning, above the 20 mph wind limit for "
              "facade passes. Wednesday is the only day this week under the limit.",
         story="Authorization covers 5 days. The forecast leaves one of them flyable.",
         reason="Forecast checked against the wind limit"),
    dict(id="drone", title="Drone 4A needs maintenance", author="Alice", approver="Mary",
         text="drone 4a needs maintenance",
         story="A passing remark in chat. The system ties it to the drone named on the permit.",
         reason="Gimbal fault, back Monday"),
    dict(id="metadata", title="Metadata problem in the images", author="Alice", approver="Sam",
         text="The test flight images are missing GPS altitude in their metadata, so photogrammetry alignment fails. "
              "The facade model cannot be processed until the metadata is corrected.",
         story="After flying, the data turns out to have a metadata problem that blocks the deliverable.",
         reason="Reproduced on two image sets"),
]


class Replay:
    def __init__(self, store: Store, data: Path, out_root: Path, notify, approve):
        self.store, self.out_root, self.notify, self.approve = store, out_root, notify, approve
        self.state_file, self.cache_file = data / "replay_state.json", data / "replay_cache.json"
        self.lock = threading.Lock()
        st = self._read(self.state_file, {})
        self.cursor: int = st.get("cursor", 0)
        self.item_id: str | None = st.get("item_id")
        self.cache: dict = self._read(self.cache_file, {})
        if self.cursor and store.empty():          # database was wiped underneath us
            self.cursor, self.item_id = 0, None

    @staticmethod
    def _read(p: Path, default):
        try:
            return json.loads(p.read_text())
        except Exception:
            return default

    def _save(self) -> None:
        self.state_file.write_text(json.dumps({"cursor": self.cursor, "item_id": self.item_id}))

    def _key(self, step: dict) -> str:
        return step["id"] + ":" + hashlib.sha1((step["text"] + llm.jev_model()).encode()).hexdigest()[:10]

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        k, waiting = divmod(self.cursor, 2)
        it = self.store.item(self.item_id) if self.item_id else None
        phase = "idle"
        if waiting:
            phase = {"processing": "processing", "refining": "processing", "ready": "proposed", "failed": "failed"}.get(
                (it or {}).get("status"), "failed")
        return {"cursor": self.cursor, "last": 2 * len(SCENARIO), "step": k, "phase": phase, "item_id": self.item_id if waiting else None,
                "error": (it or {}).get("error") if phase == "failed" else None,
                "steps": [{"title": s["title"], "author": s["author"], "text": s["text"], "story": s["story"],
                           "cached": self._key(s) in self.cache} for s in SCENARIO]}

    # ---------------------------------------------------------------- forward
    def _bring_in(self, step: dict) -> None:
        """Create the intake item for a step: from the cache if we have it, otherwise live through the pipeline."""
        item_id = new_id("it")
        it = {"id": item_id, "status": "processing", "label": step["title"], "author": step["author"],
              "source": {"kind": "text", "text": step["text"], "replay_step": step["id"]}}
        cached = self.cache.get(self._key(step))
        if cached:
            prop = dict(cached)
            prop["effects"] = effects.compute(prop["type"], prop["title"], prop["links"], self.store.nodes(), self.store.edges())
            it.update(status="ready", proposal=prop, timings={"total": 0, "cached": True})
            self.store.put_item(it)
            self.notify({"type": "item", "id": item_id, "status": "ready"})
        else:
            self.store.put_item(it)
            self.notify({"type": "item", "id": item_id, "status": "processing"})
            threading.Thread(target=pipeline.process, args=(item_id, self.store, self.out_root, self.notify), daemon=True).start()
        self.item_id = item_id

    def forward(self) -> dict:
        with self.lock:
            k, waiting = divmod(self.cursor, 2)
            if not waiting:
                if k >= len(SCENARIO):
                    raise ValueError("That was the last step")
                self._bring_in(SCENARIO[k])
                self.cursor += 1
            else:
                step, it = SCENARIO[k], self.store.item(self.item_id) if self.item_id else None
                if not it or it["status"] == "failed":          # retry a failed step
                    if it:
                        self.store.delete_item(it["id"])
                    self._bring_in(step)
                elif it["status"] != "ready":
                    raise ValueError("Still working on this step")
                else:
                    prop = it["proposal"]
                    self.cache[self._key(step)] = {k_: v for k_, v in prop.items() if k_ != "effects"}
                    self.cache_file.write_text(json.dumps(self.cache))
                    self.approve(it, prop["type"], prop["title"], prop["links"], step["approver"], step["reason"])
                    self.item_id = None
                    self.cursor += 1
            self._save()
            return self.status()

    # ---------------------------------------------------------------- back
    def back(self) -> dict:
        with self.lock:
            k, waiting = divmod(self.cursor, 2)
            if self.cursor == 0:
                raise ValueError("Already at the start")
            if waiting:                                   # just withdraw the waiting item; the graph is untouched
                if self.item_id:
                    it = self.store.item(self.item_id)
                    if it and it["status"] in ("processing", "refining"):
                        raise ValueError("Still working on this step")
                    self.store.delete_item(self.item_id)
                self.item_id = None
                self.cursor -= 1
            else:                                         # un-approve step k-1: rebuild, then show it as proposed again
                self.rebuild(k - 1)
                self._bring_in(SCENARIO[k - 1])
                self.cursor = 2 * (k - 1) + 1
            self._save()
            self.notify({"type": "graph", "reset": False})
            return self.status()

    def rebuild(self, approved: int) -> None:
        """Seed project + the first `approved` steps, re-applied from the cache (no model calls)."""
        self.store.reset()
        pipeline.seed_graph(self.store)
        for step in SCENARIO[:approved]:
            prop = dict(self.cache[self._key(step)])
            prop["effects"] = effects.compute(prop["type"], prop["title"], prop["links"], self.store.nodes(), self.store.edges())
            it = {"id": new_id("it"), "status": "ready", "label": step["title"], "author": step["author"],
                  "source": {"kind": "text", "text": step["text"], "replay_step": step["id"]}, "proposal": prop,
                  "timings": {"total": 0, "cached": True}}
            self.store.put_item(it)
            self.approve(it, prop["type"], prop["title"], prop["links"], step["approver"], step["reason"], quiet=True)

    def approved_by_hand(self, it: dict, type_: str, title: str, links: list[dict]) -> None:
        """The waiting step was approved in the review panel (possibly edited): that counts as the Forward press."""
        with self.lock:
            step = SCENARIO[self.cursor // 2]
            prop = {k: v for k, v in it["proposal"].items() if k != "effects"}
            prop.update(type=type_, title=title, links=links)
            self.cache[self._key(step)] = prop
            self.cache_file.write_text(json.dumps(self.cache))
            self.item_id, self.cursor = None, self.cursor + 1
            self._save()

    def restart(self) -> None:
        with self.lock:
            self.cursor, self.item_id = 0, None
            self._save()
