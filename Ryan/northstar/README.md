# North star MVP: add something, see where it goes, approve it

The one interaction from [plan.md](../plan.md), section 1, working end to end:

1. **Add:** drop files, paste, or type a note ("drone 4a needs maintenance").
2. **Propose:** the system works out the node type, which existing nodes it connects to, and what it would affect.
3. **Explore:** the proposal appears on the graph as a dashed ghost node; nodes it would change are outlined in red.
4. **Approve, edit or dismiss:** approving adds the node, applies the effects and records a revision with its source and reason.

## Replay mode

The bar above the graph steps through the whole project from an **empty graph**, one thing at a time:

1. **Setup (13 presses):** the project's own nodes are added one per press, in the order of `seed.py`: the site, the drones, the flight plan, the wind limit, the permit package, the flight, and so on, each bringing its links to what is already there. The last setup press connects the live data feeds.
2. **The story (7 steps, 2 presses each):** notice to proceed, site visit findings, insurance delay, the airspace rule change, one flyable day, "drone 4a needs maintenance", and the image metadata problem. The first press brings the item in (it runs through the real pipeline and shows as a proposed placement with its effects); the second, labelled **Approve**, approves it.

- **Forward / Back** move one press at a time; left and right arrow keys do the same. Back goes all the way to the empty project.
- **⏮** jumps to the empty project. **Skip setup ⏭** (shown during setup) adds the rest of the project's own nodes at once.
- **Reset demo** returns to "the project is set up", just before the story.
- API: `POST /api/replay/forward`, `/api/replay/back`, `/api/replay/goto?to=start|setup`. `replay` in `/api/state` carries `pos`, `total`, `setup_total` and a ready-made `caption` (title and story) for any UI.

The story steps are a reading of the whiteboard and should be checked by the drone experts. The first time a story step runs it is live (about 5 seconds for Jev); its approved proposal is then cached in the data folder, so going back and forward again is instant and identical. **Run through it once before a demo.** Back rebuilds the graph from scratch, which also wipes anything added by hand during the replay. While the replay is still in setup, the live feeds are held back so they don't add nodes out of order.

## Ask the project

The box under the graph answers questions from what is in the graph, and shows what it used.

- **What is searched:** every node's summary card, the full text of dropped documents (each page or section of a converted file is embedded when the node is approved), and the current flags on the graph ("Flight 5 is at risk because…").
- **How:** the question is embedded, pgvector returns the nearest chunks, and Jev answers from those numbered sources only, quoting the words it relied on. If the sources don't contain the answer it says so.
- **Highlighting:** the nodes used light up on the graph with their source numbers and everything else dims. The panel lists each source with its page and the quoted words highlighted. Clicking a number or a node jumps to that source.
- Questions and answers are not saved to the graph.

Limits: at most 12 sources reach Jev, so a fact buried in a long document can still be missed, and documents added before this feature are indexed in the background at startup. Images inside documents are not searched.

## Querying the graph (for other features to build on)

Three read-only endpoints. None of them calls a language model.

**`GET /api/search`**: find nodes and passages.

| Parameter | Meaning |
| --- | --- |
| `q` | Free text. Matched two ways and fused: by meaning (pgvector over every node card and document passage) and by keywords (Postgres full-text, any of the words). Leave empty to just list nodes, newest first |
| `type` | Comma-separated node types, e.g. `decision,blocker` |
| `owner` | Owner name, e.g. `Mary` |
| `since` | ISO date or timestamp; nodes created on or after it |
| `k` | Number of nodes back (default 10, max 50) |
| `passages` | Passages per node (default 3, max 10) |

Each result has the node (id, title, type, status, owner, summary, tags), a score, which side matched (`meaning`, `keyword`), and its best passages with their locator (page, sheet, view…), text, and a keyword `snippet` with matches wrapped in `[[ ]]`. If the embedding server is unreachable it falls back to keywords (`"mode": "keyword"`).

```bash
curl -G localhost:8100/api/search --data-urlencode "q=application fee" --data-urlencode "type=document"
```

**`GET /api/nodes/{id}`**: everything about one node: its text and source, its passages (paged with `limit` and `offset`), links in both directions with the neighbour's title and status, open flags on it, what it has flagged on other nodes, and its history. This is what an evidence drawer needs.

