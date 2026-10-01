from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.dependencies import get_current_user
from app.services import cache_service

router = APIRouter()


class UserPreferences(BaseModel):
    search_scope: str = "city"
    specialty_filter: list[str] = []
    show_payments: bool = False
    show_trends: bool = False
    show_data_flags: bool = True
    show_auth_notice: bool = True
    preferred_specialties: list[str] = []
    min_volume: int = 0
    sort_by: str = "volume"
    payment_company_filter: str = "All Companies"
    payment_level_filter: str = "All Payment Levels"
    default_states: list[str] = []


class ProfileUpdateRequest(BaseModel):
    defaults: UserPreferences


def _load_profile() -> dict:
    """Load profile using the core library's profile system."""
    try:
        from doctor_prospector.profiles import load_profile
        return load_profile()
    except Exception:
        return {
            "name": "Default",
            "created": None,
            "updated": None,
            "defaults": UserPreferences().model_dump(),
        }


def _save_profile(profile: dict) -> None:
    """Save profile using the core library's profile system."""
    from doctor_prospector.profiles import save_profile
    save_profile(profile)


@router.get("")
async def get_settings(user: dict = Depends(get_current_user)):
    """Get user preferences and settings."""
    return _load_profile()


@router.put("")
async def update_settings(
    update: ProfileUpdateRequest,
    user: dict = Depends(get_current_user),
):
    """Update user preferences."""
    profile = _load_profile()
    profile["defaults"] = {**profile.get("defaults", {}), **update.defaults.model_dump()}
    _save_profile(profile)
    return profile


@router.post("/reset")
async def reset_settings(user: dict = Depends(get_current_user)):
    """Reset preferences to factory defaults."""
    from doctor_prospector.profiles import DEFAULT_PROFILE, save_profile
    save_profile(DEFAULT_PROFILE.copy())
    return DEFAULT_PROFILE


@router.get("/refresh-status")
async def get_refresh_status(user: dict = Depends(get_current_user)):
    """Get background data refresh status."""
    from app.services.scheduler import get_refresh_status
    return get_refresh_status()


@router.post("/refresh-now")
async def trigger_refresh(user: dict = Depends(get_current_user)):
    """Manually trigger a data refresh cycle."""
    import asyncio
    from app.services.scheduler import _run_refresh_cycle
    asyncio.create_task(_run_refresh_cycle())
    return {"message": "Refresh cycle started"}


@router.get("/cache")
async def get_cache_status(user: dict = Depends(get_current_user)):
    """Get cache overview (per-source stats)."""
    return await cache_service.get_cache_status()


@router.post("/cache/clean-expired")
async def clean_expired(user: dict = Depends(get_current_user)):
    """Remove expired cache entries."""
    cache = cache_service._get_cache()
    count = await cache.clear_expired()
    return {"message": f"Removed {count} expired entries", "entries_removed": count}


@router.post("/cache/clear-all")
async def clear_all_cache(user: dict = Depends(get_current_user)):
    """Clear ALL cache entries. Danger zone."""
    status = await cache_service.get_cache_status()
    by_source = status.get("by_source", {})
    total = 0
    for source_name in by_source:
        count = await cache_service.clear_source_cache(source_name)
        total += count
    return {"message": f"Cleared {total} entries from all sources", "entries_cleared": total}
