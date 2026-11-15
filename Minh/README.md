# Minh: intake and converter engine (handoff)

The intake and converter engine of the drone-project knowledge-graph hackathon (everything of mine lives in this `Minh/` folder; the team's planning docs are in [`../Ryan/`](../Ryan/), shared embeddings in [`../api/`](../api/)). Drop any project file, paste a conversation or a link, or ask it to research something, (Rhino models, PDFs, emails, photos, markups, Teams screenshots, video, voice notes, Office files, zips) and get an embedding-ready package: text, image, audio and video chunks plus JSON metadata and extracted entities, ready for the graph to place.

- **Using it / package spec** → [`converter/README.md`](converter/README.md)
- **Picking up the work** → this page: code map, design decisions, gotchas, test checklist, next steps

Quick start (Windows; on macOS/Linux use `.venv/bin/python`):

```bash
cd Minh
python -m venv .venv
.venv/Scripts/python -m pip install -r converter/requirements.txt
.venv/Scripts/python -m converter serve      # drag-and-drop UI on http://127.0.0.1:8765
```

All paths below are relative to this `Minh/` folder unless they start with `../` (repo root). Run every command from inside `Minh/`.

## What this is and who depends on it

Part of the drone-project knowledge-graph hackathon project (see `../Ryan/PROJECT_BRIEF.md`). This module is only the **converter**: any dropped file becomes a Universal Embedding Package (UEP) folder (`manifest.json` + `chunks.jsonl` + `assets/`). Teammates build **embedding** and **graph** on top of those packages.

- **Scope: convert, don't judge.** This module only turns whatever is dropped (files, pasted text, links, a research question) into clean, meaningful content. It does **not** decide what relates to what, how important something is, or whether it needs a decision: placement, linking and approval belong to the graph side (e.g. Ryan's north-star pipeline). The only links it writes are physical containment: an attachment is `part_of` its email, a file is `part_of` its zip.
- **The package format is a contract.** Teammates read `manifest.json`, `chunks.jsonl` and `converter_output/index.jsonl`. Adding fields is fine. Renaming or removing fields, or changing the meaning of `id` / `role` / `locator` / `links`, breaks them. If you must, bump `SCHEMA_VERSION` in `core.py` and update `converter/README.md`.
- **Two layers.** The **local converter** extracts hard facts deterministically with no network calls. The optional **agent** (`converter/agent.py`, via OpenRouter) adds *readable content* on top: one prompt plus files in; who sent it, a summary, key points with sources, figures worth keeping and the handwriting on markups out. "Convert only" in the UI (or the CLI) stays fully local.

## The agent layer (prompt + files → clean, meaningful content)

Needs `OPENROUTER_API_KEY` in `.env` at the **repo root** (copy `../.env.example`; never commit `.env`). The agent finds it by searching parent folders. Models are set in `.env`:
`CONVERTER_ROUTER_MODEL` (default `anthropic/claude-haiku-5.5`, reads the prompt) and `CONVERTER_AGENT_MODEL` (default `anthropic/claude-sonnet-5.5`, reads text and images). Requests use OpenRouter `provider.data_collection = "deny"` (`CONVERTER_ALLOW_DATA_COLLECTION`).

