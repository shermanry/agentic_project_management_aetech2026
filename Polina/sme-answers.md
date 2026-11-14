# Drone operations: subject-matter answers

_Answers to the drone-operations questions in [../Ryan/plan.md](../Ryan/plan.md) §12._
_Polina Ustinova · in progress_

Status: **complete — all 9 answered.** Q7's manufacturing card is owned elsewhere
(`ecem/manufacturing-card`).

## Summary of findings that change the plan

Each is argued in full below, under the question it came from.

| # | Finding | Affects |
| --- | --- | --- |
| 1 | **Blast radius of a date change** — given a proposed new date, compute what it costs. Rescheduling is the top-ranked pain and its cost ranges from one approval to a full re-authorization cycle | proposed headline feature · Q5 |
| 2 | **Constraints come in three classes**: hard (blocks), soft (penalizes), **derate** (date holds, a downstream estimate changes). Derates are how weather reaches the scope estimate | schema · Q1 |
| 3 | **Permit lead time (14–30 days) far exceeds the forecast horizon (2–3 days)** — every date is committed blind. Climatological ranking of candidate windows is the concrete mitigation | scheduling · Q3A |
| 4 | **Flight geometry, not project purpose, is the governing axis.** Vertical-near-structure vs planar-over-open-ground predicts the constraints; inspection/monitoring/manufacturing does not | example cards · Q7 |
| 5 | **Evidence must be snapshotted, not linked.** Forecasts and NOTAMs expire; citing them is how a challenged decision is defended. Today this means digging through old emails | schema · Q4 |
| 6 | **Revisions need `alternatives_available`.** Some approvals cannot be refused; recording them as plain approvals misstates what happened | schema · Q4 |
| 7 | **Client visibility is a state machine, not a permission flag** — internal while unresolved, published once closed, with names and budget redacted per field | role model · Q4 |
| 8 | **The client view needs a request action**, not read-only. Clients influence scope, schedule and frequency — never independently | client view · Q4 |
| 9 | **Participation has four kinds**: decides / approves / **consulted** / informed | schema · Q4 |
| 10 | **The binding constraint migrates by project shape** — permits and weather on one-off work, crew and equipment on recurrent work | scheduling · Q3B |
| 11 | **Scope ends at takeoff.** Deliverable production is out; deliverable *requirements* and pre-flight data-quality prediction stay in | scope · Q6 |
| 12 | **Legal-clear and operationally-clear are different states.** A presidential visit brings patrolling helicopters before any TFR is published | airspace · Q2 |
| 13 | **Incidents need root-cause attribution** — pilot / equipment / environment. Environmental failures are the ones planning should have caught | schema · Q9 |
| 14 | **Do not rebuild Aloft.** The gap is cross-referencing airspace against everything Aloft cannot see, not airspace visualization | scoping · Q2 |
| 15 | **Reschedule reasons are mandatory and enumerated, and the signal is in the aggregate.** No single slip warrants investigation; a pattern across them does | schema · Q9 |

### Inputs missing from the current plan

Named in this interview, absent from `plan.md` §: public event calendars · construction
activity schedules · flight logs and pilot notes · equipment availability · third-party
document status (insurance, owner authorization) · applicant status (first-time vs frequent
flyer)

Every limit below is tagged **hard** (never fly) or **soft** (degraded, fly with mitigation),
because that distinction is what a constraint engine actually runs on. It is not currently
captured in the node schema in `plan.md` §9 — see the note at the end of Q1.

---

## Q1. What makes a flight go or no-go?

### General limits — all flight types

| Condition | Limit | Hard / soft | Origin |
| --- | --- | --- | --- |
| Sustained wind | above 20 mph | hard | operator judgment |
| Gusts | above 25 mph | hard | operator judgment |
| Precipitation | any | hard | operator judgment |
| Visibility | below 3 statute miles | hard | **FAA Part 107** |
| Other weather minimums | per Part 107 | hard | **FAA Part 107** |

### By flight type

Limits tighten when the aircraft works close to a structure. The same site and the same
forecast produce a different answer depending on what the flight is for.

| Flight type | Sustained wind | Gusts | Note |
| --- | --- | --- | --- |
| General / open-area work | 20 mph | 25 mph | the baseline above |
| **Close proximity** — facade inspection, bridge inspection | **~10 mph** | **minimal** | roughly half the general limit; stability near the structure is the governing concern |

### Lighting

Overcast is preferred. Lighting is a **soft** constraint — unfavorable light degrades the
capture but does not on its own cancel a flight.

### Temperature — a derate, not a gate

Temperature is **not** a go/no-go condition in practice.

- **Equipment limits come from the airframe spec**, not from operator judgment. Take the
  DJI Mavic 3 Enterprise as the reference aircraft and read its published operating range.
- **Crew comfort binds before the equipment does.** In heat or cold, people reach their
  limit first. This is a constraint on the crew, not on the aircraft.
- **The real effect is on endurance.** Hot, cold and high wind all consume battery capacity
  faster, which shortens flight time per battery and increases the number of swaps.

### Three classes of constraint, not two

This answer adds a third kind that `plan.md` §9 does not express. All three are needed:

| Class | Effect on the plan | Example |
| --- | --- | --- |
| **Hard** | removes the date entirely | gusts above 25 mph |
| **Soft** | penalizes the date, still flyable | not overcast |
| **Derate** | date stays viable, a downstream estimate changes | cold, heat or high wind shortening battery endurance |

