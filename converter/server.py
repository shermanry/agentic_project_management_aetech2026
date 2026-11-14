"""Local drag-and-drop UI + JSON API. Runs on 127.0.0.1 only; nothing leaves the machine.

    POST /api/convert              multipart files -> list of manifests
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
        return sorted(rows, key=lambda r: r["updated_at"], reverse=True)

    @app.get("/api/packages/{pid}")
    def package(pid: str):
        d = pkg_dir(pid)
        m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        chunks = [json.loads(l) for l in (d / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
        # backlinks: who points at this package (e.g. "marked up by")
        backlinks = []
        idx = out / "index.jsonl"
        if idx.exists():
            for l in idx.read_text(encoding="utf-8").splitlines():
                if l.strip():
                    r = json.loads(l)
                    for link in r.get("links", []):
                        if link["target"] == pid and link["type"] not in ("part_of", "contains"):
                            backlinks.append({"type": link["type"], "source": r["id"], "title": r["title"]})
        return {"manifest": m, "chunks": chunks, "backlinks": backlinks}

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
