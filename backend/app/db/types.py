"""Column types and migration helpers that work on PostgreSQL and SQLite.

Docker runs PostgreSQL; the standalone install runs SQLite. Models and
migrations use these instead of postgresql-only types so one schema works
on both. On PostgreSQL they produce exactly the same columns as before
(native UUID, JSONB).
"""

import uuid
from typing import Any, Callable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on PostgreSQL, JSON (text) on SQLite
JSONType = sa.JSON().with_variant(JSONB(), "postgresql")

class UUIDType(sa.TypeDecorator):
    """Native UUID on PostgreSQL, CHAR(32) on SQLite; accepts str or UUID.

    Routes pass ids around as strings (JWT "sub", URL params). asyncpg
    accepts those for UUID columns, but SQLite's Uuid type calls .hex on
    the value and fails, so normalise here instead of at every call site.
    """

    impl = sa.Uuid
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if isinstance(value, str):
            return uuid.UUID(value)
        return value


def is_postgres(bind) -> bool:
    return bind.dialect.name == "postgresql"


def uuid_server_default(bind):
    """gen_random_uuid() on PostgreSQL; elsewhere the app supplies ids."""
    return sa.text("gen_random_uuid()") if is_postgres(bind) else None


def device_profiles_table() -> sa.TableClause:
    """Lightweight table for data migrations (no ORM import)."""
    return sa.table(
        "device_profiles",
        sa.column("id", sa.Uuid()),
        sa.column("name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("is_preset", sa.Boolean()),
        sa.column("is_active", sa.Boolean()),
        sa.column("filters_json", JSONType),
    )


def update_preset_filters(bind, name: str, change: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
    """Rewrite a preset's filters_json in Python (portable, unlike jsonb operators)."""
    t = device_profiles_table()
    rows = bind.execute(
        sa.select(t.c.id, t.c.filters_json).where(t.c.name == name, t.c.is_preset.is_(True))
    ).fetchall()
    for row_id, filters in rows:
        bind.execute(t.update().where(t.c.id == row_id).values(filters_json=change(dict(filters or {}))))