The derate class is what connects weather to **scope**. A cold, windy-but-legal day is still
a go, but it costs more batteries, more swaps and more crew hours than the same flight in
mild conditions. A scheduler that only filters dates cannot express this; the scope estimate
has to read the same weather nodes the scheduler does.

Note that **wind appears twice**: it is a hard gate above 20/25 mph, and below that it is
still a derate on endurance.

### Implication for the build

Three things follow from this answer that the current data model does not express:

1. **Constraints need a class, not just a value** — hard, soft or derate, per the table above.
2. **Constraints are scoped to flight type, not to the project.** A single site can hold a
   20 mph limit and a 10 mph limit at once, and which one applies depends on the mission.
   This is an edge from flight-type to constraint, not a project-level setting.
3. **Some limits belong to the airframe, some to the crew, some to the operator.** Aircraft
   limits are lookups from a spec sheet. Crew limits are human. Operator limits are judgment.
   Only the first is automatable, which is the product's whole argument in miniature.

### What the wind numbers are measured against

At planning time the wind figure is **read off the forecast** — that is, a standard
surface-level forecast reading, not a modeled value at flight altitude.

Knowing the wind **at altitude** would be better. **AirData** already does this well,
providing altitude wind forecasts alongside satellite data, and is a strong source candidate
for the ingest work.

**Calibration warning for the build.** The 20 mph / 25 mph limits above were learned against
surface forecast readings. Wind at 200–300 ft is meaningfully stronger, so applying those
same thresholds to an altitude-corrected figure would reject dates that are in reality
flyable. Two valid options, but the team has to pick one deliberately:

- show both values, and keep the hard thresholds bound to the **forecast** figure; or
- restate the thresholds for altitude, with new numbers from the operator.

Silently swapping one number for the other is the bug to avoid.

### Cloud clearance — on the books, inert in practice

Part 107 requires 500 ft below and 2,000 ft horizontally from clouds. In practice this has
**never** been the binding constraint. Drones generally operate up to 400 ft AGL, so clouds
do not realistically appear along a flight route.

**Visibility below 3 statute miles cancels flights. Cloud clearance does not.**

**Design principle this establishes:** not every regulation deserves a node. Encoding a rule
that has never changed a decision adds a factor the user must read past, and makes the
constraints that *do* bind harder to see. The graph should carry what actually moves
decisions — which means an expert has to say which rules those are. No regulatory database
makes that distinction, and that is precisely the knowledge this product is built to hold.

### Who decides, and when

**The pilot — the Remote Pilot in Command — is always the final authority.** Nobody overrules
the RPIC on a go/no-go. This is not a team convention; it is codified in **14 CFR §107.19**.

**Timeline of the decision:**

| When | What happens | How common |
| --- | --- | --- |
| Day before | Flight is confirmed or cancelled | the normal case |
| Morning of | Cancelled when unpredicted circumstances arise | rare |

### Why this matters more than any other answer here

The legal structure of drone operations already says a human holds final authority and cannot
delegate it. The product does not have to argue that expertise is load-bearing — regulation
says so. The system's job is therefore **not** to decide. It is to make the day-before call
well-informed, and to surface the rare overnight change before the crew is already driving
to site.

That also fixes the system's target: **the decision point is T-1 day.** Information is useful
if it reaches the RPIC before that call, and close to worthless if it arrives after. This is
the operational meaning of "unassigned nodes should be placed before they become impactful."

---

## Q2. Which airspace checks happen before a flight?

Three checks run before a flight, and they are not the same kind of work. The first two are
lookups. The third is forecasting.

### 1. Confirm authorizations are approved

Verify that the required airspace authorizations are in an approved state — not submitted,
not pending. Approved.

### 2. Check the airspace map for new NOTAMs and TFRs

Re-check close to the flight. The relevant question is not "was it clear when we planned
this" but "has anything been published since." A TFR issued after planning is exactly the
kind of late-arriving information that has to reach the RPIC before the T-1 call.

### 3. Predict restrictions that have not been published yet

When scheduling, look ahead at upcoming public and government activity to anticipate
**blackout days** — dates where the FAA is likely to issue a TFR that does not exist yet.

This is not a lookup. There is no feed that returns "a TFR will probably be issued here."
It is inference from a public events calendar plus experience of what the FAA does around
such events.

### The case that defines the product

**A government-related activity such as a presidential visit can make a site unusable even
when the airspace is legally open.**

A day or two ahead of the visit, with no TFR published and the sky clear on every map,
law-enforcement helicopters begin patrolling the area. The flight is legal. It is also a bad
idea, and an experienced operator will not launch into it.

This single case separates three things the system must keep apart:

| | Says | Source |
| --- | --- | --- |
| **Legal status** | airspace is open | FAA feeds — correct, and insufficient |
| **Operational reality** | helicopter traffic overhead | operator inference from a public calendar |
| **The decision** | do not fly | RPIC |

No API returns the middle row. The FAA data is not wrong; it answers a different question
than the one the pilot is actually asking. **An operational planning system that only
surfaces the legal answer will confidently recommend a day the expert would reject** — which
is the argument for building expert constraints into the graph as first-class nodes rather
than treating them as user notes on top of authoritative data.

