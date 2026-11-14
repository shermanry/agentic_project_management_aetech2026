"""Agent layer: one prompt + files in, a filled-in, linked node out. Nobody fills forms.

    prompt + files
      1. interpret   (fast model)  prompt -> per-file context: who, channel, intent, the message, what it refers to
      2. convert     (local)       the deterministic converter, with that context
      3. understand  (vision model) reads text + the most informative images and returns the MEANINGFUL parts:
                                    summary, node type (team taxonomy), importance, key statements, figures worth
                                    keeping (with crops), what's handwritten on markups, links to existing nodes
      4. write back                 everything the model adds is marked suggested_by="agent:<model>" and
                                    status="suggested" -> accept or undo in the UI

The local facts (layers, EXIF, PDF comments, pixel-exact markup regions) are never overwritten; the agent
adds chunks at the END of chunks.jsonl (so existing chunk ids stay stable) and an `agent` section in the
manifest. Undo removes exactly those additions.

Config (.env at repo root, see .env.example):
    OPENROUTER_API_KEY        required
    CONVERTER_AGENT_MODEL     default anthropic/claude-sonnet-5.5   (vision, reads the files)
    CONVERTER_ROUTER_MODEL    default anthropic/claude-haiku-5.5    (reads the prompt)
    CONVERTER_ALLOW_DATA_COLLECTION  default "deny": only providers that don't store/train on requests
    CONVERTER_RESEARCH_MODEL  default = CONVERTER_AGENT_MODEL (web research for text-only prompts)
    CONVERTER_RESEARCH_RESULTS default 6 web results per research request

Text-only prompts (no files) are handled too: a pasted conversation becomes a note, links are fetched,
and "find out / look up ..." requests run a web search with citations (see text_intake()).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from .core import now_iso
from .engine import _update_index

OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"
NODE_TYPES = ["decision", "discovery", "event", "data_feed", "deliverable", "blocker", "constraint", "document"]
IMPORTANCE = ["low", "medium", "high", "critical"]
LINK_TYPES = ["relates_to", "answers", "asks_about", "supersedes", "depends_on", "marks_up", "same_topic", "contradicts"]
MAX_IMAGES = 10
MAX_TEXT_CHARS = 24_000
LIBRARY_BRIEF_MAX = 40


# ---------------------------------------------------------------- config / http
def _load_dotenv() -> None:
    for parent in Path(__file__).resolve().parents:
        env = parent / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


_load_dotenv()


def available() -> bool:
    return bool(os.environ.get("OPENROUTER_API_KEY"))


def agent_model() -> str:
    return os.environ.get("CONVERTER_AGENT_MODEL", "anthropic/claude-sonnet-5.5")


def router_model() -> str:
    return os.environ.get("CONVERTER_ROUTER_MODEL", "anthropic/claude-haiku-5.5")


class AgentError(RuntimeError):
    pass


def chat_json(model: str, messages: list[dict], max_tokens: int = 4000) -> tuple[dict, dict]:
    """One chat completion that must return a JSON object. Returns (parsed, usage)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise AgentError("OPENROUTER_API_KEY is not set (copy .env.example to .env at the repo root)")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.2,
            "response_format": {"type": "json_object"}, "usage": {"include": True},
            "provider": {"data_collection": os.environ.get("CONVERTER_ALLOW_DATA_COLLECTION", "deny")}}
    last = None
    for attempt in range(3):
        req = urllib.request.Request(OPENROUTER_CHAT, data=json.dumps(body).encode(), method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json",
            "X-Title": "UEP converter agent"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}: {e.read()[:400].decode(errors='replace')}"
            if e.code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(2 * (attempt + 1)); continue
            raise AgentError(f"OpenRouter {last}") from None
        except urllib.error.URLError as e:
            raise AgentError(f"could not reach OpenRouter: {e.reason}") from None
        if "error" in data:
            last = str(data["error"])[:400]
            if attempt < 2:
                time.sleep(2); continue
            raise AgentError(f"OpenRouter error: {last}")
        text = data["choices"][0]["message"].get("content") or ""
        try:
            return _parse_json(text), data.get("usage", {})
        except ValueError:
            last = f"model did not return JSON: {text[:200]}"
            messages = messages + [{"role": "assistant", "content": text},
                                   {"role": "user", "content": "Return ONLY the JSON object, no prose."}]
            body["messages"] = messages
    raise AgentError(last or "agent failed")


