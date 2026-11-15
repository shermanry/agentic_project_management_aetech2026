"""East Tower facade survey, rebuilt from the operator interview in Polina/sme-answers.md (mainly Q1, Q2, Q3A, Q4, Q6).

Same shape as seed.py. The working project uses these tables; the presentation app keeps the whiteboard story in
seed.py, because its cached replay steps link to those nodes by id.

How the interview maps onto the graph:
  constraint   a limit, with data.class = hard (removes the date) | soft (penalises it) | derate (date holds, an
               estimate changes), data.origin (FAA, operator, airframe, authority) and data.applies_to (flight geometry)
  blocker      something a party outside the drone team has to supply: owner, lead time, what it holds up
  decision     data.decides / approves / consulted / informed, and data.alternatives_available where it matters
  discovery    knowledge no feed holds: site visit findings, predicted blackout days
  depends_on   "cannot happen, or cannot be trusted, without"; the chain the operator said lived in one person's head:
               third-party documents -> permit package -> permit -> crew booking -> flight -> processing -> delivery
"""
from __future__ import annotations

PROJECT = {"id": "east-tower", "name": "East Tower facade survey"}
PEOPLE = [{"name": "Sam", "role": "pilot"}, {"name": "Mary", "role": "project manager"},
          {"name": "Alice", "role": "field technician"}, {"name": "Client", "role": "client"}]

HARD, SOFT, DERATE = "hard", "soft", "derate"


def _limit(ref, title, cls, origin, summary, tags, applies_to="vertical, close to a structure", owner="Sam"):
    return dict(ref=ref, type="constraint", title=title, owner=owner, tags=tags + [cls],
                summary=summary, data={"class": cls, "origin": origin, "applies_to": applies_to})


