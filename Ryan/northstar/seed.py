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


def card_text(n: dict) -> str:
    return f"{n['title']}. {n.get('summary', '')} Tags: {', '.join(n.get('tags', []))}"
