"""Run Alembic migrations in-process.

The API normally migrates at startup by launching `python -m alembic`. The
frozen desktop app has no python.exe to launch, so its launcher calls this
before starting the server (and sets DOCTOR_PROSPECTOR_SKIP_MIGRATIONS=1).
Must be called outside a running event loop: env.py uses asyncio.run().
"""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def upgrade_to_head() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
