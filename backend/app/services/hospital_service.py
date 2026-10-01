"""Hospital service - wraps hospital data loading from multiple sources.

Replicates the merge logic from streamlit_app/pages/01_hospitals.py::load_hospitals()
"""

import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _load_json_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.warning("Hospital data file not found: %s", path)
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else []


def _load_manual_hospitals(config_path: Path) -> list[dict[str, Any]]:
    if not config_path.exists():
        return []
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    manual = config.get("manual_hospitals", [])
    for h in manual:
        h.setdefault("data_source", "CMS Data")
    return manual


def _fix_title_apostrophes(name: str) -> str:
    """"St Joseph'S" -> "St Joseph's" (artifact of str.title())."""
    return re.sub(r"(\w)'S\b", r"\1's", name)


def load_all_hospitals() -> list[dict[str, Any]]:
    """Load and merge hospitals from TVT Registry, CMS-discovered, and manual config.

    All TVT entries are kept (multiple hospitals per city allowed).
    Manual/CMS only added if their city+state isn't already covered by TVT.
    """
    settings = get_settings()
    data_dir = Path(settings.data_dir)
    config_path = Path(settings.config_yaml_path)

    # 1. TVT Registry hospitals (primary)
    tvt_path = data_dir / "output" / "all_hospitals.json"
    tvt_hospitals = _load_json_file(tvt_path)
    for h in tvt_hospitals:
        h.setdefault("data_source", "TVT Registry")

    # 2. Manual hospitals from config.yaml
    manual_hospitals = _load_manual_hospitals(config_path)

    # 3. CMS-discovered hospitals
    cms_path = data_dir / "output" / "cms_discovered_hospitals.json"
    cms_hospitals = _load_json_file(cms_path)
    for h in cms_hospitals:
        h.setdefault("data_source", "CMS Data")

    # Merge: keep ALL TVT entries, only dedup manual/CMS against seen cities
    # (matches Streamlit's load_hospitals() logic exactly)
    merged = list(tvt_hospitals)
    seen = set()
    for h in tvt_hospitals:
        city = (h.get("city") or "").strip().upper()
        state = (h.get("state") or "").strip().upper()
        if city and state:
            seen.add(f"{city}|{state}")

    for source_list in [manual_hospitals, cms_hospitals]:
        for h in source_list:
            city = (h.get("city") or "").strip().upper()
            state = (h.get("state") or "").strip().upper()
            key = f"{city}|{state}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(h)

    # Source names were title-cased with str.title(), which yields "St Joseph'S"
    for h in merged:
        if h.get("name"):
            h["name"] = _fix_title_apostrophes(h["name"])
        for a in h.get("affiliated_hospitals") or []:
            if a.get("name"):
                a["name"] = _fix_title_apostrophes(a["name"])

    logger.info(
        "Loaded %d hospitals (TVT: %d, Manual: %d, CMS: %d)",
        len(merged), len(tvt_hospitals), len(manual_hospitals), len(cms_hospitals),
    )
    return merged


