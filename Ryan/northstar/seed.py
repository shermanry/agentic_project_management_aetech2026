"""Seed project: a facade survey, taken from the team's whiteboard example. Placeholder details."""
from __future__ import annotations

PROJECT = {"id": "east-tower", "name": "East Tower facade survey"}
PEOPLE = [{"name": "Sam", "role": "pilot"}, {"name": "Mary", "role": "project manager"},
          {"name": "Alice", "role": "field technician"}, {"name": "Client", "role": "client"}]

NODES = [
    dict(ref="site", type="entity", title="East Tower site", owner="Mary", tags=["site", "facade"],
         summary="42-storey tower in lower Manhattan. East and north facades are in scope. Class B airspace."),
    dict(ref="drone_4a", type="entity", title="Drone 4A", owner="Mary", tags=["equipment", "drone"],
         summary="Primary survey drone, registration FA-4A. Named on the NYPD permit application.",
         data={"aliases": ["drone 4a", "4a", "drone4a", "FA-4A"]}),
    dict(ref="drone_4b", type="entity", title="Drone 4B", owner="Mary", tags=["equipment", "drone"],
         summary="Backup survey drone, registration FA-4B. Not named on the current permit.",
         data={"aliases": ["drone 4b", "4b", "FA-4B"]}),
    dict(ref="flight_plan", type="decision", title="Flight plan v3", owner="Sam", state="decided", tags=["flight-plan"],
         summary="Flight paths, pilot and visual observer positions, take-off and landing spots for the east facade. Adds a north observation point."),
    dict(ref="wind_limit", type="constraint", title="Wind limit: 20 mph for facade passes", owner="Sam", tags=["weather", "safety"],
         summary="Maximum sustained wind for flying close to the facade. Lowered from 25 mph after a wind simulation showed gusts funnelling along the east face."),
    dict(ref="weather", type="data_feed", title="Wind forecast feed", owner="Sam", tags=["weather"],
         summary="Hourly wind and precipitation forecast for the site."),
    dict(ref="insurance", type="blocker", title="Insurance proof from legal", owner="Mary", state="waiting", tags=["permit", "insurance"],
         summary="Certificate of insurance requested from the legal department. Needed for the permit package."),
    dict(ref="permit", type="deliverable", title="NYPD take-off permit package", owner="Mary", state="in_progress", tags=["permit", "regulation"],
         summary="Forms, flight plan drawings, drone registration (FA-4A), pilot licence, insurance proof and community notice. Must be submitted 30 days before the flight date."),
    dict(ref="permit_date", type="decision", title="Permit date: week of Thursday's flight", owner="Mary", state="decided", tags=["permit", "schedule"],
         summary="The flight date chosen for the permit application, picked before the weather could be known."),
    dict(ref="flight_thu", type="event", title="Flight 5: Thursday 9am, east facade", owner="Sam", state="scheduled", tags=["flight", "schedule"],
         summary="Facade mapping pass of the east elevation with Drone 4A. Crew: Sam (pilot), Alice (visual observer).",
         data={"when": "Thursday 09:00"}),
    dict(ref="rfi12", type="document", title="RFI #12: mullion spacing, level 14", owner="Mary", tags=["rfi", "facade"],
         summary="Contractor asks to confirm curtain wall mullion spacing on level 14 of the east facade."),
    dict(ref="facade_model", type="deliverable", title="Facade model and repair estimate", owner="Mary", state="not_started", tags=["deliverable", "photogrammetry"],
         summary="Photogrammetry model of the facade and an estimate of repair effort, delivered to the client."),
]

EDGES = [
    ("flight_thu", "drone_4a", "depends_on", "Flight is planned with Drone 4A"),
    ("flight_thu", "permit", "depends_on", "Cannot take off without the NYPD permit"),
    ("flight_thu", "flight_plan", "depends_on", "Flies the approved plan"),
    ("flight_thu", "wind_limit", "depends_on", "Must be under the wind limit"),
    ("flight_thu", "weather", "depends_on", "Go or no-go depends on the forecast"),
    ("flight_thu", "site", "about", "Takes place at the site"),
    ("permit", "drone_4a", "depends_on", "Application names Drone 4A's registration"),
    ("permit", "flight_plan", "depends_on", "Includes the flight plan drawings"),
    ("permit", "insurance", "depends_on", "Needs proof of insurance"),
    ("permit", "permit_date", "depends_on", "Filed for the chosen date"),
    ("permit_date", "weather", "depends_on", "Date was picked before the forecast was known"),
    ("facade_model", "flight_thu", "depends_on", "Built from the flight's images"),
    ("rfi12", "site", "about", "Concerns the east facade"),
    ("wind_limit", "weather", "about", "Checked against the forecast"),
]

