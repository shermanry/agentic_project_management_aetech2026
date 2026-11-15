"""Shared pieces for live-data monitors: site config, HTTP, snapshots and events.

A monitor fetches one feed, compares it with its last snapshot, and returns events only
for changes that matter. Events are appended to monitors/data/events.jsonl (later: the
Postgres event log). Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
USER_AGENT = "aec-drone-pm-monitor/0.1 (hackathon prototype)"

try:  # some Pythons (e.g. uv's) don't see the OS certificate store; certifi's bundle fixes that when installed
    import certifi
    import ssl
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL = None


# ---------- site config ----------

@dataclass
class Limits:
    max_wind_mph: float = 20.0          # sustained, at flight altitude
    max_gust_mph: float = 25.0
    max_precip_prob: float = 30.0       # percent
    min_visibility_m: float = 4828.0    # 3 statute miles (Part 107)
    flight_altitude_m: int = 120        # 10, 80 or 120: which forecast height to use
    daylight_only: bool = True


@dataclass
class Site:
    id: str
    name: str
    lat: float
    lon: float
    address: str = ""
    bin: str = ""                        # NYC building id, if known
    radius_nm: float = 3.0               # how close a TFR / event must be to matter
    flight_window: dict = field(default_factory=dict)   # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    airports: list = field(default_factory=lambda: ["KLGA", "KJFK", "KEWR"])
    borough: str = ""
    police_precinct: str = ""            # NYC precinct number, e.g. "1"; used to match city events
    limits: Limits = field(default_factory=Limits)

    @classmethod
    def load(cls, path: Path) -> "Site":
        raw = json.loads(Path(path).read_text())
        raw["limits"] = Limits(**raw.get("limits", {}))
        return cls(**raw)

    def window(self) -> tuple[Optional[date], Optional[date]]:
        w = self.flight_window or {}
        s, e = w.get("start"), w.get("end")
        return (date.fromisoformat(s) if s else None, date.fromisoformat(e) if e else None)

    def days_to_flight(self, today: Optional[date] = None) -> Optional[int]:
        start, _ = self.window()
        return None if start is None else (start - (today or date.today())).days


# ---------- events ----------

SEVERITY = ("info", "low", "medium", "high")


@dataclass
class Event:
    source: str                      # monitor name
    kind: str                        # e.g. weather.flyability_changed, airspace.tfr_new
    title: str                       # one line, human readable
    summary: str = ""
    severity_hint: str = "info"      # info | low | medium | high: a hint; the attention engine scores
    site: str = ""
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    location: Optional[dict] = None  # {"lat":..,"lon":..} or GeoJSON
    url: Optional[str] = None
    dedupe_key: str = ""             # same key = same real-world thing, update in place
    data: dict = field(default_factory=dict)
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    id: str = ""

    def __post_init__(self):
        assert self.severity_hint in SEVERITY, self.severity_hint
        if not self.id:
            h = hashlib.sha1(f"{self.source}|{self.kind}|{self.dedupe_key}|{self.observed_at}".encode()).hexdigest()
            self.id = "ev_" + h[:12]


def write_events(events: list[Event], path: Path = DATA / "events.jsonl") -> None:
    if not events:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for e in events:
            f.write(json.dumps(asdict(e)) + "\n")


# ---------- HTTP ----------

def get_json(url: str, params: Optional[dict] = None, timeout: int = 30, retries: int = 2) -> Any:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/geo+json"})
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read())
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url[:120]} failed: {last}")


# ---------- geometry ----------

def distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r_nm = 3440.065
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r_nm * math.asin(math.sqrt(a))


def _rings(geom: dict) -> list[list[list[float]]]:
    t, c = geom.get("type"), geom.get("coordinates", [])
    if t == "Polygon":
        return [c[0]]
    if t == "MultiPolygon":
        return [p[0] for p in c]
    return []


def _inside(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside, j = False, len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi:
            inside = not inside
        j = i
    return inside


def geom_distance_nm(lat: float, lon: float, geom: dict) -> float:
    """0 if the point is inside the polygon, else distance to its nearest vertex (good enough at NM scale)."""
    rings = _rings(geom)
    if not rings:
        return float("inf")
    if any(_inside(lon, lat, r) for r in rings):
        return 0.0
    return min(distance_nm(lat, lon, p[1], p[0]) for r in rings for p in r)


# ---------- monitor base ----------

class Monitor:
    name = "base"
    cadence_s = 3600          # normal cadence
    near_flight_cadence_s = None  # tighter cadence within NEAR_FLIGHT_DAYS of the window
    NEAR_FLIGHT_DAYS = 3

    def __init__(self, site: Site):
        self.site = site
        self.state_path = DATA / "state" / f"{site.id}.{self.name}.json"

    def cadence(self) -> int:
        d = self.site.days_to_flight()
        _, end = self.site.window()
        in_play = d is not None and d <= self.NEAR_FLIGHT_DAYS and (end is None or end >= date.today())
        return self.near_flight_cadence_s if (in_play and self.near_flight_cadence_s) else self.cadence_s

    def load_state(self) -> Optional[dict]:
        try:
            return json.loads(self.state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def save_state(self, state: dict) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=1, default=str))

    def run(self) -> list[Event]:
        """Fetch, diff against the last snapshot, save the new one, return events."""
        prev = self.load_state()
        snapshot, events = self.check(prev)
        self.save_state(snapshot)
        return events

    def check(self, prev: Optional[dict]) -> tuple[dict, list[Event]]:
        raise NotImplementedError

    def event(self, **kw) -> Event:
        return Event(source=self.name, site=self.site.id, **kw)


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)