**`GET /api/nodes/{id}/neighbours?direction=&depth=`**: walk the graph in the database (one recursive query). `direction=affects` returns what would be hit if this node changed, `rests_on` what it depends on, `any` the plain neighbourhood. `depth` 1 to 6. Each node comes back once, at its shortest distance, with the path.

`/api/ask` uses the same hybrid search, then has Jev answer from the top sources.

## Rules and the analysis loop (only when you ask)

The **Rules** button in the header opens the rules view. **Suggest rules** runs the analysis loop once: it sends the graph and the decision history to an Opus-class model (`ANALYSIS_MODEL`, default `anthropic/claude-opus-5.5` via OpenRouter) and gets back at most three rules for what the built-in effects missed. It never runs on a schedule or by itself, and it asks for confirmation first (about 20 to 60 seconds and $0.05 to $0.30 per run).

- Each suggestion is a small JSON rule ("when a blocker is linked to a deliverable tagged photogrammetry, mark the linked events as *check capture settings*"), shown in plain words with the model's reason and what it would have caught.
- **Dry run:** every suggestion is replayed against what is already in the project. Clicking it outlines on the graph the nodes it would have flagged that the built-in rules did not.
- **Approve** makes it live: from then on `effects.py` applies it after the built-in rules, for approvals and live feeds alike, and every effect it causes names the rule. **Dismiss** (with a reason) and **Retire** keep it on record so the next run doesn't suggest it again.
- Every run, approval and dismissal is in the decision history; runs are also in the `runs` table with tokens and cost.

On the whiteboard replay, one run (19 s, $0.06) suggested: re-open decisions built on a contradicted feed, flag the next capture flight when processing is blocked, and check the client deadline when a deliverable is blocked.

## How it works

```
drop / paste / chat
   └─ converter (Minh/converter)     file -> text, images, metadata
   └─ embeddings (api/embeddings.py) nearest existing nodes  +  exact name matches ("drone 4a" -> Drone 4A)
   └─ Jev via OpenRouter             type, title, summary, tags, links with a reason and confidence
   └─ effects.py (plain code)        dry run: what gets blocked, put at risk or re-opened, and who to notify
   └─ proposal -> user reviews -> approve -> node + edges + status changes + one revision in the event log
```

- **Fast path:** text, images, PDFs, emails. Measured on Ryan's M4 Air once warm: about 5 to 10 seconds, almost all of it the Jev call (convert and embed are under a second).
- **Slow path:** 3D models, video, audio, unknown formats, or anything Jev says is too thin to judge. A first guess is shown straight away ("agent is reading it"), then the converter's vision agent reads the file and Jev re-proposes. The sample Rhino model took about 34 seconds.
- **Nothing is saved until approved.** Editing the type or links in the review panel re-runs the dry run.

| File | What it does |
| --- | --- |
| `app.py` | FastAPI routes, live updates to the browser (server-sent events) |
| `pipeline.py` | Intake: convert, match, ask Jev, compute effects; fast and slow paths |
| `effects.py` | The dry run. Rules are plain code for now; the plan is JSON rules written by the analysis loop |
| `store.py` | Postgres + pgvector on the team's shared schema: nodes, versions, card vectors, aliases, edges, approvals, events, attention items |
| `db/001_schema.sql` | Vendored copy of Sharare's decision-engine schema (branch `sharare/decision-engine`, commit d1d0b9d). Delete once that branch is merged and mount hers instead |
| `db/020_search.sql` | Keyword-search and edge indexes, applied at every startup |
| `db/010_northstar.sql` | One extra table, `intake_items`: things being processed or waiting for review |
| `qa.py` | Question answering over the graph with cited sources |
| `replay.py` | The replay scenario and the Back / Forward logic |
| `livefeeds.py` | Runs the monitors, maps their events to feed nodes, ripples bad news, clears good news, sends discoveries to intake; demo scenarios |
| `analysis.py` | The user-triggered analysis loop: context, prompt, validation, dry run, stored proposals |
| `seed.py` | Example project: East Tower facade survey. Placeholder details |
| `llm.py` | OpenRouter call that must return one JSON object |
| `static/index.html` | The canvas UI, no build step |

## Run it

Needs the repo-root `.env` (see `.env.example`) and Docker.

**Everything in Docker** (tested with Colima on an M4 Mac):

```bash
docker compose -f Ryan/northstar/docker-compose.yml up --build
```

Then open http://localhost:8100. The app container reaches the EmbeddingGemma server on the host at `host.docker.internal:8000`; set `LOCAL_EMBEDDING_URL_DOCKER` to point somewhere else.

