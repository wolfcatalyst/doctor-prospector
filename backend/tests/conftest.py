import pytest


@pytest.fixture
def app_settings():
    """Override settings for testing."""
    from app.core.config import Settings
    return Settings(
        database_url="sqlite+aiosqlite:///test.db",
        redis_url="redis://localhost:6379/1",
        secret_key="test-secret-key",
        auth_enabled=False,
    )
