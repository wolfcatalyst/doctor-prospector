"""Data-quality flags for hospitals and physicians.

Public sources disagree, lag, and sometimes describe the wrong thing (a
physician's billing office instead of a hospital). These flags tell the
user when a record deserves a second look. They never hide data.

Levels:
  red    -- the record is probably not what it looks like, or key facts
            can't be verified
  yellow -- usable, but something is missing or worth double-checking

The frontend shows them only when the "Show data warnings" preference is
on; the API always returns them.
"""

from datetime import date, datetime
from typing import Any

# NPPES records untouched this long often have a stale practice address
STALE_NPI_YEARS = 5


def _flag(level: str, code: str, message: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message}


def hospital_flags(h: dict[str, Any], is_tavr: bool) -> list[dict[str, str]]:
    """Flags for one hospital/site record."""
    flags: list[dict[str, str]] = []
    name = h.get("name") or ""

    if h.get("site_type") == "practice":
        flags.append(_flag(
            "red", "PHYSICIAN_PRACTICE",
            "Physician practice office, not a hospital. CMS reports volume where "
            "doctors bill; procedures happen at the affiliated hospitals.",
        ))
        return flags
    if name.startswith("TAVR Site -"):
        flags.append(_flag(
            "red", "UNIDENTIFIED_SITE",
            "Unidentified billing address. No hospital or practice is registered "
            "here in CMS data; check the affiliated hospitals instead.",
        ))
        return flags

    if not h.get("ccn"):
        flags.append(_flag(
            "red", "NO_FACILITY_MATCH",
            "Not matched to a CMS facility record (sources use different names). "
            "Beds, cath lab, CMS rating and Medicare volume may be missing.",
        ))
    elif h.get("name_source") == "CMS_POS" and h.get("name_match_tier") == 3:
        flags.append(_flag(
            "yellow", "ZIP_ONLY_MATCH",
            "Facility identified by ZIP code only (the one hospital in that ZIP). "
            "Verify the name before relying on it.",
        ))

    if is_tavr and h.get("ccn"):
        missing = []
        if h.get("has_cath_lab") is False:
            missing.append("cath lab")
        if h.get("has_open_heart_surgery") is False:
            missing.append("open-heart surgery")
        if missing:
            flags.append(_flag(
                "yellow", "MISSING_TAVR_CAPABILITY",
                f"CMS lists no {' or '.join(missing)} here. TAVR programs normally "
                "have both, so the CMS record may be outdated or this is a satellite campus.",
            ))

    if h.get("ccn") and h.get("cms_overall_rating") is None:
        flags.append(_flag(
            "yellow", "NO_CMS_RATING",
            "No CMS Hospital Compare star rating (not rated, or too few reported measures).",
        ))

    return flags


def physician_flags(p: dict[str, Any], today: date | None = None) -> list[dict[str, str]]:
    """Flags for one physician record (NPPES + CMS utilization)."""
    flags: list[dict[str, str]] = []
    today = today or date.today()

    if p.get("address_mismatch"):
        flags.append(_flag(
            "yellow", "MAY_HAVE_MOVED",
            f"Current NPI address is in {p.get('nppes_current_city')}, "
            f"{p.get('nppes_current_state')} but Medicare billing was in "
            f"{p.get('cms_billing_city')}, {p.get('cms_billing_state')}. "
            "They may have moved since the billing year.",
        ))

    updated = p.get("last_updated")
    if updated:
        try:
            age_years = (today - datetime.strptime(updated[:10], "%Y-%m-%d").date()).days / 365.25
            if age_years >= STALE_NPI_YEARS:
                flags.append(_flag(
                    "yellow", "STALE_NPI_RECORD",
                    f"NPI record last updated {updated[:10]} ({int(age_years)} years ago); "
                    "address and specialty may be out of date.",
                ))
        except ValueError:
            pass

    if p.get("has_volume") is False or p.get("total_services") == 0:
        flags.append(_flag(
            "yellow", "NO_MEDICARE_VOLUME",
            "No Medicare volume for this profile's procedures. CMS hides counts "
            "under 11 per code, and non-Medicare cases aren't included.",
        ))

    return flags


def with_hospital_flags(h: dict[str, Any], is_tavr: bool) -> dict[str, Any]:
    """Copy of a cached hospital record with data_flags attached."""
    return {**h, "data_flags": hospital_flags(h, is_tavr)}


def with_physician_flags(p: dict[str, Any]) -> dict[str, Any]:
    return {**p, "data_flags": physician_flags(p)}
