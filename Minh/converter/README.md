# Converter engine: any file → Universal Embedding Package (UEP)

Drop any project file and get back one folder per file holding **text, image, audio and video chunks** plus **JSON metadata**. The folder is ready for the embedding step and becomes a node in the graph.

> Picking this up? Read the [repo-root README](../README.md) first: code map, design decisions, gotchas, test checklist and next steps.

Everything runs locally. The converter makes no model calls and no network calls. Embedding, tagging by model, and graph building happen downstream and read the packages described below.

```
drop file ──► converter ──► converter_output/<package_id>/  ──► embedding (team) ──► graph (team)
                              manifest.json   node metadata
                              chunks.jsonl    embeddable units
                              assets/         png / jpg / wav / mp4
```

## Run it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r converter/requirements.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m converter serve                               # http://127.0.0.1:8765 drag-and-drop UI
.venv/Scripts/python -m converter convert path/to/files_or_folders    # command line, same output
.venv/Scripts/python -m converter formats                             # list supported extensions
.venv/Scripts/python samples/make_samples.py                          # synthetic test files -> samples/generated/
.venv/Scripts/python samples/make_samples.py --markups                # markup samples (convert a .3dm first)
```

You don't need Rhino, Office or ffmpeg installed. ffmpeg comes bundled with `imageio-ffmpeg`.

From Python:

```python
from converter import convert_file
manifest = convert_file("site_model.3dm", "converter_output")
```

## What each format becomes

| Kind | Extensions | Text chunks | Media chunks | Metadata highlights |
| --- | --- | --- | --- | --- |
| rhino_model | .3dm | overview, one per layer, named objects, annotations/text dots, document + object user text | shaded **top / front / right / axonometric** snapshots, plus an axonometric view with **each major layer highlighted** | units, extents (also in metres), object types per layer, blocks + instance counts, materials, named views, earth anchor location |
| document | .pdf, .docx | per page / per heading section, tables as header + rows | **every PDF page rendered** (drawings are visual), embedded images | author, title, outline/TOC, pages with text |
| presentation | .pptx | per slide incl. speaker notes | embedded media | slide count |
| spreadsheet / table | .xlsx .csv .tsv | header + 40 rows per chunk | – | sheets, columns |
| email | .eml, .msg | latest message and quoted history kept separate, headers | inline/attached images | from, to, cc, date, subject. **Non-image attachments become child packages** |
| image | .jpg .png .tif .webp … | caption built from EXIF | normalized image (≤2048 px) | EXIF, **GPS**, **drone XMP** (DJI relative altitude, gimbal pitch, yaw) |
| video | .mp4 .mov .mkv … | transcript in 30 s windows* | keyframes (one every ~5 s, max 24) + **30 s low-res clips** | duration, resolution, fps, GPS from phone/drone metadata |
| audio | .mp3 .m4a .wav … | transcript in 30 s windows* | 30 s wav segments (16 kHz mono) | duration, codec |
| archive | .zip | file listing | – | every member becomes a child package |
| text / web / data | .txt .md .json .html … | markdown split by heading, html stripped | – | links, json keys |
| unknown | anything else | text if the file is mostly printable | – | stored with a warning |

\* In AI mode, transcripts (and video clip descriptions, and text from scanned pages) come from the media pass via Jev on OpenRouter. In "Convert only" mode, transcripts need `pip install faster-whisper`, which runs locally. Without it, audio and video still produce segments, and the manifest gets a warning plus `"transcript": "pending"`.

## Context and markups: making the content meaningful

A file on its own rarely says *why* it matters. "Make the canopy lighter" lives in the Teams message, not in the screenshot. The converter captures that context and builds it into the vectors.

**Context** (UI side panel, or `--note --author --role --channel` on the command line):

```jsonc
"context": { "author": "A. Chen", "author_role": "project lead", "channel": "teams",
             "note": "Client wants the canopy lighter - circled.", "date": "2026-11-14",
             "intent": "markup",          // optional: force markup / "reference" to skip detection
             "refers_to": "uep_…" }       // optional: the original being marked up (used only to cut out the strokes)
