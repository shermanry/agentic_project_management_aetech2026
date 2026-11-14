# North star MVP: add something, see where it goes, approve it

The one interaction from [plan.md](../plan.md), section 1, working end to end:

1. **Add:** drop files, paste, or type a note ("drone 4a needs maintenance").
2. **Propose:** the system works out the node type, which existing nodes it connects to, and what it would affect.
3. **Explore:** the proposal appears on the graph as a dashed ghost node; nodes it would change are outlined in red.
4. **Approve, edit or dismiss:** approving adds the node, applies the effects and records a revision with its source and reason.

## Replay mode

The bar above the graph steps through the facade survey from the team's whiteboard, one thing at a time:

- **Forward** brings in the next item (it runs through the real pipeline and shows as a proposed placement with its effects). Pressing it again, now labelled **Approve**, approves it.
- **Back** undoes exactly one Forward: first un-approving, then withdrawing the item.
- Left and right arrow keys do the same. **Reset demo** returns to the start.

The seven steps are in `replay.py`: notice to proceed, site visit findings, insurance delay, the airspace rule change, one flyable day, "drone 4a needs maintenance", and the image metadata problem. They are a reading of the whiteboard and should be checked by the drone experts.

The first time a step runs it is live (about 5 seconds for Jev). The approved proposal is then cached in the data folder, so going back and forward again is instant and identical. **Run through it once before a demo** so every step is cached. Back rebuilds the graph from the seed plus the cached steps, which also wipes anything added by hand during the replay.

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
| `db/010_northstar.sql` | One extra table, `intake_items`: things being processed or waiting for review |
| `replay.py` | The replay scenario and the Back / Forward logic |
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

Settings (environment or `.env`): `DATABASE_URL`, `JEV_MODEL` (default `typesafe/jev-router`), `JEV_REASONING_EFFORT`, `NORTHSTAR_DATA`, `CONVERTER_PATH`, plus the embedding settings in `.env.example`.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/state` | Nodes, edges, incoming items with proposals, event log |
| GET | `/api/events` | Server-sent events: item status changes, "ready", graph changes |
| POST | `/api/intake` | Multipart: `text`, `author`, `files[]`. Returns item ids |
| POST | `/api/items/{id}/preview` | Dry-run effects for an edited placement. Saves nothing |
| POST | `/api/items/{id}/approve` | Add the node, apply effects, record a revision |
| POST | `/api/items/{id}/dismiss` | Record a dismissal with a reason |
| POST | `/api/reset` | Demo helper: reload the example project |

## Known gaps

- **The schema is a vendored copy** of Sharare's, pinned to one commit. If hers changes, this copy must be refreshed until the branches merge.
- **Only part of the shared schema is used.** Proposals wait in `intake_items` and become confirmed nodes on approval; they are not stored as `candidate` nodes with `proposed` edges yet. Decision versions, lineage, rules and runs are untouched.
- **"At risk" is an attention item, not a node state.** The shared schema's per-type states have no blocked or at-risk value, so effects are written to `attention_items` and the UI shows the latest open one.
- **Effects are hard-coded rules** in `effects.py`, not generated JSON rules.
- **No way to resolve a blocker yet:** statuses turn red on approval; nothing turns them back.
- **One project, no login.** "You are" is a dropdown.
- **Slack intake is not wired.** The chat box stands in for it; `/api/intake` is what a Slack bot would call.
- **Jev is a router,** so speed varies per call (2.7 to 6.4 seconds seen). Pin `JEV_MODEL` to one fast model if the demo needs consistency.
