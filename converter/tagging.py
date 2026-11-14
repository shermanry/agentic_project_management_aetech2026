"""Rule-based starter tags. These are deliberately simple and marked
`suggested_by: rules` so a model can replace or extend them later in the pipeline."""
from __future__ import annotations

import re

# tag -> keywords (lower-case, matched on word boundaries)
VOCAB: dict[str, list[str]] = {
    "regulation": ["faa", "part 107", "laanc", "waiver", "airspace", "tfr", "notam", "regulation", "compliance", "permit"],
    "weather": ["weather", "wind", "gust", "rain", "storm", "forecast", "visibility", "precipitation", "temperature"],
    "schedule": ["schedule", "deadline", "due", "postpone", "reschedule", "cancel", "milestone", "timeline"],
    "rfi": ["rfi", "request for information"],
    "decision": ["decide", "decision", "approve", "approved", "approval", "sign off", "sign-off", "confirm"],
    "flight": ["drone", "uav", "uas", "flight", "pilot", "altitude", "waypoint", "takeoff", "landing", "mission"],
    "survey": ["survey", "photogrammetry", "lidar", "point cloud", "scan", "orthomosaic", "mapping"],
    "inspection": ["inspection", "inspect", "defect", "crack", "damage", "facade", "roof", "corrosion"],
    "monitoring": ["monitoring", "progress", "construction progress", "every 2 weeks", "biweekly", "weekly"],
    "site": ["site", "location", "address", "boundary", "parcel", "coordinates", "gps"],
    "geometry": ["model", "rhino", "revit", "ifc", "geometry", "mesh", "brep", "layer"],
    "cost": ["budget", "cost", "fee", "invoice", "quote", "price"],
    "safety": ["safety", "risk", "hazard", "collision", "obstacle", "emergency"],
}

_PATTERNS = {tag: re.compile(r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b", re.I) for tag, kws in VOCAB.items()}
_DECISION_HINTS = re.compile(r"(\?\s*$|please confirm|can you confirm|need(s)? (a )?decision|approve|sign[- ]off|let me know)", re.I | re.M)


def keyword_tags(text: str) -> set[str]:
    return {tag for tag, pat in _PATTERNS.items() if pat.search(text)}


def needs_decision(text: str) -> bool:
    return bool(_DECISION_HINTS.search(text))