# Parts of the building (after Leslie's YBuild overview). Kept in their own list and added AFTER NODES during
# setup, so the ids of the nodes above never change (cached replay steps link to them by id).
PARTS = [
    dict(ref="part_east", type="entity", title="East elevation", owner="Sam", tags=["building-part", "facade", "east"],
         summary="East face of the tower, the main survey target. Gusts funnel along it; curtain wall with vertical fins.",
         data={"aliases": ["east elevation", "east facade", "east façade", "east face", "east side"], "part": "east"}),
    dict(ref="part_north", type="entity", title="North façade", owner="Sam", tags=["building-part", "facade", "north"],
         summary="North face of the tower, in scope. Narrow street canyon below; observed from the north observation point.",
         data={"aliases": ["north facade", "north façade", "north elevation", "north face", "north side"], "part": "north"}),
    dict(ref="part_upper", type="entity", title="Upper façade, levels 10 and above", owner="Sam", tags=["building-part", "facade", "upper"],
         summary="Upper curtain wall, including level 14 where the contractor asked about mullion spacing.",
         data={"aliases": ["upper facade", "upper façade", "upper levels", "level 14"], "part": "upper"}),
    dict(ref="part_roof", type="entity", title="Roof and parapet", owner="Sam", tags=["building-part", "roof"],
         summary="Roof, parapet and rooftop mechanical units. A possible source of compass interference and wind exposure.",
         data={"aliases": ["roof", "rooftop", "parapet", "mechanical units"], "part": "roof"}),
    dict(ref="part_entrance", type="entity", title="Podium and ground-level entrance", owner="Mary", tags=["building-part", "ground"],
         summary="Podium roof and street-level entrance. Candidate take-off and landing spot; pedestrians below.",
         data={"aliases": ["podium", "podium roof", "entrance", "street level", "ground level"], "part": "entrance"}),
]

PART_EDGES = [
    ("part_east", "site", "part_of", "East face of the tower"),
    ("part_north", "site", "part_of", "North face of the tower"),
    ("part_upper", "site", "part_of", "Upper levels of the tower"),
    ("part_roof", "site", "part_of", "Top of the tower"),
    ("part_entrance", "site", "part_of", "Base of the tower"),
    ("flight_thu", "part_east", "about", "Maps the east elevation"),
    ("flight_plan", "part_east", "about", "Flight paths along the east face"),
    ("flight_plan", "part_north", "about", "Adds a north observation point"),
    ("flight_plan", "part_entrance", "about", "Take-off and landing spots"),
    ("wind_limit", "part_east", "about", "Set because gusts funnel along the east face"),
    ("rfi12", "part_upper", "about", "Mullion spacing on level 14"),
    ("rfi12", "part_east", "about", "East facade curtain wall"),
    ("facade_model", "part_east", "about", "Models the east facade"),
    ("facade_model", "part_north", "about", "Models the north facade"),
]


def card_text(n: dict) -> str:
    return f"{n['title']}. {n.get('summary', '')} Tags: {', '.join(n.get('tags', []))}"


# ---------------------------------------------------------------- example projects
# NORTHSTAR_PROJECT picks another project from projects.json. Its seed file replaces the tables above, so every
# place that reads seed.NODES, seed.PROJECT and so on gets the chosen project without knowing about it.
SCENARIO = None                                                       # None = the facade story in replay.py
STARTER_REFS = ["site", "drone_4a", "flight_plan", "permit", "flight_thu"]


def _load_project() -> None:
    import importlib.util
    import os

    import projects
    pid = os.environ.get("NORTHSTAR_PROJECT", "").strip()
    if not pid or pid == PROJECT["id"]:
        return
    p = projects.entry(pid)
    if not p:
        raise SystemExit(f"NORTHSTAR_PROJECT={pid} is not in projects.json")
    path = projects.seed_path(p)
    if not path.is_file():
        raise SystemExit(f"Project '{pid}' needs its seed file, which is not on disk: {path}")
    spec = importlib.util.spec_from_file_location("project_seed", path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    g = globals()
    for k in ("PROJECT", "PEOPLE", "NODES", "EDGES"):
        g[k] = getattr(m, k)
    g["PARTS"], g["PART_EDGES"] = getattr(m, "PARTS", []), getattr(m, "PART_EDGES", [])
    g["SCENARIO"] = getattr(m, "SCENARIO", None)
    g["STARTER_REFS"] = getattr(m, "STARTER_REFS", [n["ref"] for n in g["NODES"][:5]])


_load_project()
