"""Edwards Connect service - wraps EdwardsConnectSource for the API layer."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_source = None


def _get_source():
    global _source
    if _source is None:
        from doctor_prospector.sources.edwards_connect import EdwardsConnectSource
        _source = EdwardsConnectSource()
    return _source


async def get_all_edwards_hospitals(
    state: Optional[str] = None,
    search: Optional[str] = None,
    force_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Get all Edwards TAVR center listings, optionally filtered."""
    source = _get_source()
    try:
        result = await source.fetch_cached(force_refresh=force_refresh, state=state or None)
        hospitals = result.data if result.data else []
    except Exception as e:
        logger.error("Error fetching Edwards data: %s", e)
        return []

    # Text search filter (applied post-fetch since we cache by state)
    if search:
        search_lower = search.lower()
        hospitals = [
            h for h in hospitals
            if search_lower in (h.get("name") or "").lower()
            or search_lower in (h.get("city") or "").lower()
            or search_lower in (h.get("state") or "").lower()
            or _search_team_members(h.get("team_members", []), search_lower)
        ]

    return hospitals


async def get_edwards_hospital_by_name(
    hospital_name: str,
    city: Optional[str] = None,
    state: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Find an Edwards listing matching a hospital name (fuzzy)."""
    hospitals = await get_all_edwards_hospitals(state=state)
    if not hospitals:
        return None

    name_lower = hospital_name.lower()

    # Exact name match first
    for h in hospitals:
        if (h.get("name") or "").lower() == name_lower:
            return h

    # Substring match
    for h in hospitals:
        h_name = (h.get("name") or "").lower()
        if name_lower in h_name or h_name in name_lower:
            if city and (h.get("city") or "").lower() != city.lower():
                continue
            return h

    return None


def _search_team_members(team_members: list[dict], search_lower: str) -> bool:
    """Check if any team member name matches the search term."""
    for tm in team_members:
        full_name = f"{tm.get('first_name', '')} {tm.get('last_name', '')}".lower()
        if search_lower in full_name:
            return True
    return False