def _parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("no JSON object")
    return json.loads(text[start:end + 1])


# ---------------------------------------------------------------- library
def _read_manifest(out: Path, pid: str) -> dict | None:
    p = out / pid / "manifest.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def library_brief(out: Path, focus_entities: dict | None = None, exclude: set[str] | None = None,
                  limit: int = LIBRARY_BRIEF_MAX) -> list[dict]:
    """Compact list of existing nodes the model can link to. Nodes sharing entities with the
    incoming file come first, then the most recent."""
    rows = []
    idx = out / "index.jsonl"
    if not idx.exists():
        return rows
    want = {f"{k}:{v}" for k, vs in (focus_entities or {}).items() for v in vs if k != "element"}
    for line in idx.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if exclude and r["id"] in exclude:
            continue
        m = _read_manifest(out, r["id"])
        if not m:
            continue
        ents = m.get("metadata", {}).get("entities", {})
        have = {f"{k}:{v}" for k, vs in ents.items() for v in vs}
        ag = m.get("agent") or {}
        rows.append({
            "id": m["id"], "kind": m["kind"], "title": ag.get("title") or m["title"],
            "summary": (ag.get("summary") or m.get("description") or "")[:240],
            "node_type": ag.get("node_type"), "from": m.get("context", {}).get("author"),
            "project": m.get("context", {}).get("project"),
            "entities": sorted(have)[:12], "_score": len(want & have), "_t": r.get("updated_at", ""),
        })
    rows.sort(key=lambda r: (r["_score"], r["_t"]), reverse=True)
    return [{k: v for k, v in r.items() if not k.startswith("_") and v} for r in rows[:limit]]


# ---------------------------------------------------------------- 1. interpret the prompt
INTERPRET_SYSTEM = """You route files into a drone-survey / architecture project knowledge graph.
The user gives ONE free-text prompt and some files. Work out, for each file, the context a person
would otherwise have to type into a form. Be literal: only state what the prompt or filenames support.

Return JSON:
{
  "files": [{
     "filename": str,
     "author": str|null,          // who sent / drew / wrote it, e.g. "J. Smith" or "client"
     "author_role": "client"|"project lead"|"team"|"contractor"|"consultant"|"me"|null,
     "channel": "email"|"teams"|"slack"|"meeting"|"site"|"whatsapp"|null,
     "note": str|null,            // the message/request that came WITH the file, in plain words (not the user's instruction to you)
     "intent": "markup"|"reference"|null,   // markup = someone drew on it to request a change
     "refers_to": str|null,       // id of an existing library node this file is about / marks up, only if clearly indicated
     "project": str|null          // project name if the prompt names one, e.g. "Pier 54"
  }],
  "focus": str|null               // what the user wants pulled out, e.g. "structural comments only"; null if not specified
}"""


def interpret(prompt: str, filenames: list[str], library: list[dict]) -> tuple[dict, dict]:
    msg = (f"PROMPT:\n{prompt or '(none)'}\n\nFILES:\n" + "\n".join(f"- {f}" for f in filenames) +
           "\n\nEXISTING LIBRARY NODES (id, kind, title):\n" +
           "\n".join(f"- {r['id']} [{r['kind']}] {r['title']}" for r in library[:LIBRARY_BRIEF_MAX]))
    out, usage = chat_json(router_model(), [{"role": "system", "content": INTERPRET_SYSTEM},
                                            {"role": "user", "content": msg}], max_tokens=1500)
    ids = {r["id"] for r in library}
    by_name = {f.get("filename"): f for f in out.get("files", []) if isinstance(f, dict)}
    files = []
    for name in filenames:
        f = by_name.get(name) or (out.get("files") or [{}])[0] if len(filenames) == 1 else by_name.get(name, {})
        f = dict(f or {})
        if f.get("refers_to") not in ids:
            f["refers_to"] = None
        if f.get("intent") not in ("markup", "reference"):
            f["intent"] = None
        files.append({"filename": name, **{k: f.get(k) for k in ("author", "author_role", "channel", "note", "intent", "refers_to", "project")}})
    return {"files": files, "focus": out.get("focus")}, usage


