#!/usr/bin/env bash
# Doctor Prospector standalone installer for macOS / Linux (no Docker needed).
#
#   1. Checks for Python 3.11+
#   2. Creates .venv and installs dependencies
#   3. Creates .env from .env.example with a random SECRET_KEY
#   4. Builds the web pages if frontend/dist is missing (needs Node.js)
#   5. Creates the SQLite database
#   6. Loads the physician volume history from the bundled snapshot (seconds)
#
# Safe to re-run: existing .venv, .env and database are kept.
#
#   ./install.sh
#   ./install.sh --load-history  # also fetch years newer than the snapshot
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
fail() { printf '\n\033[31mERROR: %s\033[0m\n' "$1"; exit 1; }

LOAD_HISTORY=""
for arg in "$@"; do
  case "$arg" in
    --load-history) LOAD_HISTORY=yes ;;
    *) fail "unknown option: $arg" ;;
  esac
done

# --- 1. Python --------------------------------------------------------------
step "Checking Python"
PYTHON=""
for candidate in python3.12 python3.13 python3.11 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$candidate"; break
  fi
done
[ -n "$PYTHON" ] || fail "Python 3.11 or newer is required (https://www.python.org/downloads/), then re-run."
echo "Using $PYTHON ($("$PYTHON" --version))"

# --- 2. Virtual environment ---------------------------------------------------
VENV_PY="$ROOT/.venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
  step "Creating virtual environment (.venv)"
  "$PYTHON" -m venv .venv || fail "Could not create .venv (on Debian/Ubuntu: sudo apt install python3-venv)"
else
  step "Using existing virtual environment (.venv)"
fi

step "Installing dependencies (a few minutes the first time)"
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install -e . -e ./backend --quiet || fail "Dependency install failed (see messages above)"

# --- 3. .env --------------------------------------------------------------------
if [ ! -f .env ]; then
  step "Creating .env from .env.example"
  SECRET="$("$VENV_PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed "s|^SECRET_KEY=.*|SECRET_KEY=$SECRET|" .env.example > .env
else
  step "Keeping existing .env"
fi

# --- 4. Web pages -----------------------------------------------------------------
if [ ! -f frontend/dist/index.html ]; then
  step "Building the web pages"
  if command -v npm >/dev/null 2>&1; then
    (cd frontend && (npm ci --no-audit --no-fund || npm install --no-audit --no-fund) && npm run build) \
      || fail "Frontend build failed (see messages above)"
  else
    printf '\033[33mNode.js isn'"'"'t installed, so the web pages can'"'"'t be built here.\n'
    printf 'Install Node.js 20+ (https://nodejs.org) and re-run, or use a release that includes frontend/dist.\033[0m\n'
  fi
else
  step "Web pages already built (frontend/dist)"
fi

# --- 5. Database --------------------------------------------------------------------
step "Creating/updating the database"
export PYTHONPATH="$ROOT/src:$ROOT/backend"
(cd backend && "$VENV_PY" -m alembic upgrade head) || fail "Database setup failed (see messages above)"

# --- 6. Physician history -------------------------------------------------------------
# Published CMS years never change, so the repo ships them as a snapshot
# (data/seed). Importing takes seconds; refresh_all fetches newer years later.
step "Loading physician history (bundled snapshot)"
"$VENV_PY" scripts/history_seed.py import || \
  echo "Snapshot import failed; fetch from CMS instead (35-60 min): .venv/bin/python scripts/refresh_all.py --only db_history"
if [ "$LOAD_HISTORY" = yes ]; then
  step "Fetching any newer years from CMS"
  "$VENV_PY" scripts/refresh_all.py --only db_history
fi

printf '\n\033[32mInstall complete. Start Doctor Prospector with: ./run.sh\033[0m\n'
