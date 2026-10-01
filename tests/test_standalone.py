"""Tests for the standalone (non-Docker) setup: config, token store, DB URLs."""

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


class TestSettings:
    def test_relative_sqlite_path_anchored_to_project_root(self, monkeypatch):
        from app.core.config import PROJECT_ROOT, Settings

        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///data/test.db")
        s = Settings(_env_file=None)
        assert s.database_url == f"sqlite+aiosqlite:///{(PROJECT_ROOT / 'data' / 'test.db').as_posix()}"
        assert s.is_sqlite

    def test_postgres_url_untouched(self, monkeypatch):
        from app.core.config import Settings

        url = "postgresql+asyncpg://u:p@postgres:5432/doctor_prospector"
        monkeypatch.setenv("DATABASE_URL", url)
        s = Settings(_env_file=None)
        assert s.database_url == url and not s.is_sqlite

    def test_defaults_need_no_services(self, monkeypatch):
        from app.core.config import Settings

        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        s = Settings(_env_file=None)
        assert s.is_sqlite and s.redis_url == ""

    def test_unknown_env_file_keys_ignored(self, tmp_path):
        from app.core.config import Settings

        env = tmp_path / ".env"
        env.write_text("STREAMLIT_PORT=8501\nPORT=8123\n", encoding="utf-8")
        assert Settings(_env_file=env).port == 8123


class TestTokenStore:
    def test_memory_store_revokes_until_expiry(self):
        from app.auth.token_store import MemoryTokenStore

        async def run():
            store = MemoryTokenStore()
            assert not await store.is_revoked("t1")
            await store.revoke("t1", ttl_seconds=60)
            assert await store.is_revoked("t1")
            await store.revoke("t2", ttl_seconds=-5)  # already expired -> clamped to 1s
            return await store.is_revoked("t2")

        assert asyncio.run(run()) is True


class TestScriptDatabaseUrl:
    def test_env_var_wins_and_async_driver_converted(self, monkeypatch):
        import db

        monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost:5432/x")
        assert db.database_url() == "postgresql://u:p@localhost:5432/x"

    def test_relative_sqlite_resolved(self, monkeypatch):
        import db

        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///data/doctor_prospector.db")
        assert db.database_url() == f"sqlite:///{(ROOT / 'data' / 'doctor_prospector.db').as_posix()}"

    def test_describe_hides_password(self):
        import db

        assert db.describe("postgresql://prospector:secret@localhost:5432/x") == "postgresql://prospector:***@localhost:5432/x"


class TestUUIDType:
    def test_accepts_string_ids(self):
        import uuid

        from app.db.types import UUIDType

        u = uuid.uuid4()
        t = UUIDType()
        assert t.process_bind_param(str(u), None) == u
        assert t.process_bind_param(u, None) == u
        assert t.process_bind_param(None, None) is None
