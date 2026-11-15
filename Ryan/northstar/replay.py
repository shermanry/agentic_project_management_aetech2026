"""Replay mode: step forward and backward through the facade survey from the team's whiteboard.

Each scenario step is something that arrived during the real project. One press of Forward either brings the
next item in (it goes through the normal intake pipeline and shows as a proposed placement with its effects),
or approves the item that is waiting. One press of Back undoes exactly one Forward.

The timeline starts from an EMPTY project. Position `pos` counts Forward presses:

    pos 0                      nothing: no nodes at all
    pos 1 .. F                 setup: the project's own nodes are added one per press, in the order of seed.NODES
                               (site, drones, plan, limits, permit, flight...), then the live data feeds
    pos F + 2k                 k story steps approved, nothing waiting
    pos F + 2k + 1             k approved, story step k is proposed and waiting for approval

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
import seed
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


# Starting points for a working project (project mode). Refs are from seed.py; order matters for links.
TEMPLATES = {
    "empty": {"label": "Empty project", "refs": []},
    "starter": {"label": "Starter: site, drone, flight plan, permit, flight", "refs": ["site", "drone_4a", "flight_plan", "permit", "flight_thu"]},
    "full": {"label": "Full example: every project node, building parts and live feeds", "refs": None},
}


class Replay:
    def __init__(self, store: Store, data: Path, out_root: Path, notify, approve, feeds=None, enabled: bool = True):
        self.store, self.out_root, self.notify, self.approve, self.feeds = store, out_root, notify, approve, feeds
        self.enabled = enabled                                   # False in project mode: the replay lives in the presentation app
        self.state_file, self.cache_file = data / "replay_state.json", data / "replay_cache.json"
        self.lock = threading.Lock()
        self.setup = ([{"kind": "node", "node": n} for n in seed.NODES + seed.PARTS]
                      + ([{"kind": "feeds"}] if feeds else []))
        self.F = len(self.setup)
        st = self._read(self.state_file, None)
        self.fresh = st is None                                  # first run on this machine: caller sets the project up
        st = st or {}
        if "pos" in st:
            old_f = st.get("F", len(seed.NODES) + (1 if feeds else 0))    # state written before the setup list grew
            self.pos: int = st["pos"] - old_f + self.F if st["pos"] >= old_f else st["pos"]
        else:
            self.pos = self.F + st.get("cursor", 0)              # oldest state files only had the story cursor
        self.item_id: str | None = st.get("item_id")
        self.template: str = st.get("template", "full")          # what this project was started from (project mode)
        self.cache: dict = self._read(self.cache_file, {})
        self.warning: str | None = None
        if store.empty():                                        # database was wiped underneath us
            self.pos, self.item_id = 0, None

    @staticmethod
    def _read(p: Path, default):
        try:
            return json.loads(p.read_text())
        except Exception:
            return default

    def _save(self) -> None:
        self.state_file.write_text(json.dumps({"pos": self.pos, "F": self.F, "item_id": self.item_id, "template": self.template}))

    def _key(self, step: dict) -> str:
        return step["id"] + ":" + hashlib.sha1((step["text"] + llm.jev_model()).encode()).hexdigest()[:10]

    @property
    def cursor(self) -> int:
        """Position within the story steps (0 while the project is still being set up)."""
        return max(0, self.pos - self.F)

    def in_setup(self) -> bool:
        return self.pos < self.F

    # ---------------------------------------------------------------- status
    def _setup_title(self, s: dict) -> str:
        return s["node"]["title"] if s["kind"] == "node" else "Live data feeds"

    def status(self) -> dict:
        k, waiting = divmod(self.cursor, 2)
        it = self.store.item(self.item_id) if self.item_id else None
        n = len(SCENARIO)
        if self.pos == 0:
            phase, cap = "start", ("An empty project", "Nothing has been added yet. Forward adds the first node.")
        elif self.pos < self.F:
            s, nxt = self.setup[self.pos - 1], self.setup[self.pos]
            phase = "setup"
            cap = (f"Setting up · {self.pos} of {self.F}: {self._setup_title(s)}",
                   f"Next: {self._setup_title(nxt)}. The project as planned, before anything went wrong.")
        elif waiting:
            phase = {"processing": "processing", "refining": "processing", "ready": "proposed", "failed": "failed"}.get(
                (it or {}).get("status"), "failed")
            s = SCENARIO[k]
            cap = {"processing": (f"Step {k + 1} of {n}: {s['title']}", f"{s['author']} added it. Working out where it goes…"),
                   "proposed": (f"Step {k + 1} of {n}: {s['title']} · proposed", s["story"] + " Forward approves it."),
                   "failed": (f"Step {k + 1} of {n}: {s['title']}", "That step failed (" + ((it or {}).get("error") or "unknown error") + "). Forward tries again.")}[phase]
        else:
            phase = "idle"
            if k == 0:
                cap = ("The project is set up", f"This is the plan. Forward brings in what happened next: {SCENARIO[0]['title']}.")
            elif k >= n:
                cap = (f"All {n} steps replayed", "Back steps through them in reverse, all the way to the empty project.")
            else:
                nxt = SCENARIO[k]
                cap = (f"Step {k} of {n} approved: {SCENARIO[k - 1]['title']}",
                       f"Next: {nxt['title']}" + ("" if self._key(nxt) in self.cache else " (runs live, a few seconds)"))
        return {"enabled": self.enabled, "template": self.template,
                "templates": [{"id": k, "label": v["label"]} for k, v in TEMPLATES.items()],
                "pos": self.pos, "total": self.F + 2 * n, "setup_total": self.F, "caption": {"title": cap[0], "story": cap[1]},
                "setup": [{"title": self._setup_title(s), "type": s["node"]["type"] if s["kind"] == "node" else "data_feed"} for s in self.setup],
                # story-step fields (unchanged shape; cursor is 0 during setup)
                "cursor": self.cursor, "last": 2 * n, "step": k, "phase": phase, "item_id": self.item_id if waiting else None,
                "error": (it or {}).get("error") if phase == "failed" else None, "warning": self.warning,
                "steps": [{"title": s["title"], "author": s["author"], "text": s["text"], "story": s["story"],
                           "cached": self._key(s) in self.cache} for s in SCENARIO]}

    # ---------------------------------------------------------------- setup steps (the project's own nodes)
    def _embed_cards(self, steps: list[dict]) -> tuple[list, str | None]:
        nodes = [s["node"] for s in steps if s["kind"] == "node"]
        try:
            return (pipeline.embeddings.embed([seed.card_text(n) for n in nodes], kind="document") if nodes else []), pipeline.embeddings.model_id()
        except Exception as e:
            self.warning = f"Added without embeddings ({str(e)[:140]}). Matching falls back to names."
            return [None] * len(nodes), None

    def _add_setup(self, steps: list[dict], first_index: int) -> None:
        """Add setup steps in order. A node brings the seed edges whose other end is already in the graph."""
        vecs, model = self._embed_cards(steps)
        vi = 0
        for offset, s in enumerate(steps):
            if first_index + offset == 0:
                self.store.log("system", "project.created", f"Project “{seed.PROJECT['name']}” created")
            if s["kind"] == "feeds":
                if self.feeds:
                    self.feeds.ensure_nodes(force=True)
                    self.store.log("Monitors", "feeds.connected", "Live data feeds connected", "Weather, airspace, rule changes, city events")
                continue
            n = s["node"]
            nid = self.store.put_node(n, vector=vecs[vi], vector_model=model, created_by=n.get("owner") or "system")
            vi += 1
            for src, dst, typ, reason in seed.EDGES + seed.PART_EDGES:
                if n["ref"] in (src, dst):
                    a, b = self.store.node_by_ref(src), self.store.node_by_ref(dst)
                    if a and b:
                        self.store.put_edge(a["id"], b["id"], typ, reason, 1.0, "seed")
            self.store.log(n.get("owner") or "system", "node.created", f"Added “{n['title']}” to the project",
                           payload={"node_id": nid, "source": "project setup", "added_by": n.get("owner") or "system"})

    def start_project(self, template: str) -> dict:
        """Project mode: wipe the working project and start it again from a template."""
        if template not in TEMPLATES:
            raise ValueError(f"template must be one of {list(TEMPLATES)}")
        with self.lock:
            refs = TEMPLATES[template]["refs"]
            steps = self.setup if refs is None else [s for r_ in refs for s in self.setup
                                                     if s["kind"] == "node" and s["node"]["ref"] == r_]
            self.store.reset()
            self.warning, self.template = None, template
            if steps:
                self._add_setup(steps, 0)
            else:
                self.store.log("system", "project.created", f"Project “{seed.PROJECT['name']}” created")
            self.pos, self.item_id = self.F, None
            self._save()
            self.notify({"type": "graph", "reset": True})
            return self.status()

    def _check_enabled(self) -> None:
        if not self.enabled:
            raise ValueError("The replay runs in the presentation app, not in the working project")

    def ensure_setup_nodes(self) -> int:
        """A project that was set up before the setup list grew is missing the newer nodes (e.g. building parts).
        Add them in place, without rebuilding. Returns how many were added. Only for the full example."""
        with self.lock:
            if self.pos < self.F or (not self.enabled and self.template != "full"):
                return 0
            missing = [s for s in self.setup if s["kind"] == "node" and not self.store.node_by_ref(s["node"]["ref"])]
            if missing:
                self._add_setup(missing, 1)
                self._save()
            return len(missing)

    # ---------------------------------------------------------------- story steps
    def _bring_in(self, step: dict) -> None:
        """Create the intake item for a step: from the cache if we have it, otherwise live through the pipeline."""
        item_id = new_id("it")
        it = {"id": item_id, "status": "processing", "label": step["title"], "author": step["author"],
              "source": {"kind": "text", "text": step["text"], "replay_step": step["id"]}}
        cached = self.cache.get(self._key(step))
        if cached:
            prop = dict(cached)
            prop["effects"] = effects.compute(prop["type"], prop["title"], prop["links"], self.store.nodes(), self.store.edges(), self.store.caused())
            it.update(status="ready", proposal=prop, timings={"total": 0, "cached": True})
            self.store.put_item(it)
            self.notify({"type": "item", "id": item_id, "status": "ready"})
        else:
            self.store.put_item(it)
            self.notify({"type": "item", "id": item_id, "status": "processing"})
            threading.Thread(target=pipeline.process, args=(item_id, self.store, self.out_root, self.notify), daemon=True).start()
        self.item_id = item_id

    def forward(self) -> dict:
        self._check_enabled()
        with self.lock:
            if self.pos < self.F:                                   # setup: one node per press
                self._add_setup([self.setup[self.pos]], self.pos)
                self.pos += 1
                self._save()
                self.notify({"type": "graph", "reset": False})
                return self.status()
            k, waiting = divmod(self.cursor, 2)
            if not waiting:
                if k >= len(SCENARIO):
                    raise ValueError("That was the last step")
                self._bring_in(SCENARIO[k])
                self.pos += 1
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
                    self.pos += 1
            self._save()
            return self.status()

    # ---------------------------------------------------------------- back
    def back(self) -> dict:
        self._check_enabled()
        with self.lock:
            if self.pos == 0:
                raise ValueError("Already at the start")
            k, waiting = divmod(self.cursor, 2)
            if self.pos <= self.F:                               # undo one setup node
                self.rebuild(self.pos - 1, 0)
                self.pos -= 1
            elif waiting:                                        # just withdraw the waiting item; the graph is untouched
                if self.item_id:
                    it = self.store.item(self.item_id)
                    if it and it["status"] in ("processing", "refining"):
                        raise ValueError("Still working on this step")
                    self.store.delete_item(self.item_id)
                self.item_id = None
                self.pos -= 1
            else:                                                # un-approve step k-1: rebuild, then show it as proposed again
                self.rebuild(self.F, k - 1)
                self._bring_in(SCENARIO[k - 1])
                self.pos = self.F + 2 * (k - 1) + 1
            self._save()
            self.notify({"type": "graph", "reset": False})
            return self.status()

    def goto(self, to: str) -> dict:
        """Jump to the empty start ("start") or to the fully set-up project before the story ("setup")."""
        self._check_enabled()
        if to not in ("start", "setup"):
            raise ValueError("to must be start or setup")
        with self.lock:
            target = 0 if to == "start" else self.F
            self.rebuild(target, 0)
            self.pos, self.item_id = target, None
            self._save()
            self.notify({"type": "graph", "reset": True})
            return self.status()

    def rebuild(self, setup_n: int, approved: int) -> None:
        """Empty project + the first `setup_n` setup steps + the first `approved` story steps, re-applied from
        the cache (no model calls). Node ids come out the same every time, so cached links stay valid."""
        self.store.reset()
        self.warning = None
        if setup_n:
            self._add_setup(self.setup[:setup_n], 0)
        for step in SCENARIO[:approved]:
            prop = dict(self.cache[self._key(step)])
            prop["effects"] = effects.compute(prop["type"], prop["title"], prop["links"], self.store.nodes(), self.store.edges(), self.store.caused())
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
            self.item_id, self.pos = None, self.pos + 1
            self._save()
