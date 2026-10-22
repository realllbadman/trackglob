#!/usr/bin/env bash
# Stop whatever is listening on port 8006.
PORT=8006
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 && echo "Stopped process on port ${PORT}." || echo "Nothing running on port ${PORT}."
else
  pkill -f "uvicorn backend.main:app" && echo "Stopped uvicorn." || echo "Nothing running."
fi
