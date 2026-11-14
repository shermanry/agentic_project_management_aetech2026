# Front end: product design review and phased build plan

_Draft for team critique · 2026-11-14 · reviews [Ryan/northstar](../Ryan/northstar/README.md) (the working app), Grant's prototype (branch `grant`), Sharare's mockups (branch `sharare/decision-engine`) and Ryan's SVG mockups ([Ryan/plan.md](../Ryan/plan.md) §5)_

**How to use this doc:** same convention as the other plans. Each item is marked **Decided**, **Proposed** or **Open**. Section 5 is the build plan. Each phase is one PR, reviewed before it goes into `main`.

## 1. The test we design against (Proposed)

A judge watches for three minutes. The core story has to land in **under one minute**:

> **Weather changed → flight affected → pilot approves a change → client understands why.**

Every screen is scored on five questions:

| Question | What "good" looks like |
| --- | --- |
| **Clarity** | Within 5 seconds of opening, you can name the project, the next flight and its status, and the one decision waiting on you |
| **Evidence** | Any red flag can be opened to the real source behind it: the forecast numbers against the limit, the notice text, the Slack message |
| **Action** | The proposed change is stated in one sentence, with Approve / Change / Dismiss right next to it |
| **Traceability** | After approval, the record shows who changed what, from what to what, why, and which evidence it rested on |
| **Hackathon scope** | Screens share components. We know which interactions need the real back end and which can be scripted |

## 2. Verdict

The team has **strong pieces and no single product yet.** The back end can already do the hard part: add something, propose where it goes, dry-run its effects, approve it, keep the log. But the only working UI is built around that intake step, not around the judge's story. The strongest product thinking, in Grant's prototype, is about a different project. If we demo today, a judge sees a graph of boxes and a replay bar. They don't see a flight moving and a client getting told why.

## 3. How the current screens score

✓ works · ◐ partly · ✗ missing

| | Northstar app (working) | Grant prototype (no back end) | Ryan's SVG mockups | Sharare's mockups |
| --- | --- | --- | --- | --- |
| Story / seed | East Tower facade, wind | **Harbor Street Clinic**, building design and operations | East Tower facade, wind | **Riverside MOB**, roof inspection |
| Clarity | ✗ The graph is the home screen; no next flight, no status summary. The header shows model names | ◐ Decisions view and checklist are clear, but about a clinic | ✓ Client "Next flight / Progress / Waiting on you" cards are the best answer anyone has drawn | ◐ |
| Evidence | ◐ Effects list says *why*; the source is a text string you can't open | ◐ Content previews on nodes (metric bars, quotes) | ◐ "See evidence →" links, not designed | ✓ Inputs with temperature, versions, stale reason |
| Action | ◐ Approve / Dismiss is clear, but it approves **adding information**, not **a decision**. There's no "move the flight" proposal | ✓ Decide dialog, options, compare layout, reopen / "still holds" | ✓ "Move Thursday's flight · next window Mon 8–11 →" | ◐ "Ask agent to re-check" |
| Traceability | ◐ Event log with actor, reason, effects; the reason is optional and entries aren't clickable | ◐ Per-decision history, client-safe explanations | ✓ PM timeline: before → after, by, reason, because | ✓ Version timeline with diffs |
| Runs on real data | ✓ | ✗ | ✗ | ✗ |

**The one-minute test today:** in northstar, a weather change can only be triggered with `POST /api/feeds/inject/thursday_unflyable`. The flight turns red, but nothing proposes a new date and there's no client view. **The loop breaks at "pilot approves" and "client understands".**

## 4. What is missing, most serious first

### 4.1 Blocking the demo

1. **There's no single story.** Four seeds are in play: East Tower (northstar, Ryan's mockups), 120 Broadway (monitors), Riverside MOB (Sharare), Harbor Street Clinic (Grant). Front-end work can't be checked against the back end, and judges remember one building. **Proposed:** East Tower facade survey at 120 Broadway, because it's the seed the running back end and the live monitors already use. **Open:** confirm today.
2. **The weather change → new date → approve step doesn't exist.** The most important moment has no screen and no endpoint. It needs a **decision proposal card**: "Move Flight 5 from Thu 19 to Mon 23, 8–11 am", the reason in one line, the evidence (forecast vs limit), what else moves (crew, permit window), and Approve / Pick another / Dismiss. Back end: scheduler specialist (Sharare's breakdown, item H2). Front end can start against a scripted proposal.
3. **There's no client view in any working UI.** Ryan's client SVG is the right design. It needs building, and it needs a plain-language line per change. Grant's "approve the explanation before clients see it" gate is the right safeguard, so keep it.
4. **Time is missing.** Drone work is driven by windows, lead times and the 30-day NYPD rule, but the working app has no schedule, calendar or countdown anywhere. A graph can't show "Thursday is in 5 days and unflyable". **Proposed:** a schedule strip (Ryan's PM mockup) on every role's home screen, with the authorization window and per-day weather.

### 4.2 Will confuse users and judges

