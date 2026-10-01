"""Device profile routes - CRUD for device market profiles."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.dependencies import get_current_user, get_active_device_profile
from app.schemas.device_profile import (
    DeviceProfileCreate,
    DeviceProfileUpdate,
    SavedSpecialty,
)
from app.services import device_profile_service


class SaveSpecialtyRequest(BaseModel):
    name: str
    specialty: str = ""
    hcpcs_codes: list[str] = []

router = APIRouter()


@router.get("")
async def list_profiles(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all profiles visible to the current user (own + presets)."""
    profiles = await device_profile_service.list_profiles(user["id"], db)
    active_id = None
    for p in profiles:
        if p["is_active"]:
            active_id = p["id"]
            break
    return {"profiles": profiles, "active_profile_id": active_id}


@router.post("")
async def create_profile(
    body: DeviceProfileCreate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new device market profile."""
    profile = await device_profile_service.create_profile(
        user_id=user["id"],
        name=body.name,
        description=body.description,
        filters=body.filters.model_dump(),
        db=db,
    )
    return profile


@router.get("/active")
async def get_active_profile(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get the current user's active device profile filters."""
    filters = await device_profile_service.get_active_profile(user["id"], db)
    return {"filters": filters}


@router.get("/{profile_id}")
async def get_profile(
    profile_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific profile."""
    profile = await device_profile_service.get_profile(profile_id, db)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.put("/{profile_id}")
async def update_profile(
    profile_id: UUID,
    body: DeviceProfileUpdate,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a profile. Cannot update preset profiles."""
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.filters is not None:
        updates["filters"] = body.filters.model_dump()

    profile = await device_profile_service.update_profile(
        profile_id, user["id"], updates, db
    )
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Profile not found or cannot edit preset profiles",
        )
    return profile


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a profile. Cannot delete preset profiles."""
    deleted = await device_profile_service.delete_profile(
        profile_id, user["id"], db
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail="Profile not found or cannot delete preset profiles",
        )
    return {"message": "Profile deleted"}


@router.post("/{profile_id}/activate")
async def activate_profile(
    profile_id: UUID,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Set a profile as the user's active device market profile."""
    activated = await device_profile_service.activate_profile(
        profile_id, user["id"], db
    )
    if not activated:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"message": "Profile activated", "profile_id": str(profile_id)}


@router.post("/{profile_id}/saved-specialties")
async def add_saved_specialty(
    profile_id: UUID,
    body: SaveSpecialtyRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a custom physician search as a specialty on a profile.

    Works on both presets and custom profiles — saved specialties
    are user-specific customizations, not schema changes.
    """
    result = await device_profile_service.add_saved_specialty(
        profile_id, body.model_dump(), db,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result


@router.delete("/{profile_id}/saved-specialties/{specialty_name}")
async def delete_saved_specialty(
    profile_id: UUID,
    specialty_name: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a saved specialty from a profile."""
    result = await device_profile_service.delete_saved_specialty(
        profile_id, specialty_name, db,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return result
