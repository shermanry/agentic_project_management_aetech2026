# Plan: Decision Lineage Back End

_Draft for team critique · 2026-11-14 · companion to [Ryan's plan](../Ryan/plan.md)_

**How to use this doc:** each section is marked **Decided**, **Proposed** or **Open**, the same way as Ryan's plan. It goes deeper on the back end: how we capture data, keep history, and trace which inputs a decision came from.

Use case context: [NYC facade inspection workflow](docs/use-case/facade-inspection.md) (whiteboard + walkthrough)

Live mockup (3 screens: canvas, lineage, sources): https://claude.ai/artifact/8GtKS4XzxNX6XjMEfjsDrG · source files in [docs/mockups](docs/mockups)

## 1. What this part of the system does

A node-based decision log for drone work. People and agents drop nodes onto a shared canvas (sources, observations, suggestions, decisions, action items, logs). The back end:

- captures each source and keeps its full history cheaply
- turns raw drone data into short **observations** that can be searched and embedded
- records every decision as a **snapshot** that points to the exact versions of the inputs it used
- scores how much each input influenced a decision (**temperature**)
- flags a decision as **stale** when one of its inputs gets a newer version
- shows lineage at three levels of detail (simple, medium, advanced)

## 2. Principles (Proposed)

1. **Append-only.** Nothing is updated in place. A change to a source or a decision creates a new version. History comes for free and lineage stays correct.
2. **Decisions point to versions, not nodes.** If a weather node refreshes every hour, a decision from last Tuesday must still point to Tuesday's forecast. This is the main gap compared with linking to `evidence: ["n_088"]` only.
3. **Never embed raw drone data. Embed what was observed.** A 2 GB flight becomes 20–50 short text observations ("NE roof corner: possible blistering, ~2 m², confidence 0.7, image #0412"). Only those get embedded.
4. **Agents suggest, people decide.** Agent output is a suggestion or action item with status `proposed`. A reviewer accepts or dismisses it, and that response is part of the lineage.
5. **Everything runs locally** with `docker compose up`. No cloud services in the stack (decided by the team).

## 3. Capture: cheapest design that keeps full history (Proposed)

| Layer | What goes there | Where | How we keep it cheap |
| --- | --- | --- | --- |
| Raw | Photos, video, point clouds, raw emails, API responses | Local folder `./data/raw/<content-hash>` (mounted volume) | Write once. Video kept as keyframes only. |
| Version | One row per **meaningful** change to a source | Postgres `node_versions` | Content hash + change threshold: if nothing changed, skip the write |
| Semantic | Observations and summaries with embeddings | Postgres + pgvector | Embed lazily, only when lineage or an agent first needs that version |

**Rules:**

- **Hash and threshold.** A weather API polled every hour that returns the same forecast creates no new version. Only a meaningful change (e.g. rain probability ±15%, wind ±5 km/h) does. Thresholds are set per source.
- **Streams are processed before storing.** Telemetry and live readings go into a plain `readings` table with no embeddings. Only **events** (gust over a limit, geofence breach) become observation nodes.
- **Cheap model for bulk work, better model for decisions.** A small vision model writes the image captions and defect flags; the stronger model only runs the suggestion step.
- **Inbox folder for the demo.** The worker watches `./data/inbox`. Dropping a flight folder or an `.eml` file triggers capture → hash → version → summarize. A replay script stands in for real streams so the demo is the same every time.

**Freshness policy per source:** `static` (manual re-import), `periodic` (cron schedule in the worker), `on_upload` (inbox), `stream` (replay script → readings → events).

## 4. Data model (Proposed)

Fits alongside Ryan's node / edge / revision JSON. The main additions are `node_versions` and `decision_inputs`.

```sql
users(id, name)

nodes(id, kind, title, tags text[], created_by, created_at)
  -- kind: source | observation | analysis | suggestion | decision | action_item | log
  --       (+ Ryan's: document | weather | regulation | rfi | message | model | flight)

node_versions(id, node_id, version_no, content_text, metadata jsonb,
              raw_uri, content_hash, embedding vector(N) NULL,
              capture_spec_id NULL, produced_by_run_id NULL, captured_at)

capture_specs(id, source_node_id, version_no,
              instruction text,           -- plain language, written by a person
              compiled jsonb,             -- structured extraction spec made by the LLM
              approved_by, created_at)

analysis_defs(id, node_id, version_no,
              mode,                       -- generated | registered | external
              code text NULL, ref text NULL,   -- script body, or repo path / image / endpoint
              params_schema jsonb, approved_by, created_at)

analysis_runs(id, analysis_def_id, input_version_ids bigint[], params jsonb,
              code_hash, status, logs_uri, started_at, finished_at)
  -- outputs are node_versions with produced_by_run_id = this run

edges(id, from_node, to_node, type, origin, confidence, reason,
      approved bool, tags text[], created_by, created_at)
  -- type and origin as in Ryan's plan (constrains, supports, supersedes, derived_from ...)

node_roles(node_id, user_id, role)        -- owner | editor | reviewer | viewer

sources(node_id, connector, config jsonb,
        refresh_policy, cron, change_threshold jsonb, last_captured_at)
readings(source_id, ts, payload jsonb)    -- stream history, never embedded

decision_versions(id, decision_node_id, version_no, statement, rationale,
                  origin,                 -- manual | agent
                  kind,                   -- decision | suggestion | action_item
                  status,                 -- proposed | accepted | dismissed | done | superseded
                  parent_version_id, decided_at, author_id)

decision_inputs(decision_version_id, node_version_id,
                temperature float,        -- 0..1, influence on THIS decision
                influence_reason text,
                suggested_by,             -- user | agent
                accepted bool)

comments(id, node_id, user_id, body, created_at)
events(id, actor, verb, object_id, payload jsonb, at)   -- activity feed
canvas_snapshots(project_id, yjs_state bytea, saved_at)
```

**How this maps to Ryan's `revision`:** a `decision_versions` row is a revision of one decision. `parent_version_id` = `revision.parent`. `decision_inputs` replaces `evidence: [...]`, but each entry points to a **node version** and carries a temperature and a reason.

## 5. Temperature (Proposed)

Two different scores, kept separate:

| Score | Lives on | Meaning | Set by |
| --- | --- | --- | --- |
| `importance` (Ryan's) | The node | How important this item is to the project overall | AI, overridable per project |
| `temperature` | `decision_inputs` | How much this input influenced **this** decision | LLM-assessed influence × recency decay × similarity to the decision |

On the canvas, edge thickness and colour show temperature: hot ≥ 0.7, warm 0.3–0.7, cold < 0.3 (dashed).

## 6. Lineage (Proposed)

**Two ways decisions enter the system:**

1. **Manual.** A person logs a real-world decision with its timestamp. The **lineage finder** searches for similar node versions captured **before** `decided_at`, an LLM ranks them and writes `temperature` + `influence_reason`, and the person accepts or rejects each suggested input.
2. **Agent.** The decision agent is given a question and a subgraph. It drafts a suggestion with cited inputs, which waits as `proposed` until a reviewer accepts it. Accepted suggestions can become action items or feed a decision; that link is lineage too.

**Stale check (one query):** a decision version is stale if any of its `decision_inputs` points to a node version that now has a newer version. This is the strongest demo moment: "last week's suggestion is stale because today's flight shows the blister grew 40%".

**Three levels of detail.** One recursive CTE over `decision_inputs` + `edges` with parameters `max_depth`, `min_temperature`, `top_k`, `include_superseded`, `as_of`:

| Level | Depth | Filter | Shows | Typical nodes |
| --- | --- | --- | --- | --- |
| Simple | 1 | Top 3 hottest | Decision + its strongest direct inputs | ~4–5 |
| Medium | ≤ 3 | temperature ≥ 0.3 | + observations, flights, earlier suggestions | ~10–30 |
| Advanced | Full | None | + cold inputs, dismissed suggestions, superseded versions of sources and decisions | 15–50+ |

**Open:** Ryan's plan uses basic / medium / advanced for **role views** (client / PM / pilot). Proposal: each role opens lineage at its matching level by default (client → simple, PM → medium, pilot → advanced) and can switch.

**Version timeline:** an `as_of` slider on any decision steps through v1 → v2 → v3, with a diff of which inputs were added, dropped or changed temperature.

## 7. Capture instructions on source nodes (Proposed)

Each source node carries a plain-language **capture instruction** saying which part of the source matters. Examples:

- **3D model:** "Only the exterior envelope: external walls, curtain wall, windows, balconies, parapets. Ignore interiors and MEP."
- **Weather:** "Hourly wind speed, gusts, rain probability and visibility for the site, 7:00–17:00, next 5 days."
- **Email thread:** "Only messages about flight dates, permits or site access."
- **Regulations:** "Rules that apply to drone flights in Manhattan, especially temporary restrictions."

**Compile once, run every refresh.** Running an LLM over a huge model or dataset on every refresh is slow, costly and gives different results each time. Instead:

1. When a person writes or edits the instruction, the LLM **compiles** it into a structured extraction spec, such as IFC classes + property filters (`IsExternal = true`), or a list of weather fields + time window + location.
2. The person sees a **preview** of what would be captured (e.g. "212 exterior elements, 3% of the model") and approves it.
3. Every refresh runs the compiled spec **without an LLM**, so the result is the same each time and cheap to produce.

**Why it matters for the back end:**

- **Versioned like everything else.** Editing the instruction creates a new spec version and triggers a re-capture. Each `node_version` records which spec produced it, so lineage shows not only what data a decision used but which slice of the source it was.
- **Cheaper history.** The content hash is computed on the **extracted** slice. A change to the model's interior, or to weather fields we don't track, creates no new version.
- **Better embeddings.** Summaries and embeddings describe only the relevant part, so lineage search is less noisy.

## 8. Analysis nodes (Proposed)

A node type that **computes** something from other nodes and produces new nodes. Many AEC decisions rest on analysis, not raw data.

| Mode | What it is | Example |
| --- | --- | --- |
| Generated | The agent writes a Python script from a description; a person reviews it before it runs | "Find the hours in the authorized window where gusts < 20 mph and rain probability < 30%" |
| Registered | A script already in our repo, or a container image, with declared inputs and parameters | Ground sampling distance and stand-off distance from camera settings |
| External | A call to an outside tool or service | Rhino.Compute / Grasshopper, a CFD run, photogrammetry software |

**Every run is recorded for lineage:** which input **versions**, which code (hash or version), which parameters, the logs, and the output nodes it created. A decision can then cite an analysis result, and the lineage traces back through the analysis to its inputs.

**Stale propagation:** if an input to an analysis gets a new version (new forecast, revised flight plan), its outputs are flagged stale and the agent suggests a re-run. Decisions that used those outputs are flagged too.

**Running it safely, locally:** a separate `runner` container with no network access, CPU/memory/time limits and read-only inputs. Generated scripts never run without a person approving them first.

**Analyses taken from the [facade inspection use case](docs/use-case/facade-inspection.md):**

- **Flight window:** which of the authorized days and hours meet the wind, rain and visibility limits (the "only 1 of 5 days" finding).
- **Line of sight / blind spots:** which facade areas can't be seen from the chosen take-off and observation spots (trees, building geometry).
- **Coverage and camera settings:** stand-off distance, overlap and ground sampling distance for the required level of detail.
- **Metadata check:** validate and correct image metadata before processing (the separate application the team had to build).
- **Repair estimate:** defect areas from observations → repair quantities and effort.

**For the hackathon:** one generated or registered analysis is enough. **Flight window** is the best fit: it uses the weather source, its output drives the scheduling decision, and it shows stale propagation when the forecast changes.

## 9. Collaboration canvas (Proposed)

- **Yjs + `y-websocket`** for live multi-user editing: node positions, cursors, presence, selection. Snapshot to `canvas_snapshots` every few seconds.
- **Postgres is the source of truth for domain data** (nodes, versions, edges, decisions, lineage). All creates and edits go through the API, which checks roles, writes, then broadcasts.
- **Roles per node** (owner, editor, reviewer, viewer), enforced in the API. Only a reviewer or owner can accept or dismiss a suggestion.
- **No real login for the hackathon.** Seeded users and a user switcher, so two browsers can act as two people.
- Comments on nodes and an activity feed from `events`.

## 10. Local stack (Decided: local + Docker · rest Proposed)

| Service | Purpose |
| --- | --- |
| `db` | `pgvector/pgvector:pg16`; schema and seed data in `./db/init` run on first boot |
| `api` | FastAPI (following Ryan's plan): REST, lineage queries, agent endpoints, WebSocket broadcast via Postgres `LISTEN/NOTIFY` |
| `worker` | Inbox watcher, scheduled refresh (cron), stream replay, summarize + lazy embed |
| `collab` | `y-websocket` server |
| `runner` | Runs analysis scripts in isolation: no network, resource and time limits, read-only inputs |
| `web` | Canvas (React Flow suggested) and lineage view (elkjs or dagre layout) |

- Raw files live in a mounted `./data/raw` folder. No object storage needed.
- Embeddings: pin the vector dimension on day 1, since switching models means re-embedding everything (same point as Ryan's section 7).
- `docker compose down -v && docker compose up` resets the demo to a clean seeded state.

## 11. Demo flow (Proposed)

1. Two browsers, two users on one canvas.
2. Dev (pilot) drops Flight 03 into the inbox → observations appear as child nodes.
3. The agent compares flights, checks the weather and the schedule, and suggests an action ("Inspect NE corner Thursday before the rain") with inputs and temperatures.
4. Mara (reviewer) accepts it live in the other browser → it becomes an action item and feeds decision D-014.
5. A new email arrives (the roofer moves to 7:00) → D-014 v2 is flagged **stale**.
6. Open lineage: simple → medium → advanced, then move the timeline back to see the earlier versions and the input that made v2 stale.

The mockup uses a roof-inspection story. The same flow works for Ryan's wind / flight-scheduling story; only the seed data changes.

## 12. In and out of scope

**In:** the canvas with live collaboration, roles, comments, and the activity feed · capture with hashing and versions · capture instructions on at least one source (weather or 3D model) · one analysis node (flight window) · observations from drone images · agent suggestions with cited inputs · stale flag · lineage at three levels with the version timeline · seed data (3 flights, weather, email, schedule, 2–3 users).

**Out:** real authentication, live photogrammetry, real streams (replay instead), storage tiering and retention, a full tags UI beyond filter chips.

## 13. Open questions

1. **Use case for the demo:** inspection (defects) or construction monitoring (progress against schedule)? Or Ryan's flight-scheduling story?
2. **Simple / medium / advanced:** role views, lineage levels, or both (proposal in section 6)?
3. **Suggestion model:** local only, or the hosted OpenRouter model (Jev) for the agent call? Local 7–8B models are weaker at multi-input reasoning.
4. **What counts as a decision version:** every edit, or only edits with a stated reason?
5. **Change thresholds:** what counts as a meaningful change for each source (weather, schedule, telemetry)? This needs answers from the drone experts.
6. **Branches:** does the demo need "what if" branches, or is a linear version history enough?
7. **3D model format:** IFC, Revit export, or a mesh from photogrammetry? This decides how capture instructions compile (property filters vs. geometric selection).
8. **Existing scripts:** which analysis scripts or Grasshopper definitions does the team already have that we could register instead of generating?
9. **Generated code:** who on the team reviews and approves an agent-written analysis script before it runs?
