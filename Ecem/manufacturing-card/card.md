# Manufacturing project card: aerial AM

_Answers the open items for the manufacturing card in [PROJECT_BRIEF.md](../../Ryan/PROJECT_BRIEF.md), [plan.md](../../Ryan/plan.md) and [agent-architecture.md](../../Ryan/agent-architecture.md). Draft for team critique._

**The project.** A thin, non-structural shell printed in place on a rooftop terrace by two builder drones and a scan drone. The terrace has no crane access and no room for a printer frame, which is what justifies drones. Process figures come from Zhang et al., *Nature* 609 (2022); names, dates and the wind limit are placeholders.

**Why it matters for the product.** The facade survey makes a few big decisions before one flight. Manufacturing makes a decision every layer, 72 times for a 2.05 m tower. It's the strongest test of "decision record plus live data".

## 1. Inputs (brief: "list every input each would use")

| Input | Source | Node type | Example |
|---|---|---|---|
| Client brief, scope, site photos | Internal / passive (email) | document, entity | "Shell over the terrace, 2.4 m, no crane access" |
| Site survey: height, access, footprint | Internal | entity, constraint | Terrace size, roof load, launch area |
| Design model and its versions | Internal (Rhino/Grasshopper) | entity (digital twin), revisions | Twin v4, sliced into layers |
| Material spec and mix tests | Internal (lab) | document, constraint | Mix No.1 vs No.4 slump under downwash |
| Robot fleet and telemetry | External API (drones) | entity, data_feed | Battery, faults, position per drone |
| Layer scans | AI-generated / sensor | data_feed | Mesh of each layer vs twin, deviation in mm |
| Rooftop wind and temperature | External API / sensor | data_feed | Anemometer, forecast |
| Flight and airspace approval | External (FAA rules) | blocker, constraint | Approval for multi-drone flight over the roof |
| Crew roster | Internal | blocker | Refill and battery technician per shift |
| Consumables | Internal | constraint, data_feed | Cartridges, mix batches, charged batteries |
| Stability checks | AI-generated | discovery, decision | "Layer 19 stage fails unless sequence changes" |
| Field messages | Passive (Slack) | discovery | "bd2 battery cell fault" |

## 2. APIs and connectors

Drone telemetry (fleet or flight-controller API), scan processing (mesh vs twin), weather and an on-site anemometer, FAA airspace (shared with the facade pack), CAD/twin (Rhino or a file drop), Slack, calendar. New compared with the facade pack: telemetry, scan comparison, and the twin.

## 3. Node types (agent-architecture.md, question 5)

The eight types plus `entity` cover most of it. Every node in `data/aerial_am_nodes.csv` now has a `team_type` column. Five things manufacturing needs that the facade survey doesn't:

| Missing | Why | Suggested modelling |
|---|---|---|
| **Repeating work unit (layer)** | The same decision recurs every layer with fresh inputs | A `decision` with `cadence: per_layer`, or a new `work_unit` type that spawns one release decision each |
| **Consumable** | Material and batteries burn down and expire (open time) | `constraint` plus a `data_feed` for the level, or a new `consumable` type with quantity and expiry |
| **Quality check** | Each layer is measured against design; repeated failure re-opens design | `data_feed` producing `discovery` nodes; rule 2 in `rules.json` |
| **Design version / twin** | Design changes mid-build; every layer must trace to a version | `entity` with revisions; edges `derived_from` to each layer |
| **Gate** | Several phases end in approvals (method, buildability, freeze, safety, acceptance) | A `decision` tagged `gate`, or a gate field on the phase |

Manufacturing phases for the node `phase` field: `brief | method | design | prepare | build | close` (17 steps in [README.md](../README.md)).

## 4. Test data with a decision history (plan.md, section 10)

`seed_manufacturing.py` has the same shape as `Ryan/northstar/seed.py`: 24 nodes, 22 edges, using only the app's node and edge types. Its `SCENARIO` has the same fields as `replay.py` and gives 8 steps: brief, method chosen, mix No.4 slumps, dry run sets the wind limit, layers 16–18 drift, gusts hold layer 23, BuilDrone 2 battery fault, final scan accepted with notes. `seed_manufacturing.json` is the same data as JSON. Nothing in `Ryan/` is changed; swapping it in is a one-line import.

## 5. Rule pack (agent-architecture.md, section 3 and question 6)

`rules.json`: nine rules for `aerial-am-manufacturing`, in the section 3 format, all `proposed`:

1. Layer release waiting on inputs near the end of open time → red, chase the missing input
2. Deviation over tolerance three layers in a row → discovery, re-open the design decision
3. Gust over the limit, or weather feed silent during a build → hold the layer gate
4. Builder fault or low battery → reassign if the fleet can finish before the mix sets (Jev judgment)
5. Build day within 24 h → check crew, approval, forecast, material, batteries
6. A constraint value changes → re-check pending releases and the toolpath
7. A design decision changes the twin → run the stage stability check first
8. Refill crew not confirmed 48 h out → nudge, then escalate to the PM
9. All layers done and final scan in → create the acceptance decision with evidence attached

Never automated, in my view: method choice, design freeze, final acceptance, and anything that resumes printing after a fault.

## 6. Answers to section 12 questions, for manufacturing

- **Go / no-go (Q1):** last layer within tolerance, layer below cured, next stage stable, wind under the limit, material within open time, battery enough. Wind and cure limits must come from a pilot; the papers only tested indoors.
- **Decisions and who makes them (Q4):** method, material, tolerance, toolpath, freeze (design lead); every layer release (design lead with site lead); budget, crew, permits, sign-off (PM).
- **What goes wrong (Q5):** drift that offsets can't fix, wind holds that run past the open time, a builder failing mid-layer, crew or consumables missing on build day.
- **Handover (Q6):** the printed element, a final scan against design, and the full decision log.
- **What a client must trace later (Q8):** every hold, redesign and acceptance, with the scan and readings it rested on.
- **What happens next (Q9):** after a wind hold, refill with fresh mix if the wait passed the open time; after repeated drift, revise upper layers and re-check stability; after a drone fault, continue slower with one builder or stop at the layer boundary.

## Sources

- Zhang et al., Aerial additive manufacturing with multiple autonomous robots, *Nature* 609, 709–717 (2022)
- Stuart-Smith, Darekar, Danahy, Pawar, Kovac, Collective Aerial Additive Manufacturing
- The rise of aerial additive manufacturing in construction, *Frontiers in Materials* (2024)
