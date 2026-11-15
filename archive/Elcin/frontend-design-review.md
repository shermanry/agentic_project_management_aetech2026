# Front end: product design review and phased build plan

_Draft for team critique · 2026-11-14 · reviews [Ryan/northstar](../../src/northstar/README.md) (the working app), Grant's prototype (branch `grant`), Sharare's mockups (branch `sharare/decision-engine`) and Ryan's SVG mockups ([Ryan/plan.md](../../docs/plan.md) §5)_

**How to use this doc:** same convention as the other plans. Each item is marked **Decided**, **Proposed** or **Open**. Section 5 is the build plan. Each phase is one PR, reviewed before it goes into `main`.

## 1. The test we design against (Proposed)

This is not a scheduling tool. Scheduling is one specialist that could sit on top. The product is **a living decision record for a project**: anything that arrives becomes a node, the system shows where it fits and which decisions it puts in question, a person decides with a reason, and anyone can later trace why. The drone facade survey is the worked example, not the product.

A judge watches for three minutes. The core story has to land in **under one minute**:

> **New information arrives → the system shows which decision it affects → the owner re-decides with a reason and evidence → a stakeholder can see why it changed.**

The trigger can be anything: a rule change, a client email, a Slack remark, a marked-up drawing, a forecast. The worked example below uses the airspace rule change from the whiteboard (replay step 4), which reopens the permit package.

Every screen is scored on five questions:

| Question | What "good" looks like |
| --- | --- |
| **Clarity** | Within 5 seconds of opening, you can name the project, what changed since you last looked, and the decision waiting on you |
| **Evidence** | Any flag can be opened to the real source behind it: the notice text, the email, the Slack message, the feed reading |
| **Action** | The proposed change is stated in one sentence, with Approve / Change / Dismiss right next to it |
| **Traceability** | After approval, the record shows who changed what, from what to what, why, and which evidence it rested on |
| **Hackathon scope** | Screens share components. We know which interactions need the real back end and which can be scripted |

## 2. Verdict

The team has **strong pieces and no single product yet.** The back end can already do the first half of the story: add something, propose where it goes, dry-run what it would reopen, approve it, keep the log. **The second half, re-deciding and explaining, has no screen.** The strongest product thinking about decisions is in Grant's prototype, but it is about a different project and has no back end. If we demo today, a judge sees a graph of boxes turn amber. They don't see a decision being made again, or anyone told why.

### Standing out from similar pitches

Another team has pitched a similar idea, so the first minute has to show what's distinct, not what's common. "AI tags your files and draws a graph" and "AI finds a better date" are table stakes. What only we have, if the front end shows it:

1. **Propose, then approve, with consequences shown first.** Nothing enters the record silently; you see what it would reopen before you accept it (northstar's dry run).
2. **Decisions remember what they rested on.** Each decision points at the exact versions of its inputs, so when an input changes the decision is flagged stale, with the reason (Sharare's lineage layer).
3. **One record, three readings.** The pilot sees the graph, the PM sees the timeline, the client sees plain-language explanations that a person approved first (Grant's sharing gate).
4. **Anything can come in.** A Rhino model, a marked-up PDF, a Teams screenshot or a pasted thread (Minh's converter).

Each phase below should make at least one of these visible.

## 3. How the current screens score

✓ works · ◐ partly · ✗ missing

| | Northstar app (working) | Grant prototype (no back end) | Ryan's SVG mockups | Sharare's mockups |
| --- | --- | --- | --- | --- |
| Story / seed | East Tower facade, wind | **Harbor Street Clinic**, building design and operations | East Tower facade, wind | **Riverside MOB**, roof inspection |
| Clarity | ✗ The graph is the home screen; no "what changed / what's waiting on you" summary. The header shows model names | ◐ Decisions view and checklist are clear, but about a clinic | ✓ Client "Waiting on you" and "Why things changed" are the best answer anyone has drawn | ◐ |
| Evidence | ◐ Effects list says *why*; the source is a text string you can't open | ◐ Content previews on nodes (metric bars, quotes) | ◐ "See evidence →" links, not designed | ✓ Inputs with temperature, versions, stale reason |
| Action | ◐ Approve / Dismiss is clear, but it approves **adding information**, not **a decision**. A reopened decision has no way to be decided again | ✓ Decide dialog, options, compare layout, reopen / "still holds" | ◐ "What's next" suggestions, not designed as a decision | ◐ "Ask agent to re-check" |
| Traceability | ◐ Event log with actor, reason, effects; the reason is optional and entries aren't clickable | ◐ Per-decision history, client-safe explanations | ✓ PM timeline: before → after, by, reason, because | ✓ Version timeline with diffs |
| Runs on real data | ✓ | ✗ | ✗ | ✗ |

**The one-minute test today:** in northstar, replay step 4 brings in "Airspace approval moves to DHS". It's proposed, linked to the permit package, and approving it turns the package amber ("re-opened"). That half works well. Then the story stops: there's no screen to re-decide the permit package, no required reason, no way to see which inputs the old decision rested on, and no client view. **The loop breaks at "owner re-decides" and "stakeholder sees why".**

## 4. What is missing, most serious first

### 4.1 Blocking the demo

1. **There's no single story.** Four seeds are in play: East Tower (northstar, Ryan's mockups), 120 Broadway (monitors), Riverside MOB (Sharare), Harbor Street Clinic (Grant). Front-end work can't be checked against the back end, and judges remember one project. **Proposed:** the facade survey from the whiteboard (East Tower, 120 Broadway). It's the seed the running back end uses, and its permit-package loops are decisions being revisited, which is exactly our point. **Open:** confirm today.
2. **Re-deciding doesn't exist.** The system can say "this decision is re-opened", but nothing lets the owner decide it again. It needs a **decision card**: the question, the current answer and what it rested on, what changed (the new input, highlighted), options (Grant's Compare layout), a reason that Jev drafts and the person confirms, then **Decide** / **Still holds** / Dismiss. Either answer becomes a new version that cites its inputs. Proposals can come from Jev's "What's next" or a specialist later; none is required for the demo.
3. **There's no stakeholder view in any working UI.** Ryan's client SVG is the right design. It needs building, and it needs a plain-language line per change. Grant's "approve the explanation before clients see it" gate is the right safeguard, so keep it.
4. **The lineage is invisible.** Our most distinct idea, that a decision knows which versions it rested on and goes stale when one changes, isn't on any working screen. Sharare's mockup shows it; northstar doesn't use those tables yet. Without it, we look like the other "AI graph" pitches.

### 4.2 Will confuse users and judges

5. **"Approve" means two different things.** Approving a *placement* (this notice belongs with the permit package) and approving a *decision* (revise and resubmit the package) look the same in northstar. **Proposed:** call them **"Add to project"** and **"Decide"**, and make them two different components. Only a decision gets a revision with required reason and evidence.
6. **The reason is optional.** Plan decision R4 says the reason is required for decisions, drafted by Jev and edited by the person. Without it, traceability is empty. **Proposed:** pre-fill a draft reason, and block "Decide" until it's confirmed.
7. **The evidence is shallow.** "82% · same date" and "source: Federal Register" don't let anyone check the claim. Every flag needs an **evidence drawer**: the excerpt or image that matters, the source link, when it was captured, and the version it came from (Sharare's model). For a live feed, a small chart of the reading against its limit.
8. **Roles are a name picker, not a view.** "You are: Sam (pilot)" only changes the author name. There are three naming schemes in the docs: client / PM / pilot, basic / medium / advanced, client / team / expert. **Proposed:** the UI uses **Client · Project manager · Pilot**; the docs' levels are internal. Each role gets a different home screen (section 5).
9. **Nothing tells you what to do next.** "What's next" and the attention levels (flashing red with at most 1–2 per person, then red, amber, grey) are designed in [usecase-facade-survey.md](../../docs/usecase-facade-survey.md) §3 but appear in no working screen. Today every blocked node pulses, so too many things pulse.
10. **Deadlines and lead times have no home.** The whiteboard's pain is time (the 30-day permit rule, a 5-day window), but no working screen shows a due date or countdown. A small "due soon" list on each home screen is enough; a full schedule view is not our product.
11. **The graph doesn't scale and doesn't stay still.** The force layout re-runs, labels cut off at 23 characters, there's no zoom or pan, and edge labels only show on selection. Past about 20 nodes it becomes a tangle. Grant's semantic zoom, cluster layout and quiet link styles solve this. The graph should be the **pilot's** tool, not everyone's home screen.

### 4.3 Polish we can't skip

12. **Developer chrome is on screen:** model names, Reset demo, and the replay bar taking up the top of the graph. **Proposed:** a presenter mode. The replay bar becomes a small floating remote, hidden for judges and shown for rehearsal.
13. **Slow and failed states:** ghost cards and spinners exist (good), but a failure is a 9-second toast. A live LLM call on stage takes 5–10 s. Every card needs four designed states: working / ready / failed with Retry / cached.
14. **Accessibility:** status uses colour plus a legend, and the pulse respects reduced motion (good). SVG nodes can't be reached by keyboard and have no focus style. Status needs a text or icon, not colour alone.
15. **Mobile:** people in the field use Slack for the hackathon; the stakeholder view should still work at phone width, because judges open links on phones.

### 4.4 Scope calls on Grant's prototype

Grant's prototype is domain-neutral (a clinic design project), which is a point in its favour: it shows the record isn't only for drones. Calls to make:

- **User-defined kinds** ("Make a kind from this item"). Good for generality, but the back end's rules depend on fixed core types (decision G2). **Proposed:** a kind is a label on top of a core type, so both work. **Open.**
- **Design / Operations switch and live-target dashboards.** "A missed target sets the decision to needs review" is the same idea as a stale decision, applied after handover. Strong for the story "decisions stay alive", but costly to build. **Proposed:** park it for the build, and mention it in the pitch.
- **Project setup wizard:** the demo opens on a seeded project, so a wizard costs time without changing the demo. Revisit after the hackathon.
- **Showing generality on stage:** **Proposed:** one 10-second beat at the end, opening a second seeded project of a different kind (Grant's clinic) in the same app, to show the record isn't a drone tool.

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
| Outcome | Every role sees what changed since they last looked, which decisions are open or reopened, and what's waiting on them, within 5 seconds |
| Build | Home cards per role (changed since you looked · decisions waiting on you · due soon), attention list ("What's next") with at most 2 flashing items |
| Needs from back end | ✓ `/api/state` (derive on the client first), ＋ `GET /api/summary?role=` later, ＋ `due` / `lead_time_days` exposed on nodes (they're in the schema) |
| Done when | A new person answers "what needs my decision, and why now?" without help |

### Phase 2: Add to project (intake, existing back end)

| | |
| --- | --- |
| Outcome | Northstar's intake and review, rebuilt with the new components |
| Build | Drop zone + chat box, ghost cards with the four states (§4.3 item 12), the **"Add to project"** review panel: type, links with reason, "If you add this" effects, Add / Edit / Dismiss |
| Needs from back end | ✓ `POST /api/intake`, ✓ `/preview`, ✓ `/approve`, ✓ `/dismiss` |
| Done when | A pasted notice ("airspace approval moves to DHS") goes from pasted to added, and the permit package shows as reopened, in under 15 s. A dropped file (PDF or Rhino model) shows its first guess straight away |

### Phase 3: Evidence drawer

| | |
| --- | --- |
| Outcome | Any red or amber item opens to the proof |
| Build | One evidence drawer used everywhere: the excerpt, image or markup region that matters, source link, captured-at, which version. A small chart for feed readings |
| Needs from back end | ＋ `GET /api/nodes/{id}` with source, chunks and versions; the converter's `locator` lets the drawer open the right page, view or layer |
| Done when | Clicking the reopened permit package shows the DHS notice text, its link and date, and which version of the package it affects |

### Phase 4: Decide (the hero moment)

| | |
| --- | --- |
| Outcome | A reopened decision is decided again, with a reason, and the new version cites what it rested on |
| Build | **Decision card**: question, current answer and its inputs, what changed (the new input highlighted), options (Grant's Compare layout), reason drafted by Jev and confirmed by the person, **Decide** / **Still holds** / Dismiss. The old version stays in the history |
| Needs from back end | ＋ decision versions with cited inputs (Sharare's `decision_versions` / `decision_inputs`), ＋ `POST /api/decisions/{id}/decide`, ＋ a Jev-drafted reason and options |
| Interim | Front end can start against a scripted decision JSON for the permit package |
| Done when | The one-minute story runs up to "owner re-decides", with no API calls typed by hand |

### Phase 5: Decision history and lineage (Traceability, PM home)

| | |
| --- | --- |
| Outcome | The PM's timeline: each version with by, when, before → after, reason and evidence links, plus a stale flag when an input moved on |
| Build | Timeline list + version detail (Ryan's PM mockup), filters (All · Technical · Mine), stale badge with "Still holds" / Reopen, lineage at the **simple** level (the decision and its 3 hottest inputs, from Sharare's mockup) |
| Needs from back end | ✓ events in `/api/state`; ＋ decision versions, stale flags and `lineage(version, simple)` from Sharare's schema (needs the branch merged and used by northstar) |
| Done when | "Why did the permit package change?" can be answered by clicking, with evidence, and a stale decision says which input made it stale |

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

Lineage at medium and advanced levels with the `as_of` slider (Sharare's mockup), replay scrubber as a timeline, the 3D graph from Grant's prototype, a second project of a different kind (§4.4), the rule-approval screen for the analysis loop. Specialists such as a scheduler plug in here as proposers of decision versions; they don't need their own screens.

### What can be scripted vs what must be real

| Interaction | For the demo |
| --- | --- |
| Intake, proposal, effects, approval, event log | **Real**: it works today |
| The triggering change (rule notice, email, Slack line) | Real path: replay step or pasted text |
| Options and drafted reason on the decision card | Scripted until the Jev call lands, then real |
| Stale flag and lineage | Real once Sharare's tables are used; the seed already has stale decisions |
| Plain-language client lines | Templated, then Jev-drafted |
| Ask box | Keyword search over nodes, then real Q&A |
| Slack | Real only if L6 (workspace) is settled today; otherwise the chat box stands in |

## 6. Decisions needed from the team

| # | Decision | Recommendation | Status |
| --- | --- | --- | --- |
| F1 | One demo story and seed | The whiteboard facade survey (East Tower, 120 Broadway), told as a decision record, not a schedule. Trigger: the airspace rule change | Open |
| F1b | What we lead with against the similar pitch | Decisions that remember their inputs and go stale, shown in the first minute (§2) | Open |
| F2 | Which UI is the base | New `web/` app on the northstar API, using Grant's visual language. Northstar's `static/index.html` stays as the dev console | Open |
| F3 | Framework | No-build ES modules for the hackathon | Open |
| F4 | Role names in the UI | Client · Project manager · Pilot | Open |
| F5 | Two kinds of approval | "Add to project" vs "Decide"; only "Decide" requires a reason | Open |
| F6 | What gets parked | User-defined kinds, Design/Operations, setup wizard | Open |
| F7 | Front-end owner per phase | Grant leads; one reviewer from the back end on each PR | Open |

## 7. Not reviewed

- The live artifact linked in the team chat could not be opened from this account; this review uses the prototype files on the `grant` branch instead.
- Grant's README mentions a "front-end concepts doc" with the decision-to-dashboard contract. It isn't in the repo.