### Build implications

1. **Airspace status needs re-checking on a schedule**, not once at planning time. The
   NOTAM/TFR check is a T-1 action, not a kickoff action.
2. **"Likely restriction" is a node type.** Predicted blackout days have no source feed, carry
   a confidence rather than a fact, and are authored by a human. They belong in the graph
   anyway, because they drive scheduling weeks ahead.
3. **Public event calendars are an input stream** the current plan does not list. They are the
   upstream signal for both predicted TFRs and predicted helicopter activity.
4. **Legal-clear and operationally-clear must be displayed as separate states.** Collapsing
   them into one green check is the failure mode this product exists to prevent.

### Where these checks happen today

| Tool | Used for | Notes |
| --- | --- | --- |
| **Aloft** | airspace visualization, authorizations, waiver feasibility | **the primary tool.** Shows a real-world airspace map and tells the operator whether a waiver is obtainable under current conditions |
| FAA UAS map | official airspace reference | |
| FAA NOTAMs | notices and temporary restrictions | |
| AirData | weather, including wind at altitude, plus satellite data | also cited in Q1 |

### Scoping consequence: do not rebuild Aloft

Aloft already does airspace visualization and waiver feasibility well. **Rebuilding it would
spend the project's time on a solved problem.**

The gap is not that airspace data is unavailable. It is that these four tools do not talk to
each other, and none of them can see the rest of the project — crane schedules, crew
availability, client deliverables, site access. The value this product adds is
**cross-referencing airspace against everything Aloft cannot see.**

Practical approach: pull the underlying FAA data (UASFM grid, NOTAMs/TFRs) as nodes so it can
participate in the graph, and link out to Aloft for the authoritative visual and the waiver
question rather than reimplementing either.

---

## Q3. A real project, start to finish

Two projects are covered, chosen because they have different shapes:

- **3A — Facade inspection.** A one-time series of flights. Written up below.
- **3B — Recurrent monitoring.** Repeating flights over a construction period. To follow.

---

## Q3A. Facade inspection — one-time series of flights

### What the client needed

A preliminary facade inspection to evaluate existing conditions and estimate repair effort.

| | |
| --- | --- |
| **Scope** | Drone mapping of all facade surfaces, so the inspection could be conducted remotely |
| **Deliverables** | Orthomosaics and 3D reconstructions, via photogrammetry processing |
| **Building** | ~400 ft tall |
| **Airspace** | Uncontrolled — no FAA authorization required |
| **Jurisdiction** | NYPD authorization required |
| **Crew** | 2 — one pilot, one visual observer |
| **Outcome** | Delivered, but **significantly over on both schedule and budget** |

### How it actually went

| # | Phase | What happened |
| --- | --- | --- |
| 1 | Notice to Proceed | Preliminary site analysis to understand building geometry |
| 2 | Preliminary schedule | Built around permitting lead time, document preparation and flight planning effort |
| 3 | Site visit | Equipment checks — **compass interference levels, GPS connection strength**. Chose takeoff/landing positions and observer locations. Resolved blind spots the virtual analysis had missed. Ran a camera test to fix settings and standoff distance. Drone was hand-held throughout; no takeoffs, because no permits existed yet |
| 4 | Permit identification | Checked airspace regulations and local drone law. **Discovered NYPD requires 30 days' notice for a first-time applicant** (14 days for a frequent flyer) |
| 5 | Date selection | Weather cannot be confirmed more than 2–3 days ahead. **Dates were chosen blind** |
| 6 | Document package | Nothing for FAA. NYPD package included detailed flight plan diagrams showing drone flight paths, pilot position and VO positions |
| 7 | Submission, then wait | ~3 weeks |
| 8 | **Rules changed mid-wait** | FIFA games prompted new airspace rules. **DHS approval now required before NYPD would proceed.** Back to document preparation |
| 9 | Approval | Permit granted for **5 days — the maximum a single application allows**. Weather made only **1 of those 5 days** flyable. Decision: fly the one day, and start a fresh document package for a new set of dates in parallel |
| 10 | Crew scheduling | Confirm availability of the specific people named on the NYPD submission, and negotiate with another project manager to free key staff |
| 11 | Flight 1 | On-site wind was stronger than forecast. **Downgraded to a half-day flight and treated it as a test.** Collected a sample dataset |
| 12 | Client review | Sample processed and shown to client. **Feedback: image resolution insufficient.** Flight path had to be redesigned |
| 13 | **Camera change** | Switched to the zoom camera to hold a 20 ft standoff from the facade for safety. Zoom changes the shutter the drone uses, so **every flight now takes at least twice as long**. Max speed ~2 mph against a 400 ft facade at 20 ft offset |
| 14 | Re-authorization | Another round of flight authorization and law-enforcement coordination |
| 15 | Flights 2–7 | Six more flights across 3 weeks |
| 16 | **Forced 10-day pause** | After flight 3, NYPD issued blackout dates for FIFA |
| 17 | Processing | Run in parallel with flying. **Some maps came out broken** |
| 18 | Root cause | **Weak GPS signal in specific areas, caused by the building's own geometry** |
| 19 | Custom fix | Built a metadata analysis and repair tool to rewrite image GPS metadata and force images to the correct location. The math was derived from **flight logs, pilot notes and photogrammetry principles** |
| 20 | Delivery | Data processed and delivered |

