#!/usr/bin/env bash
# start.sh — one command on demo day (SPEC §39): build the web app, prepare the database, serve app + API on :8000.
#   ./start.sh          # this machine only (127.0.0.1)
#   ./start.sh --lan    # phones on the team hotspot: http://<laptop-ip>:8000
set -euo pipefail
cd "$(dirname "$0")"
BIND=127.0.0.1
[ "${1:-}" = "--lan" ] && BIND=0.0.0.0

(cd web && { [ -d node_modules ] || npm install; } && npm run build)

cd backend
if [ ! -d .venv ]; then
  python3.12 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
PY=.venv/bin/python
[ -x "$PY" ] || PY=.venv/Scripts/python
"$PY" -m railflow.manage init-db
"$PY" -m railflow.manage seed-demo           # passwords from ../.env (see .env.example)
export RAILFLOW_SERVE_WEB=1
echo "RailFlow on http://$BIND:8000"
exec "$PY" -m uvicorn railflow.main:app --host "$BIND" --port 8000
