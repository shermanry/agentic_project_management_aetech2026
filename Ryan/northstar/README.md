# North star MVP: add something, see where it goes, approve it

The one interaction from [plan.md](../plan.md), section 1, working end to end:

1. **Add:** drop files, paste, or type a note ("drone 4a needs maintenance").
2. **Propose:** the system works out the node type, which existing nodes it connects to, and what it would affect.
3. **Explore:** the proposal appears on the graph as a dashed ghost node; nodes it would change are outlined in red.
4. **Approve, edit or dismiss:** approving adds the node, applies the effects and records a revision with its source and reason.

## Two apps: the working project and the presentation

The same code runs in two modes, each with its own database, so rehearsing the demo never touches real work.

| | Working project | Presentation (replay) |
| --- | --- | --- |
| Start | `.venv/bin/uvicorn app:app --port 8100` | `./run_demo.sh` |
| URL | http://localhost:8100 | http://localhost:8200 |
| Mode | `NORTHSTAR_MODE=project` (default) | `NORTHSTAR_MODE=demo` |
| Database | `drone` | `drone_demo` (created on first start) |
| Replay bar | Hidden; the replay endpoints refuse | Shown: ⏮, Back, Forward, Skip setup, Reset demo |
| Header | **Start fresh…** and a "Replay demo ↗" link | **Reset demo** |
| Live feeds | Only in the full example | Off, so the replay is repeatable (Simulate still works) |

**Starting a fresh project** (working app): choose **Start fresh…** in the header. It wipes the project and its history after a confirmation and starts again from one of:

