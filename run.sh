#!/usr/bin/env bash
# Start the app on port 8006 (frees the port first). Extra args go to uvicorn, e.g. ./run.sh --reload
set -euo pipefail
cd "$(dirname "$0")"
PORT=8006

if [ ! -f .env ]; then
  echo "No .env found — copying .env.example (edit it before going live)."
  cp .env.example .env
fi

if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
else
  pkill -f "uvicorn backend.main:app" >/dev/null 2>&1 || true
fi
sleep 0.5

PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python

exec "$PY" -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" "$@"
