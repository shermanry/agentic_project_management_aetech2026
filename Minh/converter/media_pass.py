"""Media pass: turn audio, video and image-only pages into text, using a model that takes those inputs natively
(default: Jev Router on OpenRouter, which accepts audio, video, files and images).

Runs inside the AI layer, before the reading step, so the reader sees the words too. "Convert only" never
calls it: the local converter stays offline.

    audio package  -> each 30 s wav segment  -> role "transcript"          (verbatim speech, t_start/t_end)
    video package  -> each 30 s clip         -> role "transcript"          (speech in the clip)
                                             -> role "clip_description"    (what is visible + timestamped moments)
    PDF / drawing  -> pages without a text layer -> role "page_text"       (everything written on the page)

Every chunk it adds has meta.suggested_by = "agent-media:<model>" and meta.media_for = the source chunk id,
so re-reading skips work already done and agent.undo() removes it. Extraction only: it describes what is
there; it never judges relevance or importance.

Config (.env): CONVERTER_MEDIA_MODEL (default typesafe/jev-router), CONVERTER_MEDIA_WORKERS (default 4),
CONVERTER_MEDIA_MAX_ITEMS (default 60 segments / clips / pages per file).
"""
from __future__ import annotations

import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .agent import AgentError, _image_part, _lock, _save, chat_json

TEXT_LAYER_MIN_CHARS = 80   # a PDF page with less text than this is treated as scanned / drawing-only
MAX_VIDEO_BYTES = 18_000_000
MAX_AUDIO_BYTES = 12_000_000


def media_model() -> str:
    return os.environ.get("CONVERTER_MEDIA_MODEL", "typesafe/jev-router")


AUDIO_SYSTEM = """Transcribe the speech in this audio segment verbatim, in its original language.
Keep numbers, names and units exactly as spoken. Mark unclear words as [inaudible]. If there is no speech
(silence, noise, music, a tone), return an empty transcript. Do not summarise or add anything.
Return JSON: {"transcript": str, "language": str|null, "speakers": int|null}"""

VIDEO_SYSTEM = """This is a short clip from a project video (often drone or site footage of buildings).
1. transcript: the speech in the clip verbatim (empty if none).
2. description: 1-3 factual sentences on what is visible: the building or site, which side or element,
   camera movement, conditions (weather, light), people, equipment, visible defects or changes. Only what you can see.
3. moments: notable visible things with the time IN THIS CLIP in seconds (e.g. "crane enters frame", "crack on
   parapet"). Few and factual; empty if nothing stands out.
Do not judge importance. Return JSON:
{"transcript": str, "description": str, "moments": [{"t": number, "text": str}]}"""

PAGE_SYSTEM = """This is one page of a scanned document or drawing with no usable text layer. Transcribe ALL
readable text on it: notes, labels, dimensions, levels, grid lines, title block fields (project, drawing number,
revision, date, scale, author), stamps and handwriting. Keep the reading order: title block last.
Then give a one-sentence description of what the page shows (e.g. "north elevation drawing", "site photo with notes").
Return JSON: {"text": str, "description": str, "title_block": {"project": str|null, "drawing_no": str|null,
"revision": str|null, "date": str|null, "scale": str|null} | null}"""


def _b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _audio_job(d: Path, c: dict) -> dict | None:
    p = d / c["asset"]
    if p.stat().st_size > MAX_AUDIO_BYTES:
        return None
    fmt = p.suffix.lstrip(".").lower() or "wav"
    r, u = chat_json(media_model(), [{"role": "system", "content": AUDIO_SYSTEM}, {"role": "user", "content": [
        {"type": "text", "text": "Audio segment:"},
        {"type": "input_audio", "input_audio": {"data": _b64(p), "format": fmt}}]}], max_tokens=3000)
    text = (r.get("transcript") or "").strip()
    out = []
    if text:
        out.append({"modality": "text", "role": "transcript", "text": text, "locator": dict(c["locator"]),
                    "meta": {"language": r.get("language"), "speakers": r.get("speakers")}})
    return {"chunks": out, "usage": u}


def _video_job(d: Path, c: dict) -> dict | None:
    p = d / c["asset"]
    if p.stat().st_size > MAX_VIDEO_BYTES:
        return None
    r, u = chat_json(media_model(), [{"role": "system", "content": VIDEO_SYSTEM}, {"role": "user", "content": [
        {"type": "text", "text": f"Clip {c['locator'].get('t_start', 0)}s-{c['locator'].get('t_end', '?')}s of the video:"},
        {"type": "video_url", "video_url": {"url": "data:video/mp4;base64," + _b64(p)}}]}], max_tokens=3000)
    t0 = float(c["locator"].get("t_start") or 0)
    out = []
    speech = (r.get("transcript") or "").strip()
    if speech:
        out.append({"modality": "text", "role": "transcript", "text": speech, "locator": dict(c["locator"]), "meta": {}})
    desc = (r.get("description") or "").strip()
    moments = [m for m in (r.get("moments") or []) if isinstance(m, dict) and m.get("text")]
    if desc or moments:
        lines = [desc] if desc else []
        for m in moments:
            try:
                at = t0 + float(m.get("t") or 0)
            except (TypeError, ValueError):
                at = t0
            lines.append(f"{int(at // 60)}:{int(at % 60):02d} {m['text'].strip()}")
        out.append({"modality": "text", "role": "clip_description", "text": "\n".join(lines), "locator": dict(c["locator"]),
                    "meta": {"moments": [{"t": round(t0 + float(m.get("t") or 0), 1), "text": m["text"]} for m in moments
                                         if isinstance(m.get("t"), (int, float))]}})
    return {"chunks": out, "usage": u}


