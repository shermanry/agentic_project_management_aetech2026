"""Run the monitors for one site.

    python monitors/run.py --once                 # every monitor once, print events
    python monitors/run.py                        # loop forever, each on its own cadence
    python monitors/run.py --once --only tfr,weather_forecast
    python monitors/run.py --context "120 Broadway, New York"   # look up a site
    python monitors/run.py --odds 12-08 12-12     # historical flyable odds for a date range

Events go to monitors/data/events.jsonl (git-ignored). The first run of each monitor only
records a baseline; later runs emit events for changes.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from base import HERE, Site, write_events  # noqa: E402
from feeds import ALL, flyable_odds, site_context  # noqa: E402

ICON = {"high": "!!", "medium": "! ", "low": ". ", "info": "  "}


def show(ev) -> None:
    print(f"  {ICON[ev.severity_hint]} [{ev.source}] {ev.title}")
    if ev.summary:
        print(f"       {ev.summary[:200]}")


def run_one(m) -> list:
    t = time.time()
    try:
        evs = m.run()
        print(f"{m.name:<18} ok   {time.time() - t:5.1f}s  {len(evs)} event(s)  next in {m.cadence() // 60} min")
        for e in evs:
            show(e)
        write_events(evs)
        return evs
    except Exception as e:  # one broken feed must not stop the others
        print(f"{m.name:<18} FAIL {time.time() - t:5.1f}s  {e}")
        if "--debug" in sys.argv:
            traceback.print_exc()
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=str(HERE / "site.json"), help="site config (default monitors/site.json)")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated monitor names")
    ap.add_argument("--context", metavar="ADDRESS")
    ap.add_argument("--odds", nargs=2, metavar=("MM-DD", "MM-DD"))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    if a.context:
        print(json.dumps(site_context(a.context), indent=2))
        return
    site_path = Path(a.site)
    if not site_path.exists():
        site_path = HERE / "site.example.json"
        print(f"(no site.json, using {site_path.name})")
    site = Site.load(site_path)
    if a.odds:
        print(json.dumps(flyable_odds(site, *a.odds), indent=2))
        return

    wanted = {s.strip() for s in a.only.split(",") if s.strip()}
    monitors = [cls(site) for cls in ALL if not wanted or cls.name in wanted]
    print(f"Site: {site.name} ({site.lat:.4f}, {site.lon:.4f}), flight window {site.flight_window or 'not set'}")

    if a.once:
        for m in monitors:
            run_one(m)
        return

    due = {m.name: 0.0 for m in monitors}
    while True:
        now = time.time()
        for m in monitors:
            if now >= due[m.name]:
                run_one(m)
                due[m.name] = time.time() + m.cadence()
        time.sleep(max(5, min(due.values()) - time.time()))


if __name__ == "__main__":
    main()
