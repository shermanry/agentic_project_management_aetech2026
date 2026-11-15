"""Example projects: one copy of the app per project, each with its own port, database and data folder.

    projects.json      the list: id, name, seed file, port, database, starting template, live feeds on or off
    data/projects.local.json   projects people created from the page ("Add new project"); same shape, not in git
    ./run_project.sh   start one (it calls `projects.py env <id>` for the settings)
    GET /api/projects  the list for the project menu in the page, with which ones are running

A project's seed file has the same shape as seed.py (PROJECT, PEOPLE, NODES, EDGES) and may add PARTS,
PART_EDGES, SCENARIO (its replay story) and STARTER_REFS. seed.py loads it when NORTHSTAR_PROJECT is set.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_ID = "east-tower"


LOCAL = HERE / "data" / "projects.local.json"        # projects created from the page; data/ is git-ignored
MAX_PROJECTS = 12                                    # each project is a running copy of the app
FIRST_NEW_PORT = 8120


def _read(path: Path) -> list[dict]:
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def registry() -> list[dict]:
    return _read(HERE / "projects.json") + _read(LOCAL)


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
             "created": bool(p.get("created")), "available": seed_path(p).is_file(), "running": p["id"] == current_id or _listening(p["port"])} for p in registry()]


def create(name: str, people: list[dict], kind: str = "") -> dict:
    """A person adds a project from the page: an empty project with its own seed file, port and database.
    It is written to data/projects.local.json, so it is still listed after a restart."""
    name = " ".join((name or "").split())[:80]
    if not name:
        raise ValueError("The project needs a name")
    reg = registry()
    if len(reg) >= MAX_PROJECTS:
        raise ValueError(f"There are already {len(reg)} projects; {MAX_PROJECTS} is the most this machine runs")
    if any(p["name"].lower() == name.lower() for p in reg):
        raise ValueError(f"There is already a project called “{name}”")
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:32] or "project"
    pid, n = base, 2
    while any(p["id"] == pid for p in reg):
        pid, n = f"{base}-{n}", n + 1
    port = FIRST_NEW_PORT
    while any(p["port"] == port for p in reg) or _listening(port):
        port += 1
    folder = HERE / "data" / "projects" / pid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "seed.py").write_text(
        f'"""Project created from the page on {time.strftime("%Y-%m-%d")}. It starts empty; everything is added in the app."""\n'
        f"PROJECT = {{'id': {pid!r}, 'name': {name!r}}}\nPEOPLE = {people!r}\nNODES = []\nEDGES = []\n")
    p = {"id": pid, "name": name, "kind": kind or "New project", "seed": f"data/projects/{pid}/seed.py", "port": port,
         "database": "drone_" + pid.replace("-", "_"), "template": "empty", "feeds": False, "created": True}
    LOCAL.write_text(json.dumps(_read(LOCAL) + [p], indent=1))
    return p


def start(project_id: str, wait_s: float = 45.0) -> dict:
    """Start a project's copy of the app if it is not running (creates its database the first time)."""
    p = entry(project_id)
    if not p:
        raise ValueError(f"No project “{project_id}”")
    if not seed_path(p).is_file():
        raise ValueError(f"“{p['name']}” is not installed: its seed file is not on disk")
    if not _listening(p["port"]):
        log = HERE / "data" / f"project-{p['id']}.log"
        env_ = {k: v for k, v in os.environ.items()       # the new copy takes its settings from projects.json, not from this one
                if k not in ("NORTHSTAR_PROJECT", "NORTHSTAR_DATA", "NORTHSTAR_TEMPLATE", "NORTHSTAR_MODE", "NORTHSTAR_SEED",
                             "DATABASE_URL", "PORT", "FEEDS_ENABLED")}
        with log.open("ab") as f:
            subprocess.Popen([str(HERE / "run_project.sh"), p["id"]], cwd=HERE, stdout=f, stderr=f, stdin=subprocess.DEVNULL,
                             env=env_, start_new_session=True)
        deadline = time.time() + wait_s
        while time.time() < deadline and not _listening(p["port"]):
            time.sleep(0.5)
        if not _listening(p["port"]):
            raise RuntimeError(f"“{p['name']}” did not start; see {log}")
    return {"id": p["id"], "name": p["name"], "port": p["port"], "running": True}


def delete(project_id: str) -> dict:
    """A person deletes a project they added from the page. It leaves the list straight away; a separate short-lived
    process then stops its copy of the app, drops its database and removes its files, so a project can delete
    itself. Projects in projects.json are part of the repository and cannot be deleted this way."""
    local = _read(LOCAL)
    p = next((x for x in local if x["id"] == project_id), None)
    if not p:
        if entry(project_id):
            raise ValueError("This project is one of the built-in examples and cannot be deleted from the page")
        raise LookupError(f"No project “{project_id}”")
    if not (p.get("created") and re.fullmatch(r"[a-z0-9-]+", p["id"]) and re.fullmatch(r"drone_[a-z0-9_]+", p["database"])):
        raise ValueError(f"“{p['name']}” was not created from the page and cannot be deleted from it")
    LOCAL.write_text(json.dumps([x for x in local if x["id"] != project_id], indent=1))
    with (HERE / "data" / "deleted-projects.log").open("ab") as f:
        subprocess.Popen([sys.executable, str(HERE / "projects.py"), "purge", json.dumps(p)], cwd=HERE, stdout=f, stderr=f,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    return {"id": p["id"], "name": p["name"], "deleted": True}


def purge(p: dict) -> None:
    """The second half of delete(), run as its own process: stop the app, drop the database, remove the files."""
    stamp = lambda: time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"{stamp()} deleting {p['id']} (port {p['port']}, database {p['database']})", flush=True)
    time.sleep(1.0)                                   # let the app answer the person who asked before it is stopped
    pids = subprocess.run(["lsof", "-nP", f"-tiTCP:{p['port']}", "-sTCP:LISTEN"], capture_output=True, text=True).stdout.split()
    for pid in pids:
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid], capture_output=True, text=True).stdout
        if f"--port {p['port']}" in cmd and "uvicorn" in cmd:      # only this project's copy of the app, nothing else on that port
            os.kill(int(pid), signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline and _listening(p["port"]):
        time.sleep(0.25)
    try:
        import psycopg
        with psycopg.connect(_database_url("postgres"), autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{p["database"]}" WITH (FORCE)')
    except Exception as e:
        print(f"{stamp()} database {p['database']} not dropped: {e}", flush=True)
    for folder in (HERE / "data" / "projects" / p["id"], HERE / "data" / p["id"]):
        shutil.rmtree(folder, ignore_errors=True)
    (HERE / "data" / f"project-{p['id']}.log").unlink(missing_ok=True)
    print(f"{stamp()} deleted {p['id']}", flush=True)


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
    elif cmd == "purge" and len(sys.argv) > 2:      # started by delete(); not meant to be run by hand
        purge(json.loads(sys.argv[2]))
    else:
        raise SystemExit("usage: projects.py list | env <project id>")
