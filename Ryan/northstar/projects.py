"""Example projects: one copy of the app per project, each with its own port, database and data folder.

    projects.json      the list: id, name, seed file, port, database, starting template, live feeds on or off
    ./run_project.sh   start one (it calls `projects.py env <id>` for the settings)
    GET /api/projects  the list for the project menu in the page, with which ones are running

A project's seed file has the same shape as seed.py (PROJECT, PEOPLE, NODES, EDGES) and may add PARTS,
PART_EDGES, SCENARIO (its replay story) and STARTER_REFS. seed.py loads it when NORTHSTAR_PROJECT is set.
"""
from __future__ import annotations

import json
import os
import shlex
import socket
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ID = "east-tower"


def registry() -> list[dict]:
    try:
        return json.loads((HERE / "projects.json").read_text())
    except Exception:
        return []


def entry(project_id: str) -> dict | None:
    return next((p for p in registry() if p["id"] == project_id), None)


def seed_path(p: dict) -> Path:
    """Where the project's seed file is. NORTHSTAR_SEED points the chosen project at a different file."""
    override = os.environ.get("NORTHSTAR_SEED")
    if override and p["id"] == os.environ.get("NORTHSTAR_PROJECT"):
        return Path(override).resolve()
    return (HERE / p["seed"]).resolve()


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.25):
            return True
    except OSError:
        return False


def listing(current_id: str) -> list[dict]:
    """For the page's project menu. `running` is a quick port check; `available` means its seed file is on disk."""
    return [{"id": p["id"], "name": p["name"], "kind": p.get("kind", ""), "port": p["port"], "current": p["id"] == current_id,
             "available": seed_path(p).is_file(), "running": p["id"] == current_id or _listening(p["port"])} for p in registry()]


def _database_url(name: str) -> str:
    base = os.environ.get("DATABASE_BASE", "postgresql://drone:drone@localhost:5433/")
    return base.rstrip("/") + "/" + name


def ensure_database(name: str) -> None:
    """Create the project's database if it is not there yet (the schema is created by the app on first start)."""
    import psycopg
    with psycopg.connect(_database_url("postgres"), autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            c.execute(f'CREATE DATABASE "{name}"')


def env(project_id: str) -> dict:
    p = entry(project_id)
    if not p:
        raise SystemExit(f"No project '{project_id}'. Known: {', '.join(x['id'] for x in registry())}")
    if not seed_path(p).is_file():
        raise SystemExit(f"Project '{project_id}' needs its seed file, which is not on disk: {seed_path(p)}")
    out = {"NORTHSTAR_PROJECT": p["id"], "PORT": str(os.environ.get("PORT") or p["port"]),
           "DATABASE_URL": os.environ.get("DATABASE_URL") or _database_url(p["database"]),
           "NORTHSTAR_TEMPLATE": p.get("template", "starter"), "FEEDS_ENABLED": "1" if p.get("feeds") else "0"}
    if p["id"] != DEFAULT_ID:                       # the default project keeps the plain data/ folder it always had
        out["NORTHSTAR_DATA"] = os.environ.get("NORTHSTAR_DATA") or str(HERE / "data" / p["id"])
    return out


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        for p in listing(""):
            print(f"{p['id']:<16} port {p['port']}  {'running' if p['running'] else 'stopped':<8} {'' if p['available'] else '(seed file missing) '}{p['name']}")
    elif cmd == "env" and len(sys.argv) > 2:
        e = env(sys.argv[2])
        if not os.environ.get("DATABASE_URL"):
            ensure_database(entry(sys.argv[2])["database"])
        print("\n".join(f"export {k}={shlex.quote(v)}" for k, v in e.items()))
    else:
        raise SystemExit("usage: projects.py list | env <project id>")
