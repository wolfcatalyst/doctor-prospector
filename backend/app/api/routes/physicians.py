from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_current_user, get_active_device_profile
from app.db.engine import get_db
from app.services import (
    physician_service,
    payment_service,
    history_service,
    trial_service,
    publication_service,
)

from app.services.data_flags import with_physician_flags

router = APIRouter()


@router.get("/search")
async def search_physicians(
    state: str | None = Query(None),
    states: list[str] | None = Query(None),
    city: str | None = Query(None),
    name: str | None = Query(None),
    specialty: str | None = Query(None),
    min_volume: int | None = Query(None, ge=0),
    hcpcs_codes: list[str] | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Search physicians by state, name, specialty.

    When hcpcs_codes is provided (custom search mode), it overrides
    the active profile's HCPCS codes for this search only.
    """
    if not state and not states:
        raise HTTPException(status_code=400, detail="At least one state is required")

    # Custom search: override profile HCPCS codes
    effective_profile = device_profile
    if hcpcs_codes:
        effective_profile = {**(device_profile or {}), "hcpcs_codes": hcpcs_codes}

    result = await physician_service.search_physicians_by_state(
        state=state or "",
        states=states,
        city=city,
        name=name,
        specialty=specialty,
        min_volume=min_volume,
        page=page,
        per_page=per_page,
        device_profile=effective_profile,
    )
    result["physicians"] = [with_physician_flags(p) for p in result.get("physicians", [])]
    return result


@router.get("/{npi}")
async def get_physician(
    npi: str,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get physician detail from NPPES + profile-aware CMS volumes."""
    physician = await physician_service.get_physician_by_npi(npi, device_profile=device_profile)
    if not physician:
        raise HTTPException(status_code=404, detail=f"Physician not found: {npi}")
    return with_physician_flags(physician)


@router.get("/{npi}/payments")
async def get_physician_payments(
    npi: str,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get Open Payments data for a physician."""
    key_companies = device_profile.get("manufacturers") if device_profile else None
    data = await payment_service.get_payments_for_npi(npi, key_companies=key_companies)
    if data is None:
        return {"npi": npi, "payments": [], "message": "No payment data found"}
    return data


@router.get("/{npi}/history")
async def get_physician_history(
    npi: str,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
    db: AsyncSession = Depends(get_db),
):
    """Get CMS historical volume trends, filtered by profile HCPCS codes."""
    hcpcs_codes = device_profile.get("hcpcs_codes") if device_profile else None
    data = await history_service.get_history_for_npi(npi, db=db, hcpcs_codes=hcpcs_codes)
    if data is None:
        return {"npi": npi, "volume_by_year": {}, "message": "No historical data found"}
    return data


@router.get("/{npi}/trials")
async def get_physician_trials(
    npi: str,
    physician_name: str | None = Query(None),
    skip_cache: bool = Query(False),
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get clinical trial participation with location-based confidence."""
    physician = None
    if not physician_name:
        physician = await physician_service.get_physician_by_npi(npi, device_profile=device_profile)
        if physician:
            physician_name = physician.get("full_name", "")
        else:
            return {"npi": npi, "trials": [], "message": "Physician name required for trial search"}

    # Get physician location for confidence scoring
    if not physician:
        physician = await physician_service.get_physician_by_npi(npi, device_profile=device_profile)
    city = physician.get("practice_city") or physician.get("provider_city") if physician else None
    state = physician.get("practice_state") or physician.get("provider_state") if physician else None

    trials = await trial_service.get_trials_for_physician(
        physician_name, physician_city=city, physician_state=state,
        skip_cache=skip_cache,
    )
    return {"npi": npi, "trials": trials, "total": len(trials)}


@router.get("/{npi}/publications")
async def get_physician_publications(
    npi: str,
    first_name: str | None = Query(None),
    last_name: str | None = Query(None),
    institution: str | None = Query(None),
    skip_cache: bool = Query(False),
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get PubMed publications using profile-aware search terms."""
    if not last_name:
        physician = await physician_service.get_physician_by_npi(npi, device_profile=device_profile)
        if physician:
            first_name = first_name or physician.get("first_name", "")
            last_name = physician.get("last_name", "")

    if not last_name:
        return {"npi": npi, "publications": [], "message": "Last name required for publication search"}

    # Use profile's trial_search_terms for PubMed Tier 3 keyword search
    search_terms = None
    if device_profile:
        search_terms = device_profile.get("trial_search_terms")

    publications = await publication_service.get_publications(
        first_name=first_name,
        last_name=last_name,
        institution=institution,
        npi=npi,
        skip_cache=skip_cache,
        search_terms=search_terms,
    )
    return {"npi": npi, "publications": publications, "total": len(publications)}
