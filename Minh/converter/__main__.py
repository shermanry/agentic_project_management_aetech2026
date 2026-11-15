"""Command line:

    python -m converter convert <files or folders...> [-o converter_output]
    python -m converter serve [--port 8765] [-o converter_output]
    python -m converter formats
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .engine import convert_file, supported_extensions

DEFAULT_OUT = Path("converter_output")


def _iter_inputs(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from (f for f in sorted(p.rglob("*")) if f.is_file() and not f.name.startswith("."))
        elif p.is_file():
            yield p
        else:
            print(f"  ! not found: {p}", file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="converter", description="Universal file -> embedding package converter")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert", help="convert files or folders")
    c.add_argument("inputs", nargs="+")
    c.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    c.add_argument("--note", default="", help="the message that came with the file(s)")
    c.add_argument("--author", default="", help="who sent / drew it")
    c.add_argument("--role", default="", help="client | project lead | team | contractor | consultant")
    c.add_argument("--channel", default="", help="email | teams | slack | site | meeting")
    c.add_argument("--intent", default="", choices=["", "markup", "reference"], help="force markup detection on/off")
    c.add_argument("--refers-to", default="", help="package id of the original this marks up")
    s = sub.add_parser("serve", help="run the local drag-and-drop UI")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    sub.add_parser("formats", help="list supported file extensions")
    lk = sub.add_parser("link", help="link a root folder (local path or Google Drive folder link): every file and folder a node")
    lk.add_argument("source")
    lk.add_argument("-o", "--out", type=Path, default=DEFAULT_OUT)
    lk.add_argument("--ai", action="store_true", help="also run the AI reading on every file (needs OPENROUTER_API_KEY)")
    lk.add_argument("--watch", action="store_true", help="keep watching for new or changed files")
    lk.add_argument("--interval", type=int, default=60, help="seconds between checks in watch mode")
    lk.add_argument("--forward", default="", help="also POST each file to this intake URL (e.g. Ryan's /api/intake)")
    lk.add_argument("--note", default="", help="a note attached to every file")
    a = ap.parse_args(argv)

    if a.cmd == "link":
        import time
        from . import sources
        job = sources.start(a.out, a.source, mode="agent" if a.ai else "local", watch=a.watch,
                            forward_url=a.forward or None, prompt=a.note, interval=a.interval)
        last = None
        try:
            while job.status in ("listing", "running", "watching"):
                line = f"  {job.status:9} {job.done + job.skipped + job.failed}/{job.total}  converted {job.done}  " \
                       f"already done {job.skipped}  failed {job.failed}  ${job.cost:.3f}"
                if line != last:
                    print(line, flush=True)
                    last = line
                time.sleep(1)
        except KeyboardInterrupt:
            sources.stop(job.id)
            print("  stopping…")
        for err in job.errors[-20:]:
            print(f"  ! {err}")
        print(f"{job.status}: {job.done} converted, {job.skipped} already done, {job.failed} failed -> {a.out.resolve()} "
              f"(root folder node {job.root_id})")
        return 0 if job.status in ("done", "stopped") else 1

    if a.cmd == "formats":
        by_kind: dict[str, list[str]] = {}
        for ext, kind in supported_extensions().items():
            by_kind.setdefault(kind, []).append(ext)
        for kind, exts in sorted(by_kind.items()):
            print(f"{kind:14} {' '.join(exts)}")
        return 0
    if a.cmd == "convert":
        n = 0
        context = {"note": a.note, "author": a.author, "author_role": a.role, "channel": a.channel,
                   "intent": a.intent, "refers_to": a.refers_to}
        for f in _iter_inputs(a.inputs):
            m = convert_file(f, a.out, context=context)
            n += 1
            warn = f"  ({len(m['warnings'])} warning(s))" if m["warnings"] else ""
            print(f"  {m['id']}  {m['kind']:13} {m['chunk_count']:4} chunks  {'+'.join(m['modalities']):22} {f.name}{warn}")
            for w in m["warnings"]:
                print(f"      - {w}")
        print(f"{n} file(s) -> {a.out.resolve()}")
        return 0
    if a.cmd == "serve":
        import uvicorn
        from .server import create_app
        print(f"Converter UI: http://127.0.0.1:{a.port}   (output: {a.out.resolve()})")
        uvicorn.run(create_app(a.out), host="127.0.0.1", port=a.port, log_level="warning")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