### The structural conflict at the centre of this project

> **NYPD requires 30 days' notice. Weather is knowable 2–3 days ahead.**

An operator is legally obliged to commit to dates roughly ten times further out than the
forecast horizon allows them to validate. **Every date is chosen blind.** This is not an
inefficiency to be optimised away — it is a hard structural conflict between a regulatory
clock and a meteorological one, and in this project it produced:

- a 5-day permit window that yielded **one** usable flying day
- a half-day test flight instead of a full capture
- repeated restarts of the document package
- a substantial overrun on both schedule and budget

**This is the problem the product exists to address.** It cannot remove the conflict. What it
can do is make the odds visible at the moment the dates are chosen — using climatology for
the candidate window rather than a forecast that does not yet exist — so that the operator
picks the 5 days with the best historical probability of being flyable, instead of picking
blind. That is a concrete, defensible, demonstrable piece of value.

It also explains why the frequent-flyer distinction matters commercially: dropping from 30
days to 14 halves the blind window.

### Decisions that changed the project

Each of these is a revision in the sense of `plan.md` §3, and each shows a different trigger.

| Decision | Triggered by | Consequence |
| --- | --- | --- |
| Choose permit dates blind | 30-day lead vs 2–3 day forecast | 1 of 5 permitted days flyable |
| Rebuild the document package | **FIFA → new airspace rules → DHS approval required** | ~3 weeks lost after the wait had already been served |
| Fly one day, re-apply in parallel | Only 1 of 5 days viable | Kept the project moving under a 5-day-per-application cap |
| Downgrade flight 1 to a half-day test | **On-site wind stronger than forecast** | Sample data instead of a full capture — which turned out to be lucky |
| Redesign the flight path | **Client feedback: resolution too low** | Triggered the camera change below |
| Switch to the zoom camera | 20 ft standoff required for safety | Shutter changes, **flight time at least doubles**, speed drops to ~2 mph |
| Pause 10 days after flight 3 | **NYPD blackout dates for FIFA** | Schedule slip |
| Build a GPS metadata repair tool | **Broken maps traced to building geometry degrading GPS** | Unplanned engineering work; fix derived from flight logs and pilot notes |

### What this project proves about the data model

1. **A deliverable quality requirement reaches back and changes the flight plan, the
   equipment, the duration and the budget.** "Resolution not high enough" → zoom camera →
   different shutter → 2× flight time → more flights → more permits → more delay. A single
   client comment propagated through every other factor in the project. **This is the cascade
   the demo should show.**

2. **Regulations are not static reference data.** The rules changed *during* the application
   wait, because of an unrelated public event. Anything that treats regulation as a lookup
   table rather than a live, versioned node will miss this entirely.

3. **The crew is a hard constraint, not a resource pool.** The specific people named on the
   NYPD submission are the only people who may fly. Their availability had to be negotiated
   with another project manager. Swapping in a different pilot means re-permitting.

4. **GPS reliability is a function of building geometry** — exactly the factor flagged as
   under-appreciated. It did not block a flight; it silently corrupted the deliverable and
   was only discovered in processing, weeks later. **A failure that surfaces late is worse
   than one that blocks early**, and this one was predictable from the site model.

5. **The site visit produced knowledge no API holds**: compass interference readings, real
   GPS strength, viable takeoff and landing positions, VO positions, blind spots the virtual
   analysis missed, and camera settings with standoff distance. This is the canonical set of
   expert nodes.

6. **The permit document package is a generated artifact.** Flight path diagrams, pilot
   position, VO positions — all derivable from the flight plan. This is the clearest
   automation win in the whole project, and it had to be rebuilt from scratch twice.

### Build implications

- **Climatological date selection** is the headline feature this project argues for: given a
  permit window N days out, rank candidate date sets by historical probability of flyable
  conditions. The forecast does not exist yet; the climatology does.
- **Permit rules are nodes with their own attributes** — lead time, maximum days per
  application, applicant status (first-time vs frequent flyer), issuing body, dependencies on
  other authorities. The DHS-before-NYPD dependency is an edge between authorities.
- **Document package generation** from the flight plan is high value and low effort.
- **GPS/compass quality must be modeled against building geometry** and raised at planning
  time, not discovered in processing.
- **Named crew members are constraint nodes** tied to specific permits.

### What would have helped most

Asked which single thing would have saved the most, the answer was not one missing fact. It
was four kinds of coordination friction — three of them controllable.

**1. Team availability coordination.** Confirming that the specific named crew are free, and
negotiating them away from other projects, was slow manual work on every re-application.

**2. Third-party document requests.** Several required documents are produced by people
outside the drone team, each with their own lead time and their own reasons for being slow:

| Document | Who produces it |
| --- | --- |
| Proof of insurance | internal legal team |
| Letter of authorization to fly over property | the property owner |

Chasing these has no system. They are requested by message, and they block the permit
application, which blocks everything downstream.

**3. Prediction of restrictions from scheduled city events.** The forward-looking check
described in Q2, done systematically instead of from memory.

**4. Dependencies written down.**

> **"If all the dependencies were clearly outlined, not lived in one person's head."**

