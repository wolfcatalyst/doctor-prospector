"""Background data refresh scheduler.

Runs inside the FastAPI process — no external cron or task queue needed.
Periodically checks data freshness and refreshes stale sources.

Schedule:
- Every 6 hours: Check API-based source TTLs, refresh if expired
- Every 24 hours: Refresh Hospital Compare ratings (universal)
- On startup: Check if any data needs immediate refresh
- Weekly: Check for new CMS PUF year and auto-import if found
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Global state for tracking refresh status
_refresh_status: dict[str, dict[str, Any]] = {}
_scheduler_task: asyncio.Task | None = None


def get_refresh_status() -> dict[str, Any]:
    """Get current refresh status for all sources."""
    return {
        "sources": dict(_refresh_status),
        "scheduler_running": _scheduler_task is not None and not _scheduler_task.done(),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _update_status(source: str, status: str, detail: str = ""):
    """Update refresh status for a source."""
    _refresh_status[source] = {
        "status": status,
        "detail": detail,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }


async def _refresh_hospital_compare():
    """Refresh CMS Hospital Compare data (universal quality ratings)."""
    _update_status("hospital_compare", "refreshing")
    try:
        from doctor_prospector.sources.cms_hospital_compare import cms_hospital_compare_source
        result = await cms_hospital_compare_source.fetch_cached()
        count = len(result.data) if result.data else 0
        _update_status("hospital_compare", "ok", f"{count} hospitals, from_cache={result.from_cache}")
    except Exception as e:
        logger.error("Failed to refresh Hospital Compare: %s", e)
        _update_status("hospital_compare", "error", str(e))


async def _refresh_drg_for_profile(drg_codes: list[str], profile_name: str):
    """Refresh CMS DRG data for a specific profile's codes."""
    key = f"drg_{profile_name}"
    _update_status(key, "refreshing")
    try:
        from doctor_prospector.sources.cms_drg import cms_drg_source
        result = await cms_drg_source.fetch_cached(drg_codes=drg_codes)
        count = len(result.data) if result.data else 0
        _update_status(key, "ok", f"{count} hospitals, from_cache={result.from_cache}")
    except Exception as e:
        logger.error("Failed to refresh DRG data for %s: %s", profile_name, e)
        _update_status(key, "error", str(e))


async def _check_puf_update():
    """Check if CMS published a new PUF year and auto-import.

    CMS typically publishes new yearly data around May-June.
    We check by looking at the known PUF URLs and comparing
    against what's already in the physician_volumes table.
    """
    _update_status("puf_historical", "checking")
    try:
        from sqlalchemy import text
        from app.db.engine import engine as async_engine

        # Check what years we have in the DB
        async with async_engine.begin() as conn:
            result = await conn.execute(
                text("SELECT DISTINCT year FROM physician_volumes ORDER BY year")
            )
            db_years = {row[0] for row in result.fetchall()}

        if not db_years:
            _update_status("puf_historical", "empty", "No historical data imported yet")
            return

        # Check what years are available from CMS
        try:
            from scripts.import_puf import PUF_URLS
        except ImportError:
            # Script not in path — try direct import
            import importlib.util
            import os
            spec = importlib.util.spec_from_file_location(
                "import_puf",
                os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "import_puf.py"),
            )
            if not spec or not spec.loader:
                _update_status("puf_historical", "ok", f"Years in DB: {sorted(db_years)}")
                return
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            PUF_URLS = mod.PUF_URLS

        available_years = set(PUF_URLS.keys())
        missing_years = available_years - db_years

        if missing_years:
            latest_missing = max(missing_years)
            _update_status(
                "puf_historical", "update_available",
                f"New year(s) available: {sorted(missing_years)}. "
                f"Run: python scripts/import_puf.py --download --years {latest_missing}",
            )
            logger.info(
                "PUF update available: years %s not in DB. "
                "Auto-import not enabled — run import_puf.py manually.",
                sorted(missing_years),
            )
        else:
            _update_status(
                "puf_historical", "ok",
                f"Up to date. Years in DB: {sorted(db_years)}",
            )
    except Exception as e:
        logger.error("PUF update check failed: %s", e)
        _update_status("puf_historical", "error", str(e))


async def _refresh_all_profiles():
    """Pre-warm DRG data for all active profiles."""
    try:
        from sqlalchemy import text
        from app.db.engine import engine as async_engine

        from sqlalchemy import select
        from app.db.models import DeviceProfile

        # ORM select so filters_json comes back as a dict on SQLite too
        async with async_engine.begin() as conn:
            result = await conn.execute(
                select(DeviceProfile.name, DeviceProfile.filters_json).where(DeviceProfile.is_preset.is_(True))
            )
            profiles = result.fetchall()

        for name, filters in profiles:
            drg_codes = filters.get("drg_codes", [])
            if drg_codes:
                await _refresh_drg_for_profile(drg_codes, name)
    except Exception as e:
        logger.error("Failed to refresh profile data: %s", e)


async def _run_refresh_cycle():
    """Run one full refresh cycle."""
    logger.info("Starting data refresh cycle")
    _update_status("_scheduler", "running", "Refresh cycle in progress")

    await _refresh_hospital_compare()
    await _refresh_all_profiles()
    await _check_puf_update()

    _update_status("_scheduler", "idle", f"Next check in 6 hours")
    logger.info("Data refresh cycle complete")


async def scheduler_loop():
    """Main scheduler loop. Runs forever inside the FastAPI process."""
    # Initial delay — let the app finish starting up
    await asyncio.sleep(30)

    logger.info("Background scheduler started")
    _update_status("_scheduler", "started")

    # Run initial check
    try:
        await _run_refresh_cycle()
    except Exception as e:
        logger.error("Initial refresh cycle failed: %s", e)

    # Then run every 6 hours
    while True:
        try:
            await asyncio.sleep(6 * 60 * 60)  # 6 hours
            await _run_refresh_cycle()
        except asyncio.CancelledError:
            logger.info("Scheduler shutting down")
            break
        except Exception as e:
            logger.error("Scheduler cycle failed: %s", e)
            _update_status("_scheduler", "error", str(e))
            # Wait before retrying
            await asyncio.sleep(60)


def start_scheduler():
    """Start the background scheduler task. Call from FastAPI lifespan."""
    global _scheduler_task
    _scheduler_task = asyncio.create_task(scheduler_loop())
    logger.info("Background data scheduler task created")
    return _scheduler_task


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("Background scheduler cancelled")
    _scheduler_task = None