```

- The note becomes its own chunk (`role: "context"`) and is folded into every image caption. A vector then says *who asked for what*, not just what the picture looks like.
- Emails fill the context automatically: the sender becomes the author and the body becomes the message. Attachments inherit it.
- Re-converting a file without new context keeps the old context.
- In the UI: **Ctrl+V** pastes a screenshot straight from Teams/Outlook/Snipping Tool. Pasting *text* (with nothing selected) drops it into the note. From/role/via are remembered; the note clears after each drop.

**Markups** (`kind: "markup"`): an image where someone drew on a render/photo/drawing.

| How the marks are found | When |
| --- | --- |
| **diff** against the original | the original is in the library (perceptual-hash match) and has the same framing |
| **aligned-diff**: OpenCV ORB features + homography, then diff | screenshots, crops, rescales, pictures inside a Teams/Slack window |
| **colour** strokes (red / magenta, thin, rare in the image) | no original available |
| **pdf-annotations**: exact Bluebeam/Acrobat comments (author, text, type, replies) | PDFs with markups |

Each marked area becomes a `role: "markup_region"` chunk: a cropped image plus text naming the position, pen colour, author and request. If the markup sits on one of our **Rhino views**, it also names the **model layers under the mark** (from the per-layer renders), e.g. *"covering model layer(s) SRF_PAVE"*. That ties a client comment to model elements. Handwritten text isn't read locally (`markup_text: "pending"`); a vision model downstream can fill it in.

**Links**: the converter does not decide what relates to what. The only links are physical containment:

```jsonc
"links": [
  { "type": "part_of",  "target": "uep_88cec6feafc7" },     // attachment of an email / file in a zip
  { "type": "contains", "target": "uep_a185711027d6" }
]
```

A markup records which original it was drawn on as a fact, `metadata.markup.drawn_on` (`package_id`, `chunk_id`, `title`).

**Entities** (`metadata.entities`) are normalised names the graph can join on exactly, complementing embedding similarity: `rfi` (rfi-012), `level` (level-6; ranges expanded), `elevation` (north-elevation), `grid` (grid-B4), `sheet` (A-101), `date` (nov-20, 2026-11-14), `person` (emails), `regulation` (laanc, part 107, tfr), `element` (canopy, parapet, roof, crane…). They are extracted facts; whether two packages sharing `level-6` + `north-elevation` belong together is for the graph to decide.

## Package spec (`uep/0.1`)

**`manifest.json`** describes one node:

```jsonc
{
  "schema": "uep/0.1",
  "id": "uep_d40459f945dd",            // first 12 hex of the file's sha256 -> same bytes = same id (dedup)
  "kind": "rhino_model",               // see table above
  "title": "tower_site",
  "description": "Rhino 3D model ... 14 objects on 4 layers ...",   // human/embeddable summary
  "source": { "filename", "extension", "mime", "size_bytes", "sha256", "ingested_at",
              "aliases": ["every filename this same content arrived as"] },
  "modalities": ["text", "image"],
  "tags": { "values": ["geometry", "kind:rhino_model", "from:client", "channel:teams", ...], "suggested_by": "rules" },
  "context": { "author", "author_role", "channel", "note", "date", "intent", "refers_to" },   // see above
  "metadata": { ...kind-specific...,
                "entities": { "level": ["level-6"], "rfi": ["rfi-012"], ... },
                "markup": { "regions", "positions", "colours", "method", "layers", "drawn_on", "markup_text" },  // markups only
                "parent_id": "uep_…", "parent_ids": ["uep_…"] },   // set when it came from an email/zip
  "links": [ { "type": "part_of" | "contains", "target": "uep_…" } ],     // containment only
  "agent": { "title", "summary", "counts", "markup_text", "model", "usage" },   // only if read by the AI
  "thumbnail": "assets/view_axonometric.png",
  "chunk_count": 17,
  "children": ["uep_…"],               // attachments / zip members, each its own package
  "warnings": ["..."]                  // anything skipped or approximated
}
```

**`chunks.jsonl`** has one embeddable unit per line:

```jsonc
{
  "id": "uep_d40459f945dd:0009",       // stable: package id + index
  "package_id": "uep_d40459f945dd",
  "index": 9,
  "modality": "image",                 // text | image | audio | video
  "text": "Axonometric view of Rhino model 'tower_site'. Overall extents 80 x 70 x 40.2 meters ...",
  "asset": "assets/view_axonometric.png",   // null for text chunks
  "mime": "image/png",
  "role": "snapshot",                  // summary | context | header | body | quoted | page | table | slide | layer | annotation
                                       // | metadata | snapshot | figure | keyframe | segment | transcript | attachment
                                       // | markup | markup_region
  // image chunks also carry meta.dhash (64-bit perceptual hash) for "same picture" lookups
  "locator": { "view": "axonometric" },     // where in the source: page / section / sheet / rows / slide / layer / view / t / t_start,t_end
  "meta": {}
}
```

Rules the embedding side can rely on:

- **Every chunk has `text`**. Media chunks carry a caption or context line, so a text-only model can embed everything, and a multimodal model (e.g. Gemini Embedding 2) can embed `asset` and fall back to `text`.
- **Chunk 0 is always `role: "summary"`**: title + description, a compact vector for the whole node.
- Text chunks are about 1,500 characters max, split on paragraph or sentence boundaries with about 150 characters of overlap.
- `locator` lets the graph/UI jump back to the exact page, layer, view or timestamp.
- `converter_output/index.jsonl` lists every package (id, kind, title, filename, modalities, parent, children). It's the entry point for batch embedding.
- Tags are simple keyword rules (`suggested_by: "rules"`) meant as a starting point. The tagging model should replace or extend them.

## Rhino notes

- Snapshots come from the **render meshes saved in the .3dm**. Files saved with *Save Small*, or written by scripts, have none. Those surfaces are drawn from their untrimmed UV grid, so openings/trims don't show and a warning is added. To get accurate images, save from Rhino normally (shaded/rendered viewport once).
- Hidden layers and hidden objects are left out of the images but still counted in the text.
- Block instances are drawn with their transforms (nested up to 4 levels).
- Renders are 1280×960 PNG with flat shading in layer colours. In per-layer views the layer is orange and everything else is ghosted grey.

## Adding a format

Add a handler anywhere in `converter/handlers/` and import it in `handlers/__init__.py`:

```python
from ..core import Package
from ..engine import register, Context

@register("point_cloud", ".e57", ".las")
def convert_pointcloud(pkg: Package, ctx: Context) -> None:
    pkg.metadata["points"] = ...
    pkg.add_text("Point cloud of ...", role="body")
    rel = pkg.add_asset_bytes("top.png", png_bytes)
    pkg.add_image(rel, "Top view of the point cloud", role="snapshot", locator={"view": "top"})
    # ctx.convert_child(bytes, "inner.pdf", pkg)  -> for embedded files
```

## Not covered yet

- Local OCR for scanned PDFs (AI mode reads them via the media pass; Convert only still renders pages as images for a vision embedder)
- Slide images for .pptx (needs PowerPoint/LibreOffice). Embedded media is extracted instead.
- Revit (.rvt), IFC, DWG, point clouds (.e57/.las), drone flight logs (.srt telemetry sidecars, DJI .txt)
- HEIC photos (`pip install pillow-heif` would add them)
