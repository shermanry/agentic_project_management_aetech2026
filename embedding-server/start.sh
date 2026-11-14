#!/usr/bin/env bash
# Start the embedding server, reachable from other machines on the network (default port 8000).
cd "$(dirname "$0")"
exec .venv/bin/uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
