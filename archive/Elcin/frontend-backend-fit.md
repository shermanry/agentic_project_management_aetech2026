# Front end on the existing back end: fit, conflicts and what to decide

_Product review · 2026-11-14 · companion to [frontend-design-review.md](frontend-design-review.md). Checked against `main` at `76cfb5e`, `converter` at `dac4fa8` and `sharare/decision-engine` at `d1d0b9d`_

**Question:** if we build the phased front end on the back end we already have (the northstar app, Sharare's schema and Minh's converter), what fits, what conflicts, and what does each phase cost?

## 1. Bottom line

- **Phases 0 to 2 need no back-end change.** They can start today.
- **Phase 3 (evidence) needs one read endpoint.**
- **Phases 4 and 5 (Decide, history and lineage) are blocked by a product decision, not by code.** Right now the system has **two different meanings of "this decision is affected"**, and the UI can only show one.
- **The database is further ahead than the app.** Sharare's schema already has decision versions, cited inputs, a stale view, role view levels and a rule that a decided version must have a reason. Northstar uses almost none of it.

| Phase | Fit with today's back end | Back-end work | Who |
| --- | --- | --- | --- |
| 0 Foundation | ✓ | Mount `web/` before the `/` catch-all in `app.py` | Front end |
| 1 What changed / waiting on you | ◐ | Select `due`, `lead_time_days`, `valid_from/to` in `store.nodes()` and seed them (they exist in the schema) | Ryan, S |
| 2 Add to project | ✓ | None | Front end |
| 3 Evidence drawer | ✗ | `GET /api/nodes/{id}`: versions, chunks with `locator`, source link, converter package | Ryan, M |
| 4 Decide | ✗ | Conflicts C1–C3 below, then `POST /api/decisions/{id}/decide` | Ryan + Sharare, M |
| 5 History and lineage | ✗ | Same as Phase 4, plus `lineage(version, 'simple')` | Sharare, S–M |
| 6 Stakeholder view | ✗ | Conflict C4: visibility and plain-language lines | Ryan, M |
| 7 Live and Slack | ◐ | SSE works; Slack not started (L6 open) | Ryan |

## 2. Conflicts

### C1. Two meanings of "this decision is affected" (blocks Phases 4–5)

| | Northstar today | Sharare's lineage layer |
| --- | --- | --- |
| Mechanism | `effects.py` rules run on approval and write an `attention_items` row with `effect:reopened` (or `at_risk`, `blocked`) | A decision version cites exact input **versions**; `stale_decisions` lists decisions whose cited input now has a newer version |
| Triggered by | A **new node** linked to the decision (the DHS notice) | A **new version of an existing node** (forecast v2, package v2) |
| Clears when | Someone clicks Mark resolved, or a superseding item arrives | The decision gets a new version that cites the current inputs |
| Says why | One-line rule reason | Which input changed, from which version to which |
| Used by the app | Yes | No: northstar writes version 1 of each node and never writes `decision_versions` |

**Why it matters for the product:** our main differentiator (decisions remember what they rested on and go stale) is the mechanism the app *doesn't* run. If the UI shows "reopened" from attention items, a judge never sees lineage. If it shows "stale", nothing in the live app ever turns stale.

**Proposed:** keep `effects.py` for the **preview** ("if you add this, the permit package would be reopened"), because it's fast and explainable. **On approval,** write the effect as lineage instead of a flag: a new `decision_versions` row on the affected decision with `status = ready` and `change_kind = inputs_changed`, citing the new node's version. The decision card (Phase 4) then reads `decision_current` and `decision_proposals`; the history (Phase 5) reads versions. Attention items stay for *who to tell*, not for the state.

**Decide by:** Ryan + Sharare, today. Everything in Phases 4–5 waits on this.

### C2. Seed decisions have no versions or inputs (blocks Phase 5)

Northstar's `seed.py` creates decisions such as "Flight plan v3" and "Permit date" as nodes with `state = decided`, but no `decision_versions` or `decision_inputs`. Sharare's `002_seed.sql` has a believable decision history, but it's a **different seed** that northstar doesn't load. With today's data, the lineage view would be empty.

**Proposed:** one seed. Port the decision history from `002_seed.sql` into `seed.py` (v1 of each decision with 2–4 cited inputs and a reason). **Decide:** which file is the source of truth, `seed.py` or `002_seed.sql`.

### C3. Approve means one thing in the API (Phase 4)

There's one write path, `POST /api/items/{id}/approve`, and its event verb is `candidate.confirmed`. The schema already separates the two approvals: `approvals.subject_type` has `candidate` and `decision_version`, and `decision_versions` refuses a `decided` row without a rationale. The API just doesn't use the second one yet.

**Proposed:** add `POST /api/decisions/{id}/decide` with `{statement, rationale, inputs[], by}`. In one transaction it writes a node version, a `decision_versions` row (`decided`), its `decision_inputs`, an `approvals` row (`decision_version`), a `decision.decided` event, and closes the decision's open attention items. This matches front-end decision F5 ("Add to project" vs "Decide") with no schema change.