def _page_job(d: Path, c: dict) -> dict | None:
    r, u = chat_json(media_model(), [{"role": "system", "content": PAGE_SYSTEM}, {"role": "user", "content": [
        {"type": "text", "text": f"Page {c['locator'].get('page')}:"}, _image_part(d / c["asset"], max_side=2000)]}],
        max_tokens=4000)
    text = (r.get("text") or "").strip()
    desc = (r.get("description") or "").strip()
    if not text and not desc:
        return {"chunks": [], "usage": u}
    body = (f"{desc}\n\n" if desc else "") + text
    return {"chunks": [{"modality": "text", "role": "page_text", "text": body, "locator": dict(c["locator"]),
                        "meta": {"title_block": r.get("title_block")}}], "usage": u}


def _plan(manifest: dict, chunks: list[dict]) -> list[tuple[str, dict]]:
    done = {c["meta"].get("media_for") for c in chunks if c["meta"].get("media_for")}
    limit = int(os.environ.get("CONVERTER_MEDIA_MAX_ITEMS", "60"))
    jobs: list[tuple[str, dict]] = []
    kind = manifest["kind"]
    have_transcript = any(c["role"] == "transcript" and not c["meta"].get("suggested_by") for c in chunks)
    if kind == "audio" and not have_transcript:
        jobs += [("audio", c) for c in chunks if c["modality"] == "audio" and c.get("asset")]
    if kind == "video":
        jobs += [("video", c) for c in chunks if c["modality"] == "video" and c.get("asset")]
    if manifest["source"]["extension"] == ".pdf":
        text_by_page: dict[int, int] = {}
        for c in chunks:
            if c["modality"] == "text" and c["role"] == "page" and c["locator"].get("page"):
                text_by_page[c["locator"]["page"]] = text_by_page.get(c["locator"]["page"], 0) + len(c["text"] or "")
        jobs += [("page", c) for c in chunks if c["modality"] == "image" and c["role"] == "page" and c.get("asset")
                 and text_by_page.get(c["locator"].get("page"), 0) < TEXT_LAYER_MIN_CHARS]
    return [(k, c) for k, c in jobs if c["id"] not in done][:limit]


def enrich(out: Path, pid: str) -> dict:
    """Run the media pass on one package (idempotent). Returns a small report."""
    d = out / pid
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    jobs = _plan(manifest, chunks)
    if not jobs:
        return {"items": 0}
    fn = {"audio": _audio_job, "video": _video_job, "page": _page_job}

    def run(job):
        kind, c = job
        try:
            return kind, c, fn[kind](d, c), None
        except AgentError as e:
            return kind, c, None, str(e)

    with ThreadPoolExecutor(max_workers=int(os.environ.get("CONVERTER_MEDIA_WORKERS", "4"))) as ex:
        results = list(ex.map(run, jobs))

    by = f"agent-media:{media_model()}"
    new, cost, errors = [], 0.0, []
    for kind, c, res, err in sorted(results, key=lambda r: r[1]["index"]):
        if err:
            errors.append(f"{kind} {c['id']}: {err[:160]}")
            continue
        if not res:
            errors.append(f"{kind} {c['id']}: skipped (too large)")
            continue
        cost += (res["usage"] or {}).get("cost") or 0
        for nc in res["chunks"] or [{"modality": "text", "role": "no_speech", "text": "", "locator": dict(c["locator"]), "meta": {}}]:
            nc["meta"] = {**nc.get("meta", {}), "suggested_by": by, "media_for": c["id"]}
            nc.setdefault("asset", None); nc.setdefault("mime", None)
            new.append(nc)

    with _lock(pid):
        # reload in case something else wrote meanwhile; drop the old reading (it will be redone right after)
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        chunks = [x for x in chunks if not x["meta"].get("suggested_by", "").startswith("agent:")]
        manifest.pop("agent", None)
        base = max((x["index"] for x in chunks), default=-1) + 1
        kept = [n for n in new if n["role"] != "no_speech"]
        marks = [n for n in new if n["role"] == "no_speech"]  # remember "already checked, nothing there"
        for i, n in enumerate(kept + marks):
            n.update({"id": f"{pid}:{base + i:04d}", "package_id": pid, "index": base + i})
        chunks += kept + marks
        mp = manifest.setdefault("media_pass", {"model": media_model(), "items": 0, "cost": 0.0, "errors": []})
        mp["items"] += len(jobs)
        mp["cost"] = round(mp.get("cost", 0) + cost, 5)
        mp["errors"] = (mp.get("errors") or [])[-10:] + errors
        roles = {n["role"] for n in kept}
        cleared = [w for w in manifest.get("warnings", [])
                   if ("transcript" in roles and w.startswith("no transcript")) or ("page_text" in roles and w.startswith("no text layer"))]
        if cleared:  # remembered so undo() can put them back
            mp["cleared_warnings"] = sorted(set(mp.get("cleared_warnings", [])) | set(cleared))
            manifest["warnings"] = [w for w in manifest["warnings"] if w not in cleared]
        if "transcript" in roles:
            mp["previous_transcript_status"] = mp.get("previous_transcript_status", manifest.get("metadata", {}).get("transcript"))
            manifest.setdefault("metadata", {})["transcript"] = f"agent-media:{media_model()}"
        if kept:  # the words found in audio/video/scans feed entity extraction too (levels, sheets, dates…)
            from .entities import extract
            ents = manifest.setdefault("metadata", {}).setdefault("entities", {})
            for k, vs in extract("\n".join(n["text"] for n in kept)).items():
                ents[k] = sorted(set(ents.get(k, [])) | set(vs))
        _save(out, manifest, chunks)
    return {"items": len(jobs), "added": len(kept), "cost": round(cost, 5), "errors": errors}
