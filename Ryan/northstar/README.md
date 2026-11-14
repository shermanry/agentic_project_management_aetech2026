# North star MVP: add something, see where it goes, approve it

The one interaction from [plan.md](../plan.md), section 1, working end to end:

1. **Add:** drop files, paste, or type a note ("drone 4a needs maintenance").
2. **Propose:** the system works out the node type, which existing nodes it connects to, and what it would affect.
3. **Explore:** the proposal appears on the graph as a dashed ghost node; nodes it would change are outlined in red.
4. **Approve, edit or dismiss:** approving adds the node, applies the effects and records a revision with its source and reason.

## How it works

```
drop / paste / chat
   └─ converter (local, Minh's)      file -> text, images, metadata
   └─ embeddings (api/embeddings.py) nearest existing nodes  +  exact name matches ("drone 4a" -> Drone 4A)
   └─ Jev via OpenRouter             type, title, summary, tags, links with a reason and confidence
   └─ effects.py (plain code)        dry run: what gets blocked, put at risk or re-opened, and who to notify
   └─ proposal -> user reviews -> approve -> node + edges + status changes + one revision in the event log
```

- **Fast path:** text, images, PDFs, emails. Measured on Ryan's M4 Air once warm: about 5 to 7 seconds, almost all of it the Jev call (convert and embed are under a second).
- **Slow path:** 3D models, video, audio, unknown formats, or anything Jev says is too thin to judge. A first guess is shown straight away ("agent is reading it"), then the converter's vision agent reads the file and Jev re-proposes. The sample Rhino model took about 34 seconds.
- **Nothing is saved until approved.** Editing the type or links in the review panel re-runs the dry run.

| File | What it does |
| --- | --- |
| `app.py` | FastAPI routes, live updates to the browser (server-sent events) |
| `pipeline.py` | Intake: convert, match, ask Jev, compute effects; fast and slow paths |
| `effects.py` | The dry run. Rules are plain code for now; the plan is JSON rules written by the analysis loop |
| `store.py` | SQLite: nodes, edges, items, and an append-only event log (the decision history) |
| `seed.py` | Example project: East Tower facade survey. Placeholder details |
| `llm.py` | OpenRouter call that must return one JSON object |
| `static/index.html` | The canvas UI, no build step |

## Run it

Needs the repo-root `.env` (see `.env.example`) and the `converter/` package at the repo root.
Until the `converter` branch is merged into main, point `CONVERTER_PATH` at a checkout of it; without it only text and images are read.

```bash
cd Ryan/northstar
uv venv --python 3.12
uv pip install -r requirements.txt -r ../../converter/requirements.txt
.venv/bin/uvicorn app:app --port 8100
```

Then open http://localhost:8100. On the Mac that hosts the embedding server, add `LOCAL_EMBEDDING_URL=http://localhost:8000` in front of the last command.

Docker (written but **not yet tested**, Docker isn't installed on the machine this was built on; `rhino3dm` may need a build step on ARM Linux):

```bash
docker compose -f Ryan/northstar/docker-compose.yml up --build
```

Settings (environment or `.env`): `JEV_MODEL` (default `typesafe/jev-router`), `JEV_REASONING_EFFORT`, `NORTHSTAR_DATA`, `CONVERTER_PATH`, plus the embedding settings in `.env.example`.

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

- **Storage is SQLite,** not the Postgres schema on `sharare/decision-engine`. All SQL is in `store.py`, so swapping is contained, but it is not done.
- **Effects are hard-coded rules** in `effects.py`, not generated JSON rules.
- **No way to resolve a blocker yet:** statuses turn red on approval; nothing turns them back.
- **One project, no login.** "You are" is a dropdown.
- **Slack intake is not wired.** The chat box stands in for it; `/api/intake` is what a Slack bot would call.
- **Jev is a router,** so speed varies per call (2.7 to 6.4 seconds seen). Pin `JEV_MODEL` to one fast model if the demo needs consistency.
