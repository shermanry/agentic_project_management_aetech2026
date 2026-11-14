"""Live data feeds: run the repo-root monitors/ inside the app and turn their events into graph changes.

Decision A4: only live feeds update the graph without asking. So:

  bad news   (a flight-window day turns unflyable, a TFR over the site, LAANC ceiling change, storm)
             -> the feed's data_feed node goes 'changed', and effects.py ripples from it exactly as if a
                discovery "blocks" the feed: Thursday's flight goes at risk, the permit date re-opens.
  good news  (the day is flyable again, the TFR ended, the alert expired)
             -> the matching flags close (same dedupe_key); the feed goes back to 'healthy'.
  discovery  (a new FAA/DHS rule or notice)
             -> submitted through normal intake as text, so Jev proposes a placement and a person approves.
  anything else is recorded in the event log only (with a reading on the feed's source).

Settings: FEEDS_ENABLED (default 1), MONITOR_SITE (default monitors/site.json, else site.example.json).
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import effects

REPO = Path(__file__).resolve().parents[2]
MONITORS = REPO / "monitors"
if str(MONITORS) not in sys.path:
    sys.path.append(str(MONITORS))   # append: northstar's own modules win any name clash

import base as mon_base      # noqa: E402  (monitors/base.py)
import feeds as mon_feeds    # noqa: E402  (monitors/feeds.py)

# Monitors grouped into one data_feed node each, so the graph stays readable.
FEEDS = {
    "weather": dict(title="Wind forecast feed", monitors=["weather_forecast", "weather_alerts", "aviation_weather"],
                    summary="Open-Meteo hourly forecast at flight altitude, NWS alerts, and METAR at LGA, JFK, EWR.",
                    connector="http:open-meteo+nws+awc"),
    "feed_airspace": dict(title="Airspace feed (FAA TFRs, LAANC grid)", monitors=["tfr", "uas_ceiling"],
                          summary="Temporary flight restrictions near the site and the LAANC ceiling over it.",
                          connector="http:faa-tfr+uas-facility-map",
                          edges=[("flight_thu", "depends_on", "Can't fly inside a TFR or above the LAANC ceiling")]),
    "feed_rules": dict(title="Rule changes feed (Federal Register)", monitors=["regulations"],
                       summary="New FAA, DHS and TSA rules and notices about drones and airspace.",
                       connector="http:federal-register",
                       edges=[("__self__", "about", "permit", "New rules may change what the permit needs")]),
    "feed_city": dict(title="NYC permitted events feed", monitors=["nyc_events"],
                      summary="Permitted street events, closures and productions in the site's precinct during the flight window.",
                      connector="http:nyc-open-data",
                      edges=[("__self__", "about", "site", "Street closures and crowds near the site")]),
    "feed_space": dict(title="GPS / space weather feed (NOAA Kp)", monitors=["space_weather"],
                       summary="Geomagnetic storm forecast; Kp of 5 or more can degrade GPS.",
                       connector="http:noaa-swpc",
                       edges=[("flight_thu", "depends_on", "Needs reliable GPS for the facade passes")]),
}
MONITOR_TO_FEED = {m: ref for ref, f in FEEDS.items() for m in f["monitors"]}
MAX_INTAKES_PER_RUN = 3


def classify(ev: mon_base.Event) -> str:
    """'bad' (ripple + flags), 'good' (close flags), 'discovery' (intake), or 'log'."""
    k, d, sev = ev.kind, ev.data or {}, ev.severity_hint
    if k == "weather.flyability_changed":
        if not d.get("in_flight_window"):
            return "log"
        return "good" if d.get("flyable") else "bad"
    if k == "weather.window_summary":
        return "bad" if len(d.get("flyable_days", [])) <= 1 else "good"
    if k == "weather.alert_new":
        return "bad" if sev in ("high", "medium") else "log"
    if k in ("weather.alert_ended", "airspace.tfr_ended"):
        return "good"
    if k in ("airspace.tfr_new", "airspace.laanc_ceiling_changed", "space.geomagnetic_storm"):
        return "bad"
    if k in ("rules.document_new", "airspace.tfr_regional"):
        return "discovery" if sev in ("medium", "high") else "log"
    return "log"


class LiveFeeds:
    def __init__(self, store, notify: Callable[[dict], None], submit_text: Callable[[str, str], str], data_dir: Path):
        self.store, self.notify, self.submit_text = store, notify, submit_text
        site_path = Path(os.environ.get("MONITOR_SITE", MONITORS / "site.json"))
        if not site_path.exists():
            site_path = MONITORS / "site.example.json"
        self.site = mon_base.Site.load(site_path)
        self.monitors = {cls.name: cls(self.site) for cls in mon_feeds.ALL}
        state_dir = data_dir / "monitors"
        for m in self.monitors.values():   # keep app snapshots apart from command-line runs
            m.state_path = state_dir / f"{self.site.id}.{m.name}.json"
        self.status = {name: {"feed": MONITOR_TO_FEED[name], "last_run": None, "next_run": 0.0, "ok": None,
                              "error": None, "events": 0} for name in self.monitors}
        self._lock = threading.Lock()
        self._stop = threading.Event()

    # ------------------------------------------------------------ graph setup
    def ensure_nodes(self) -> dict[str, str]:
        """Create any missing feed nodes (and their edges), register them as sources. Returns ref -> node id."""
        ids = {}
        for ref, f in FEEDS.items():
            n = self.store.node_by_ref(ref)
            if n is None:
                nid = self.store.put_node({"ref": ref, "type": "data_feed", "title": f["title"], "summary": f["summary"],
                                           "tags": ["live-data", "feed"], "owner": "Sam", "state": "healthy",
                                           "data": {"monitors": f["monitors"]}}, created_by="monitors")
                for e in f.get("edges", []):
                    if e[0] == "__self__":
                        target = self.store.node_by_ref(e[2])
                        if target:
                            self.store.put_edge(nid, target["id"], e[1], e[3], 1.0, "seed")
                    else:
                        src = self.store.node_by_ref(e[0])
                        if src:
                            self.store.put_edge(src["id"], nid, e[1], e[2], 1.0, "seed")
            else:
                nid = n["id"]
            ids[ref] = nid
            cad = min(self.monitors[m].cadence() for m in f["monitors"])
            self.store.register_source(nid, f["connector"], {"monitors": f["monitors"], "site": self.site.id},
                                       f"every {cad // 60} min")
        return ids

    # ------------------------------------------------------------ applying events
    def apply(self, ev: mon_base.Event) -> dict:
        ids = self.ensure_nodes()
        feed_ref = MONITOR_TO_FEED.get(ev.source, "weather")
        feed_id = ids[feed_ref]
        how = classify(ev)
        payload = {"title": f"{FEEDS[feed_ref]['title'].split(' (')[0]}: {ev.title}", "reason": ev.summary,
                   "monitor": ev.source, "kind": ev.kind, "severity_hint": ev.severity_hint, "url": ev.url,
                   "dedupe_key": ev.dedupe_key, "valid_from": ev.valid_from, "valid_to": ev.valid_to,
                   "handled_as": how, "data": ev.data}
        fx = None
        if how == "bad":
            fx = effects.compute("discovery", ev.title, [{"target": feed_id, "type": "blocks"}],
                                 self.store.nodes(), self.store.edges())
            payload["effects"] = [{"node_id": e["node_id"], "title": e["title"], "change": e["change"], "why": e["why"]}
                                  for e in fx["effects"]]
        seq = self.store.feed_event(feed_id, f"feed.{ev.kind}", payload, fx, ev.dedupe_key)
        item_id = None
        if how == "discovery":
            text = f"{ev.title}\n\n{ev.summary}\n\nSource: {ev.url or ev.source}"
            item_id = self.submit_text(text, "Monitors")
        self.notify({"type": "graph", "seq": seq, "node_id": feed_id})
        return {"revision": seq, "feed": feed_ref, "handled_as": how, "item_id": item_id,
                "effects": payload.get("effects", [])}

    # ------------------------------------------------------------ running monitors
    def run(self, names: list[str] | None = None) -> dict:
        out = {}
        with self._lock:
            intakes = 0
            for name in names or list(self.monitors):
                m, st = self.monitors[name], self.status[name]
                t = time.time()
                try:
                    evs = m.run()
                    applied = []
                    for ev in evs:
                        if classify(ev) == "discovery":
                            if intakes >= MAX_INTAKES_PER_RUN:
                                ev.severity_hint = "low"   # still logged, not proposed
                            else:
                                intakes += 1
                        applied.append(self.apply(ev))
                    st.update(ok=True, error=None, events=st["events"] + len(evs))
                    out[name] = {"ok": True, "events": len(evs), "applied": applied}
                except Exception as e:   # one broken feed must not stop the others
                    st.update(ok=False, error=str(e)[:300])
                    out[name] = {"ok": False, "error": str(e)[:300]}
                    traceback.print_exc()
                st.update(last_run=time.time(), seconds=round(time.time() - t, 1), next_run=time.time() + m.cadence())
        return out

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True, name="livefeeds").start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        try:
            self.ensure_nodes()
        except Exception:
            traceback.print_exc()
        while not self._stop.is_set():
            due = [n for n, s in self.status.items() if time.time() >= s["next_run"]]
            if due:
                self.run(due)
            nxt = min(s["next_run"] for s in self.status.values())
            self._stop.wait(max(5.0, min(60.0, nxt - time.time())))

    def snapshot(self) -> dict:
        return {"site": {"id": self.site.id, "name": self.site.name, "lat": self.site.lat, "lon": self.site.lon,
                         "flight_window": self.site.flight_window},
                "monitors": self.status, "feeds": {r: f["title"] for r, f in FEEDS.items()},
                "scenarios": sorted(SCENARIOS)}

    # ------------------------------------------------------------ demo injection
    def inject(self, scenario: str) -> dict:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario; choose one of {sorted(SCENARIOS)}")
        return self.apply(SCENARIOS[scenario](self.site))


def _next_weekday(wd: int) -> date:   # 0 = Monday ... 3 = Thursday
    d = date.today() + timedelta(days=1)
    while d.weekday() != wd:
        d += timedelta(days=1)
    return d


def _ev(**kw) -> mon_base.Event:
    return mon_base.Event(**kw)


SCENARIOS: dict[str, Callable] = {
    "thursday_unflyable": lambda s: _ev(
        source="weather_forecast", kind="weather.flyability_changed", site=s.id, severity_hint="high",
        title=f"{_next_weekday(3)} (Thursday): no longer flyable (1 flyable daylight hour)",
        summary="Worst: wind 31 mph at 120 m, gusts 38 mph, rain 20%. Limited by wind, gusts.",
        valid_from=str(_next_weekday(3)), valid_to=str(_next_weekday(3)), dedupe_key=f"flyability:{_next_weekday(3)}",
        data={"day": str(_next_weekday(3)), "in_flight_window": True, "flyable": False, "flyable_hours": 1,
              "demo": True}, url="https://open-meteo.com/"),
    "thursday_flyable": lambda s: _ev(
        source="weather_forecast", kind="weather.flyability_changed", site=s.id, severity_hint="medium",
        title=f"{_next_weekday(3)} (Thursday): now flyable (8 flyable daylight hours)",
        summary="Worst: wind 14 mph at 120 m, gusts 19 mph, rain 0%.",
        valid_from=str(_next_weekday(3)), valid_to=str(_next_weekday(3)), dedupe_key=f"flyability:{_next_weekday(3)}",
        data={"day": str(_next_weekday(3)), "in_flight_window": True, "flyable": True, "flyable_hours": 8,
              "demo": True}, url="https://open-meteo.com/"),
    "tfr_over_site": lambda s: _ev(
        source="tfr", kind="airspace.tfr_new", site=s.id, severity_hint="high",
        title="TFR 6/9999 covers the site: VIP MOVEMENT",
        summary="Temporary flight restriction, lower Manhattan, 3 NM radius, surface to 3,000 ft, during a VIP visit.",
        valid_from=str(_next_weekday(3)), valid_to=str(_next_weekday(3) + timedelta(days=1)), dedupe_key="tfr:6/9999",
        data={"notam_id": "6/9999", "distance_nm": 0, "type": "VIP", "demo": True}, url="https://tfr.faa.gov/"),
    "tfr_ended": lambda s: _ev(
        source="tfr", kind="airspace.tfr_ended", site=s.id, severity_hint="low",
        title="TFR 6/9999 near the site has ended", dedupe_key="tfr:6/9999", data={"notam_id": "6/9999", "demo": True}),
    "rule_change": lambda s: _ev(
        source="regulations", kind="rules.document_new", site=s.id, severity_hint="medium",
        title="Rule: Special security instructions; drone operations over New York City moved to DHS approval",
        summary=("Effective in 10 days, small unmanned aircraft operations within the New York City area during designated "
                 "security events require DHS coordination in addition to FAA airspace authorization and local permits."),
        dedupe_key="fr:demo-dhs", data={"demo": True}, url="https://www.federalregister.gov/"),
    "gps_storm": lambda s: _ev(
        source="space_weather", kind="space.geomagnetic_storm", site=s.id, severity_hint="medium",
        title=f"Geomagnetic storm forecast {_next_weekday(3)} (Kp 6.3): GPS may be degraded",
        valid_from=str(_next_weekday(3)), valid_to=str(_next_weekday(3)), dedupe_key=f"kp:{_next_weekday(3)}",
        data={"kp": 6.3, "demo": True}, url="https://www.swpc.noaa.gov/products/planetary-k-index"),
}
