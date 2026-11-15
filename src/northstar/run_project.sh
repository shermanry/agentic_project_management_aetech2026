#!/bin/zsh
# Start one example project as its own copy of the app: own port, own database, own data folder.
#   ./run_project.sh                 list the projects and which are running
#   ./run_project.sh rooftop-shell   start that one (creates its database the first time)
# Needs Postgres from docker-compose.yml to be up. Switch between running projects from the page's project menu.
cd "$(dirname "$0")"
if [ -z "$1" ]; then exec .venv/bin/python projects.py list; fi
settings="$(.venv/bin/python projects.py env "$1")" || exit 1
eval "$settings"
[ -n "$NORTHSTAR_DATA" ] && mkdir -p "$NORTHSTAR_DATA"
echo "Starting $NORTHSTAR_PROJECT on http://localhost:$PORT/app/"
exec .venv/bin/python -m uvicorn app:app --port "$PORT"