**App on your machine, Postgres in Docker** (faster to iterate; needed today for full file conversion):

```bash
docker compose -f Ryan/northstar/docker-compose.yml up -d db
cd Ryan/northstar
uv venv --python 3.12
uv pip install -r requirements.txt -r ../../Minh/converter/requirements.txt
.venv/bin/uvicorn app:app --port 8100
```

- Postgres listens on host port **5433** (user, password and database are all `drone`), so it doesn't clash with Sharare's on 5432.
- The app creates the schema itself if the database is empty, so any Postgres 16 with pgvector works: set `DATABASE_URL`.
- **Converter:** file conversion uses Minh's package at `Minh/converter`, found automatically (override with `CONVERTER_PATH`). The Docker image installs its requirements too, but the converter has not been tested inside the image (`rhino3dm` may need a build step on ARM Linux).
- On the Mac that hosts the embedding server, put `LOCAL_EMBEDDING_URL=http://localhost:8000` in front of the uvicorn command.

Settings (environment or `.env`): `DATABASE_URL`, `FEEDS_ENABLED`, `MONITOR_SITE`, `JEV_MODEL` (default `typesafe/jev-router`), `JEV_REASONING_EFFORT`, `NORTHSTAR_DATA`, `CONVERTER_PATH`, plus the embedding settings in `.env.example`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/state` | Nodes, edges, incoming items with proposals, event log |
| GET | `/api/events` | Server-sent events: item status changes, "ready", graph changes |
| POST | `/api/intake` | Multipart: `text`, `author`, `files[]`. Returns item ids |
| POST | `/api/items/{id}/preview` | Dry-run effects for an edited placement. Saves nothing |
| POST | `/api/items/{id}/approve` | Add the node, apply effects, record a revision |
| POST | `/api/items/{id}/dismiss` | Record a dismissal with a reason |
| GET | `/api/feeds` | Live data monitors: site, last and next run, errors, demo scenarios |
| POST | `/api/feeds/run?only=` | Run monitors now (all, or a comma-separated list) |
| POST | `/api/feeds/inject/{scenario}` | Demo: push a canned feed change through the real path |
| GET | `/api/search` | Hybrid search with filters; no model call. See "Querying the graph" |
| GET | `/api/nodes/{id}` | Node detail: text, source, passages, links, flags, history |
| GET | `/api/nodes/{id}/neighbours` | Graph walk: `affects`, `rests_on` or `any`, to a depth |
| POST | `/api/ask` | `{question}` -> answer, cited sources with quotes, timings. Saves nothing |
| POST | `/api/nodes/{id}/resolve` | Mark a blocker, discovery or constraint resolved; clears the flags it raised |
| POST | `/api/replay/forward`, `/api/replay/back` | Step the replay |
| GET | `/api/rules` | Suggested, active and retired rules |
| POST | `/api/rules/suggest` | Run the analysis loop once (body: `by`). Proposes rules; changes nothing else |
| POST | `/api/rules/{id}/approve` | Make a suggested rule live |
| POST | `/api/rules/{id}/dismiss` | Dismiss a suggestion or retire an active rule (body: `by`, `reason`) |
| POST | `/api/reset` | Demo helper: reload the example project |

## Known gaps

- **The schema is a vendored copy** of Sharare's, pinned to one commit. If hers changes, this copy must be refreshed until the branches merge.
- **Only part of the shared schema is used.** Proposals wait in `intake_items` and become confirmed nodes on approval; they are not stored as `candidate` nodes with `proposed` edges yet. Decision versions, lineage, rules and runs are untouched.
- **"At risk" is an attention item, not a node state.** The shared schema's per-type states have no blocked or at-risk value, so effects are written to `attention_items` and the UI shows the latest open one.
- **Built-in effects are still code** in `effects.py`; only rules approved from the analysis loop are JSON. The rule language is deliberately small (match a new node's type and link to a target's type or tags; flag the target, its dependents or its neighbours).
- **Rules survive Reset demo** (they're the pack, not the project), but their dry-run evidence points at the old project.
- **One project, no login.** "You are" is a dropdown.
- **Slack intake is not wired.** The chat box stands in for it; `/api/intake` is what a Slack bot would call.
- **Jev is a router,** so speed varies per call (2.7 to 6.4 seconds seen). Pin `JEV_MODEL` to one fast model if the demo needs consistency.
