#!/bin/zsh
# The presentation app: replay controls, its own database (drone_demo) and data folder. http://localhost:8200
cd "$(dirname "$0")"
mkdir -p data/demo
[ -f data/demo/replay_cache.json ] || cp data/replay_cache.json data/demo/ 2>/dev/null   # reuse rehearsed steps if we have them
NORTHSTAR_MODE=demo FEEDS_ENABLED=0 NORTHSTAR_DATA=data/demo \
DATABASE_URL="${DEMO_DATABASE_URL:-postgresql://drone:drone@localhost:5433/drone_demo}" \
exec .venv/bin/uvicorn app:app --port "${DEMO_PORT:-8200}"