### C4. Nothing in the data says what a client may see (blocks Phase 6)

- Attention levels are written for `pilot` and `pm` only, never `client`.
- There's no visibility flag on nodes, events or decisions. Event payloads mix internal detail (proposer model, chain, raw reason) with what could be shared.
- `project_members.view_level` (basic / medium / advanced) exists in the schema but northstar never fills it; roles come from the hard-coded `seed.PEOPLE` list.

**Proposed:** a `client_line` (plain-language sentence) and a `shared` flag on each decision version, written when the PM approves the explanation (Grant's sharing gate). The client view reads only shared decision versions, never raw events. Roles come from `project_members`.

### C5. The replay and hand-made decisions fight each other (demo risk)

The replay rebuilds the graph from the seed plus cached steps when you press **Back**, which wipes anything done by hand. The replay steps only know how to *add information*; none of them *decide*. If the hero moment is "the owner re-decides" (Phase 4), either:

- (a) add a replay step type `decide` with a cached decision, or
- (b) do the decision by hand live, and never press Back after it.

**Proposed:** (a). It keeps the demo repeatable. **Decide:** Ryan.

### C6. Converter scope narrowed (`dac4fa8`, not yet on main)

Minh's latest commit makes the converter **extract only**: no node types, importance, relevance links or accept step. Only `part_of` / `contains` links remain, and a markup records what it was drawn on as `metadata.markup.drawn_on`.

- **Doesn't break northstar.** I checked: `agent.understand(out, pid, prompt=)` keeps its signature, agent chunks still carry `meta.suggested_by = "agent:…"`, `manifest.agent.model` is still there, and northstar never read `marks_up` or `needs_decision`.
- **It does fit the product.** Jev in northstar becomes the only thing that places and links, which matches "Add to project".
- **Gap it opens:** a client markup on a Rhino view no longer links to the model anywhere. Northstar should turn `drawn_on` into a `marks_up` / `about` edge in the proposal, or the markup → model story is lost.
- **Product overlap:** the converter has its own drag-and-drop UI on port 8765. That's a third intake screen. **Proposed:** a developer tool only; users drop files in the main app.

## 3. Smaller mismatches

| # | Mismatch | Proposed fix |
| --- | --- | --- |
| M1 | `/api/state` returns everything in one blob, re-fetched on every SSE message | Fine for the demo. Add `GET /api/nodes/{id}` for detail; keep the blob for the canvas |
| M2 | Node `status` is computed: an open attention flag overrides the node's state. The UI can't tell "decided but flagged" from "reopened" | After C1, show the state from the decision version and the flag as a separate badge |
| M3 | Event verbs (`candidate.confirmed`, feed verbs) carry no "is this a decision" signal | Add `decision.*` verbs (C3); the history filters on them |
| M4 | Evidence is `data.source` as a string; the converter package id is kept on the proposal but not exposed per node | Expose `package_id` and serve `manifest` / `chunks` through `GET /api/nodes/{id}` |
| M5 | `app.mount("/", StaticFiles(...))` catches every path | Mount `web/` at `/app` (or before `/`), and keep northstar's page as the dev console |
| M6 | Three branches with front-end-adjacent work are unmerged (`grant`, `sharare/decision-engine`, `converter`) | Merge all three before Phase 3. The vendored schema in northstar is **identical** to Sharare's (only a header comment differs), so merging her branch is low risk |
| M7 | One project, no login, "You are" dropdown | Fine for the hackathon; the role switch drives the view, not permissions |

## 4. What I'd ask the team to decide today

| # | Decision | Owner | Unblocks |
| --- | --- | --- | --- |
| B1 | C1: one meaning of "affected". Preview with effects, record as decision versions | Ryan + Sharare | Phases 4, 5 |
| B2 | C2: one seed file, with decision history | Ryan + Sharare | Phase 5, the demo |
| B3 | C3: add the decide endpoint | Ryan | Phase 4 |
| B4 | C4: shared flag and client line on decision versions | Ryan + front end | Phase 6 |
| B5 | C5: replay step that decides | Ryan | A repeatable demo |
| B6 | M6: merge `grant`, `sharare/decision-engine`, `converter` | Branch owners | Phase 3 onward |

## 5. Suggested order of work

1. **Now, in parallel:** front end builds Phases 0–2 on today's API. Back end settles B1–B2 and merges the branches (B6).
2. **Next:** `GET /api/nodes/{id}` and the decide endpoint (B3). Front end builds Phase 3, then Phase 4 against a stub of the decide endpoint.
3. **Then:** lineage read (`simple` level) and the decide replay step (B5). Front end builds Phase 5.
4. **Last before rehearsal:** client line and shared flag (B4), then Phase 6.

**Unknown that changes this plan:** how much time is left before judging. If it's under a day, cut Phase 3 to a source link plus excerpt, and do Phase 5 with the `simple` lineage level only.
