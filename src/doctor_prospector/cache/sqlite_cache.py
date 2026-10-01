"""SQLite-based cache with TTL support."""

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class SQLiteCache:
    """Async SQLite cache with time-to-live (TTL) support.

    Stores key-value pairs with expiration times. Useful for caching
    API responses and scraping results.

    Example:
        cache = SQLiteCache("data/cache/tavr.db")
        await cache.set("key", {"data": "value"}, ttl_hours=24)
        data = await cache.get("key")
    """

    def __init__(self, db_path: str | Path):
        """Initialize cache.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialized = False

    async def _init_db(self):
        """Initialize database schema if needed."""
        if self._initialized:
            return

        def _create_table(conn: sqlite3.Connection):
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source
                ON cache(source)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires
                ON cache(expires_at)
            """)
            conn.commit()

        await asyncio.to_thread(self._sync_operation, _create_table)
        self._initialized = True

    def _sync_operation(self, func):
        """Execute a synchronous database operation."""
        with sqlite3.connect(self.db_path) as conn:
            return func(conn)

    async def get(self, key: str) -> Optional[Any]:
        """Get cached value by key.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        await self._init_db()

        def _get(conn: sqlite3.Connection):
            cursor = conn.execute(
                """
                SELECT value, expires_at FROM cache
                WHERE key = ? AND expires_at > ?
                """,
                (key, datetime.utcnow().isoformat())
            )
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

        return await asyncio.to_thread(self._sync_operation, _get)

    async def set(
        self,
        key: str,
        value: Any,
        ttl_hours: int = 24,
        source: Optional[str] = None
    ):
        """Set cached value with TTL.

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)
            ttl_hours: Time to live in hours
            source: Optional source name for bulk operations
        """
        await self._init_db()

        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(hours=ttl_hours)

        def _set(conn: sqlite3.Connection):
            conn.execute(
                """
                INSERT OR REPLACE INTO cache
                (key, value, source, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    key,
                    json.dumps(value),
                    source,
                    created_at.isoformat(),
                    expires_at.isoformat()
                )
            )
            conn.commit()

        await asyncio.to_thread(self._sync_operation, _set)
        logger.debug(f"Cached {key} (expires in {ttl_hours}h)")

    async def delete(self, key: str):
        """Delete a cached value.

        Args:
            key: Cache key to delete
        """
        await self._init_db()

        def _delete(conn: sqlite3.Connection):
            conn.execute("DELETE FROM cache WHERE key = ?", (key,))
            conn.commit()

        await asyncio.to_thread(self._sync_operation, _delete)

    async def clear_source(self, source: str):
        """Clear all cached values for a source.

        Args:
            source: Source name to clear
        """
        await self._init_db()

        def _clear(conn: sqlite3.Connection):
            cursor = conn.execute(
                "DELETE FROM cache WHERE source = ?",
                (source,)
            )
            count = cursor.rowcount
            conn.commit()
            return count

        count = await asyncio.to_thread(self._sync_operation, _clear)
        logger.info(f"Cleared {count} cached entries for source: {source}")

    async def clear_expired(self):
        """Remove expired cache entries.

        Returns:
            Number of entries deleted
        """
        await self._init_db()

        def _clear(conn: sqlite3.Connection):
            cursor = conn.execute(
                "DELETE FROM cache WHERE expires_at <= ?",
                (datetime.utcnow().isoformat(),)
            )
            count = cursor.rowcount
            conn.commit()
            return count

        count = await asyncio.to_thread(self._sync_operation, _clear)
        if count > 0:
            logger.info(f"Removed {count} expired cache entries")
        return count

    async def get_freshness(self) -> dict[str, dict]:
        """Get per-source freshness information.

        Queries the existing created_at/expires_at columns to show when
        each source was last fetched and when its cache expires.

        Returns:
            Dict mapping source name to freshness info:
            {source: {entry_count, oldest_entry, newest_entry, oldest_expiry, newest_expiry}}
        """
        await self._init_db()

        def _freshness(conn: sqlite3.Connection):
            now = datetime.utcnow().isoformat()
            cursor = conn.execute("""
                SELECT
                    source,
                    COUNT(*) as entry_count,
                    MIN(created_at) as oldest_entry,
                    MAX(created_at) as newest_entry,
                    MIN(expires_at) as oldest_expiry,
                    MAX(expires_at) as newest_expiry
                FROM cache
                WHERE source IS NOT NULL
                AND expires_at > ?
                GROUP BY source
            """, (now,))

            result = {}
            for row in cursor.fetchall():
                result[row[0]] = {
                    "entry_count": row[1],
                    "oldest_entry": row[2],
                    "newest_entry": row[3],
                    "oldest_expiry": row[4],
                    "newest_expiry": row[5],
                }
            return result

        return await asyncio.to_thread(self._sync_operation, _freshness)

    async def get_status(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        await self._init_db()

        def _stats(conn: sqlite3.Connection):
            cursor = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN expires_at > ? THEN 1 ELSE 0 END) as valid,
                    SUM(CASE WHEN expires_at <= ? THEN 1 ELSE 0 END) as expired
                FROM cache
            """, (datetime.utcnow().isoformat(), datetime.utcnow().isoformat()))
            row = cursor.fetchone()

            # Get per-source counts
            cursor = conn.execute("""
                SELECT source, COUNT(*) as count
                FROM cache
                WHERE expires_at > ?
                GROUP BY source
            """, (datetime.utcnow().isoformat(),))
            by_source = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            return {
                "total_entries": row[0],
                "valid_entries": row[1],
                "expired_entries": row[2],
                "by_source": by_source,
                "db_path": str(self.db_path)
            }

        return await asyncio.to_thread(self._sync_operation, _stats)
