"""Cache service - wraps SQLiteCache and freshness probes."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _get_cache():
    from doctor_prospector.sources.base import _get_cache as get_source_cache
    return get_source_cache()


async def get_cache_status() -> dict[str, Any]:
    """Get overall cache statistics."""
    cache = _get_cache()
    return await cache.get_status()


async def get_cache_freshness() -> dict[str, dict]:
    """Get per-source cache freshness info."""
    cache = _get_cache()
    return await cache.get_freshness()


async def clear_source_cache(source_name: str) -> int:
    """Clear cache for a specific source. Returns entries cleared."""
    cache = _get_cache()
    # Get count before clearing
    status = await cache.get_status()
    by_source = status.get("by_source", {})
    count = by_source.get(source_name, 0)
    await cache.clear_source(source_name)
    return count


async def clear_expired() -> None:
    """Remove all expired cache entries."""
    cache = _get_cache()
    await cache.clear_expired()


async def run_freshness_probes() -> list[dict[str, Any]]:
    """Run all upstream freshness probes."""
    try:
        from doctor_prospector.freshness import run_all_probes
        results = await run_all_probes()
        return [
            {
                "source_name": r.source_name,
                "status": r.status,
                "message": r.message,
                "upstream_version": r.upstream_version,
                "local_version": r.local_version,
                "checked_at": r.checked_at.isoformat() if r.checked_at else None,
                "error": r.error,
            }
            for r in results
        ]
    except Exception as e:
        logger.error("Error running freshness probes: %s", e)
        return []
