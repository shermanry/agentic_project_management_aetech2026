"""Seed project: aerial additive manufacturing of a rooftop shell. Manufacturing example card.

Same shape as Ryan/northstar/seed.py (PROJECT, PEOPLE, NODES, EDGES) plus a replay SCENARIO in the shape of
Ryan/northstar/replay.py, so it can be swapped in as a second project. Placeholder details: names, dates and
the wind limit are examples; process figures (202 mL per load, about 5 mm tolerance, scan after every layer)
come from Zhang et al., Nature 609 (2022).
"""
from __future__ import annotations

PROJECT = {"id": "rooftop-shell", "name": "Rooftop shell: aerial AM pilot"}
PEOPLE = [{"name": "Ecem", "role": "design lead"}, {"name": "Jordan", "role": "project manager"},
          {"name": "Lee", "role": "site lead"}, {"name": "Client", "role": "client"}]

NODES = [
    dict(ref="site", type="entity", title="Rooftop terrace site", owner="Jordan", tags=["site", "at-height"],
         summary="Terrace on a 9-storey building. No crane access and no room for a gantry: the reason drones were chosen."),
    dict(ref="shell", type="deliverable", title="Printed shell, 2.4 m", owner="Ecem", state="in_progress", tags=["deliverable", "print"],
         summary="Thin-walled, non-structural shell printed in place, layer by layer. Enclosure only."),
    dict(ref="twin", type="entity", title="Digital twin v4", owner="Ecem", tags=["design", "twin"],
         summary="Design model, sliced into horizontal layers, with a stability check for every interim stage.",
         data={"aliases": ["twin", "design model", "v4"]}),
    dict(ref="buildrone_1", type="entity", title="BuilDrone 1", owner="Lee", tags=["equipment", "drone", "builder"],
         summary="Quadrotor with cartridge extruder and delta arm. Carries about one layer per trip.",
         data={"aliases": ["builddrone 1", "bd1", "drone 1"]}),
    dict(ref="buildrone_2", type="entity", title="BuilDrone 2", owner="Lee", tags=["equipment", "drone", "builder"],
         summary="Second builder. Prints while BuilDrone 1 refills, so layers stay continuous.",
         data={"aliases": ["builddrone 2", "bd2", "drone 2"]}),
    dict(ref="scandrone", type="entity", title="ScanDrone", owner="Lee", tags=["equipment", "drone", "scanner"],
         summary="Camera drone that maps each new layer for the deviation check."),
    dict(ref="method", type="decision", title="Fabrication method: aerial AM", owner="Ecem", state="decided", tags=["method", "design"],
         summary="Aerial AM chosen over gantry and ground robots because the terrace is at height with no crane access."),
    dict(ref="mix", type="decision", title="Material: cement mix No.1", owner="Ecem", state="decided", tags=["material", "design"],
         summary="Mix No.1 holds its shape best under downwash. Chosen after mix No.4 slumped in tests."),
    dict(ref="toolpath", type="decision", title="Toolpath: rounded Peano", owner="Ecem", state="decided", tags=["toolpath", "design"],
         summary="Shortest path per layer, so each layer fits one cartridge."),
    dict(ref="release", type="decision", title="Release next layer", owner="Ecem", state="awaiting_inputs", tags=["layer-gate", "build"],
         summary="Go, hold or adjust. Needs the latest scan, cure state, stability check, wind reading, material and battery."),
    dict(ref="tolerance", type="constraint", title="Tolerance: 5 mm per layer", owner="Ecem", tags=["quality"],
         summary="Maximum deviation of the nozzle path from the design, reachable with the delta arm."),
    dict(ref="payload", type="constraint", title="Payload: 202 mL per load", owner="Lee", tags=["logistics", "payload"],
         summary="Usable cartridge volume. About one layer per trip, so a refill after every layer."),
    dict(ref="wind_limit", type="constraint", title="Wind limit: 6 m/s for printing", owner="Lee", tags=["weather", "safety"],
         summary="Set during the dry run. Above it, path tracking drifts and the extrusion is disturbed. Example value."),
    dict(ref="open_time", type="constraint", title="Mix open time", owner="Ecem", tags=["material", "logistics"],
         summary="The mix must be deposited before it starts to set in the cartridge."),
    dict(ref="weather", type="data_feed", title="Rooftop wind and temperature", owner="Lee", tags=["weather"],
         summary="Anemometer and temperature on the terrace, polled every few minutes during the build."),
    dict(ref="scan_feed", type="data_feed", title="Layer scan feed", owner="Lee", tags=["scan", "quality"],
         summary="Mesh of each new layer from the ScanDrone, compared against the digital twin."),
    dict(ref="telemetry", type="data_feed", title="Drone telemetry", owner="Lee", tags=["equipment", "battery"],
         summary="Battery, motor and position health for every drone."),
    dict(ref="dry_run", type="event", title="Dry run: light-trace flight", owner="Lee", state="happened", tags=["prepare", "safety"],
         summary="Drones fly the full path with lights and no material, to check tracking and spacing."),
    dict(ref="build_day", type="event", title="Build day 2: layers 19–40", owner="Lee", state="scheduled", tags=["build", "schedule"],
         summary="Second print day. Crew: Lee (site lead), refill technician, Ecem on the layer gate."),
    dict(ref="final_scan", type="event", title="Final laser scan", owner="Ecem", state="scheduled", tags=["close", "quality"],
         summary="Full scan of the as-built shell against the design, for acceptance."),
    dict(ref="flight_ok", type="blocker", title="Flight approval for rooftop operations", owner="Jordan", state="done", tags=["permit", "airspace"],
         summary="Approval to fly several drones over the terrace. Needed before the dry run."),
    dict(ref="crew", type="blocker", title="Refill and battery crew for build day 2", owner="Jordan", state="waiting", tags=["staffing", "logistics"],
         summary="One technician to refill cartridges and swap batteries every layer."),
    dict(ref="mix_report", type="document", title="Mix test report", owner="Ecem", tags=["material", "evidence"],
         summary="Slump, flow and set-time results for mixes No.1 and No.4 under propeller downwash."),
    dict(ref="paper", type="document", title="Zhang et al., Nature 2022", owner="Ecem", tags=["reference"],
         summary="Aerial additive manufacturing with multiple autonomous robots. Source for the process and limits."),
]