- **Empty project:** no nodes.
- **Starter:** five nodes (the site, Drone 4A, the flight plan, the permit package, Thursday's flight) and the links between them. A brand-new install starts here.
- **Full example:** every project node, the building parts and the live data feeds.

The API is `POST /api/project/new?template=empty|starter|full`. `POST /api/reset` starts the project again from the template it was last started from. There is still one project per app; several named projects side by side is not built.

With Docker, `docker compose -f Ryan/northstar/docker-compose.yml up` now starts both: the working app on 8100 and the presentation app on 8200.

## Replay mode

_Presentation app only (http://localhost:8200)._

The bar above the graph steps through the whole project from an **empty graph**, one thing at a time:

1. **Setup (18 presses):** the project's own nodes are added one per press, in the order of `seed.py`: the site, the drones, the flight plan, the wind limit, the permit package, the flight, and so on, then the five building parts, each bringing its links to what is already there. The last setup press connects the live data feeds.
2. **The story (7 steps, 2 presses each):** notice to proceed, site visit findings, insurance delay, the airspace rule change, one flyable day, "drone 4a needs maintenance", and the image metadata problem. The first press brings the item in (it runs through the real pipeline and shows as a proposed placement with its effects); the second, labelled **Approve**, approves it.

- **Forward / Back** move one press at a time; left and right arrow keys do the same. Back goes all the way to the empty project.
- **⏮** jumps to the empty project. **Skip setup ⏭** (shown during setup) adds the rest of the project's own nodes at once.
- **Reset demo** returns to "the project is set up", just before the story.
- The rehearsed steps are cached in `data/demo/`; `run_demo.sh` copies the working app's cache there the first time.
- API: `POST /api/replay/forward`, `/api/replay/back`, `/api/replay/goto?to=start|setup`. `replay` in `/api/state` carries `pos`, `total`, `setup_total` and a ready-made `caption` (title and story) for any UI.

The story steps are a reading of the whiteboard and should be checked by the drone experts. The first time a story step runs it is live (about 5 seconds for Jev); its approved proposal is then cached in the data folder, so going back and forward again is instant and identical. **Run through it once before a demo.** Back rebuilds the graph from scratch, which also wipes anything added by hand during the replay. While the replay is still in setup, the live feeds are held back so they don't add nodes out of order.

## Ask the project

The box under the graph answers questions from what is in the graph, and shows what it used.

- **What is searched:** every node's summary card, the full text of dropped documents (each page or section of a converted file is embedded when the node is approved), and the current flags on the graph ("Flight 5 is at risk because…").
- **How:** the question is embedded, pgvector returns the nearest chunks, and Jev answers from those numbered sources only, quoting the words it relied on. If the sources don't contain the answer it says so.
- **Highlighting:** the nodes used light up on the graph with their source numbers and everything else dims. The panel lists each source with its page and the quoted words highlighted. Clicking a number or a node jumps to that source.
- Questions and answers are not saved to the graph.

Limits: at most 12 sources reach Jev, so a fact buried in a long document can still be missed, and documents added before this feature are indexed in the background at startup. Images inside documents are not searched.

## The building and its parts

The project has five building-part nodes (east elevation, north façade, upper façade, roof and parapet, podium and entrance), tagged `building-part` and linked `part_of` the site. The flight, the flight plan, the wind limit, RFI #12 and the facade model are linked `about` the parts they concern, and new items that mention a part ("rooftop mechanical units", "north elevation") get linked to it by Jev.

A part has no status of its own. `GET /api/parts` (also `parts` in `/api/state`) rolls up everything linked to it:

- **red** if something about it is blocked or at risk,
- **amber** if a decision about it is re-opened, or there is an open finding or blocker about it,
- otherwise **none**; plus the list of linked items with their status and the reason for each link.

The page shows this as a small massing of the tower in the left column: each face is a part, coloured from the roll-up, and clicking it opens the part with "At this part of the building". Any other front end (the 3D building in Leslie's prototype, for instance) can colour itself from the same call. The parts are placeholders modelled on Leslie's overview page; the drone experts should say which parts matter.

## Connecting two nodes by hand

On the graph page, drag from one node to another. The side panel then shows:

- **What the system found:** how similar the two are in meaning, shared tags, whether one names the other, and any link they already have.
- **Suggested connections:** up to three from Jev, each with a direction, a type, a reason and a confidence, plus how many other nodes it would change. Clicking one fills in the editor. If Jev finds nothing sensible it says so.
- **The link to add:** direction, type and reason, all editable. "If you add this" is a dry run that updates as you edit.
- **Add link** saves the edge, applies its effects and records it in the decision history with who added it and why. Esc or Cancel discards it.

A link can change other nodes. If the new link makes something depend on a node that is already blocked or at risk, it inherits that risk, and so does whatever rests on it. Those flags clear when the original cause is resolved.

Endpoints: `POST /api/edges/suggest` and `POST /api/edges/preview` save nothing; `POST /api/edges` adds the link. All take `{source, target, type, reason, by}` where `source` is the "from" node. The logic is in `links.py`.

## Adding many files at once: in order of creation, Jev at each step

A proposal can only link to what is already in the graph. So files that arrive together are **added one at a time, oldest first** (`ordered.py`):

- **One file** behaves as before: it is read, proposed, and waits for a person to review it.
- **Two or more files arriving together** (a multi-file drop, a dropped folder, a linked folder) are a batch. They are sorted by each file's own date, then by name in natural order (A2 before A10). For each one in turn: it is read, Jev proposes its type and links against the graph as it stands at that moment, and it is **added automatically** before the next one is read. File 7 can link to files 1 to 6.
- Each automatic addition is in the history like any other, with "Added automatically, in order of creation (7 of 25)" as its reason.
- The pages send each file's last-modified date as the `modified` form field; linked folders use the date from the folder listing. Without dates, the order is by file name.
- It is slower than reading in parallel: about 6 seconds per file. `INTAKE_ORDERED=0` goes back to parallel reading with a review for every file.

**Answering Jev's question.** When a proposal is missing a key fact, Jev asks one short question ("What specifically are the lily pads, and who owns the replacement?"). The review card shows it with a box to answer. The answer is kept with the item and the item is read again with it, so the title, type, links and effects can all change. Nothing is added to the graph until the proposal is accepted. `POST /api/items/{id}/answer` with `{answer, by}`.

**Linking what is already there.** For a project whose files were read all at once and came out as loose nodes, `POST /api/relink` (or `.venv/bin/python relink.py <project id>`) walks the existing nodes oldest first, shows Jev each one with the nodes before it, and adds the links it proposes. Nodes that already have outgoing links are left alone.

## Example projects and switching between them

Each example project runs as **its own copy of the app**, with its own port, database and data folder, so one can never disturb another. The list is in `projects.json`.

| Project | Start it | Opens at |
| --- | --- | --- |
| East Tower facade survey (the default) | the usual `uvicorn app:app --port 8100`, or `./run_project.sh east-tower` | http://localhost:8100/app/ |
| Rooftop shell: aerial AM pilot (Ecem's manufacturing card) | `./run_project.sh rooftop-shell` | http://localhost:8110/app/ |

- `./run_project.sh` with no name lists the projects and which are running.
- **Switching:** when more than one is running, a **Project** menu appears in the top bar of `/app` (and in the header of the graph page). Picking a project opens the same tab on that project. A project that is not running is listed but greyed out.
- The first start of a project creates its database and loads its seed. Postgres from `docker-compose.yml` must be up.
- The rooftop shell needs `Ecem/manufacturing-card/seed_manufacturing.py`, which arrives with PR #3. Until then it shows as "not installed".

**Adding a project from the page:** the project menu ends with **+ Add new project…**. It asks for a name, creates an empty project (seed file under `data/projects/<id>/`, an entry in `data/projects.local.json`, its own database and the next free port from 8120), starts its copy of the app and opens it. A listed project that is stopped can be picked from the menu to start it. `POST /api/projects` `{name, by}` and `POST /api/projects/{id}/start` do the same. Through one shared link (a tunnel to one port) the other projects are reached at `/p/<project id>/app/`: the app passes those requests on to that project's copy on the same machine, and the project menu uses those addresses automatically.

**Deleting a project from the page:** when the open project was added from the page, the menu also has **− Delete this project…**. After a confirmation it removes the project from the list, stops its copy of the app, drops its database and deletes its files (`POST /api/projects/<id>/delete`). This cannot be undone. The built-in projects in `projects.json` cannot be deleted this way.

**Adding an example project by hand:** write a seed file with the same shape as `seed.py` (`PROJECT`, `PEOPLE`, `NODES`, `EDGES`; optionally `PARTS`, `PART_EDGES`, a replay `SCENARIO` and `STARTER_REFS`), then add a line to `projects.json` with an unused port and database name. Set `"feeds": false` unless the New York live feeds make sense for it.

How it works: `NORTHSTAR_PROJECT` picks the project; `seed.py` then loads that project's seed file in place of its own tables, so the rest of the app is unchanged. `GET /api/projects` returns the list for the menu.

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
| `projects.json`, `projects.py`, `run_project.sh` | The example projects, their settings, and the launcher |
| `brief.py` | Design brief generator for the Client tab |
| `ordered.py` | The lane that adds a batch of files one at a time, in order of creation |
| `relink.py` | Links the nodes a project already has, in order of creation |
| `links.py` | Connecting two existing nodes: signals, Jev suggestions, dry-run effects |
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
| POST | `/api/feeds/inject/{scenario}?feed=` | Demo: push a canned feed change through the real path (`feed` = the ref of a feed a person added) |
| POST | `/api/feeds` | A person adds a live feed. Body: `kind` (weather, airspace, city, rules, space), `title`, `address` (NYC; empty = project site), `window` `{start,end}`, `limits` (e.g. `max_wind_mph`), `depends` (node ids), `by`. Creates the feed node with these settings, links what depends on it, starts its monitors and takes a first reading. In the front end: Live feeds, "+ Add live feed" |
| POST | `/api/feeds/{node_id}/remove` | Remove a feed a person added (built-in feeds stay); its links and open flags go, the history stays |
| GET | `/api/parts` | Building parts with a red / amber / none level rolled up from linked nodes |
| GET | `/api/search` | Hybrid search with filters; no model call. See "Querying the graph" |
| GET | `/api/nodes/{id}` | Node detail: text, source, passages, links, flags, history |
| GET | `/api/nodes/{id}/neighbours` | Graph walk: `affects`, `rests_on` or `any`, to a depth |
| POST | `/api/edges/suggest`, `/api/edges/preview`, `/api/edges` | Suggest, dry-run and add a link between two existing nodes |
| POST | `/api/projects/{id}/delete` | Delete a project that was added from the page: stops it, drops its database, removes its files |
| GET | `/api/projects` | The example projects, which one this app is, and which others are running |
| POST | `/api/items/{id}/answer` | Answer Jev's question on a proposal; the item is read again with the answer |
| POST | `/api/relink` | Link the project's existing nodes, oldest first, with Jev at each step |
| GET | `/api/brief` | Draft design brief in Markdown, templated from the live record (no model call). Used by the Client tab |
| POST | `/api/ask` | `{question}` -> answer, cited sources with quotes, timings. Saves nothing |
| POST | `/api/nodes/{id}/resolve` | Mark a blocker, discovery or constraint resolved; clears the flags it raised |
| POST | `/api/project/new` | Working app: wipe the project and start from `template=empty`, `starter` or `full` |
| POST | `/api/replay/forward`, `/api/replay/back`, `/api/replay/goto` | Presentation app: step or jump the replay |
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

## Adding a whole folder (Minh's linked folders, wired into intake)

In `/app`, **+ Add** is a menu: Files, A folder, Google Drive folder, A note, and the review tray.

- **A folder** (or a folder dropped anywhere on the page): the browser opens it and sends every file to `POST /api/intake`
  as its own item, two at a time, with its folder as the note. System, lock, backup and temp files are left out.
- **Google Drive folder**: `POST /api/intake/folder` (form: `source`, `author`, `text`) lists and downloads the folder with
  `Minh/converter/sources.py` and adds each file to intake. `source` can also be the path of a folder on the server.
  `GET /api/intake/folder/{id}` gives progress; `POST /api/intake/folder/{id}/stop` stops it.
  The Drive folder must be shared "Anyone with the link". Without `GOOGLE_API_KEY` in `.env`, 50 files per folder at most.
- Limits: `FOLDER_MAX_FILES` (default 40 per folder, one Jev call each), `INTAKE_PARALLEL` (default 4 files read at once).
- Needs `gdown` (in `Minh/converter/requirements.txt`).

## Items with no connections

Anything that goes in without links gets a second look. When a proposal is approved with no links and the
project has other nodes (its proposal was written before the rest of the graph existed), the app waits for a
pause in the approvals and then has Jev link the loose nodes, oldest first, each against what came before it.
The canvas in `/app` also shows "N items have no connections · Find connections", which runs the same pass on
demand (`POST /api/relink`). `/api/state` reports `linking: true` while a pass is running.

## East Tower's nodes come from the operator interview

The working East Tower project is seeded from `seed_facade_sme.py`, built from `Polina/sme-answers.md`
(40 nodes, 5 building parts, 5 live feeds). The presentation app keeps the whiteboard story in `seed.py`,
because its cached replay steps link to those nodes by id. `EAST_TOWER_SEED=classic` gives the working project
the old tables.

- **Constraints** carry `data.class`: `hard` (removes the date), `soft` (penalises it) or `derate` (the date holds,
  an estimate changes), plus `data.origin` and the flight geometry they apply to. The class is also a tag.
- **Blockers** are things a party outside the drone team supplies: insurance proof, the owner's letter, DHS
  approval, the named crew's release from another project.
- **Decisions** carry who decides, approves, is consulted and is informed, and `alternatives_available` where
  there is none (the permit dates).
- **The dependency chain**: third-party documents -> NYPD package -> permit -> crew booking -> flight ->
  processing -> delivery. The flight also depends on the day-before go or no-go call, which depends on every
  hard limit, both airspace states (legal and operational) and the forecast.
- **Start fresh** in the working project: Starter is that chain (10 nodes); Full is everything.
