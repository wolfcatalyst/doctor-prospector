"""Filesystem locations.

Two roots, which are the same folder except in the Windows desktop app:

- PROJECT_ROOT: the code and bundled read-only files (frontend build,
  migrations, seed data). The repo root locally, /app in Docker, the
  install folder for the desktop app.
- DATA_ROOT: where the app reads and writes its data (data/, config.yaml,
  .env). The DOCTOR_PROSPECTOR_HOME environment variable sets it; the desktop
  app points it at %LOCALAPPDATA%\DoctorProspector because the install folder
  is read-only. Unset (Docker, script install) it's PROJECT_ROOT.

Paths resolve from these instead of the working directory, so starting the
app from another folder can't silently use an empty cache.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = Path(os.environ["DOCTOR_PROSPECTOR_HOME"]).resolve() if os.environ.get("DOCTOR_PROSPECTOR_HOME") else PROJECT_ROOT
DATA_DIR = DATA_ROOT / "data"
CACHE_DB_PATH = DATA_DIR / "cache" / "doctor_prospector.db"
