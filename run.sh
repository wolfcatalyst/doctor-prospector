#!/usr/bin/env bash
# Start Doctor Prospector (standalone) and open it in the browser.
#   ./run.sh              # start + open browser
#   ./run.sh --no-browser
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PY="$ROOT/.venv/bin/python"
[ -x "$VENV_PY" ] || { echo "Not installed yet. Run: ./install.sh"; exit 1; }

# HOST / PORT from .env (defaults match .env.example)
HOST=127.0.0.1; PORT=8000
if [ -f "$ROOT/.env" ]; then
  HOST="$(sed -n 's/^[[:space:]]*HOST[[:space:]]*=[[:space:]]*//p' "$ROOT/.env" | tail -1)"; HOST="${HOST:-127.0.0.1}"
  PORT="$(sed -n 's/^[[:space:]]*PORT[[:space:]]*=[[:space:]]*\([0-9]*\).*/\1/p' "$ROOT/.env" | tail -1)"; PORT="${PORT:-8000}"
fi
BROWSE_HOST="$HOST"; [ "$HOST" = "0.0.0.0" ] && BROWSE_HOST=localhost
URL="http://$BROWSE_HOST:$PORT"

export PYTHONPATH="$ROOT/src:$ROOT/backend"
export PYTHONIOENCODING=utf-8

if [ "${1:-}" != "--no-browser" ]; then
  (
    for _ in $(seq 1 60); do
      if curl -fsS "$URL/api/v1/health" >/dev/null 2>&1; then
        if command -v open >/dev/null 2>&1; then open "$URL"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"; fi
        break
      fi
      sleep 1
    done
  ) &
fi

echo "Doctor Prospector running at $URL  (Ctrl+C to stop)"
cd "$ROOT/backend"
exec "$VENV_PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT"