def search_hospitals(
    hospitals: list[dict[str, Any]],
    state: Optional[str] = None,
    states: Optional[list[str]] = None,
    min_volume: Optional[int] = None,
    max_volume: Optional[int] = None,
    star_rating: Optional[int] = None,
    cms_rating: Optional[int] = None,
    search: Optional[str] = None,
    sort_by: str = "volume",
    sort_order: str = "desc",
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any]:
    """Filter, sort, and paginate hospitals."""
    filtered = list(hospitals)

    # State filter
    target_states = set()
    if state:
        target_states.add(state.upper())
    if states:
        target_states.update(s.upper() for s in states)
    if target_states:
        filtered = [h for h in filtered if (h.get("state") or "").upper() in target_states]

    # Volume filter (uses DRG volume if available, falls back to TVT volume)
    if min_volume is not None:
        filtered = [h for h in filtered if _get_volume(h) >= min_volume]
    if max_volume is not None:
        filtered = [h for h in filtered if _get_volume(h) <= max_volume]

    # Star rating filter (TVT 1-3 scale)
    if star_rating is not None:
        filtered = [h for h in filtered if h.get("star_rating") == star_rating]

    # CMS Hospital Compare rating filter (1-5 scale)
    if cms_rating is not None:
        filtered = [h for h in filtered if (h.get("cms_overall_rating") or 0) >= cms_rating]

    # Text search
    if search:
        search_lower = search.lower()
        filtered = [
            h for h in filtered
            if search_lower in (h.get("name") or "").lower()
            or search_lower in (h.get("city") or "").lower()
            or search_lower in (h.get("state") or "").lower()
            or search_lower in (h.get("address") or "").lower()
            or search_lower in (h.get("notes") or "").lower()
        ]

    # Sort (volume/rating use universal helpers that pick best available data)
    sort_keys = {
        "volume": lambda h: _get_volume(h),
        "rating": lambda h: _get_rating(h),
        "name": lambda h: (h.get("name") or "").lower(),
        "state": lambda h: (h.get("state") or "").lower(),
    }
    key_fn = sort_keys.get(sort_by, sort_keys["volume"])
    reverse = sort_order == "desc"
    filtered.sort(key=key_fn, reverse=reverse)

    # Paginate
    total = len(filtered)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = filtered[start:end]

    return {
        "hospitals": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


def _get_volume(h: dict[str, Any]) -> int:
    """Get the best available volume metric for a hospital.

    Uses DRG volume (universal) if available, falls back to TVT annual volume.
    """
    return h.get("drg_volume") or h.get("annual_tavr_volume") or 0


def _get_rating(h: dict[str, Any]) -> int:
    """Get the best available quality rating for a hospital.

    Uses CMS Hospital Compare (1-5) if available, falls back to TVT star rating (1-3).
    """
    return h.get("cms_overall_rating") or h.get("star_rating") or 0


def _slugify(text: str) -> str:
    """Normalize text to a comparable slug: lowercase, only alphanumeric and spaces."""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def find_hospital_by_id(hospitals: list[dict[str, Any]], site_id: str) -> Optional[dict[str, Any]]:
    """Find a hospital by site_id, ccn, entity_id, or name-based slug."""
    for h in hospitals:
        if h.get("site_id") == site_id:
            return h
        if h.get("ccn") == site_id:
            return h
        if h.get("entity_id") == site_id:
            return h
    # Fallback: normalize both the lookup slug and hospital names the same way
    slug = _slugify(site_id)
    for h in hospitals:
        if _slugify(h.get("name") or "") == slug:
            return h
    return None


# ---------------------------------------------------------------------------
# DRG-based hospital discovery (non-TAVR profiles)
# ---------------------------------------------------------------------------


async def load_hospitals_from_drg(drg_codes: list[str]) -> list[dict[str, Any]]:
    """Build a hospital list from CMS DRG data for non-TAVR profiles.

    Instead of using the baked TVT Registry JSON, this discovers hospitals
    directly from Medicare claims data filtered by the profile's DRG codes.
    Returns hospital dicts compatible with the same schema as TVT hospitals.
    """
    from doctor_prospector.sources.cms_drg import cms_drg_source

    result = await cms_drg_source.fetch_cached(drg_codes=drg_codes)
    if not result.data:
        logger.warning("No DRG data returned for codes: %s", drg_codes)
        return []

    hospitals = []
    for drg_h in result.data:
        hospitals.append({
            "name": drg_h.get("fac_name", ""),
            "ccn": drg_h.get("ccn", ""),
            "city": drg_h.get("city", ""),
            "state": drg_h.get("state", ""),
            "zip": drg_h.get("zip", ""),
            "drg_volume": drg_h.get("drg_volume", 0),
            "drg_avg_payment": drg_h.get("drg_avg_payment", 0.0),
            "drg_codes_found": drg_h.get("drg_codes_found", []),
            "data_source": "CMS Data",
        })

    logger.info("Loaded %d hospitals from DRG data (codes: %s)", len(hospitals), drg_codes)
    return hospitals


# ---------------------------------------------------------------------------
# Enrichment: merge data from CMS source plugins into hospital records
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize hospital name for fuzzy matching."""
    n = name.lower().strip()
    for prefix in ("the ", "a "):
        if n.startswith(prefix):
            n = n[len(prefix):]
    for suffix in (" hospital", " medical center", " health system", " health",
                    " healthcare", " medical", " center"):
        if n.endswith(suffix):
            n = n[:-len(suffix)]
    return re.sub(r"[^\w\s]", "", n).strip()


async def enrich_hospitals_with_drg(
    hospitals: list[dict[str, Any]],
    drg_codes: list[str],
) -> list[dict[str, Any]]:
    """Enrich hospital list with CMS DRG volume data.

    Matches by CCN (exact), then falls back to name+state fuzzy matching.
    """
    if not drg_codes:
        return hospitals

    from doctor_prospector.sources.cms_drg import cms_drg_source

    result = await cms_drg_source.fetch_cached(drg_codes=drg_codes)
    if not result.data:
        return hospitals

    # Build lookups
    ccn_lookup: dict[str, dict] = {}
    name_state_lookup: dict[str, dict] = {}
    for drg_h in result.data:
        ccn = drg_h.get("ccn", "").strip()
        if ccn:
            ccn_lookup[ccn] = drg_h
        name_key = f"{_normalize_name(drg_h.get('fac_name', ''))}|{drg_h.get('state', '').upper()}"
        name_state_lookup[name_key] = drg_h

    matched = 0
    for h in hospitals:
        # Try CCN match first (hospitals from CMS POS may have this)
        ccn = h.get("ccn") or h.get("facility_id") or ""
        drg_h = ccn_lookup.get(ccn.strip())

        # Fallback to name+state
        if not drg_h:
            name_key = f"{_normalize_name(h.get('name', ''))}|{h.get('state', '').upper()}"
            drg_h = name_state_lookup.get(name_key)

        if drg_h:
            h["drg_volume"] = drg_h.get("drg_volume")
            h["drg_avg_payment"] = drg_h.get("drg_avg_payment")
            matched += 1

    logger.info("DRG enrichment: matched %d/%d hospitals", matched, len(hospitals))
    return hospitals


async def enrich_hospitals_with_compare(
    hospitals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich hospital list with CMS Hospital Compare quality ratings.

    Matches by facility_id/CCN (exact), then falls back to name+state.
    This is universal data — runs for all profiles.
    """
    from doctor_prospector.sources.cms_hospital_compare import cms_hospital_compare_source

    result = await cms_hospital_compare_source.fetch_cached()
    if not result.data:
        return hospitals

    # Build lookups
    ccn_lookup: dict[str, dict] = {}
    name_state_lookup: dict[str, dict] = {}
    for cmp_h in result.data:
        fid = cmp_h.get("facility_id", "").strip()
        if fid:
            ccn_lookup[fid] = cmp_h
        name_key = f"{_normalize_name(cmp_h.get('facility_name', ''))}|{cmp_h.get('state', '').upper()}"
        name_state_lookup[name_key] = cmp_h

    matched = 0
    for h in hospitals:
        ccn = h.get("ccn") or h.get("facility_id") or ""
        cmp_h = ccn_lookup.get(ccn.strip())

        if not cmp_h:
            name_key = f"{_normalize_name(h.get('name', ''))}|{h.get('state', '').upper()}"
            cmp_h = name_state_lookup.get(name_key)

        if cmp_h and cmp_h.get("overall_rating") is not None:
            h["cms_overall_rating"] = cmp_h["overall_rating"]
            matched += 1

    logger.info("Hospital Compare enrichment: matched %d/%d hospitals", matched, len(hospitals))
    return hospitals