5. **"Approve" means two different things.** Approving a *placement* (this Slack message belongs with Drone 4A) and approving a *decision* (fly Monday) look the same in northstar. **Proposed:** call them **"Add to project"** and **"Decide"**, and make them two different components. Only a decision gets a revision with required reason and evidence.
6. **The reason is optional.** Plan decision R4 says the reason is required for decisions, drafted by Jev and edited by the person. Without it, traceability is empty. **Proposed:** pre-fill a draft reason, and block "Decide" until it's confirmed.
7. **The evidence is shallow.** "82% · same date" and "source: weather" don't let anyone check the claim. Every flag needs an **evidence drawer**: the feed reading (per-day wind against the limit as a small chart), the source link, when it was fetched, and the version it came from (Sharare's model).
8. **Roles are a name picker, not a view.** "You are: Sam (pilot)" only changes the author name. There are three naming schemes in the docs: client / PM / pilot, basic / medium / advanced, client / team / expert. **Proposed:** the UI uses **Client · Project manager · Pilot**; the docs' levels are internal. Each role gets a different home screen (section 5).
9. **Nothing tells you what to do next.** "What's next" and the attention levels (flashing red with at most 1–2 per person, then red, amber, grey) are designed in [usecase-facade-survey.md](../Ryan/usecase-facade-survey.md) §3 but appear in no working screen. Today every blocked node pulses, so too many things pulse.
10. **The graph doesn't scale and doesn't stay still.** The force layout re-runs, labels cut off at 23 characters, there's no zoom or pan, and edge labels only show on selection. Past about 20 nodes it becomes a tangle. Grant's semantic zoom, cluster layout and quiet link styles solve this. The graph should be the **pilot's** tool, not everyone's home screen.

### 4.3 Polish we can't skip

11. **Developer chrome is on screen:** model names, Reset demo, and the replay bar taking up the top of the graph. **Proposed:** a presenter mode. The replay bar becomes a small floating remote, hidden for judges and shown for rehearsal.
12. **Slow and failed states:** ghost cards and spinners exist (good), but a failure is a 9-second toast. A live LLM call on stage takes 5–10 s. Every card needs four designed states: working / ready / failed with Retry / cached.
13. **Accessibility:** status uses colour plus a legend, and the pulse respects reduced motion (good). SVG nodes can't be reached by keyboard and have no focus style. Status needs a text or icon, not colour alone.
14. **Mobile:** the pilot is in the field. Slack covers that for the hackathon; the client view should still work at phone width, because judges open links on phones.

### 4.4 Scope to park (from Grant's prototype)

Grant's prototype has good ideas that **don't fit the drone demo**. Keep them in the prototype and out of the build for now:

- **User-defined kinds** ("Make a kind from this item"). The back end's rules depend on fixed core types (decision G2). Show a kind as a label on top of a core type, if at all.
- **The Design / Operations switch and the live-target dashboards** are post-occupancy building features, a different product.
- **Project setup wizard:** the demo opens on a seeded project, so a wizard costs time without changing the demo. Revisit after the hackathon.

