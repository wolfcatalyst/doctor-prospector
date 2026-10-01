import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user, get_active_device_profile
from app.services import hospital_service, physician_service, trial_service
from app.services.data_flags import with_hospital_flags, with_physician_flags

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache loaded hospitals in memory (reloaded on restart)
_hospitals_cache: list | None = None
# Track whether Hospital Compare enrichment has been applied (TVT list)
_compare_enriched: bool = False
# Cache for DRG-based hospital lists, keyed by sorted drg_codes tuple
_drg_hospitals_cache: dict[tuple, list] = {}


def _get_tvt_hospitals() -> list:
    """Load TVT Registry hospitals (used for TAVR profiles)."""
    global _hospitals_cache
    if _hospitals_cache is None:
        _hospitals_cache = hospital_service.load_all_hospitals()
    return _hospitals_cache


def _has_tavr_module(device_profile: dict | None) -> bool:
    """Check if the active profile uses the TAVR module."""
    if not device_profile:
        return True  # default to TVT if no profile
    modules = device_profile.get("modules", [])
    return "tavr" in modules


async def _get_enriched_hospitals(device_profile: dict | None = None) -> list:
    """Get hospitals enriched with CMS data.

    For TAVR profiles: loads TVT Registry hospitals + DRG/Compare enrichment.
    For non-TAVR profiles: builds hospital list from DRG data + Compare enrichment.
    """
    global _compare_enriched

    if _has_tavr_module(device_profile):
        # TAVR path: TVT hospitals + enrichment
        hospitals = _get_tvt_hospitals()

        if not _compare_enriched:
            await hospital_service.enrich_hospitals_with_compare(hospitals)
            _compare_enriched = True

        if device_profile:
            drg_codes = device_profile.get("drg_codes", [])
            if drg_codes:
                await hospital_service.enrich_hospitals_with_drg(hospitals, drg_codes)

        return hospitals
    else:
        # Non-TAVR path: build hospital list from DRG data
        drg_codes = device_profile.get("drg_codes", []) if device_profile else []
        if not drg_codes:
            logger.warning("Non-TAVR profile has no DRG codes — no hospitals to show")
            return []

        cache_key = tuple(sorted(drg_codes))
        if cache_key not in _drg_hospitals_cache:
            hospitals = await hospital_service.load_hospitals_from_drg(drg_codes)
            await hospital_service.enrich_hospitals_with_compare(hospitals)
            _drg_hospitals_cache[cache_key] = hospitals

        return _drg_hospitals_cache[cache_key]


@router.get("")
async def list_hospitals(
    state: str | None = Query(None),
    states: list[str] | None = Query(None),
    min_volume: int | None = Query(None, ge=0),
    max_volume: int | None = Query(None, ge=0),
    star_rating: int | None = Query(None, ge=1, le=3),
    cms_rating: int | None = Query(None, ge=1, le=5),
    search: str | None = Query(None),
    sort_by: str = Query("volume", pattern="^(volume|rating|name|state)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """List hospitals with filtering, sorting, and pagination."""
    hospitals = await _get_enriched_hospitals(device_profile)
    result = hospital_service.search_hospitals(
        hospitals,
        state=state,
        states=states,
        min_volume=min_volume,
        max_volume=max_volume,
        star_rating=star_rating,
        cms_rating=cms_rating,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        per_page=per_page,
    )
    is_tavr = _has_tavr_module(device_profile)
    result["hospitals"] = [with_hospital_flags(h, is_tavr) for h in result["hospitals"]]
    return result


@router.get("/{site_id}")
async def get_hospital(
    site_id: str,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get hospital detail with POS facility data and CMS enrichment."""
    hospitals = await _get_enriched_hospitals(device_profile)
    hospital = hospital_service.find_hospital_by_id(hospitals, site_id)
    if not hospital:
        raise HTTPException(status_code=404, detail=f"Hospital not found: {site_id}")
    return with_hospital_flags(hospital, _has_tavr_module(device_profile))


@router.get("/{site_id}/physicians")
async def get_hospital_physicians(
    site_id: str,
    specialty: str | None = Query(None),
    search_scope: str = Query("city", pattern="^(city|state|all)$"),
    include_historical: bool = Query(False),
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get physicians at a hospital."""
    hospitals = await _get_enriched_hospitals(device_profile)
    hospital = hospital_service.find_hospital_by_id(hospitals, site_id)
    if not hospital:
        raise HTTPException(status_code=404, detail=f"Hospital not found: {site_id}")

    physicians = await physician_service.search_physicians_for_hospital(
        hospital=hospital,
        specialty=specialty,
        search_scope=search_scope,
        include_historical=include_historical,
        device_profile=device_profile,
    )
    physicians = [with_physician_flags(p) for p in physicians]
    return {"physicians": physicians, "total": len(physicians)}


@router.get("/{site_id}/trials")
async def get_hospital_trials(
    site_id: str,
    user: dict = Depends(get_current_user),
    device_profile: dict = Depends(get_active_device_profile),
):
    """Get clinical trials at a hospital."""
    hospitals = await _get_enriched_hospitals(device_profile)
    hospital = hospital_service.find_hospital_by_id(hospitals, site_id)
    if not hospital:
        raise HTTPException(status_code=404, detail=f"Hospital not found: {site_id}")

    # Use trial search terms from active profile if available
    condition = None
    if device_profile:
        terms = device_profile.get("trial_search_terms")
        if terms:
            # Quote multi-word terms so ClinicalTrials.gov treats them as
            # phrases; unquoted, "robotic surgery OR ..." matches any "surgery"
            condition = " OR ".join(f'"{t}"' if " " in t else t for t in terms)

    trials = await trial_service.get_trials_for_hospital(
        hospital_name=hospital.get("name", ""),
        state=hospital.get("state"),
        condition=condition,
    )
    return {"trials": trials, "total": len(trials)}


@router.post("/reload")
async def reload_hospitals(user: dict = Depends(get_current_user)):
    """Force reload hospital data from files."""
    global _hospitals_cache, _compare_enriched, _drg_hospitals_cache
    _hospitals_cache = None
    _compare_enriched = False
    _drg_hospitals_cache = {}
    hospitals = _get_tvt_hospitals()
    return {"message": f"Reloaded {len(hospitals)} hospitals"}