Flow (`agent.ask`):
1. **interpret** (router model): prompt + filenames become per-file context: author, role, channel, note, intent, project. No library lookup.
2. **convert** (local converter, unchanged) with that context.
2b. **media pass** (`converter/media_pass.py`, `CONVERTER_MEDIA_MODEL`, default `typesafe/jev-router`, which takes audio, video, files and images natively): each 30 s audio segment becomes a verbatim `transcript` chunk; each 30 s video clip becomes a `transcript` plus a `clip_description` (what is visible, timestamped moments); PDF pages with no text layer become `page_text` (all labels, dimensions, title block). Chunks are marked `suggested_by: "agent-media:<model>"` and `media_for: <source chunk>`, so re-reads skip finished items. The text also feeds entity extraction. Measured on the samples: a 31 s voice note, a narrated 9 s clip and a scanned drawing each took about 13 s and $0.005 to $0.006 for the media pass ($0.01 to $0.02 per file including the reading).
3. **understand** (agent model): manifest essentials + text chunks (about 24k chars) + up to 10 of the most informative images become JSON with title, summary, tags, **key_points** (self-contained statements of what the file says or shows, each citing its source chunk/page/image), **figures** (with optional crops) and **markup_text** (handwriting on images). The prompt explicitly forbids judging importance, classifying, or relating to other nodes.
4. **write back**: new chunks are *appended* (existing chunk ids stay stable) with roles `agent_summary | key_point | figure | markup_text` and `meta.suggested_by = "agent:<model>"`; `manifest.agent` holds title, summary, counts and usage. `agent.undo()` removes exactly those additions; re-running replaces them.

**Text only, no files** (`agent.text_intake`): the router model classifies the prompt.
- `note`: a pasted conversation, minutes or a message. It's saved as `note_<title>.md` and becomes the node.
- `links`: every URL in the prompt is downloaded (http(s) only, 80 MB cap; html/pdf/images/video/office by content type) and converted; `context.source_url` keeps the origin.
- `research`: OpenRouter web plugin (`plugins: [{"id": "web"}]`) on `CONVERTER_RESEARCH_MODEL`. It writes a cited Markdown brief `research_<title>.md` with a numbered source list; `context.source_urls` holds the URLs.

Measured: a pasted Teams thread took about 10 s / $0.01 and came out as 6 clean key points (who said what, dates, the options). A link (FAA page) took 14 s / $0.04. A research question (FAA rules over the Hudson piers) took 43 s / $0.27 and produced a brief with 10 sources. Research is the expensive path because web results go into the prompt; set `CONVERTER_RESEARCH_MODEL` to a cheaper model if needed.

API: `POST /api/ask` (form: `prompt`, optional `files[]`, optional `package_ids` to re-read existing nodes; prompt alone = text-only intake), `POST /api/packages/{id}/agent/undo`, `GET /api/agent`.
Measured on the samples: about 10 s and $0.01 to $0.02 per file. A Teams markup came out as its summary, 5 key points, 2 cropped figures and the handwriting ("lighter canopy here?").

## Linked folders (one root folder -> the first data tree)

Real projects don't arrive one file at a time: point the converter at the **project's root folder** and it converts everything inside (`converter/sources.py`).

