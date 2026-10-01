import os
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

# Code + bundled files: repo root locally, /app in Docker, the install
# folder for the desktop app (backend/app/core/config.py -> parents[3])
PROJECT_ROOT = Path(__file__).resolve().parents[3]
# Writable data (data/, config.yaml, .env). Same as PROJECT_ROOT unless
# DOCTOR_PROSPECTOR_HOME is set, which the desktop app does (%LOCALAPPDATA%).
DATA_ROOT = Path(os.environ["DOCTOR_PROSPECTOR_HOME"]).resolve() if os.environ.get("DOCTOR_PROSPECTOR_HOME") else PROJECT_ROOT


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # App
    app_name: str = "Doctor Prospector"
    app_version: str = "1.0.0"
    debug: bool = False

    # Database: SQLite file by default (standalone install). Docker sets
    # DATABASE_URL to PostgreSQL. Relative SQLite paths resolve from the
    # project root, e.g. sqlite+aiosqlite:///data/doctor_prospector.db
    database_url: str = "sqlite+aiosqlite:///data/doctor_prospector.db"

    # Redis: optional. Empty = keep the logout token blocklist in memory
    # (fine for one server process). Docker sets REDIS_URL.
    redis_url: str = ""

    # Where the standalone launcher (run.ps1 / run.sh) listens
    host: str = "127.0.0.1"
    port: int = 8000

    # Serve the built React app (frontend/dist) from the API on one port.
    # Docker uses nginx instead; the dist folder isn't in the API image, so
    # this is a no-op there.
    serve_frontend: bool = True
    frontend_dist: str = str(PROJECT_ROOT / "frontend" / "dist")

    # Auth
    secret_key: str = "CHANGE-ME-IN-PRODUCTION"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    auth_enabled: bool = False  # False = dev mode (no login required), True = enforce auth
    auth_provider: str = "local"  # "local" or "oidc"

    # OIDC (Phase 7)
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_jwks_url: str = ""

    # CORS
    cors_origins: str = "http://localhost:5173,http://localhost:3100"

    # Data paths (anchored to the project root so the working directory doesn't matter)
    data_dir: str = str(DATA_ROOT / "data")
    config_yaml_path: str = str(DATA_ROOT / "config.yaml")

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, url: str) -> str:
        """sqlite:///relative.db would resolve against the working directory; use DATA_ROOT."""
        prefix, sep, path = url.partition(":///")
        if prefix.startswith("sqlite") and sep and path and not Path(path).is_absolute():
            return f"{prefix}:///{(DATA_ROOT / path).as_posix()}"
        return url

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {
        # Repo-root .env (standalone install). Real environment variables win,
        # which is how Docker passes docker/.env into the container.
        "env_file": str(DATA_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        # Unknown keys in .env (old or hand-added) shouldn't stop the app
        "extra": "ignore",
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()