# ---------------------------------------------------------------- 1b. text-only prompts: note / links / research
URL_RE = re.compile(r"https?://[^\s<>\"'`)\]]+", re.I)
MAX_FETCH_BYTES = 80_000_000
_EXT_BY_TYPE = {"text/html": ".html", "application/xhtml+xml": ".html", "application/pdf": ".pdf", "text/plain": ".txt",
                "text/markdown": ".md", "application/json": ".json", "text/csv": ".csv", "image/jpeg": ".jpg",
                "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif", "video/mp4": ".mp4",
                "audio/mpeg": ".mp3", "audio/wav": ".wav", "application/zip": ".zip",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx"}

TEXT_SYSTEM = """The user typed text into a project knowledge-graph intake box WITHOUT attaching files.
Decide what the text is:
- "note": the text itself is content worth keeping (a pasted conversation, chat thread, email body, meeting
  notes, requirements, a site observation). Keep the content verbatim in note_text, minus any instruction to you
  such as "add this to the tree".
- "research": a request to look something up / collect information (e.g. "find the FAA rules for heliports near
  Pier 54"). Write a precise web search query.
- "links": the text is mainly URLs to fetch, plus maybe an instruction.
Return JSON: {"mode": "note"|"research"|"links", "title": str (short, specific), "query": str|null,
 "note_text": str|null, "author": str|null, "author_role": "client"|"project lead"|"team"|"contractor"|"consultant"|"me"|null,
 "channel": "email"|"teams"|"slack"|"meeting"|"site"|"whatsapp"|null, "project": str|null}"""

RESEARCH_SYSTEM = """You research for a drone-survey / architecture project team. Use the web results.
Write a concise, factual brief in Markdown: what the answer is, the specific rules / numbers / dates that matter,
and what the team should check or decide. Cite sources inline as [n] matching the numbered source list you are
given via citations. Say clearly when something is uncertain or varies by location. No filler."""


def _slug(s: str, n: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_")[:n] or "note"


def fetch_url(url: str, dest_dir: Path) -> tuple[Path, str]:
    """Download one link into dest_dir. Returns (path, filename). Only http(s), size-capped."""
    if not url.lower().startswith(("http://", "https://")):
        raise AgentError(f"not a web link: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; UEP-converter/0.1)",
                                               "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            data = r.read(MAX_FETCH_BYTES + 1)
            final = r.geturl()
    except urllib.error.HTTPError as e:
        raise AgentError(f"{url} -> HTTP {e.code}") from None
    except urllib.error.URLError as e:
        raise AgentError(f"could not open {url}: {e.reason}") from None
    if len(data) > MAX_FETCH_BYTES:
        raise AgentError(f"{url} is larger than {MAX_FETCH_BYTES // 1_000_000} MB")
    from urllib.parse import urlparse, unquote
    u = urlparse(final)
    base = Path(unquote(u.path)).name
    ext = Path(base).suffix.lower()
    if not ext or (ctype in _EXT_BY_TYPE and ext not in _EXT_BY_TYPE.values() and ctype != "application/octet-stream"):
        ext = _EXT_BY_TYPE.get(ctype, ext or ".bin")
        base = _slug(f"{u.netloc}{u.path}") + ext
    name = base if base.lower().endswith(ext) else base + ext
    p = dest_dir / name
    p.write_bytes(data)
    return p, name


def research(query: str) -> tuple[str, list[dict], dict]:
    """Web search through OpenRouter's web plugin. Returns (markdown brief, sources, usage)."""
    key = os.environ.get("OPENROUTER_API_KEY")
    body = {"model": os.environ.get("CONVERTER_RESEARCH_MODEL", agent_model()), "max_tokens": 2500, "temperature": 0.2,
            "usage": {"include": True}, "plugins": [{"id": "web", "max_results": int(os.environ.get("CONVERTER_RESEARCH_RESULTS", "6"))}],
            "provider": {"data_collection": os.environ.get("CONVERTER_ALLOW_DATA_COLLECTION", "deny")},
            "messages": [{"role": "system", "content": RESEARCH_SYSTEM}, {"role": "user", "content": query}]}
    req = urllib.request.Request(OPENROUTER_CHAT, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "UEP converter agent"})
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise AgentError(f"OpenRouter research HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    if "error" in data:
        raise AgentError(f"OpenRouter research error: {str(data['error'])[:300]}")
    msg = data["choices"][0]["message"]
    sources, seen = [], set()
    for a in msg.get("annotations") or []:
        c = a.get("url_citation") or {}
        if c.get("url") and c["url"] not in seen:
            seen.add(c["url"])
            sources.append({"url": c["url"], "title": c.get("title") or c["url"]})
    return (msg.get("content") or "").strip(), sources, data.get("usage", {})


def text_intake(prompt: str, dest_dir: Path) -> tuple[list[tuple[Path, str]], list[dict], dict, list[str]]:
    """Turn a text-only prompt into files. Returns (files, per-file context overrides, usage, errors)."""
    urls = list(dict.fromkeys(u.rstrip(".,;") for u in URL_RE.findall(prompt)))
    plan, usage = chat_json(router_model(), [{"role": "system", "content": TEXT_SYSTEM},
                                             {"role": "user", "content": prompt}], max_tokens=4000)
    who = {k: plan.get(k) for k in ("author", "author_role", "channel", "project") if plan.get(k)}
    files, ctxs, errors = [], [], []
    mode = plan.get("mode") if plan.get("mode") in ("note", "research", "links") else ("links" if urls else "note")
    if urls and mode != "note":
        instruction = URL_RE.sub("", prompt).strip()
        for u in urls[:8]:
            try:
                p, name = fetch_url(u, dest_dir)
                files.append((p, name))
                ctxs.append({**who, "source_url": u, "note": instruction or None})
            except AgentError as e:
                errors.append(str(e))
        if files:
            return files, ctxs, usage, errors
        mode = "note"
    title = plan.get("title") or "Note"
    stamp = time.strftime("%Y-%m-%d")
    if mode == "research":
        query = plan.get("query") or prompt
        brief, sources, u2 = research(query)
        usage = {"cost": (usage.get("cost") or 0) + (u2.get("cost") or 0)}
        md = f"# {title}\n\n_Research brief · {stamp} · query: {query}_\n\n{brief}\n"
        if sources:
            md += "\n## Sources\n" + "\n".join(f"{i}. [{s['title']}]({s['url']})" for i, s in enumerate(sources, 1)) + "\n"
        p = dest_dir / f"research_{_slug(title)}.md"
        p.write_text(md, encoding="utf-8")
        files.append((p, p.name))
        ctxs.append({**who, "note": prompt, "channel": who.get("channel") or "web research",
                     "source_urls": [s["url"] for s in sources]})
    else:
        body = (plan.get("note_text") or prompt).strip()
        p = dest_dir / f"note_{_slug(title)}.md"
        p.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
        files.append((p, p.name))
        ctxs.append({**who})
    return files, ctxs, usage, errors


# ---------------------------------------------------------------- 3. understand a package
UNDERSTAND_SYSTEM = f"""You are the reading layer of a project knowledge graph for drone surveys and architecture projects.
A local converter has already extracted a file into chunks (text) and images (page renders, model views,
photos, markup regions, keyframes). Metadata alone is not useful: your job is to pull out the MEANINGFUL
content a project team would want as nodes, with a pointer back to where it came from.

Rules:
- Use only what is in the material. Never invent people, dates, numbers or decisions.
- Prefer few, high-value items over many weak ones. Skip boilerplate, logos, title blocks, signatures, disclaimers, quoted history that adds nothing.
- Every insight must be self-contained (understandable without the file) and cite its source chunk id or image number.
- node_type must be one of {NODE_TYPES}:
  decision = a choice someone must make / approve; discovery = new information that may change an assumption;
  event = something at a time (flight, meeting, deadline window); data_feed = a live/updating source;
  deliverable = something owed to someone by a date; blocker = work waiting on a person/party;
  constraint = a rule or limit (wind limit, airspace, permit rule); document = reference material.
- figures: choose images that carry real information (site plans, sections, photos of conditions, marked-up areas,
  informative model views). Optional crop = [x0,y0,x1,y1] in 0..1 of that image, to cut away margins/UI/title blocks.
- markup_text: transcribe any handwriting or typed notes drawn ON images (markups), per image.
- links: only to ids from the LIBRARY list, only when there is a concrete reason. Types: {LINK_TYPES}.
- The user's prompt and focus take priority over everything else.

Return JSON:
{{
  "title": str,                         // short, specific, human title for the node
  "summary": str,                       // 1-3 sentences: what this is and why it matters to the project
  "node_type": str,
  "importance": "low"|"medium"|"high"|"critical",
  "importance_reason": str,
  "needs_decision": bool,
  "decision_question": str|null,        // the actual question to decide, if any
  "owner": str|null, "due": str|null,   // only if stated
  "tags": [str],                        // 3-8 lowercase topic tags
  "insights": [{{"text": str, "node_type": str, "why": str, "source_chunk": str|null, "image": int|null, "page": int|null}}],
  "figures": [{{"image": int, "caption": str, "why": str, "crop": [number,number,number,number]|null}}],
  "markup_text": [{{"image": int, "text": str}}],
  "links": [{{"target": str, "type": str, "why": str, "confidence": number}}]
}}"""

_IMAGE_PRIORITY = {"markup": 0, "markup_region": 1, "image": 2, "snapshot": 3, "page": 4, "figure": 5, "attachment": 2,
                   "keyframe": 6}


def _pick_images(chunks: list[dict]) -> list[dict]:
    imgs = [c for c in chunks if c["modality"] == "image" and c.get("asset")
            and not (c["meta"].get("suggested_by", "").startswith("agent"))]
    # model layer highlight views are near-duplicates of the main view: keep at most 2
    layer_views = [c for c in imgs if c["locator"].get("layer")]
    imgs = [c for c in imgs if not c["locator"].get("layer")] + layer_views[:2]
    keyframes = [c for c in imgs if c["role"] == "keyframe"]
    if len(keyframes) > 4:  # evenly spaced sample
        keep = {id(keyframes[round(i * (len(keyframes) - 1) / 3)]) for i in range(4)}
        imgs = [c for c in imgs if c["role"] != "keyframe" or id(c) in keep]
    imgs.sort(key=lambda c: (_IMAGE_PRIORITY.get(c["role"], 9), c["index"]))
    return imgs[:MAX_IMAGES]


def _image_part(path: Path, max_side: int = 1024) -> dict:
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}


def _material(manifest: dict, chunks: list[dict]) -> str:
    md = manifest.get("metadata", {})
    keep = {k: md[k] for k in ("entities", "markup", "annotations", "drone", "location", "exif", "units", "size_m",
                                "object_types", "named_views", "document_user_text", "pages", "slides", "sheets",
                                "duration_s", "attachments", "date_iso", "from", "to", "subject") if k in md}
    if "layers" in md:
        keep["layers"] = [f"{l['path']} ({sum(l.get('objects', {}).values())})" for l in md["layers"] if l.get("objects")][:40]
    head = {"kind": manifest["kind"], "title": manifest["title"], "filename": manifest["source"]["filename"],
            "description": manifest.get("description"), "context": manifest.get("context"), "metadata": keep,
            "warnings": manifest.get("warnings")}
    parts, used = [json.dumps(head, ensure_ascii=False, default=str)[:6000]], 0
    for c in chunks:
        if c["modality"] != "text" or c["role"] == "summary" or (c["meta"].get("suggested_by", "").startswith("agent")):
            continue
        t = c["text"] or ""
        if used + len(t) > MAX_TEXT_CHARS:
            t = t[: max(0, MAX_TEXT_CHARS - used)]
        if not t:
            parts.append("[... more text truncated ...]")
            break
        loc = json.dumps(c["locator"]) if c["locator"] else ""
        parts.append(f"<chunk id=\"{c['id']}\" role=\"{c['role']}\" {loc}>\n{t}\n</chunk>")
        used += len(t)
    return "\n\n".join(parts)


def understand(out: Path, pid: str, prompt: str = "", focus: str | None = None) -> dict:
    d = out / pid
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    images = _pick_images(chunks)
    library = library_brief(out, manifest.get("metadata", {}).get("entities"), exclude={pid})
    content: list[dict] = [{"type": "text", "text":
        f"USER PROMPT: {prompt or '(none)'}\nFOCUS: {focus or '(none)'}\n\n"
        f"LIBRARY (existing nodes you may link to):\n{json.dumps(library, ensure_ascii=False)}\n\n"
        f"EXTRACTED MATERIAL:\n{_material(manifest, chunks)}\n\n"
        f"IMAGES follow, numbered 1..{len(images)}:"}]
    for i, c in enumerate(images, 1):
        content.append({"type": "text", "text": f"IMAGE {i} (chunk {c['id']}, role {c['role']}, "
                                                f"{json.dumps(c['locator'])}): {(c['text'] or '')[:300]}"})
        content.append(_image_part(d / c["asset"]))
    result, usage = chat_json(agent_model(), [{"role": "system", "content": UNDERSTAND_SYSTEM},
                                              {"role": "user", "content": content}], max_tokens=5000)
    return _write_back(out, manifest, chunks, images, result, usage, prompt, focus, {r["id"] for r in library})


# ---------------------------------------------------------------- 4. write back (and undo)
_LOCKS: dict[str, threading.Lock] = {}


def _lock(pid: str) -> threading.Lock:
    return _LOCKS.setdefault(pid, threading.Lock())


def _save(out: Path, manifest: dict, chunks: list[dict]) -> None:
    d = out / manifest["id"]
    manifest["chunk_count"] = len(chunks)
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    (d / "chunks.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False, default=str) + "\n" for c in chunks),
                                    encoding="utf-8")
    _update_index(out, manifest)


def _strip_agent(out: Path, manifest: dict, chunks: list[dict]) -> list[dict]:
    d = out / manifest["id"]
    for c in chunks:
        if c["meta"].get("suggested_by", "").startswith("agent") and c.get("asset", "") and "/agent_" in c["asset"]:
            (d / c["asset"]).unlink(missing_ok=True)
    chunks = [c for c in chunks if not c["meta"].get("suggested_by", "").startswith("agent")]
    manifest.pop("agent", None)
    manifest["links"] = [l for l in manifest.get("links", []) if not l.get("suggested_by", "").startswith("agent")]
    manifest.setdefault("tags", {}).pop("agent_values", None)
    return chunks


def _write_back(out: Path, manifest: dict, chunks: list[dict], images: list[dict], r: dict, usage: dict,
                prompt: str, focus: str | None, library_ids: set[str]) -> dict:
    pid = manifest["id"]
    by = f"agent:{agent_model()}"
    with _lock(pid):
        chunks = _strip_agent(out, manifest, chunks)  # re-running replaces the previous agent pass
        chunk_ids = {c["id"] for c in chunks}
        new: list[dict] = []

        def add(modality, text, role, locator=None, asset=None, mime=None, **meta):
            new.append({"modality": modality, "text": text, "asset": asset, "mime": mime, "role": role,
                        "locator": locator or {}, "meta": {"suggested_by": by, **meta}})

        node_type = r.get("node_type") if r.get("node_type") in NODE_TYPES else "document"
        importance = r.get("importance") if r.get("importance") in IMPORTANCE else "medium"
        title = (r.get("title") or manifest["title"]).strip()
        summary = (r.get("summary") or "").strip()
        add("text", f"{title}\n{summary}" + (f"\nDecision needed: {r['decision_question']}" if r.get("decision_question") else ""),
            "agent_summary", node_type=node_type, importance=importance)

        for ins in (r.get("insights") or [])[:20]:
            if not isinstance(ins, dict) or not ins.get("text"):
                continue
            src = ins.get("source_chunk") if ins.get("source_chunk") in chunk_ids else None
            img = _img(images, ins.get("image"))
            loc = {k: v for k, v in {"page": ins.get("page"), "source_chunk": src,
                                     "source_image": img["id"] if img else None}.items() if v}
            add("text", ins["text"].strip(), "insight", loc,
                node_type=ins.get("node_type") if ins.get("node_type") in NODE_TYPES else node_type, why=ins.get("why"))

        for k, fig in enumerate((r.get("figures") or [])[:8], 1):
            img = _img(images, fig.get("image")) if isinstance(fig, dict) else None
            if not img:
                continue
            asset = img["asset"]
            crop = fig.get("crop")
            if _valid_crop(crop):
                asset = _crop(out / pid, img["asset"], crop, f"agent_figure_{k:02d}.jpg") or asset
            add("image", (fig.get("caption") or "").strip(), "figure", {**img["locator"], "source_chunk": img["id"],
                **({"crop": crop} if _valid_crop(crop) else {})}, asset=asset,
                mime="image/jpeg" if asset.endswith(".jpg") else img.get("mime"), why=fig.get("why"))

        markup_text = []
        for mt in (r.get("markup_text") or [])[:12]:
            img = _img(images, mt.get("image")) if isinstance(mt, dict) else None
            if img and (mt.get("text") or "").strip():
                markup_text.append({"chunk": img["id"], "text": mt["text"].strip()})
                add("text", f"Written on the markup ({img['locator'].get('position', 'image')}): \"{mt['text'].strip()}\"",
                    "markup_text", {"source_chunk": img["id"], **{k: v for k, v in img["locator"].items() if k in ("position", "region", "page")}})

        links = []
        have = {(l["type"], l["target"]) for l in manifest.get("links", [])}
        for l in (r.get("links") or [])[:10]:
            if isinstance(l, dict) and l.get("target") in library_ids and l.get("target") != pid \
                    and (l.get("type"), l.get("target")) not in have:
                have.add((l.get("type"), l.get("target")))
                links.append({"type": l.get("type") if l.get("type") in LINK_TYPES else "relates_to",
                              "target": l["target"], "why": l.get("why"),
                              "confidence": round(float(l.get("confidence") or 0.6), 2),
                              "suggested_by": by, "status": "suggested"})

        base = len(chunks)
        for i, c in enumerate(new):
            c.update({"id": f"{pid}:{base + i:04d}", "package_id": pid, "index": base + i})
        chunks += new
        manifest["links"] = manifest.get("links", []) + links
        manifest.setdefault("tags", {})["agent_values"] = sorted({t.lower() for t in (r.get("tags") or []) if isinstance(t, str)})[:10]
        manifest["agent"] = {
            "status": "suggested", "model": agent_model(), "run_at": now_iso(), "prompt": prompt, "focus": focus,
            "title": title, "summary": summary, "node_type": node_type, "importance": importance,
            "importance_reason": r.get("importance_reason"), "needs_decision": bool(r.get("needs_decision")),
            "decision_question": r.get("decision_question"), "owner": r.get("owner"), "due": r.get("due"),
            "counts": {"insights": sum(c["role"] == "insight" for c in new), "figures": sum(c["role"] == "figure" for c in new),
                       "links": len(links)},
            "markup_text": markup_text,
            "usage": {k: usage.get(k) for k in ("prompt_tokens", "completion_tokens", "cost") if k in usage},
        }
        if manifest.get("metadata", {}).get("markup") and markup_text:
            mk = manifest["metadata"]["markup"]
            if isinstance(mk, dict):
                mk["markup_text"] = " | ".join(m["text"] for m in markup_text)
        _save(out, manifest, chunks)
    return manifest


def _img(images: list[dict], n) -> dict | None:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    return images[n - 1] if 1 <= n <= len(images) else None


def _valid_crop(c) -> bool:
    try:
        x0, y0, x1, y1 = (float(v) for v in c)
    except (TypeError, ValueError):
        return False
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1 and (x1 - x0) * (y1 - y0) < 0.95


def _crop(d: Path, rel: str, crop, name: str) -> str | None:
    try:
        with Image.open(d / rel) as im:
            W, H = im.size
            x0, y0, x1, y1 = (float(v) for v in crop)
            box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
            if box[2] - box[0] < 32 or box[3] - box[1] < 32:
                return None
            im.convert("RGB").crop(box).save(d / "assets" / name, "JPEG", quality=90)
        return f"assets/{name}"
    except Exception:
        return None


def set_status(out: Path, pid: str, action: str) -> dict:
    """accept: mark the agent's additions accepted. undo: remove them."""
    d = out / pid
    with _lock(pid):
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        if action == "undo":
            chunks = _strip_agent(out, manifest, chunks)
        elif action == "accept" and manifest.get("agent"):
            manifest["agent"]["status"] = "accepted"
            manifest["agent"]["accepted_at"] = now_iso()
            for l in manifest.get("links", []):
                if l.get("suggested_by", "").startswith("agent"):
                    l["status"] = "accepted"
        _save(out, manifest, chunks)
    return manifest


# ---------------------------------------------------------------- the whole flow
def ask(out: Path, prompt: str, files: list[tuple[Path, str]], convert) -> dict:
    """files: [(temp path, original name)]; convert: callable(path, out, original_name, context) -> manifest."""
    from concurrent.futures import ThreadPoolExecutor

    import tempfile

    usage_total: list[dict] = []
    errors: list[str] = []
    overrides: list[dict] = [{} for _ in files]
    intake = None
    if not files and prompt.strip():
        # text only: a pasted conversation, links to fetch, or something to research
        intake = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        files, overrides, u0, errors = text_intake(prompt, Path(intake.name))
        usage_total.append(u0)
    try:
        library = library_brief(out)
        plan, u = interpret(prompt, [n for _, n in files], library) if files else ({"files": [], "focus": None}, {})
        usage_total.append(u)
        manifests = []
        for (path, name), ctx, extra in zip(files, plan["files"], overrides):
            context = {k: ctx.get(k) for k in ("author", "author_role", "channel", "note", "intent", "refers_to", "project")}
            context.update({k: v for k, v in extra.items() if v})
            manifests.append(convert(path, out, name, context))
    finally:
        if intake:
            intake.cleanup()

    def run(m):
        try:
            return understand(out, m["id"], prompt, plan.get("focus")), None
        except Exception as e:
            return m, f"{type(e).__name__}: {e}"

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(run, manifests))
    items = []
    for m, err in results:
        ag = m.get("agent") or {}
        usage_total.append(ag.get("usage") or {})
        items.append({"id": m["id"], "filename": m["source"]["filename"], "kind": m["kind"], "thumbnail": m.get("thumbnail"),
                      "agent": ag or None, "error": err,
                      "links": [l for l in m.get("links", []) if l.get("suggested_by", "").startswith("agent") or l["type"] == "marks_up"]})
    cost = sum((u or {}).get("cost") or 0 for u in usage_total)
    return {"prompt": prompt, "plan": plan, "items": items, "errors": errors, "cost_usd": round(cost, 4),
            "models": {"router": router_model(), "agent": agent_model()}}
