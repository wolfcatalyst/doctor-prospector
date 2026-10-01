"""Database URL resolution for command-line scripts.

The app reads DATABASE_URL from the environment or the repo-root .env and
defaults to SQLite (standalone install). Scripts run on the host, so they
also recognise a Docker setup: if there is no root .env but docker/.env
exists, they talk to the Docker Postgres on localhost.

Order: DATABASE_URL env var > root .env > docker/.env (localhost) > SQLite.
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Writable data folder (the desktop app sets DOCTOR_PROSPECTOR_HOME); see doctor_prospector/paths.py
DATA_ROOT = Path(os.environ["DOCTOR_PROSPECTOR_HOME"]).resolve() if os.environ.get("DOCTOR_PROSPECTOR_HOME") else ROOT
SQLITE_DEFAULT = f"sqlite:///{(DATA_ROOT / 'data' / 'doctor_prospector.db').as_posix()}"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _sync(url: str) -> str:
    """Async driver URL (what the app uses) -> sync driver URL (scripts)."""
    url = url.replace("postgresql+asyncpg://", "postgresql://").replace("sqlite+aiosqlite://", "sqlite://")
    prefix, sep, path = url.partition(":///")
    if prefix == "sqlite" and sep and not Path(path).is_absolute():
        url = f"sqlite:///{(DATA_ROOT / path).as_posix()}"
    return url


def database_url() -> str:
    """Sync SQLAlchemy URL for the app's database."""
    if os.environ.get("DATABASE_URL"):
        return _sync(os.environ["DATABASE_URL"])

    root_env = _read_env_file(DATA_ROOT / ".env")
    if (DATA_ROOT / ".env").exists() or DATA_ROOT != ROOT:
        return _sync(root_env.get("DATABASE_URL") or SQLITE_DEFAULT)

    docker_env = _read_env_file(ROOT / "docker" / ".env")
    if docker_env:
        user = docker_env.get("POSTGRES_USER", "prospector")
        password = docker_env.get("POSTGRES_PASSWORD", "prospector")
        port = docker_env.get("POSTGRES_PORT", "5432")
        return f"postgresql://{user}:{password}@localhost:{port}/doctor_prospector"

    return SQLITE_DEFAULT


def describe(url: str) -> str:
    """URL without the password, for log output."""
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        creds, host = rest.rsplit("@", 1)
        return f"{scheme}://{creds.split(':')[0]}:***@{host}"
    return url