NODES = [
    # ---- the job
    dict(ref="site", type="entity", title="East Tower site", owner="Mary", tags=["site", "facade", "tower"],
         summary="About 400 ft tall. Uncontrolled airspace, so no FAA authorization is needed; NYPD authorization is. "
                 "A one-time series of flights.",
         data={"project_shape": "one-time series", "airspace": "uncontrolled", "jurisdiction": "NYPD"}),
    dict(ref="scope", type="decision", title="Scope: map every facade surface for a remote inspection", owner="Mary",
         state="decided", tags=["scope", "client", "requirement"],
         summary="Preliminary facade inspection to judge existing conditions and estimate repair effort. The client "
                 "owns what and when; the pilot owns how, and whether it is safe.",
         data={"decides": "Mary", "approves": "Client", "consulted": "Sam"}),
    dict(ref="resolution", type="constraint", title="Required image resolution for the inspection", owner="Mary",
         tags=["requirement", "deliverable", "client", HARD],
         summary="What the deliverable demands of the flight. It sets the standoff, the camera, the flight time and so "
                 "the number of flights and permits. Too low, and the flight path is redesigned.",
         data={"class": HARD, "origin": "client", "applies_to": "all flights"}),
    dict(ref="geometry", type="decision", title="Flight geometry: vertical, close to a structure", owner="Sam",
         state="decided", tags=["flight", "facade", "safety"],
         summary="The first question after the site is known, because it selects the limits that apply: about half the "
                 "open-ground wind limit, GPS degraded by the building, standoff and stability as the main risk.",
         data={"decides": "Sam", "informed": "Mary", "options": ["vertical, close to a structure", "planar, open ground"]}),

    # ---- what the site visit found (no feed holds this)
    dict(ref="site_visit", type="event", title="Site visit: equipment checks, drone hand-held", owner="Sam", state="happened",
         tags=["site", "schedule"],
         summary="No take-offs, because no permit exists yet. Checks compass and GPS, picks positions, finds blind spots "
                 "and runs a camera test."),
    dict(ref="sv_compass", type="discovery", title="Compass interference readings on site", owner="Sam", state="absorbed",
         tags=["compass", "interference", "site"], summary="Measured at the candidate take-off spots and along the facade."),
    dict(ref="sv_gps", type="discovery", title="GPS strength by area: weak where the tower shields the sky", owner="Sam", state="absorbed",
         tags=["gps", "risk", "facade"],
         summary="A function of the building's own geometry. It does not stop a flight; it corrupts image positions and "
                 "shows up weeks later as broken maps. Predictable at planning time, so it is raised here.",
         data={"attribution": "environment"}),
    dict(ref="sv_blind", type="discovery", title="Blind spots the desk analysis missed", owner="Alice", state="absorbed",
         tags=["site", "safety", "facade"], summary="Places where the pilot or observer loses sight of the drone."),
    dict(ref="positions", type="decision", title="Take-off, landing, pilot and observer positions", owner="Sam",
         state="decided", tags=["site", "safety", "flight-plan"],
         summary="Chosen on the site visit. They appear on the diagrams in the NYPD package.",
         data={"decides": "Sam", "informed": "Mary"}),
    dict(ref="camera", type="decision", title="Camera and standoff: zoom camera at 20 ft from the facade", owner="Sam",
         state="decided", tags=["camera", "equipment", "safety"],
         summary="A 20 ft standoff is kept for safety, so the zoom camera is needed to reach the resolution. Its shutter "
                 "at least doubles every flight: about 2 mph along a 400 ft facade.",
         data={"decides": "Sam", "consulted": "Client", "consequence": "flight time at least doubles"}),

    # ---- aircraft and crew
    dict(ref="drone_4a", type="entity", title="Drone 4A (DJI Mavic 3 Enterprise)", owner="Sam", tags=["equipment", "drone"],
         summary="Survey aircraft. Its operating limits are read from the airframe's published specification.",
         data={"aliases": ["drone 4a", "4a", "drone4a", "FA-4A", "mavic 3 enterprise"]}),
    dict(ref="crew_pilot", type="entity", title="Sam, pilot in command, named on the NYPD submission", owner="Sam",
         tags=["crew", "permit"],
         summary="Final authority on go or no-go (14 CFR 107.19). Only the people named on the submission may fly; a "
                 "different pilot means a new permit."),
    dict(ref="crew_vo", type="entity", title="Alice, visual observer, named on the NYPD submission", owner="Alice",
         tags=["crew", "permit"], summary="Second of the crew of two. Also named on the submission."),
    dict(ref="crew_booking", type="blocker", title="Named crew released from their other project", owner="Mary",
         state="waiting", tags=["crew", "schedule"],
         summary="Requested and confirmed for the permitted days, not looked up. The other project's manager approves: "
                 "the one veto held outside this project.",
         data={"supplied_by": "another project manager", "approves": "outside project manager", "lead_time_days": None}),

    # ---- limits: hard, soft and derate, set by flight geometry
    _limit("wind_limit", "Wind limit close to the facade: about 10 mph sustained", HARD, "operator judgment",
           "Half the open-ground limit of 20 mph. Measured against the surface forecast, not wind at altitude; the "
           "two must not be swapped silently.", ["wind", "weather", "safety"]),
    _limit("gust_limit", "Gusts close to the facade: minimal (25 mph in open ground)", HARD, "operator judgment",
           "Stability next to the structure is the governing concern.", ["gust", "weather", "safety"]),
    _limit("precip", "No precipitation", HARD, "operator judgment", "Any rain or snow cancels.", ["rain", "weather"],
           applies_to="all flights"),
    _limit("visibility", "Visibility of 3 statute miles or more", HARD, "FAA Part 107",
           "This one does cancel flights. Cloud clearance is on the books too, but has never been the limit below 400 ft, "
           "so it has no node.", ["weather", "faa", "regulation"], applies_to="all flights"),
    _limit("lighting", "Overcast light preferred", SOFT, "operator judgment",
           "Poor light degrades the capture; it does not cancel a flight on its own.", ["weather", "camera"]),
    _limit("endurance", "Battery endurance in cold, heat or wind", DERATE, "airframe specification",
           "The date still holds, but each battery flies for less: more swaps, more crew hours, possibly more flights. "
           "Crew comfort gives out before the aircraft does.", ["weather", "equipment", "drone"], applies_to="all flights"),

    # ---- outside world: live feeds and what an expert infers from them
    dict(ref="weather", type="data_feed", title="Wind forecast feed", owner="Sam", tags=["weather", "forecast"],
         summary="Hourly surface forecast for the site. Trustworthy 2 to 3 days ahead, no further."),
    dict(ref="climatology", type="document", title="Climatology for candidate permit windows", owner="Sam",
         tags=["weather", "schedule", "window"],
         summary="Historical odds that a given 5-day window is flyable. The forecast does not exist when the dates are "
                 "chosen; this does."),
    _limit("airspace_legal", "Airspace legally clear: no TFR or NOTAM", HARD, "FAA",
           "Re-checked the day before, not once at kickoff: the question is what has been published since.",
           ["airspace", "tfr", "faa"], applies_to="all flights"),
    _limit("airspace_ops", "Airspace operationally clear: no patrol helicopters", HARD, "operator judgment",
           "A separate state from legal. Before a presidential visit or a large event, helicopters patrol a day or two "
           "ahead of any published restriction.", ["airspace", "safety", "risk"], applies_to="all flights"),
    dict(ref="blackout", type="discovery", title="Predicted blackout days from public events", owner="Sam", state="triaged",
         tags=["airspace", "schedule", "risk"],
         summary="Dates when a restriction is likely but not yet published, inferred from the events calendar. Carries a "
                 "confidence, not a fact. A blackout can pause the series for days.",
         data={"confidence": 0.6, "authored_by": "Sam"}),

    # ---- the permit chain
    _limit("nypd_rule", "NYPD rule: 30 days' notice, at most 5 days per application", HARD, "NYPD",
           "30 days for a first-time applicant, 14 for a frequent flyer. Rules are live: they changed during the wait "
           "once already.", ["nypd", "permit", "rule"], applies_to="this project", owner="Mary"),
    dict(ref="applicant", type="entity", title="Applicant status: first-time flyer", owner="Mary", tags=["nypd", "permit"],
         summary="Sets the lead time, and so how blind the date choice is.", data={"lead_time_days": 30}),
    dict(ref="insurance", type="blocker", title="Proof of insurance from the legal team", owner="Mary", state="waiting",
         tags=["insurance", "permit"], summary="Requested by message, with its own lead time. Holds up the NYPD package.",
         data={"supplied_by": "internal legal team"}),
    dict(ref="owner_letter", type="blocker", title="Owner's letter of authorization to fly over the property", owner="Mary",
         state="waiting", tags=["authorization", "permit"],
         summary="Written by the property owner. Holds up the NYPD package.", data={"supplied_by": "property owner"}),
    dict(ref="flight_plan", type="decision", title="Flight plan: paths, standoff and speeds for every facade", owner="Sam",
         state="decided", tags=["flight-plan", "facade"],
         summary="Designed from the geometry, the required resolution, the camera choice and the site visit. Redesigned "
                 "when the scope or the resolution changes.",
         data={"decides": "Sam", "informed": "Mary"}),
    dict(ref="permit_date", type="decision", title="Permit dates: a 5-day window, chosen blind", owner="Mary",
         state="decided", tags=["permit", "schedule", "date", "window"],
         summary="Committed about ten times further ahead than the forecast reaches. The project manager approves but "
                 "cannot refuse: there is no alternative.",
         data={"decides": "Sam", "approves": "Mary", "alternatives_available": "none"}),
    dict(ref="permit", type="deliverable", title="NYPD permit document package", owner="Mary", state="in_progress",
         tags=["permit", "nypd", "regulation"],
         summary="Flight path diagrams with pilot and observer positions, insurance proof and the owner's letter. "
                 "Everything in it comes from the flight plan, and it is rebuilt for each new set of dates.",
         data={"generated_from": "flight plan"}),
    dict(ref="dhs", type="blocker", title="DHS approval, required before NYPD during major events", owner="Mary",
         state="open", tags=["dhs", "approval", "regulation"],
         summary="A dependency between authorities that appears when event rules come into force. It sends the package "
                 "back to preparation.", data={"supplied_by": "DHS"}),
    dict(ref="nypd_permit", type="deliverable", title="NYPD take-off permit for the chosen 5 days", owner="Mary",
         state="not_started", tags=["permit", "nypd", "authorization"],
         summary="About three weeks after submission. Names the crew and the dates; moving outside the window means a new "
                 "application."),

    # ---- flying
    dict(ref="go_nogo", type="decision", title="Go or no-go, called the day before", owner="Sam", state="awaiting_inputs",
         tags=["flight", "safety", "schedule"],
         summary="The pilot in command decides and nobody overrules it. Information is useful if it arrives before this "
                 "call and close to worthless after it.",
         data={"decides": "Sam", "informed": ["Mary", "Client"], "when": "T-1 day"}),
    dict(ref="flight_thu", type="event", title="Flight 1: first permitted day, east facade", owner="Sam", state="scheduled",
         tags=["flight", "schedule"],
         summary="Crew of two. If the wind on site is stronger than forecast it becomes a half-day test flight.",
         data={"when": "Thursday 09:00"}),
    dict(ref="flight_series", type="event", title="Flights 2 to 7: the remaining facades", owner="Sam", state="scheduled",
         tags=["flight", "schedule"],
         summary="Needs a fresh application for new dates, the crew again, and the client's view of the first sample."),
    dict(ref="flight_logs", type="document", title="Flight logs and pilot notes", owner="Sam", tags=["flight", "gps"],
         summary="The record of what happened in the air. Evidence for any incident, with the cause attributed to pilot, "
                 "equipment or environment."),

    # ---- after landing: outside this system, kept only as what the flights serve
    dict(ref="processing", type="event", title="Photogrammetry processing (outside this system)", owner="Mary",
         state="scheduled", tags=["photogrammetry", "deliverable"],
         summary="Done in other software. Listed because bad GPS in the images breaks it."),
    dict(ref="facade_model", type="deliverable", title="Orthomosaics and 3D model for the client", owner="Mary",
         state="not_started", tags=["deliverable", "client", "photogrammetry"],
         summary="What the client bought. This system does not produce it; it has to know what it demands."),
]