This is the clearest statement of the problem in this whole document, and it comes from the
operator rather than from the product team. The dependency chain in Q3A is real, long and
unrecorded: the insurance letter gates the NYPD package, which gates the permit, which gates
the crew booking, which gates the flight, which gates the processing, which gates delivery —
and a public event three weeks out can reset the whole chain.

Nobody wrote that down. It lived in one person's head, and it is a direct cause of the
project's overrun.

### A correction to earlier scoping advice

The Slack **messenger nanny** (`plan.md` phase 7c) targets exactly item 2 above — chasing
deliverables and dropped balls from parties outside the team. Earlier scoping notes in this
repo suggested cutting it on the grounds that it is hard to demonstrate on stage. That
judgement was about *demo value*, not about *product value*. The underlying pain is real and
was named unprompted by the operator. If it is cut, it should be cut as a staging decision
and said so explicitly, not dropped as unimportant.

### Build implications

- **Third-party documents are nodes with an owner, a lead time, a status and a blocking
  edge.** They are the clearest instance of "information that must arrive before it becomes
  impactful."
- **Crew availability is a scheduling input, not a lookup** — it requires negotiation with
  other projects, so it has to be requested and confirmed, with a state.
- **The dependency chain itself is the deliverable.** Making it visible is the product.

---

## Q3B. Construction monitoring — recurrent flights

Same opening as Q3A: site analysis, project goals, permit requirements. Everything after that
behaves differently.

| | |
| --- | --- |
| **Project duration** | ~5–6 years in total |
| **Cadence** | started monthly → moved to weekly → now **on-demand**, following construction activity |
| **Crew** | one assigned team; almost always the same pilot and VO |
| **FAA** | blanket approval, renewed every 6 months |
| **NYPD** | 5 days per application, same package resubmitted |
| **Applicant status** | **frequent flyer — 14-day lead time**, not 30 |
| **Main pain point** | **coordinating team availability and equipment** |

### Permitting becomes routine

What consumed the facade project is semi-automated here. The same document package is
resubmitted to NYPD and FAA on a cycle. The FAA blanket approval covers six months at a
time. NYPD still caps at 5 days per application, but resubmission is mechanical rather than
a fresh authoring effort each time.

Critically, **recurrence earns frequent-flyer status, which halves the NYPD lead time from
30 days to 14.** The one-time project pays the full blind-scheduling penalty described in
Q3A; the recurring project amortises it. Repetition is a commercial advantage, not just an
operational convenience.

### Rescheduling is cheap

Over a 5–6 year engagement, moving a flight to next week or next month is not critical. The
weather conflict that defined the facade project is largely absorbed by schedule flexibility.

This is why the cadence could evolve from monthly to weekly to on-demand: the flight schedule
is **derived from the construction activity schedule**, not fixed in advance. The construction
programme is an upstream input that drives drone scheduling.

### Where the difficulty moves

With permits routine and weather absorbable, the binding constraint relocates to **crew and
equipment coordination**. Extra coordination is required in two situations:

1. **Someone on the assigned team is unavailable**
2. **Special-request flights** — night operations, or milestone documentation sessions

### The structural finding: the binding constraint migrates

| | **Q3A — one-time series** | **Q3B — recurrent** |
| --- | --- | --- |
| Permitting | dominates; authored from scratch; **30-day** lead | routine resubmission; **14-day** lead; FAA blanket for 6 months |
| Weather | catastrophic — 1 of 5 permitted days flyable | absorbed by rescheduling flexibility |
| Schedule | fixed, blind, fragile | derived from construction activity; monthly → weekly → on-demand |
| Crew | negotiated per flight against other projects | one standing team |
| **Bottleneck** | **permits and weather** | **crew and equipment availability** |
| Cost of slipping a date | severe — restarts the permit chain | low |

**The same set of factors produces a different critical path depending on project shape.** A
planning tool that assumes permitting is always the hard problem would be wrong on half of
this operator's work, and a tool that assumes schedule flexibility would be dangerously wrong
on the other half.

This is a strong argument for the graph approach over a fixed checklist: the factors are the
same, but which ones bind is emergent, and the system should be able to *show* which ones
currently bind rather than asserting a fixed order of operations.

### Build implications

- **Project shape is a first-class attribute** — one-time versus recurrent — and it changes
  which constraints dominate.
- **Applicant status (first-time vs frequent flyer) is a project attribute with a direct
  numeric effect** on lead time, and therefore on how blind the date selection is.
- **The construction activity schedule is an upstream input node** that drives flight cadence.
  Nothing in the current input list covers it.
- **Cadence is itself a changing decision** — monthly to weekly to on-demand is three
  revisions over the life of a project, each with a reason worth recording.
- **Equipment availability joins crew availability** as a coordination constraint. It is
  named as a pain point here but does not appear anywhere in the current plan.
- **Special-request flights are a distinct flight type** — night operations and milestone
  documentation carry their own coordination and almost certainly their own authorizations.

---

## Q4. Who decides what, and what the client traces

Full working in **[q4-worksheet.md](q4-worksheet.md)**. Summary below.

### The governance rule

> **The RPIC provides the plan and determines what actions are needed. The PM helps make it
> work. The client is informed when needed. Other people are pulled in as required.**

Not what an outsider would assume: technical authority originates the plan, and the project
manager is the enabling function rather than the directing one.

### Where the rule breaks