- **Sources:** a local or network path (`C:\\Projects\\Pier54`, `\\\\server\\share\\Pier54`), or a **Google Drive folder link** shared "anyone with the link". With `GOOGLE_API_KEY` in `.env` it uses the Drive API (no limit; Google Docs/Sheets/Slides exported to docx/xlsx/pdf); without it, `gdown` (max 50 files per folder). Private Drive folders need a key / service account: not built.
- **Every file -> one package** (local extraction, plus the AI reading and media pass when `mode="agent"`). `source.uri` = the original's path or Drive link, plus `source.folder` and `source.modified_at`. That is the "open the file" link and the dates a "latest file" question needs.
- **Every folder -> one `folder` package** that `contains` its files and subfolders (they're `part_of` it). The folder tree is the first skeleton of the data tree. It's containment only: still no relevance judgement.
- **Safe to re-run:** files whose content was already converted are skipped (same bytes = same package id). A file that's identical to one elsewhere gets a second `part_of` instead of a duplicate. Junk is skipped: `Thumbs.db`, `desktop.ini`, Office lock files `~$…`, dotfiles. Files above `CONVERTER_LINK_MAX_MB` (default 500) are skipped.
- **Watch mode** polls for new or changed files (default every 60 s).
- **Forward:** optionally POSTs each file to another intake, e.g. Ryan's north-star `http://<host>:<port>/api/intake`, so his graph fills up from the same root.
- UI: the folder button next to ＋, or paste a folder path / Drive folder link alone in the prompt box. A live progress card shows converted / already done / failed / cost, with Stop and "Open root folder". The library has a **Folders** filter.
- CLI: `python -m converter link <path-or-drive-link> [--ai] [--watch] [--forward URL] [--note "..."]`
- API: `POST /api/links` (form: `source`, `mode` agent|local, `watch`, `forward_url`, `prompt`), `GET /api/links`, `GET /api/links/{id}`, `POST /api/links/{id}/stop`. Jobs live in memory; `converter_output/links.json` keeps a record.

Measured: a 13-file test project (brief, drawings incl. a scan and a markup, Rhino model, email, RFI zip, photo, narrated video, voice note, spreadsheet, notes; 12 folders) took 4.5 s local-only. With AI reading it took about 15 s for the 7 files not yet read ($0.08); a re-run skipped all 13.

## Run / check

From inside `Minh/` (Windows; on macOS/Linux use `.venv/bin/python`):

```bash
.venv/Scripts/python -m converter serve                 # UI on http://127.0.0.1:8765 (no auto-reload: restart after code changes)
.venv/Scripts/python -m converter convert <files|folders> [-o converter_output] [--note --author --role --channel --intent --refers-to]
.venv/Scripts/python samples/make_samples.py            # synthetic test files -> samples/generated/
.venv/Scripts/python -m converter convert samples/generated
.venv/Scripts/python samples/make_samples.py --markups  # markups drawn on the first converted view_axonometric.png
.venv/Scripts/python samples/make_samples.py --media-ai # spoken voice note, narrated video, scanned drawing (Windows TTS)
```

There is **no test suite yet**. Regression testing = regenerate the samples, convert them, and check the output. What a good run looks like:

| Sample | Expect |
| --- | --- |
| `tower_site.3dm` | `rhino_model`, ~17 chunks, 4 views + 4 layer views, 1 warning (sphere Brep without render mesh) |
| `flight_reschedule.eml` | `email`, body split latest/quoted, image attachment inside, PDF as child package (`part_of`) |
| `flight_plan_reviewed.pdf` | 2 `markup_region` chunks (Cloud+ by Project Lead, Note by Client with folded reply), entities incl. `rfi-012`, `level-30`, `north-elevation` |
| `client_markup_on_render.png` | `markup`, method `diff`, `metadata.markup.drawn_on` = the model view, `layers` filled |
| `teams_screenshot_markup.png` (cropped) and `teams_chat_screenshot.png` (inside fake Teams UI) | `markup`, method `aligned-diff`, **3 regions** (circle, arrow, written note), all red, `drawn_on` filled |
| `drone_photo.jpg` | `image` (NOT markup), GPS + DJI XMP in metadata |
| `flyover.mp4` / `voice_memo.m4a` | keyframes + 30 s clips / wav segments, warning "no transcript" (local) |
| `site_voice_note.m4a` / `drone_flyover_narrated.mp4` / `scanned_north_elevation.pdf` (AI mode) | verbatim transcript; transcript + clip description; page text incl. title block A-201 Rev C. Undo restores the local-only state exactly |

Markup output is easiest to judge by drawing `locator.bbox` of the `markup_region` chunks onto the source image and looking at it.

## Code map

```
converter/
  core.py        Package (one per file): chunks, assets, context, aliases/parents, manifest + jsonl writing; text splitting; zip
  engine.py      registry (@register(kind, *exts)), convert_file(), child conversion, _finalize (summary/context chunks,
                 tags, entities, containment links), index.jsonl (thread-locked)
  markup.py      perceptual hash, find original (hash, then ORB features), diff / aligned-diff / colour detection,
                 region chunks, Rhino layer-under-mark mapping
  entities.py    regex entities (rfi, level, elevation, grid, sheet, date, person, regulation, element)
  sources.py     linked folders: local / Google Drive walker, folder packages, jobs, watch, forward
  media_pass.py  AI media pass: audio/video/scanned pages -> transcript, clip_description, page_text
  tagging.py     keyword tag rules
  server.py      FastAPI: /api/convert (multipart + context form fields), /api/packages[/id|/zip], DELETE, /files static
  static/index.html  single-file vanilla JS UI (drop, Ctrl+V paste, context box, library, detail drawer)
  handlers/      one module per family; imported in handlers/__init__.py to register
    rhino.py     rhino3dm read + description + own software renderer (painter's algorithm, numpy + PIL)
    pdf.py       pymupdf text/page renders/embedded images + annotations (Bluebeam/Acrobat)
    email_msg.py .eml (stdlib) / .msg (extract-msg); sender becomes context; attachments become children
    image.py     EXIF/GPS/DJI XMP, normalised copy, markup analysis
    media.py     ffmpeg via imageio-ffmpeg (no ffprobe: parses `ffmpeg -i`), segments/keyframes/clips, optional faster-whisper
    office.py    docx/pptx/xlsx; text.py txt/md/csv/json/html; archive.py zip; fallback.py unknown
```

## Design decisions (keep unless there's a reason)

- **Package id = `uep_` + first 12 hex of sha256 of the bytes.** The same file arriving twice (dropped, and as an attachment) is one node. Re-conversion replaces the content but **keeps** `source.aliases`, `metadata.parent_ids` and `context` from the previous manifest (`Package.__init__`).
- **Every chunk has `text`**, including media (a caption). **Chunk 0 is `role: summary`**. If the user gave a note, a `role: context` chunk follows it. Captions include `pkg.context_line()` so vectors carry *who asked what*.
- **Context propagates**: an email's sender, channel and date go into `pkg.context`. `ctx.convert_child` passes author/role/channel/date/note to attachments and zip members.
- **Markup pipeline** (`markup.analyze`): explicit `refers_to` → hash match (`find_original`, dhash ≤ 14/64 bits, ties broken by thumbnail pixel distance) → ORB feature match against our own Rhino `snapshot` views (`find_original_by_features`) → diff (same framing, pixels verified to line up) or aligned-diff (homography) → if still nothing, colour strokes (red/magenta only). `intent: "reference"` skips all of it; `intent: "markup"` forces a markup node even with 0 regions.
- **Layer mapping** works only when the original is a Rhino `view_axonometric.png`. It reads the per-layer highlight renders (`layer_*.png`), which use `ACCENT` orange in `handlers/rhino.py`. Changing the accent colour, view angle or image size breaks `_layer_maps`.
- **Links** (`manifest.links`): only `part_of` / `contains` (attachment ↔ email, file ↔ zip). No relevance links. A markup records what it was drawn on as a plain fact, `metadata.markup.drawn_on`, because the original is needed to cut out the pen strokes precisely.
- **Tags** are rules (`suggested_by: "rules"`), meant to be replaced by the model-based tagger downstream. Entities are separate, for exact-match graph joins.

## Gotchas already hit (don't re-learn them)

- **Windows file locks**: close pymupdf docs (`with pymupdf.open(...)`) and openpyxl workbooks (`wb.close()`), or temp-dir cleanup fails. Temp dirs use `ignore_cleanup_errors=True`.
- **rhino3dm API**: use `len(mesh.Vertices)` / `len(mesh.Faces)`, not `.Count`. `mesh.Faces[i]` is a 4-tuple (tri when c == d). Document user text is `model.Strings[i] -> (key, value)`, and samples set it with `m.Strings[key] = value`. Breps saved without render meshes have none; that's handled with an untrimmed UV grid plus a warning.
- **Rhino renderer**: painter's algorithm sorted by triangle centroid. Large faces are subdivided first (`_subdivide`), otherwise the ground plane draws over buildings. Edges get a small depth bias.
- **Red hue wraps around** (0° and 360°). Never median the hue; `colour_name` uses the median RGB of vivid pixels.
- **Same aspect ratio ≠ same framing**: a 4:3 Teams screenshot of a 4:3 render used to take the plain-diff shortcut. `_align` now checks the pixels actually line up (<12% changed).
- **Screenshot crops**: the warped original overhangs the picture edge into chat UI. `detect_by_diff` keeps only differences in locally agreeing areas and drops regions on the edge of the matched area.
- **Colour detection without an original** only looks for red/magenta. Green/blue are too common in renders (ground, glass, water) and caused false positives.
- **`.claude/launch.json` for the preview server lives one folder above the repo** (the desktop session's root), not inside it.
- **The agent extracts, it doesn't judge.** It only appends content chunks and never overwrites local facts. Keep relevance, importance and linking out of it; that's the graph's job.
- `find_original*` scans every package in `converter_output` (fine at hackathon scale, O(library)). Feature matching only tries Rhino snapshot views, to keep it fast.

## Adding a format

New module in `converter/handlers/`, decorate with `@register("kind", ".ext")`, import it in `converter/handlers/__init__.py`. Use `pkg.add_text` (auto-splits), `pkg.add_asset_bytes` + `pkg.add_image` (auto-dhash), `pkg.add(Chunk(...))` for audio/video, and `ctx.convert_child(bytes, name, pkg)` for embedded files. Set `pkg.title`, `pkg.description`, `pkg.metadata`, and append to `pkg.warnings` instead of raising when something is skipped. Exceptions are caught in `engine.convert_file` and stored as warnings, so partial output survives.

## Status (2026-11-14)

Done and tested on synthetic samples plus one real Rhino model (Pier 54, ~2.2k objects, 85 chunks): every handler above, the drag-drop / paste UI, context, markups, PDF annotations, entities, text-only intake (notes, links, research).

Not tested on real data yet: real client markups, real Outlook `.msg` files, large PDFs / drawing sets, long videos.

## Next steps (rough priority)

0. **Agent**: let it split long documents into several self-contained content packages; batch mode for watched folders. (Embedding and linking stay with the graph side.)
1. **Tests**: turn the table above into pytest using `samples/make_samples.py` fixtures (markup region counts are the fragile part).
2. **Linked folders, next**: private Google Drive / SharePoint via OAuth or a service account; persist jobs across server restarts (today they live in memory); batch approval on the graph side (Ryan) so a 500-file root isn't 500 single approvals.
3. **`markup_text` / OCR**: read typed or handwritten notes on markups (local Tesseract, or a vision model if the team allows network).
4. **Media**: an `.srt` telemetry sidecar parser for DJI video (GPS/altitude per second); optional local faster-whisper for offline transcripts. (AI-mode transcripts, video descriptions and scan reading are done via the media pass.)
5. **More AEC formats**: IFC (ifcopenshell), DWG/DXF (ezdxf for DXF), E57/LAS point clouds, Revit via exported IFC, HEIC photos (pillow-heif).
6. **Teams/Slack connector** (Graph API) for the "passive streams" in the brief: pull messages and files in for conversion; placement stays with the graph.
7. **Scale**: a dhash index file instead of scanning all `chunks.jsonl` in `find_original`.

## Git

- Merged into **`main`** on 2026-11-14 (approved by the team). The **`converter`** branch is kept for converter-only work: branch from `main`, merge back when done.
- This clone has repo-local config: `user.name "Minh Dang Ngo"`, `user.email dangminh2606@outlook.com`, `credential.https://github.com.username MinhDangNgo` (must be the GitHub **username**, not the email, or Git Credential Manager asks to sign in on every push). A new contributor should set their own identity and **not** reuse these.
- Ignored: `.venv/`, `converter_output/`, `samples/generated/`. Never commit converted outputs or client files.
- Everything of mine is under `Minh/` so the repo root stays tidy for the team (Ryan keeps his work under `Ryan/`). Shared files at the root: `.gitignore`, `.env.example`, `api/`, `monitors/`.