D = "depends_on"
EDGES = [
    # the job
    ("scope", "site", "about", "The building to be inspected"),
    ("resolution", "scope", D, "Follows from what the inspection has to show"),
    ("geometry", "site", D, "Set by the building: facade work close to a structure"),
    # site visit
    ("site_visit", "site", "about", "Carried out on site"),
    ("sv_compass", "site_visit", "derived_from", "Measured on the site visit"),
    ("sv_gps", "site_visit", "derived_from", "Measured on the site visit"),
    ("sv_blind", "site_visit", "derived_from", "Found on the site visit"),
    ("positions", "sv_compass", D, "Take-off spots avoid compass interference"),
    ("positions", "sv_blind", D, "Observer positions cover the blind spots"),
    ("camera", "resolution", D, "The camera has to reach the required resolution"),
    ("camera", "geometry", D, "The 20 ft standoff comes from flying close to a structure"),
    ("camera", "drone_4a", D, "Uses the aircraft's zoom camera"),
    # limits follow the geometry and read the weather
    ("wind_limit", "geometry", D, "The lower limit applies because the flight is close to a structure"),
    ("gust_limit", "geometry", D, "The lower limit applies because the flight is close to a structure"),
    ("wind_limit", "weather", "about", "Checked against the surface forecast"),
    ("gust_limit", "weather", "about", "Checked against the surface forecast"),
    ("precip", "weather", "about", "Checked against the forecast"),
    ("visibility", "weather", "about", "Checked against the forecast"),
    ("lighting", "weather", "about", "Cloud cover from the forecast"),
    ("endurance", "weather", "about", "Temperature and wind shorten each battery"),
    ("endurance", "drone_4a", D, "Limits come from the airframe's specification"),
    ("airspace_ops", "blackout", D, "Patrols are predicted from the events calendar"),
    # flight plan
    ("flight_plan", "geometry", D, "Vertical passes along each facade"),
    ("flight_plan", "resolution", D, "Paths are designed to reach the resolution"),
    ("flight_plan", "camera", D, "Speed and spacing follow from the camera and standoff"),
    ("flight_plan", "positions", D, "Starts and ends at the chosen positions"),
    ("flight_plan", "sv_gps", D, "Paths are planned around the weak-GPS areas"),
    ("flight_plan", "endurance", D, "Battery swaps and the number of flights"),
    # permit chain
    ("nypd_rule", "applicant", D, "Lead time depends on first-time or frequent-flyer status"),
    ("permit_date", "nypd_rule", D, "Dates must be 30 days out and fit in 5 days"),
    ("permit_date", "climatology", D, "Best historical odds of flyable days"),
    ("permit_date", "blackout", D, "Avoids days likely to be restricted"),
    ("permit", "flight_plan", "derived_from", "Diagrams are drawn from the flight plan"),
    ("permit", "positions", D, "Shows pilot and observer positions"),
    ("permit", "insurance", D, "Needs proof of insurance"),
    ("permit", "owner_letter", D, "Needs the owner's authorization"),
    ("permit", "permit_date", D, "Filed for the chosen dates"),
    ("permit", "crew_pilot", D, "Names the pilot"),
    ("permit", "crew_vo", D, "Names the visual observer"),
    ("permit", "drone_4a", D, "Names the aircraft"),
    ("nypd_permit", "permit", D, "Issued on the submitted package"),
    ("nypd_permit", "nypd_rule", D, "Issued under the current rules"),
    ("nypd_permit", "dhs", D, "NYPD will not proceed without DHS when event rules apply"),
    # crew
    ("crew_booking", "nypd_permit", D, "Booked for the permitted days"),
    ("crew_booking", "crew_pilot", "about", "The named pilot"),
    ("crew_booking", "crew_vo", "about", "The named observer"),
    # go or no-go
    ("go_nogo", "wind_limit", D, "Hard limit"),
    ("go_nogo", "gust_limit", D, "Hard limit"),
    ("go_nogo", "precip", D, "Hard limit"),
    ("go_nogo", "visibility", D, "Hard limit"),
    ("go_nogo", "lighting", D, "Soft: penalises the day"),
    ("go_nogo", "airspace_legal", D, "Hard limit"),
    ("go_nogo", "airspace_ops", D, "Hard limit, judged by the pilot"),
    ("go_nogo", "crew_pilot", D, "The pilot in command makes the call"),
    ("go_nogo", "weather", D, "Made on the forecast as it stands the day before"),
    # flights
    ("flight_thu", "nypd_permit", D, "Cannot take off without the permit"),
    ("flight_thu", "crew_booking", D, "Only the named crew may fly"),
    ("flight_thu", "go_nogo", D, "Flies only on a go"),
    ("flight_thu", "flight_plan", D, "Flies the plan"),
    ("flight_thu", "drone_4a", D, "Flown with Drone 4A"),
    ("flight_thu", "site", "about", "Takes place at the site"),
    ("flight_series", "flight_thu", D, "Follows the client's review of the first sample"),
    ("flight_series", "nypd_permit", D, "Each new set of dates needs its own permit"),
    ("flight_series", "crew_booking", D, "Only the named crew may fly"),
    ("flight_series", "go_nogo", D, "Each flight has its own call"),
    ("flight_series", "flight_plan", D, "Flies the plan"),
    ("flight_logs", "flight_thu", "derived_from", "Recorded during the flight"),
    # after landing
    ("processing", "flight_thu", D, "Uses the flight's images"),
    ("processing", "flight_series", D, "Uses the flights' images"),
    ("processing", "sv_gps", D, "Weak GPS breaks the maps"),
    ("processing", "flight_logs", D, "Logs and notes are needed to repair image positions"),
    ("facade_model", "processing", D, "Built by processing the images"),
    ("facade_model", "resolution", D, "Has to meet the required resolution"),
    ("facade_model", "scope", "about", "The agreed deliverable"),
]

