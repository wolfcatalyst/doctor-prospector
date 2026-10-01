"""Physician service - wraps PhysicianMatcher and NPPES for physician search."""

import math
import logging
from typing import Any, Optional

from doctor_prospector.enrichment.physician_matcher import PhysicianMatcher
from doctor_prospector.sources.nppes import NPPESSource

logger = logging.getLogger(__name__)

_matcher = None
_nppes = None


def _get_matcher() -> PhysicianMatcher:
    global _matcher
    if _matcher is None:
        _matcher = PhysicianMatcher()
    return _matcher


def _get_nppes() -> NPPESSource:
    global _nppes
    if _nppes is None:
        _nppes = NPPESSource()
    return _nppes


async def search_physicians_by_state(
    state: str,
    states: Optional[list[str]] = None,
    city: Optional[str] = None,
    name: Optional[str] = None,
    specialty: Optional[str] = None,
    min_volume: Optional[int] = None,
    page: int = 1,
    per_page: int = 25,
    device_profile: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Search for physicians by state, filtered by active device profile.

    Wraps PhysicianMatcher.find_physicians_for_state().
    """
    matcher = _get_matcher()

    # Extract profile-specific filters
    hcpcs_codes = None
    if device_profile:
        hcpcs_codes = device_profile.get("hcpcs_codes")

    # Collect physicians from all requested states
    all_physicians = []
    search_states = set()
    if state:
        search_states.add(state.upper())
    if states:
        search_states.update(s.upper() for s in states)

    if not search_states:
        return {"physicians": [], "total": 0, "page": page, "per_page": per_page, "total_pages": 0}

    for st in search_states:
        try:
            physicians = await matcher.find_physicians_for_state(
                state=st,
                specialty=specialty if specialty and specialty != "All" else None,
                limit=500,
                hcpcs_codes=hcpcs_codes,
            )
            all_physicians.extend(physicians)
        except Exception as e:
            logger.error("Error fetching physicians for state %s: %s", st, e)

    # Dedup by NPI
    seen_npis = set()
    deduped = []
    for p in all_physicians:
        npi = p.get("npi")
        if npi and npi not in seen_npis:
            seen_npis.add(npi)
            deduped.append(p)

    # Filter by city
    if city:
        city_lower = city.lower()
        deduped = [
            p for p in deduped
            if city_lower in (p.get("practice_city") or "").lower()
            or city_lower in (p.get("provider_city") or "").lower()
        ]

    # Filter by name
    if name:
        name_lower = name.lower()
        deduped = [
            p for p in deduped
            if name_lower in (p.get("full_name") or "").lower()
            or name_lower in (p.get("provider_name") or "").lower()
        ]

    # Filter by min volume
    if min_volume is not None:
        deduped = [p for p in deduped if (p.get("total_services") or 0) >= min_volume]

    # Sort by volume descending
    deduped.sort(key=lambda p: p.get("total_services") or 0, reverse=True)

    # Paginate
    total = len(deduped)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    page_items = deduped[start:start + per_page]

    return {
        "physicians": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


async def search_physicians_for_hospital(
    hospital: dict[str, Any],
    specialty: Optional[str] = None,
    search_scope: str = "city",
    include_historical: bool = False,
    device_profile: Optional[dict[str, Any]] = None,
) -> list[dict[str, Any]]:
    """Find physicians at a specific hospital.

    Wraps PhysicianMatcher.find_physicians_for_hospital() or
    find_physicians_for_state() + filter_by_city().
    """
    matcher = _get_matcher()

    # Extract profile-specific filters
    hcpcs_codes = None
    if device_profile:
        hcpcs_codes = device_profile.get("hcpcs_codes")

    if search_scope == "state":
        physicians = await matcher.find_physicians_for_state(
            state=hospital.get("state", ""),
            specialty=specialty if specialty and specialty != "All" else None,
            hcpcs_codes=hcpcs_codes,
        )
    else:
        physicians = await matcher.find_physicians_for_hospital(
            hospital=hospital,
            specialty=specialty if specialty and specialty != "All" else None,
            include_nearby_cities=(search_scope == "all"),
            hcpcs_codes=hcpcs_codes,
        )

    # Merge historical if requested
    if include_historical:
        try:
            from doctor_prospector.sources.cms_historical import CMSHistoricalSource
            historical_source = CMSHistoricalSource()
            npis = [p.get("npi") for p in physicians if p.get("npi")]
            if npis:
                hist_result = await historical_source.fetch_cached(
                    npi=",".join(npis[:50]),
                    state=hospital.get("state", ""),
                )
                if hist_result.data:
                    hist_by_npi = {d["npi"]: d for d in hist_result.data if d.get("npi")}
                    physicians = await matcher.merge_historical_physicians(
                        physicians, hist_by_npi, hospital.get("state", ""),
                        city=hospital.get("city"),
                    )
        except Exception as e:
            logger.error("Error merging historical data: %s", e)

    return physicians


async def get_physician_by_npi(
    npi: str,
    device_profile: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    """Get physician detail from NPPES + CMS utilization volume.

    Uses the active device profile's HCPCS codes to query the right procedures.
    """
    nppes = _get_nppes()
    result = await nppes.fetch_cached(npi=npi)
    if not result.data:
        return None

    physician = result.data[0]

    # Add external URLs
    name = physician.get("full_name", "")
    physician["npi_registry_url"] = f"https://npiregistry.cms.hhs.gov/provider-view/{npi}"
    physician["doximity_url"] = f"https://www.doximity.com/search?q={name.replace(' ', '+')}"
    physician["google_search_url"] = f"https://www.google.com/search?q={name.replace(' ', '+')}+physician"

    # Merge CMS utilization data using profile-specific HCPCS codes
    hcpcs_codes = None
    if device_profile:
        hcpcs_codes = device_profile.get("hcpcs_codes")

    try:
        from doctor_prospector.sources.cms_utilization import CMSUtilizationSource
        cms = CMSUtilizationSource()
        fetch_kwargs: dict[str, Any] = {"npi": npi}
        if hcpcs_codes:
            fetch_kwargs["hcpcs_codes"] = hcpcs_codes
        cms_result = await cms.fetch_cached(**fetch_kwargs)
        if cms_result.data:
            total_services = 0
            total_beneficiaries = 0
            procedure_breakdown = []
            for proc in cms_result.data:
                svc = proc.get("line_service_count", 0) or 0
                ben = proc.get("beneficiary_unique_count", 0) or 0
                total_services += svc
                total_beneficiaries += ben
                if svc > 0:
                    procedure_breakdown.append({
                        "hcpcs_code": proc.get("hcpcs_code", ""),
                        "description": proc.get("hcpcs_description", ""),
                        "services": svc,
                        "beneficiaries": ben,
                    })
            procedure_breakdown.sort(key=lambda x: x["services"], reverse=True)

            # Same check the hospital physician list does: NPPES (current)
            # vs the city they billed Medicare from (data year)
            billing = cms_result.data[0]
            billing_city = (billing.get("provider_city") or "").strip()
            nppes_city = (physician.get("practice_city") or "").strip()
            if billing_city and nppes_city and not _get_matcher()._is_nearby(nppes_city, billing_city):
                physician["address_mismatch"] = True
                physician["nppes_current_city"] = nppes_city
                physician["nppes_current_state"] = physician.get("practice_state") or ""
                physician["cms_billing_city"] = billing_city
                physician["cms_billing_state"] = billing.get("provider_state") or ""
            physician["total_services"] = total_services
            physician["total_beneficiaries"] = total_beneficiaries
            physician["has_volume"] = total_services > 0
            physician["procedure_breakdown"] = procedure_breakdown
        else:
            physician.setdefault("total_services", 0)
            physician.setdefault("total_beneficiaries", 0)
            physician.setdefault("has_volume", False)
    except Exception as e:
        logger.warning("Could not fetch CMS utilization for %s: %s", npi, e)
        physician.setdefault("total_services", 0)
        physician.setdefault("total_beneficiaries", 0)
        physician.setdefault("has_volume", False)

    return physician
