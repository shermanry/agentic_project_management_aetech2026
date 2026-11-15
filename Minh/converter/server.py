"""Local drag-and-drop UI + JSON API. Runs on 127.0.0.1 only. "Convert only" keeps everything on this
machine; the agent endpoints send content to OpenRouter (see agent.py).

    POST /api/convert              multipart files -> list of manifests (local only)
    POST /api/ask                  prompt + optional files -> agent extraction (prompt alone = note / links / research)
    POST /api/packages/{id}/agent/undo   remove the AI extraction from a package
    GET  /api/agent                agent availability and models
    GET  /api/packages             library index
    GET  /api/packages/{id}        manifest + chunks
    GET  /api/packages/{id}/zip    the package as a zip
    DELETE /api/packages/{id}      remove a package
    GET  /files/{id}/...           assets
    GET  /api/formats              supported extensions
"""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .core import zip_package
from .engine import convert_file, supported_extensions, _INDEX_LOCK

STATIC = Path(__file__).parent / "static"


def create_app(out_root: str | Path) -> FastAPI:
    out = Path(out_root).resolve()
    out.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Universal Embedding Package converter")

    def pkg_dir(pid: str) -> Path:
        if not pid.startswith("uep_") or "/" in pid or "\\" in pid or ".." in pid:
            raise HTTPException(400, "bad id")
        d = out / pid
        if not (d / "manifest.json").exists():
            raise HTTPException(404, "not found")
        return d

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/formats")
    def formats():
        return supported_extensions()

    @app.post("/api/convert")
    def convert(files: list[UploadFile] = File(...), note: str = Form(""), author: str = Form(""),
                author_role: str = Form(""), channel: str = Form(""), date: str = Form(""),
                intent: str = Form(""), refers_to: str = Form("")):
        context = {"note": note.strip(), "author": author.strip(), "author_role": author_role, "channel": channel,
                   "date": date, "intent": intent, "refers_to": refers_to if refers_to.startswith("uep_") else ""}
        results = []
        for f in files:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
                name = Path(f.filename or "upload.bin").name
                tmp = Path(td) / name
                with open(tmp, "wb") as fh:
                    shutil.copyfileobj(f.file, fh)
                results.append(convert_file(tmp, out, original_name=name, context=context))
        return results

    # ---------------- agent: one prompt + files, everything else automatic
    @app.get("/api/agent")
    def agent_info():
        from . import agent
        return {"available": agent.available(), "agent_model": agent.agent_model(), "router_model": agent.router_model()}

    @app.post("/api/ask")
    def ask(prompt: str = Form(""), files: list[UploadFile] | None = File(None), package_ids: str = Form("")):
        from . import agent
        if not agent.available():
            raise HTTPException(400, "No OPENROUTER_API_KEY in .env: use 'Convert only' or add the key")
        try:
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
                saved = []
                for i, f in enumerate(files or []):
                    name = Path(f.filename or "upload.bin").name
                    sub = Path(td) / str(i)
                    sub.mkdir()
                    tmp = sub / name
                    with open(tmp, "wb") as fh:
                        shutil.copyfileobj(f.file, fh)
                    saved.append((tmp, name))
                text_only = not saved and not package_ids.strip() and prompt.strip()
                result = agent.ask(out, prompt.strip(), saved,
                                   lambda p, o, n, c: convert_file(p, o, original_name=n, context=c)) \
                    if (saved or text_only) else {"prompt": prompt, "plan": None, "items": [], "cost_usd": 0}
            # run the agent on existing packages too ("re-read this with my prompt")
            for pid in [p for p in package_ids.split(",") if p.strip()]:
                m = agent.understand(out, pkg_dir(pid.strip()).name, prompt.strip())
                ag = m.get("agent") or {}
                result["items"].append({"id": m["id"], "filename": m["source"]["filename"], "kind": m["kind"],
                                        "thumbnail": m.get("thumbnail"), "agent": ag, "error": None})
                result["cost_usd"] = round(result.get("cost_usd", 0) + ((ag.get("usage") or {}).get("cost") or 0), 4)
            return result
        except agent.AgentError as e:
            raise HTTPException(502, str(e))

    # ---------------- linked folders: one root folder (local path or Google Drive link) -> every file a node
    @app.post("/api/links")
    def link_folder(source: str = Form(...), mode: str = Form("agent"), watch: bool = Form(False),
                    forward_url: str = Form(""), prompt: str = Form("")):
        from . import sources, agent
        if mode == "agent" and not agent.available():
            mode = "local"
        try:
            job = sources.start(out, source, mode=mode, watch=watch, forward_url=forward_url.strip() or None,
                                prompt=prompt.strip())
        except ValueError as e:
            raise HTTPException(400, str(e))
        return job.public()

    @app.get("/api/links")
    def links():
        from . import sources
        return [j.public() for j in sources.JOBS.values()]

    @app.get("/api/links/{job_id}")
    def link_status(job_id: str):
        from . import sources
        job = sources.JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "no such link")
        return job.public()

    @app.post("/api/links/{job_id}/stop")
    def link_stop(job_id: str):
        from . import sources
        job = sources.stop(job_id)
        if not job:
            raise HTTPException(404, "no such link")
        return job.public()

    @app.post("/api/packages/{pid}/agent/undo")
    def agent_undo(pid: str):
        """Remove the AI extraction from a package; the local extraction stays."""
        from . import agent
        return agent.undo(out, pkg_dir(pid).name)

    @app.get("/api/packages")
    def packages():
        idx = out / "index.jsonl"
        if not idx.exists():
            return []
        rows = [json.loads(l) for l in idx.read_text(encoding="utf-8").splitlines() if l.strip()]
        rows = [r for r in rows if (out / r["id"] / "manifest.json").exists()]
        for r in rows:
            m = json.loads((out / r["id"] / "manifest.json").read_text(encoding="utf-8"))
            r["thumbnail"] = m.get("thumbnail")
            r["warnings"] = len(m.get("warnings", []))
            ag = m.get("agent")
            if ag:
                r["agent"] = {k: ag.get(k) for k in ("title", "summary")}
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    @app.get("/api/packages/{pid}")
    def package(pid: str):
        d = pkg_dir(pid)
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        return {"manifest": m, "chunks": chunks}

    @app.get("/api/packages/{pid}/zip")
    def package_zip(pid: str):
        d = pkg_dir(pid)
        z = Path(tempfile.gettempdir()) / f"{pid}.zip"
        zip_package(d, z)
        return FileResponse(z, filename=f"{pid}.zip", media_type="application/zip")

    @app.delete("/api/packages/{pid}")
    def delete(pid: str):
        d = pkg_dir(pid)
        shutil.rmtree(d)
        idx = out / "index.jsonl"
        with _INDEX_LOCK:
            if idx.exists():
                keep = [l for l in idx.read_text(encoding="utf-8").splitlines() if l.strip() and json.loads(l)["id"] != pid]
                idx.write_text("".join(l + "\n" for l in keep), encoding="utf-8")
        return {"deleted": pid}

    app.mount("/files", StaticFiles(directory=out), name="files")
    return app
