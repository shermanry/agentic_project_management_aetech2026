# Converter engine: handoff

**Converter** branch of the drone-project knowledge-graph hackathon. Drop any project file (Rhino models, PDFs, emails, photos, markups, Teams screenshots, video, voice notes, Office files, zips) and get an embedding-ready package: text, image, audio and video chunks plus JSON metadata, typed links and entities for the graph.

- **Using it / package spec** → [`converter/README.md`](converter/README.md)
- **Picking up the work** → this page: code map, design decisions, gotchas, test checklist, next steps

Quick start (Windows; on macOS/Linux use `.venv/bin/python`):

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r converter/requirements.txt
.venv/Scripts/python -m converter serve      # drag-and-drop UI on http://127.0.0.1:8765
```

All paths below are relative to the repo root.

## What this is and who depends on it

Part of the drone-project knowledge-graph hackathon project (see `PROJECT_BRIEF.md`; on `main` it has moved to `Ryan/PROJECT_BRIEF.md`). This module is only the **converter**: any dropped file becomes a Universal Embedding Package (UEP) folder (`manifest.json` + `chunks.jsonl` + `assets/`). Teammates build **embedding** and **graph** on top of those packages.

- **The package format is a contract.** Teammates read `manifest.json`, `chunks.jsonl` and `converter_output/index.jsonl`. Adding fields is fine. Renaming or removing fields, or changing the meaning of `id` / `role` / `locator` / `links`, breaks them. If you must, bump `SCHEMA_VERSION` in `core.py` and update `converter/README.md`.
- **Local and offline by design.** No model calls, no network calls. Anything needing a model (OCR, captions, model tags, transcripts beyond faster-whisper) is left as an explicit `pending` field for downstream. Keep it that way unless the team decides otherwise.

## Run / check

From the repo root (Windows; on macOS/Linux use `.venv/bin/python`):

```bash
.venv/Scripts/python -m converter serve                 # UI on http://127.0.0.1:8765 (no auto-reload: restart after code changes)
.venv/Scripts/python -m converter convert <files|folders> [-o converter_output] [--note --author --role --channel --intent --refers-to]
.venv/Scripts/python samples/make_samples.py            # synthetic test files -> samples/generated/
.venv/Scripts/python -m converter convert samples/generated
.venv/Scripts/python samples/make_samples.py --markups  # markups drawn on the first converted view_axonometric.png
```

There is **no test suite yet**. Regression testing = regenerate the samples, convert them, and check the output. What a good run looks like:

| Sample | Expect |
| --- | --- |
| `tower_site.3dm` | `rhino_model`, ~17 chunks, 4 views + 4 layer views, 1 warning (sphere Brep without render mesh) |
| `flight_reschedule.eml` | `email`, body split latest/quoted, image attachment inside, PDF as child package (`part_of` link) |
| `flight_plan_reviewed.pdf` | 2 `markup_region` chunks (Cloud+ by Project Lead, Note by Client with folded reply), entities incl. `rfi-012`, `level-30`, `north-elevation` |
| `client_markup_on_render.png` | `markup`, method `diff`, `marks_up` link to the model, `layers` filled |
| `teams_screenshot_markup.png` (cropped) and `teams_chat_screenshot.png` (inside fake Teams UI) | `markup`, method `aligned-diff`, **3 regions** (circle, arrow, written note), all red, `marks_up` link |
| `drone_photo.jpg` | `image` (NOT markup), GPS + DJI XMP in metadata |
| `flyover.mp4` / `voice_memo.m4a` | keyframes + 30 s clips / wav segments, warning "no transcript" unless faster-whisper is installed |

Markup output is easiest to judge by drawing `locator.bbox` of the `markup_region` chunks onto the source image and looking at it.

## Code map

```
converter/
  core.py        Package (one per file): chunks, assets, context, aliases/parents, manifest + jsonl writing; text splitting; zip
  engine.py      registry (@register(kind, *exts)), convert_file(), child conversion, _finalize (summary/context chunks,
                 tags, entities, typed links), index.jsonl (thread-locked)
  markup.py      perceptual hash, find original (hash, then ORB features), diff / aligned-diff / colour detection,
                 region chunks, Rhino layer-under-mark mapping
  entities.py    regex entities (rfi, level, elevation, grid, sheet, date, person, regulation, element)
  tagging.py     keyword tag rules + needs_decision hint
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
- **Typed links** (`manifest.links`): `part_of`, `contains`, `marks_up` (with confidence from hash distance), `refers_to`. Backlinks ("marked up by") are computed at read time in `server.py` from `index.jsonl`, not stored.
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
- `find_original*` scans every package in `converter_output` (fine at hackathon scale, O(library)). Feature matching only tries Rhino snapshot views, to keep it fast.

## Adding a format

New module in `converter/handlers/`, decorate with `@register("kind", ".ext")`, import it in `converter/handlers/__init__.py`. Use `pkg.add_text` (auto-splits), `pkg.add_asset_bytes` + `pkg.add_image` (auto-dhash), `pkg.add(Chunk(...))` for audio/video, and `ctx.convert_child(bytes, name, pkg)` for embedded files. Set `pkg.title`, `pkg.description`, `pkg.metadata`, and append to `pkg.warnings` instead of raising when something is skipped. Exceptions are caught in `engine.convert_file` and stored as warnings, so partial output survives.

## Status (2026-11-14)

Done and tested on synthetic samples plus one real Rhino model (Pier 54, ~2.2k objects, 85 chunks): every handler above, the drag-drop / paste UI, context, markups, PDF annotations, entities, links.

Not tested on real data yet: real client markups, real Outlook `.msg` files, large PDFs / drawing sets, long videos.

## Next steps (rough priority)

1. **Tests**: turn the table above into pytest using `samples/make_samples.py` fixtures (markup region counts and links are the fragile part).
2. **Watched folder**: drag emails from Outlook into a folder and they auto-convert. Outlook can't drop straight into the browser, so this would be the handiest workflow.
3. **`markup_text` / OCR**: read typed or handwritten notes on markups (local Tesseract, or a vision model if the team allows network).
4. **Transcripts by default** (faster-whisper), and an `.srt` telemetry sidecar parser for DJI video.
5. **More AEC formats**: IFC (ifcopenshell), DWG/DXF (ezdxf for DXF), E57/LAS point clouds, Revit via exported IFC, HEIC photos (pillow-heif).
6. **Teams/Slack connector** (Graph API) for the "passive streams" in the brief, suggested rather than auto-placed.
7. **Scale**: a dhash index file instead of scanning all `chunks.jsonl` in `find_original`.

## Git

- Work happens on branch **`converter`** (pushed to `origin`). No PR into `main` yet; open one when the team approves. `main` has moved on (the `Ryan/` folder), but there are no overlapping files.
- This clone has repo-local config: `user.name "Minh Dang Ngo"`, `user.email dangminh2606@outlook.com`, `credential.https://github.com.username MinhDangNgo` (must be the GitHub **username**, not the email, or Git Credential Manager asks to sign in on every push). A new contributor should set their own identity and **not** reuse these.
- Ignored: `.venv/`, `converter_output/`, `samples/generated/`. Never commit converted outputs or client files.
