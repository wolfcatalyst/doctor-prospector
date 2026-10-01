"""Device profile service - CRUD operations for device market profiles."""

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DeviceProfile, User
from app.schemas.presets import TAVR_FILTERS

logger = logging.getLogger(__name__)


async def _ensure_user(user_id: str, db: AsyncSession) -> None:
    """Ensure a user row exists (creates the dev user on first use)."""
    result = await db.execute(select(User).where(User.id == user_id))
    if result.scalar_one_or_none() is None:
        user = User(
            id=user_id,
            email="dev@doctorprospector.local",
            display_name="Dev User",
            role="admin",
        )
        db.add(user)
        await db.commit()
        logger.info("Auto-created user row for %s", user_id)


def _tavr_fallback() -> dict[str, Any]:
    """Return TAVR preset filters as a dict for fallback."""
    return TAVR_FILTERS.model_dump()


async def get_active_profile(user_id: str, db: AsyncSession) -> dict[str, Any]:
    """Get the active device profile filters for a user.

    Falls back to the TAVR preset if no profile is active.
    """
    # Try user's active profile
    user_result = await db.execute(
        select(User.active_device_profile_id).where(User.id == user_id)
    )
    active_id = user_result.scalar_one_or_none()

    if active_id:
        profile_result = await db.execute(
            select(DeviceProfile).where(DeviceProfile.id == active_id)
        )
        profile = profile_result.scalar_one_or_none()
        if profile:
            return profile.filters_json

    # Fallback: try the TAVR preset from DB
    preset_result = await db.execute(
        select(DeviceProfile).where(
            DeviceProfile.is_preset == True,
            DeviceProfile.name == "TAVR",
        )
    )
    preset = preset_result.scalar_one_or_none()
    if preset:
        return preset.filters_json

    # Ultimate fallback: hardcoded TAVR filters
    return _tavr_fallback()


async def list_profiles(user_id: str, db: AsyncSession) -> list[dict[str, Any]]:
    """List all profiles visible to a user (their own + presets)."""
    result = await db.execute(
        select(DeviceProfile).where(
            (DeviceProfile.user_id == user_id) | (DeviceProfile.is_preset == True)
        ).order_by(DeviceProfile.is_preset.desc(), DeviceProfile.name)
    )
    profiles = result.scalars().all()

    # Get user's active profile ID
    user_result = await db.execute(
        select(User.active_device_profile_id).where(User.id == user_id)
    )
    active_id = user_result.scalar_one_or_none()

    return [
        {
            "id": str(p.id),
            "name": p.name,
            "description": p.description,
            "is_preset": p.is_preset,
            "is_active": str(p.id) == str(active_id) if active_id else False,
            "filters": p.filters_json,
            "created_at": p.created_at.isoformat() if p.created_at else "",
            "updated_at": p.updated_at.isoformat() if p.updated_at else "",
        }
        for p in profiles
    ]


async def get_profile(profile_id: UUID, db: AsyncSession) -> Optional[dict[str, Any]]:
    """Get a single profile by ID."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    p = result.scalar_one_or_none()
    if not p:
        return None
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "is_preset": p.is_preset,
        "is_active": p.is_active,
        "filters": p.filters_json,
        "created_at": p.created_at.isoformat() if p.created_at else "",
        "updated_at": p.updated_at.isoformat() if p.updated_at else "",
    }


async def create_profile(
    user_id: str, name: str, description: str, filters: dict, db: AsyncSession
) -> dict[str, Any]:
    """Create a new user profile."""
    profile = DeviceProfile(
        user_id=user_id,
        name=name,
        description=description,
        is_preset=False,
        is_active=False,
        filters_json=filters,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return {
        "id": str(profile.id),
        "name": profile.name,
        "description": profile.description,
        "is_preset": False,
        "is_active": False,
        "filters": profile.filters_json,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),
    }


async def update_profile(
    profile_id: UUID, user_id: str, updates: dict, db: AsyncSession
) -> Optional[dict[str, Any]]:
    """Update a profile. Cannot update presets."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return None
    if profile.is_preset:
        return None  # Cannot edit presets

    if "name" in updates and updates["name"] is not None:
        profile.name = updates["name"]
    if "description" in updates and updates["description"] is not None:
        profile.description = updates["description"]
    if "filters" in updates and updates["filters"] is not None:
        profile.filters_json = updates["filters"]

    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return await get_profile(profile_id, db)


async def delete_profile(
    profile_id: UUID, user_id: str, db: AsyncSession
) -> bool:
    """Delete a profile. Cannot delete presets."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile or profile.is_preset:
        return False

    # If this was the active profile, clear it
    await db.execute(
        update(User)
        .where(User.active_device_profile_id == profile_id)
        .values(active_device_profile_id=None)
    )

    await db.delete(profile)
    await db.commit()
    return True


async def activate_profile(
    profile_id: UUID, user_id: str, db: AsyncSession
) -> bool:
    """Set a profile as the user's active profile."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return False

    await _ensure_user(user_id, db)

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(active_device_profile_id=profile_id)
    )
    await db.commit()
    return True


async def add_saved_specialty(
    profile_id: UUID, specialty: dict[str, Any], db: AsyncSession
) -> Optional[dict[str, Any]]:
    """Add a saved specialty to a profile's filters_json.

    Works on both presets and custom profiles.
    """
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return None

    filters = dict(profile.filters_json)
    saved = list(filters.get("saved_specialties", []))

    # Replace if same name exists
    saved = [s for s in saved if s.get("name") != specialty["name"]]
    saved.append(specialty)
    filters["saved_specialties"] = saved
    profile.filters_json = filters

    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return await get_profile(profile_id, db)


async def delete_saved_specialty(
    profile_id: UUID, specialty_name: str, db: AsyncSession
) -> Optional[dict[str, Any]]:
    """Remove a saved specialty from a profile."""
    result = await db.execute(
        select(DeviceProfile).where(DeviceProfile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        return None

    filters = dict(profile.filters_json)
    saved = list(filters.get("saved_specialties", []))
    filters["saved_specialties"] = [s for s in saved if s.get("name") != specialty_name]
    profile.filters_json = filters

    profile.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(profile)
    return await get_profile(profile_id, db)