# Live feeds the app creates itself (livefeeds.py): once they exist, these links tie them into the structure.
FEED_EDGES = [
    ("airspace_legal", "feed_airspace", "about", "TFRs and NOTAMs come from the FAA feed"),
    ("blackout", "feed_city", "derived_from", "Inferred from the city's permitted events"),
    ("nypd_rule", "feed_rules", "about", "Rule changes arrive on this feed"),
    ("dhs", "feed_rules", "about", "The DHS requirement came from a rule change"),
    ("sv_gps", "feed_space", "about", "Space weather degrades GPS as well"),
]

PARTS = [
    dict(ref="part_east", type="entity", title="East elevation", owner="Sam", tags=["building-part", "facade", "east"],
         summary="East face of the tower and the first to be flown.",
         data={"aliases": ["east elevation", "east facade", "east façade", "east face", "east side"], "part": "east"}),
    dict(ref="part_north", type="entity", title="North façade", owner="Sam", tags=["building-part", "facade", "north"],
         summary="North face of the tower. Narrow street canyon below.",
         data={"aliases": ["north facade", "north façade", "north elevation", "north face", "north side"], "part": "north"}),
    dict(ref="part_upper", type="entity", title="Upper façade, levels 10 and above", owner="Sam", tags=["building-part", "facade", "upper"],
         summary="Upper curtain wall, furthest from the pilot and the observer.",
         data={"aliases": ["upper facade", "upper façade", "upper levels"], "part": "upper"}),
    dict(ref="part_roof", type="entity", title="Roof and parapet", owner="Sam", tags=["building-part", "roof"],
         summary="Roof, parapet and rooftop mechanical units. A likely source of compass interference.",
         data={"aliases": ["roof", "rooftop", "parapet", "mechanical units"], "part": "roof"}),
    dict(ref="part_entrance", type="entity", title="Podium and ground-level entrance", owner="Mary", tags=["building-part", "ground"],
         summary="Podium roof and street level. Candidate take-off and landing spot; pedestrians below.",
         data={"aliases": ["podium", "podium roof", "entrance", "street level", "ground level"], "part": "entrance"}),
]

PART_EDGES = [
    ("part_east", "site", "part_of", "East face of the tower"),
    ("part_north", "site", "part_of", "North face of the tower"),
    ("part_upper", "site", "part_of", "Upper levels of the tower"),
    ("part_roof", "site", "part_of", "Top of the tower"),
    ("part_entrance", "site", "part_of", "Base of the tower"),
    ("flight_thu", "part_east", "about", "Maps the east elevation"),
    ("flight_series", "part_north", "about", "Maps the north facade"),
    ("flight_series", "part_upper", "about", "Maps the upper levels"),
    ("positions", "part_entrance", "about", "Take-off and landing at the podium"),
    ("sv_compass", "part_roof", "about", "Interference near the rooftop units"),
    ("sv_gps", "part_north", "about", "Weakest in the street canyon on the north side"),
    ("sv_blind", "part_upper", "about", "Upper levels are hardest to keep in sight"),
] + FEED_EDGES

# The chain the operator described, end to end: a small starting project.
STARTER_REFS = ["site", "insurance", "owner_letter", "flight_plan", "permit", "nypd_permit", "crew_booking", "flight_thu",
                "processing", "facade_model"]
