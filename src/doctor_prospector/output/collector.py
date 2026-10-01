"""Data collector for export system.

Assembles complete export data from the Streamlit session state caches
at export time, producing a clean ExportData model for the writers.
"""

import logging
import urllib.parse
from typing import Any

from .models import (
    ExportData,
    ExportOptions,
    HospitalExportRecord,
    PhysicianExportRecord,
)

logger = logging.getLogger(__name__)


def collect_export_data(
    export_queue: list[dict[str, Any]],
    options: ExportOptions,
    session_state: dict[str, Any],
) -> ExportData:
    """Assemble complete export data from queue + session state caches.

    Args:
        export_queue: List of dicts, each with 'hospital', 'physicians', 'trials', 'timestamp'.
        options: User-selected export options (which data types to include).
        session_state: Streamlit session_state dict (for payment_cache, physician_pubs_cache, etc.).

    Returns:
        ExportData with all hospitals, physicians, and enrichment data assembled.
    """
    payment_cache = session_state.get("payment_cache", {})
    pubs_cache = session_state.get("physician_pubs_cache", {})
    trials_cache = session_state.get("physician_trials_cache", {})
    historical_data = session_state.get("historical_data", {})

    hospitals = []
    for item in export_queue:
        h = item.get("hospital", {})
        physician_records = []

        for p in item.get("physicians", []):
            npi = p.get("npi", "")
            full_name = (
                p.get("name_with_credential")
                or p.get("full_name")
                or p.get("provider_name", "Unknown")
            )

            # Extract name parts for URL building
            first_name = p.get("first_name", "")
            last_name = p.get("last_name", "")
            if not first_name and full_name:
                parts = full_name.replace(",", "").split()
                first_name = parts[0] if parts else ""
                last_name = parts[-1] if len(parts) > 1 else ""

            city = p.get("practice_city") or p.get("provider_city") or h.get("city", "")
            state = p.get("practice_state") or h.get("state", "")

            # Get enrichment data from caches
            trials = []
            if options.include_trials:
                trials = _get_physician_trials(npi, trials_cache, item.get("trials", []))

            publications = []
            if options.include_publications:
                publications = _get_publications(npi, pubs_cache)

            payments = None
            if options.include_payments:
                payments = _get_payments(npi, payment_cache)

            historical = None
            if options.include_historical:
                historical = _get_historical(npi, historical_data)

            rec = PhysicianExportRecord(
                npi=npi,
                full_name=full_name,
                credential=p.get("credential"),
                primary_specialty=p.get("primary_specialty"),
                tavr_volume=p.get("total_services", 0) or 0,
                hospital_name=h.get("name", ""),
                hospital_city=h.get("city", ""),
                hospital_state=h.get("state", ""),
                practice_address=p.get("practice_address"),
                practice_address_line1=p.get("practice_address_line1"),
                practice_address_line2=p.get("practice_address_line2"),
                practice_city=city,
                practice_state=state,
                practice_postal_code=p.get("practice_postal_code", ""),
                practice_phone=p.get("practice_phone"),
                trials=trials,
                publications=publications,
                payments=payments,
                historical=historical,
                npi_registry_url=(
                    f"https://npiregistry.cms.hhs.gov/provider-view/{npi}" if npi else ""
                ),
                doximity_url=(
                    f"https://www.doximity.com/pub/{urllib.parse.quote(first_name.lower())}-{urllib.parse.quote(last_name.lower())}"
                    if first_name and last_name
                    else ""
                ),
                google_search_url=(
                    f"https://www.google.com/search?q={urllib.parse.quote(f'{full_name} {city} {state} cardiology')}"
                    if full_name and full_name != "Unknown"
                    else ""
                ),
            )
            physician_records.append(rec)

        hospital_rec = HospitalExportRecord(
            name=h.get("name", ""),
            city=h.get("city", ""),
            state=h.get("state", ""),
            # TVT volume for TAVR sites; CMS DRG volume for every other profile
            annual_tavr_volume=int(h.get("annual_tavr_volume") or h.get("drg_volume") or 0),
            cumulative_volume=h.get("cumulative_volume"),
            star_rating=str(h.get("star_rating", "")) if h.get("star_rating") else None,
            first_tavr_date=str(h.get("first_tavr_date", "")) if h.get("first_tavr_date") else None,
            site_id=h.get("site_id"),
            tvt_registry_url=h.get("tvt_registry_url"),
            reporting_period=h.get("reporting_period"),
            # POS facility details
            bed_count=h.get("bed_count"),
            has_cath_lab=h.get("has_cath_lab"),
            has_open_heart_surgery=h.get("has_open_heart_surgery"),
            cath_lab_rooms=h.get("cath_lab_rooms"),
            teaching_status=h.get("teaching_status"),
            ownership_type=h.get("ownership_type"),
            physicians=physician_records,
        )
        hospitals.append(hospital_rec)

    return ExportData(hospitals=hospitals, options=options)


def _get_physician_trials(
    npi: str, trials_cache: dict[str, Any], queue_trials: list[dict]
) -> list[dict]:
    """Get trials for a physician from cache, falling back to queue-level trials."""
    try:
        # Per-physician trial cache is the primary source
        cached = trials_cache.get(f"trials_{npi}")
        if cached is not None and isinstance(cached, list):
            return cached

        # Also check without prefix
        cached = trials_cache.get(npi)
        if cached is not None and isinstance(cached, list):
            return cached
    except Exception as e:
        logger.warning(f"Error reading trials cache for NPI {npi}: {e}")

    # Fallback: return queue-level trials (hospital-level, not physician-specific)
    return queue_trials


def _get_publications(npi: str, pubs_cache: dict[str, Any]) -> list[dict]:
    """Get publications for a physician from cache."""
    try:
        pubs = pubs_cache.get(f"pubs_{npi}")
        if pubs is not None and isinstance(pubs, list):
            return pubs

        # Also check without prefix
        pubs = pubs_cache.get(npi)
        if pubs is not None and isinstance(pubs, list):
            return pubs
    except Exception as e:
        logger.warning(f"Error reading publications cache for NPI {npi}: {e}")

    return []


def _get_payments(npi: str, payment_cache: dict[str, Any]) -> dict[str, Any] | None:
    """Get payment data for a physician from cache."""
    try:
        payments = payment_cache.get(npi)
        if payments is not None and isinstance(payments, dict):
            return payments
    except Exception as e:
        logger.warning(f"Error reading payment cache for NPI {npi}: {e}")

    return None


def _get_historical(npi: str, historical_data: dict[str, Any]) -> dict[str, Any] | None:
    """Get historical trend data for a physician."""
    try:
        data = historical_data.get(npi)
        if data is not None and isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning(f"Error reading historical data for NPI {npi}: {e}")

    return None