| Decision | Departure | Risk it represents |
| --- | --- | --- |
| **Accept scope** | `PM` decides, `CL` approves, `RPIC` only consulted on feasibility | Commercial commitments can outrun technical reality; the feasibility check is advisory |
| **Choose permit dates** | `PM` approves but **cannot refuse** — no alternative exists | An approval with no alternatives is not a decision |
| **Release crew from another project** | Approved by a **project manager outside this project** | The only external veto, held by someone with different incentives |

### Participation has four kinds, not three

Decides / approves / **consulted** / informed. The consulted edge — introduced by the operator
unprompted — is where technical feasibility constrains a commercial decision without holding
a veto.

### The client boundary

> **The client owns the commercial envelope — *what* and *when*.
> The RPIC owns the operational method — *how*, and *whether it is safe*.**

The client may request cancellation, schedule delay, changed flight frequency, or changed
scope — **but never independently**. So the client view is not read-only: it needs a
**request** action distinct from an edit, which produces a proposal for assessment rather than
a direct change.

### Client visibility is a state machine, not a permission flag

Scope risks, staffing conflicts, legal documentation and the permit document package are
**not withheld permanently**. They are withheld on two separate axes:

- **Timing** — not shown live while the issue is still being resolved. **Once resolved, the
  full picture should be published**, listing all the challenges the project absorbed.
- **Content** — specific names and budget figures are never posted automatically, at any
  point.

> Operator's principle, verbatim: **"It should be transparent but not exposing the information
> that can be used against the team by the client."**

This is compatible with the second team's pitch, and strengthens it: the client does
eventually see the complete record of challenges. They just do not watch the team fight them
in real time, and they do not get names and dollar figures attached.

`plan.md` §5 models visibility as a fixed three-tier permission scheme — a node is visible to
a role or it is not. That cannot express "internal now, client-visible once closed." Two
consequences: **issue nodes need a resolution state** that the client view filters on, and
**redaction is per-field, not per-node**, so a resolved conflict can be published with names
stripped to roles rather than withheld entirely.

### Evidence must be snapshotted, not linked

When a client challenges a decision, the answer is to explain the factors and **cite them** —
the forecast as it stood, the NOTAM that was active. Today this means **digging through old
emails**, and the original artifacts may no longer exist in that form at all.

> Operator's verdict, verbatim: **"Snapshot feature is a must."**

`revision.evidence` in `plan.md` §9 only works if the nodes it points at are immutable
point-in-time captures. A node for "weather at this site" that refreshes in place is useless
as evidence; "the forecast we held on 14 Nov for 19 Nov" is exactly what is needed.

### Schema consequences

1. Revisions need an **`alternatives_available`** field. "None" is real and frequent, and it
   is the most useful thing to show a client asking why a project ran long.
2. **Four participation types**, not three.
3. **Approvers can be external** to the project.
4. **External data must be versioned snapshots**, not live feeds, wherever a decision cites it.
5. **Node-type redaction rules per role**, so the client view cannot leak internal material
   when someone adds a node type nobody considered.

---

## Q5. What goes wrong most often

Ranked by the operator, most costly first:

| Rank | Problem |
| --- | --- |
| **1** | **Rescheduling — and coordinating the reasons for the reschedule** |
| 2 | Permitting |
| 3 | Bad data |
| 4 | Scope changes |

The phrasing on rank 1 is the important part. The problem is not moving a date. It is the
coordination that follows: everyone who has to be told, re-confirmed, and have it explained
to them.

### The cost of a reschedule is variable and invisible

Asked what actually has to happen when a flight moves:

> **"Depends. Sometimes only one PM has to approve another staff member, and sometimes the
> entire document package has to be re-submitted. This is exactly the answer this platform
> should help provide."**

The same action — move a flight — can cost anywhere between a single approval and a complete
re-authorization cycle. From Q3A, the expensive end means 14–30 days of lead time, a rebuilt
document package, and fresh documents from three external parties.

**Nobody can tell which it will be without tracing the dependency chain by hand**, and that
chain lives in one person's head (Q3A).

### Proposed headline feature: blast radius of a date change

> **Given a proposed change of date, compute and show what it costs.**

This is the operator's own answer to what the platform should do, it addresses the
top-ranked problem, and it is directly computable from a dependency graph. It is the sharpest
feature statement produced by this interview.

**What determines the cost** — each of these is already established elsewhere in this
document:

| Factor | Cheap outcome | Expensive outcome |
| --- | --- | --- |
| Is the new date inside the current permit window? | yes — no resubmission | no — new application, 5-day cap per application |
| Applicant status | frequent flyer — 14-day lead | first-time — 30-day lead |
| Are the named crew available? | yes | substitution, needing `OPM` approval and possibly re-permitting |
| Does it cross a blackout window? | no | forced pause, as with the 10-day FIFA blackout |
| Are third-party documents still valid? | yes | re-request insurance, owner authorization — external lead times |
| Does the new date change airspace requirements? | no | new authority in the chain, e.g. DHS before NYPD |
| Weather probability for the new window | climatology favourable | another blind commitment |

### Why this is the right demo

It turns beat 4 from a vague cascade into a precise, legible claim:

- Drag a flight to a new date → **"Costs: one PM approval."**
- Drag it two weeks later → **"Costs: NYPD resubmission, 14-day lead, insurance letter
  refresh, owner authorization still valid, crosses no blackout."**