EDGES = [
    ("method", "site", "depends_on", "Chosen because the site is at height with no crane access"),
    ("shell", "method", "depends_on", "Built by the chosen method"),
    ("shell", "twin", "derived_from", "Printed from the digital twin"),
    ("mix", "mix_report", "evidence_for", "Decided on the test results"),
    ("mix", "open_time", "about", "The mix sets the open time"),
    ("toolpath", "payload", "depends_on", "Path per layer must fit one load"),
    ("toolpath", "twin", "derived_from", "Path sliced from the twin"),
    ("release", "scan_feed", "depends_on", "Needs the latest layer scan"),
    ("release", "tolerance", "depends_on", "Scan must be within tolerance"),
    ("release", "weather", "depends_on", "Wind must be under the limit"),
    ("release", "wind_limit", "depends_on", "Checked against the wind limit"),
    ("release", "telemetry", "depends_on", "Battery and drone health must be ready"),
    ("release", "open_time", "depends_on", "Material must still be workable"),
    ("release", "twin", "depends_on", "Next stage must pass the stability check"),
    ("build_day", "crew", "depends_on", "Cannot print without the refill crew"),
    ("build_day", "buildrone_1", "depends_on", "Builder"),
    ("build_day", "buildrone_2", "depends_on", "Builder"),
    ("build_day", "scandrone", "depends_on", "Scans every layer"),
    ("dry_run", "flight_ok", "depends_on", "Cannot fly without approval"),
    ("wind_limit", "dry_run", "derived_from", "Set from the dry-run tracking results"),
    ("final_scan", "shell", "about", "Acceptance of the printed shell"),
    ("method", "paper", "evidence_for", "Process and limits from the paper"),
]

# Replay: the decision history, in the order things arrived. Same fields as Ryan/northstar/replay.py SCENARIO.
SCENARIO = [
    dict(id="brief", title="Client brief", author="Jordan", approver="Jordan",
         text="Client email: we want a sculptural shell over the rooftop terrace, about 2.4 m high, enclosure only. "
              "The building has no crane access to the roof and the terrace is too small for a printer frame.",
         story="The brief already contains the reason drones make sense: height and no access.",
         reason="Confirmed scope with the client"),
    dict(id="method", title="Method chosen: aerial AM", author="Ecem", approver="Jordan",
         text="Method comparison: a gantry would not fit the terrace and a crane cannot reach it. Aerial AM is justified "
              "by access and height. Trade-offs accepted: slower printing, lighter material, many refill trips.",
         story="The first design decision is whether a drone is needed at all.",
         reason="Only method that reaches the site"),
    dict(id="mix_test", title="Mix No.4 slumps under downwash", author="Ecem", approver="Ecem",
         text="Mix test report: mix No.4 flows best but slumps when the propeller downwash passes over a fresh layer. "
              "Mix No.1 holds its shape. Switching the design to mix No.1; open time gets shorter.",
         story="Material tests change a design decision before anything is printed.",
         reason="Slump measured on three test layers"),
    dict(id="dry_run", title="Dry run passes; wind limit set", author="Lee", approver="Ecem",
         text="Dry run with lights, no material: both builders tracked the path within tolerance and kept safe spacing "
              "at the narrowest layer. Tracking drifted above 6 m/s gusts, so the wind limit for printing is 6 m/s.",
         story="The safety gate before printing sets a limit that every later layer is checked against.",
         reason="Tracking logs from the dry run"),
    dict(id="drift", title="Layers 16–18 drift outward", author="Lee", approver="Ecem",
         text="Layer scans 16, 17 and 18 each show the wall 6–7 mm outside the design on the north side. "
              "Path offsets have not corrected it.",
         story="Small drift is absorbed by offsets. Three layers in a row means the design has to change.",
         reason="Revise layers 19 and up in the twin; stability re-checked"),
    dict(id="wind", title="Gusts above the limit", author="Lee", approver="Ecem",
         text="Rooftop anemometer: gusts of 8 m/s for the last 10 minutes, above the 6 m/s printing limit. "
              "Layer 23 is loaded and waiting.",
         story="The layer gate holds a loaded layer while the material's open time runs down.",
         reason="Hold; refill with fresh mix if the wait passes the open time"),
    dict(id="battery", title="BuilDrone 2 battery fault", author="Lee", approver="Ecem",
         text="bd2 battery cell fault, grounded for the day",
         story="A short field message. The system ties it to the builder scheduled for the next layers.",
         reason="Continue with BuilDrone 1 alone, refilling between layers; slower but continuous"),
    dict(id="final", title="Final scan: within tolerance", author="Ecem", approver="Client",
         text="Final laser scan of the shell against the design: median deviation within tolerance, local exceedance on "
              "the north side at layers 16–18, absorbed by the redesign of the upper layers.",
         story="Acceptance with notes, every decision traceable to its evidence.",
         reason="Accepted with notes on layers 16–18"),
]


def card_text(n: dict) -> str:
    return f"{n['title']}. {n.get('summary', '')} Tags: {', '.join(n.get('tags', []))}"