**Keep from Grant:** the statement-style decision node, Compare layout, "Reviewed, still holds" / Reopen (the same idea as Sharare's **stale** flag), Share with client / approved explanations, the Ask bar, node anatomy and link styles from `node-study.html`.

## 5. Phased build (Proposed)

Each phase is **one PR** to `main`, demo-able by itself, and lines up with a back-end feature that exists or is next on the critical path. "Needs from back end" names an endpoint that exists (✓) or has to be added (＋).

### Phase 0: Foundation (today)

| | |
| --- | --- |
| Outcome | One app shell, one seed, one component kit. Nothing new for the user yet |
| Build | `web/` folder served by the northstar FastAPI as static files. No build step, plain ES modules (same as both prototypes). Design tokens and node anatomy from Grant's `node-study.html`. Role switch in the header (Client · PM · Pilot) that changes the home screen. Presenter mode |
| Needs from back end | ✓ `GET /api/state`, ✓ `GET /api/events` (SSE) |
| Done when | The app opens the East Tower project with the right header, role switch and an empty home screen per role; light and dark both work |
| Open | Framework: no-build vanilla (fast, matches existing work) vs React + React Flow (Sharare's suggestion; better graph, needs a build). **Recommendation: no-build for the hackathon** |

### Phase 1: Status at a glance (Clarity)

| | |
| --- | --- |
| Outcome | Every role sees the next flight, its status, and what's waiting on them within 5 seconds |
| Build | Status cards (next flight · progress · waiting on you), schedule strip with the authorization window and per-day weather, attention list ("What's next") with at most 2 flashing items |
| Needs from back end | ✓ `/api/state` (derive on the client first), ＋ `GET /api/summary?role=` later, ＋ flight / window dates exposed on event nodes, ✓ `GET /api/feeds` for per-day flyability |
| Done when | A new person answers "when is the next flight and is it OK?" without help |

### Phase 2: Add to project (intake, existing back end)

| | |
| --- | --- |
| Outcome | Northstar's intake and review, rebuilt with the new components |
| Build | Drop zone + chat box, ghost cards with the four states (§4.3 item 12), the **"Add to project"** review panel: type, links with reason, "If you add this" effects, Add / Edit / Dismiss |
| Needs from back end | ✓ `POST /api/intake`, ✓ `/preview`, ✓ `/approve`, ✓ `/dismiss` |
| Done when | "drone 4a needs maintenance" goes from typed to added, and Thursday's flight turns red, in under 15 s |

### Phase 3: Evidence drawer

| | |
| --- | --- |
| Outcome | Any red or amber item opens to the proof |
| Build | One evidence drawer used everywhere: the feed reading as a small chart against the limit, source link, fetched-at, the text excerpt or image, which version |
| Needs from back end | ＋ `GET /api/nodes/{id}` with source, readings and versions; ＋ feed readings per node (the `readings` / `sources` rows already exist) |
| Done when | Clicking the red flight shows "Thu 19: gusts 28 mph, limit 20 mph · Open-Meteo · 13:00" |

### Phase 4: Decide (the hero moment)

| | |
| --- | --- |
| Outcome | Weather change → the system proposes a new date → the pilot decides with a reason |
| Build | **Decision proposal card**: one-sentence proposal, options (Grant's Compare layout: Monday vs Tuesday vs wait), what else moves, evidence, reason pre-filled and required, **Decide** / Pick another / Dismiss. A presenter-mode "weather changes" button that calls the inject endpoint |
| Needs from back end | ✓ `POST /api/feeds/inject/{scenario}`, ＋ scheduler proposal (H2) as a proposed decision version, ＋ `POST /api/decisions/{id}/decide` |
| Interim | Front end can start against a scripted proposal JSON returned by the inject call |
| Done when | The one-minute story runs up to "pilot approves" with no API calls typed by hand |

### Phase 5: Decision history (Traceability, PM home)

| | |
| --- | --- |
| Outcome | The PM's timeline: each revision with by, when, before → after, reason, evidence links |
| Build | Timeline list + revision detail (Ryan's PM mockup), filters (All · Technical · Mine), stale badge with "Still holds" / Reopen |
| Needs from back end | ✓ events in `/api/state`; ＋ decision versions and stale flags from Sharare's schema (needs the branch merged and used by northstar) |
| Done when | "Why did Flight 5 move?" can be answered by clicking, with evidence |

### Phase 6: Client view

| | |
| --- | --- |
| Outcome | The same project, read-only, in plain language |
| Build | Ryan's client mockup: status cards, "Why things changed" feed, the Ask box, deliverables. The explanation-approval gate from Grant's prototype (PM approves the plain-language line before the client sees it) |
| Needs from back end | ＋ plain-language summary per decision (Jev draft, H4), ＋ `shared_with_client` flag; ◐ Ask over the graph (Q&A, H4), which can be keyword search first |
| Done when | The one-minute story runs end to end. **Demo is safe from here** |

### Phase 7: Live and Slack (after J1–J3 land)

| | |
| --- | --- |
| Outcome | Something typed in Slack appears on screen by itself |
| Build | Live arrival animation, "confirmed in Slack by Mary" attribution, notifications for the slow path |
| Needs from back end | ✓ SSE; ＋ Slack intake and confirm-in-DM (J1–J3) |

### Phase 8: Stretch

Lineage at three levels with the `as_of` slider (Sharare's mockup), replay scrubber as a timeline, the 3D graph from Grant's prototype, the rule-approval screen for the analysis loop.

### What can be scripted vs what must be real

| Interaction | For the demo |
| --- | --- |
| Intake, proposal, effects, approval, event log | **Real**: it works today |
| Weather change | Real path, triggered by a presenter button (inject) |
| Scheduler's new-date proposal | Scripted until H2 lands, then real |
| Plain-language client lines | Templated, then Jev-drafted |
| Ask box | Keyword search over nodes, then real Q&A |
| Slack | Real only if L6 (workspace) is settled today; otherwise the chat box stands in |

## 6. Decisions needed from the team

| # | Decision | Recommendation | Status |
| --- | --- | --- | --- |
| F1 | One demo story and seed | East Tower facade, 120 Broadway | Open |
| F2 | Which UI is the base | New `web/` app on the northstar API, using Grant's visual language. Northstar's `static/index.html` stays as the dev console | Open |
| F3 | Framework | No-build ES modules for the hackathon | Open |
| F4 | Role names in the UI | Client · Project manager · Pilot | Open |
| F5 | Two kinds of approval | "Add to project" vs "Decide"; only "Decide" requires a reason | Open |
| F6 | What gets parked | User-defined kinds, Design/Operations, setup wizard | Open |
| F7 | Front-end owner per phase | Grant leads; one reviewer from the back end on each PR | Open |

## 7. Not reviewed

- The live artifact linked in the team chat could not be opened from this account; this review uses the prototype files on the `grant` branch instead.
- Grant's README mentions a "front-end concepts doc" with the decision-to-dashboard contract. It isn't in the repo.