Same gesture, two very different answers, both derived from the graph, both currently
produced by one expert thinking hard. It demonstrates the product thesis without anyone
needing to explain it.

---

## Q6. Deliverables — and what the AI should prepare

### Scope decision: deliverables are out of scope

> **"I don't want our solution to do anything with drone deliverables. The goal is to help get
> the drone up in the air, not finish the project deliverables."**

The product's boundary ends when the aircraft is flying. Producing, processing, managing or
delivering orthomosaics, 3D reconstructions, imagery and reports is out of scope — that work
belongs to photogrammetry and deliverable software that already exists.

This is a deliberate narrowing and should be respected in scoping discussions rather than
quietly reopened.

### The boundary is not absolute — two things stay in scope

Applying the rule too broadly would discard two of the strongest findings in this document.

**1. Deliverable *requirements* are planning inputs.**

On the facade project, a single client comment — resolution insufficient — forced a camera
change, which changed the shutter, which at least doubled flight time, which drove more
flights, more permits and more delay. The deliverable specification reaches back and
reshapes the flight plan, the equipment and the schedule.

> Required output quality is a **constraint node** that flight planning must satisfy. The
> system never produces the deliverable; it has to know what the deliverable demands.

**2. Predicting data-quality risk before the flight is in scope.**

The broken maps on the facade project were caused by weak GPS in specific areas, a function
of the building's own geometry. The failure surfaced weeks later in processing, but it was
**predictable at planning time** from the site model.

| | In scope | Out of scope |
| --- | --- | --- |
| Data quality | warning that this facade geometry will degrade GPS before anyone flies | repairing corrupted metadata afterwards |
| Deliverables | knowing the required resolution constrains standoff, camera and flight time | producing orthomosaics or 3D reconstructions |

**The rule:** anything that changes what happens *before takeoff* is in scope. Anything that
happens to the data *after landing* is not.

### What the AI should take over

Four things, all pre-takeoff. The system should be **both a generator and a watcher.**

| Priority | Task | Kind |
| --- | --- | --- |
| **Top** | **Prepare the permit document package** | production |
| Also | Constantly checking airspace status | monitoring |
| Also | Weather | monitoring |
| Also | Coordinating staff | chasing |

### Generation: the document package remains the top priority

Confirmed by the operator as still the highest-value item. The evidence from Q3A supports it:
the NYPD package — flight path diagrams, pilot position, VO positions — was authored from
scratch, then rebuilt entirely when the FIFA rule change introduced a DHS dependency, then
needed again for each new set of dates under the 5-day-per-application cap.

Everything in it is derivable from the flight plan, which the system already holds. This is
the clearest case of expensive manual work that a graph can produce directly.

### Monitoring: the burden is vigilance, not effort

The other three are continuous rather than one-off, and the operative word is *constantly*.
The cost is not performing an airspace check; it is having to keep performing it,
indefinitely, because something might have changed since the last look. A human carrying that
load is expensive and unreliable, and the thing they are watching for is rare.

This connects to the T-1 decision point from Q1. The value is not in reporting the weather —
it is in noticing, **before** the go/no-go call, that something moved. A TFR published after
planning, a forecast that deteriorated, a crew member who became unavailable. Each is cheap
to catch early and expensive to discover late.

**Build note.** Document package generation and the attention engine (`plan.md` phase 7b, with
the polling `worker` from §8) are both core. They are not alternatives, and the generator
should not be deprioritised in favour of the watcher.

---

## Q7. Essential inputs per project card

### The manufacturing card is not covered here

Outside this operator's expertise. It has an owner already — see the
`ecem/manufacturing-card` branch.

### What "monitoring" actually means

A correction to an assumption made during the interview. Monitoring was assumed to mean
tracking a vertical construction project over time. It does not.

> **Monitoring is most useful for flat projects — a public park, large-scale infrastructure.
> It is usually not a vertical flight.**

### The real axis is flight geometry, not project purpose

Confirmed by the operator: asking **"is this vertical work close to a structure, or planar
coverage over open ground?"** tells the system more about the operational constraints than
knowing whether the job is an inspection or a monitoring project.

This matters because the constraints follow from the geometry, not from the label. The 10 mph
wind limit in Q1 comes from **proximity to a structure**, not from the word "inspection."

| | **Vertical — close to a structure** | **Planar — open ground** |
| --- | --- | --- |
| Examples | facade inspection, bridge inspection | public park, large-scale infrastructure |
| Sustained wind limit | **~10 mph, minimal gusts** | **20 mph / 25 mph gusts** |
| Dominant risk | stability and standoff near the structure | — |
| GPS conditions | degraded by the structure's own geometry (Q3A) | open sky |
| Governing requirement | output resolution → standoff → camera → flight duration | area coverage |
| Site visit findings | essential — compass interference, GPS strength, takeoff/landing positions, VO positions, blind spots | |

Rows left blank are not yet confirmed by the operator and should not be treated as settled.

### Build implication

**Flight geometry should be an early, explicit input** — ideally the first question asked after
the site is identified, because it selects which constraint set applies. Structuring the
example cards around purpose labels (inspection / monitoring / manufacturing) organises them
by what the client bought rather than by what governs the flight.

