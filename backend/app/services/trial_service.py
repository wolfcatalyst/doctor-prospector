"""Trial service - wraps ClinicalTrialsSource."""

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _clean_name_for_search(name: str) -> str:
    """Remove middle initials and periods for better clinical trial matching.

    "AMAR S. RANAWAT" -> "Amar Ranawat"
    "John A. Smith, M.D." -> "John Smith"
    """
    # Remove credentials after comma
    name = name.split(",")[0].strip()
    # Remove single-letter initials (with or without period)
    name = re.sub(r"\b[A-Z]\.\s*", "", name)
    name = re.sub(r"\s+[A-Z]\s+", " ", name)
    # Clean up extra spaces
    name = re.sub(r"\s+", " ", name).strip()
    # Title case
    return name.title()

_source = None


def _get_source():
    global _source
    if _source is None:
        from doctor_prospector.sources.clinical_trials import ClinicalTrialsSource
        _source = ClinicalTrialsSource()
    return _source


async def get_trials_for_hospital(
    hospital_name: str,
    state: Optional[str] = None,
    condition: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Get clinical trials at a hospital.

    Args:
        hospital_name: Hospital name to search near
        state: Two-letter state code
        condition: Search condition string (defaults to TAVR)
    """
    source = _get_source()
    search_condition = condition or 'TAVR OR "transcatheter aortic valve"'
    try:
        location = f"{hospital_name}, {state}" if state else hospital_name
        result = await source.fetch_cached(
            condition=search_condition,
            location=location,
        )
        return result.data if result.data else []
    except Exception as e:
        logger.error("Error fetching trials for %s: %s", hospital_name, e)
        return []


async def get_trials_for_physician(
    physician_name: str,
    physician_city: str | None = None,
    physician_state: str | None = None,
    skip_cache: bool = False,
) -> list[dict[str, Any]]:
    """Get clinical trials for a physician (as investigator).

    Cross-references trial locations/investigators against the physician's
    known practice location to assign confidence levels.
    """
    source = _get_source()
    clean_name = _clean_name_for_search(physician_name)
    try:
        if skip_cache:
            data = await source.fetch(investigator=clean_name)
            trials = data if data else []
        else:
            result = await source.fetch_cached(investigator=clean_name)
            trials = result.data if result.data else []
    except Exception as e:
        logger.error("Error fetching trials for physician %s: %s", clean_name, e)
        return []

    # The API matches first/last name per field, so "John" and "Brown" can
    # still come from two different people. Keep only trials where a single
    # listed person carries both names, then score by location.
    name_parts = clean_name.lower().split()
    first_name = name_parts[0] if len(name_parts) > 1 else ""
    last_name = name_parts[-1] if name_parts else ""
    city = (physician_city or "").upper().strip()
    state = (physician_state or "").upper().strip()

    matched = []
    for trial in trials:
        if not _find_person_matches(trial, first_name, last_name):
            continue
        trial["match_confidence"] = _score_trial_match(
            trial, first_name, last_name, city, state,
        )
        matched.append(trial)

    return matched


def _name_matches(person_name: str, first_name: str, last_name: str) -> bool:
    """True if a listed person's name contains both the first and last name as words."""
    words = set(re.findall(r"[a-z]+", (person_name or "").lower()))
    if not last_name or last_name not in words:
        return False
    return not first_name or first_name in words


def _find_person_matches(
    trial: dict[str, Any],
    first_name: str,
    last_name: str,
) -> list[dict[str, Any]]:
    """Return the trial sites/officials where this physician is listed.

    Each match is {"affiliation": str, "city": str, "state": str}.
    """
    matches = []
    for inv in trial.get("investigators", []):
        if _name_matches(inv.get("name", ""), first_name, last_name):
            matches.append({"affiliation": (inv.get("affiliation") or "").upper(), "city": "", "state": ""})
    for loc in trial.get("locations", []):
        for contact in loc.get("contacts", []) or []:
            if _name_matches(contact.get("name", ""), first_name, last_name):
                matches.append({
                    "affiliation": (loc.get("facility") or "").upper(),
                    "city": (loc.get("city") or "").upper().strip(),
                    "state": (loc.get("state") or "").upper().strip(),
                })
    return matches


def _score_trial_match(
    trial: dict[str, Any],
    first_name: str,
    last_name: str,
    city: str,
    state: str,
) -> str:
    """Score how confident we are this trial belongs to this physician.

    Returns: "confirmed" (listed at a site in their city), "likely" (listed
    in their state, or the trial has a site there), or "name_only".
    """
    state_names = {state, _STATE_NAMES.get(state, "")} - {""}
    in_state = False
    for m in _find_person_matches(trial, first_name, last_name):
        if city and (m["city"] == city or city in m["affiliation"]):
            return "confirmed"
        if m["state"] in state_names or any(s in m["affiliation"] for s in state_names if len(s) > 2):
            in_state = True

    if in_state:
        return "likely"
    for loc in trial.get("locations", []):
        if (loc.get("state") or "").upper().strip() in state_names:
            return "likely"
    return "name_only"


_STATE_NAMES = {
    "AL": "ALABAMA", "AK": "ALASKA", "AZ": "ARIZONA", "AR": "ARKANSAS", "CA": "CALIFORNIA",
    "CO": "COLORADO", "CT": "CONNECTICUT", "DE": "DELAWARE", "DC": "DISTRICT OF COLUMBIA",
    "FL": "FLORIDA", "GA": "GEORGIA", "HI": "HAWAII", "ID": "IDAHO", "IL": "ILLINOIS",
    "IN": "INDIANA", "IA": "IOWA", "KS": "KANSAS", "KY": "KENTUCKY", "LA": "LOUISIANA",
    "ME": "MAINE", "MD": "MARYLAND", "MA": "MASSACHUSETTS", "MI": "MICHIGAN", "MN": "MINNESOTA",
    "MS": "MISSISSIPPI", "MO": "MISSOURI", "MT": "MONTANA", "NE": "NEBRASKA", "NV": "NEVADA",
    "NH": "NEW HAMPSHIRE", "NJ": "NEW JERSEY", "NM": "NEW MEXICO", "NY": "NEW YORK",
    "NC": "NORTH CAROLINA", "ND": "NORTH DAKOTA", "OH": "OHIO", "OK": "OKLAHOMA", "OR": "OREGON",
    "PA": "PENNSYLVANIA", "PR": "PUERTO RICO", "RI": "RHODE ISLAND", "SC": "SOUTH CAROLINA",
    "SD": "SOUTH DAKOTA", "TN": "TENNESSEE", "TX": "TEXAS", "UT": "UTAH", "VT": "VERMONT",
    "VA": "VIRGINIA", "WA": "WASHINGTON", "WV": "WEST VIRGINIA", "WI": "WISCONSIN", "WY": "WYOMING",
}