A useful framing for the team: **purpose determines the deliverable; geometry determines the
operation.** The product is scoped to the operation (Q6), so geometry is the axis it should
be built around.

---

## Q8. What has to be shown when a decision is questioned later

Three parties are named in the question. They have **different needs, served by different
features**, and conflating them would inflate the decision-history work beyond what is
justified.

| Who | Has it happened? | What they need | Feature that serves it |
| --- | --- | --- | --- |
| **Client** | yes | the factors behind a change, with the evidence cited — the forecast as it stood, the NOTAM that was active | decision history + evidence snapshots |
| **Regulator** | can request it | **proof of authorizations and permits** | document retention |
| **Insurer** | **never** | — | — |

### The regulator case is a filing cabinet, not a decision log

A regulator asks for the authorization and the permit. They do not ask for the reasoning
behind a date change. Retaining the issued documents, retrievable by date and site, satisfies
this entirely.

> **Scoping consequence:** "regulatory audit" should not be used to justify the decision-history
> feature. It justifies document retention, which is a much smaller piece of work. The real
> justifications for decision history are the **client challenge** case (Q4 B1) and the
> **forward-looking** case — dependencies not living in one person's head (Q3A).

Stating this plainly protects the feature from being over-engineered toward a compliance
standard nobody has ever been held to.

### Open

- **Retention period** for authorizations and permits is unknown to the operator. This is a
  question for the legal team, not for drone operations. It affects storage design only
  mildly and should not block anything.

---

## Q9. "What should happen next" moments

The question proposed three triggers: a flight slipping, a failed capture, a scope change.
**The operator re-sorted them**, and the re-sorting is the finding.

| Trigger | Operator's classification |
| --- | --- |
| Flight slips | **routine individually — but the reason is always recorded, and patterns are investigated** |
| Issue during flight | **incident** |
| Failed capture | **incident** |
| Scope change | **not an issue** — work, not failure |

### 0. A flight slips — routine, but never unrecorded

> **"Flights get rescheduled very often, but the reason why it happened needs to be tracked
> and investigated if there is a pattern or pilot error behind it."**

This is neither an incident nor a non-event. The model has three parts:

1. **Every reschedule records its reason.** Mandatory, and in a comparable form — otherwise
   step 2 is impossible.
2. **Patterns across reschedules trigger investigation.** No single slip warrants it.
3. **Pilot error as a cause triggers investigation immediately**, regardless of pattern.

**The signal is in the aggregate, not the instance.** Four reschedules in a quarter, all
caused by crew unavailability, is a finding. Each one on its own is a Tuesday. Nobody sees
the pattern unless the reasons were captured in a form that can be compared.

> **This is a different job from alerting.** Most systems fire per event. This one has to
> notice a *shape across events* — which is only possible if reasons are structured rather
> than written as free text in an email.

**Build implication:** reschedule reason is a required, enumerated field, and pattern
detection over it is a genuine feature — not a report nobody runs. Candidate reasons, drawn
from this interview: weather, permit/authorization, crew unavailable, equipment, blackout
window, client request, pilot error.

### 1. Issues during flight

1. Investigate the reason
2. Confirm safety protocols were followed
3. **Analyse drone logs** to understand the cause of the incident

### 2. Failed capture

1. Investigate the reason
2. **Attribute the cause** to one of three categories:
   - **pilot error**
   - **equipment malfunction**
   - **environmental influence** — the GPS case from Q3A is the example

### 3. Scope change — not an incident

> **"Scope change is not an issue, it just requires re-evaluation of effort, new flight path
> design and potentially on-site tests to verify the changes."**

This is exactly the camera-change cascade from Q3A, reclassified. It was expensive — it at
least doubled flight time and drove further permitting — but it was **normal work, not a
failure**. Three defined steps follow a scope change:

1. Re-evaluate effort
2. Design a new flight path
3. Possibly run on-site tests to verify the change

### The common pattern: root-cause attribution

Both real incidents resolve to the same move — **establish what caused it**, against a fixed
taxonomy of pilot / equipment / environment. This is a triage classification, and it is
useful to the system for a reason beyond record-keeping: **attribution determines whether the
problem will recur.**

- *Pilot* — addressable by briefing or crew change
- *Equipment* — addressable by maintenance or different hardware
- *Environment* — **often predictable in advance.** The Q3A GPS failure was environmental and
  was foreseeable from the building's geometry at planning time

> The environmental category is where this product earns its place. A failure attributed to
> the environment is a failure the planning system should have warned about, and every such
> attribution is a candidate rule for next time.

### Build implications

1. **Flight logs and pilot notes are an input stream** the current plan does not list. They
   appear twice in this interview: as the evidence for incident investigation here, and as the
   source data for the GPS metadata repair in Q3A. They are the operational record of what
   actually happened in the air.
2. **Incidents carry a required attribution field** with three values. Cheap to record, and it
   makes the history queryable in the way that matters — *how often is it the environment?*
3. **Scope change needs a workflow, not an alert.** Re-evaluate effort → redesign flight path →
   verify on site. Treating it as an exception would misrepresent normal operations.
4. **A slipped flight is not an incident, but its reason is mandatory.** Flagging every routine
   slip as a problem would train users to ignore the flags. Failing to record why it happened
   makes pattern detection impossible. Both failures are easy to make; the model in section 0
   above avoids them.
