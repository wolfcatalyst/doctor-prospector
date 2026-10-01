"""Export service - assembles enrichment data and generates export files.

Unlike the Streamlit collector which reads from session_state caches,
this service fetches enrichment data at export time using backend services.
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.config import get_settings
from doctor_prospector.output.models import (
    ExportData,
    ExportOptions,
    HospitalExportRecord,
    PhysicianExportRecord,
)
from doctor_prospector.output.router import export_data

from . import (
    hospital_service,
    payment_service,
    publication_service,
    trial_service,
    history_service,
)

logger = logging.getLogger(__name__)

EXPORT_DIR = Path(get_settings().data_dir) / "exports"
HISTORY_FILE = EXPORT_DIR / "export_history.json"


def _ensure_dirs():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def _load_history() -> list[dict[str, Any]]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history(history: list[dict[str, Any]]):
    _ensure_dirs()
    HISTORY_FILE.write_text(
        json.dumps(history, indent=2, default=str), encoding="utf-8"
    )


async def generate_export(
    queue_items: list[dict[str, Any]],
    options: dict[str, Any],
    hospital_list: Optional[list[dict[str, Any]]] = None,
) -> tuple[str, bytes, str, dict[str, Any]]:
    """Generate an export file from the queue.

    Args:
        queue_items: List of {hospitalId, hospitalName, physicianNpis, hospital?, physicians?}
        options: Export options (format_type, include_* flags)
        hospital_list: Enriched hospital list for the active profile (falls back
            to the TVT/discovered file when not given)

    Returns:
        (filename, file_bytes, mime_type, history_record)
    """
    export_options = ExportOptions(**options)
    export_id = str(uuid.uuid4())[:8]

    # Build full hospital + physician records with enrichment
    hospitals = []
    total_physicians = 0

    for item in queue_items:
        hospital_id = item.get("hospitalId", "")
        hospital_name = item.get("hospitalName", "Unknown Hospital")
        physician_npis = item.get("physicianNpis", [])

        # Try to load full hospital data from the service
        hospital_data = item.get("hospital")
        if not hospital_data:
            if hospital_list is None:
                hospital_list = hospital_service.load_all_hospitals()
            hospital_data = hospital_service.find_hospital_by_id(hospital_list, hospital_id)
        if not hospital_data:
            hospital_data = {"name": hospital_name, "city": "", "state": ""}

        # Build physician records with enrichment
        physician_records = []
        for npi in physician_npis:
            rec = await _build_physician_record(
                npi, hospital_data, export_options
            )
            physician_records.append(rec)

        total_physicians += len(physician_records)

        hospital_rec = HospitalExportRecord(
            name=hospital_data.get("name", hospital_name),
            city=hospital_data.get("city", ""),
            state=hospital_data.get("state", ""),
            # TVT volume for TAVR sites; CMS DRG volume for every other profile
            annual_tavr_volume=int(hospital_data.get("annual_tavr_volume") or hospital_data.get("drg_volume") or 0),
            cumulative_volume=hospital_data.get("cumulative_volume"),
            star_rating=(
                str(hospital_data["star_rating"])
                if hospital_data.get("star_rating")
                else None
            ),
            first_tavr_date=(
                str(hospital_data["first_tavr_date"])
                if hospital_data.get("first_tavr_date")
                else None
            ),
            site_id=hospital_data.get("site_id"),
            tvt_registry_url=hospital_data.get("tvt_registry_url"),
            reporting_period=hospital_data.get("reporting_period"),
            bed_count=hospital_data.get("bed_count"),
            has_cath_lab=hospital_data.get("has_cath_lab"),
            has_open_heart_surgery=hospital_data.get("has_open_heart_surgery"),
            cath_lab_rooms=hospital_data.get("cath_lab_rooms"),
            teaching_status=hospital_data.get("teaching_status"),
            ownership_type=hospital_data.get("ownership_type"),
            physicians=physician_records,
        )
        hospitals.append(hospital_rec)

    # Generate the export
    data = ExportData(hospitals=hospitals, options=export_options)
    filename, file_bytes, mime_type = export_data(data)

    if file_bytes is None:
        raise ValueError(f"Export format '{export_options.format_type}' is not yet supported")

    # Save file to disk for history/re-download
    _ensure_dirs()
    file_path = EXPORT_DIR / f"{export_id}_{filename}"
    file_path.write_bytes(file_bytes)

    # Record in history
    history_record = {
        "export_id": export_id,
        "filename": filename,
        "file_path": str(file_path),
        "format": export_options.format_type,
        "hospital_count": len(hospitals),
        "physician_count": total_physicians,
        "file_size_bytes": len(file_bytes),
        "status": "completed",
        "created_at": datetime.now().isoformat(),
        "options": options,
    }
    history = _load_history()
    history.insert(0, history_record)
    # Keep last 50 exports
    history = history[:50]
    _save_history(history)

    logger.info(
        "Export %s generated: %s (%d bytes, %d hospitals, %d physicians)",
        export_id, filename, len(file_bytes), len(hospitals), total_physicians,
    )

    return filename, file_bytes, mime_type, history_record


async def _build_physician_record(
    npi: str,
    hospital_data: dict[str, Any],
    options: ExportOptions,
) -> PhysicianExportRecord:
    """Build a fully enriched physician record by fetching from all services."""
    import urllib.parse

    # Get base physician info from NPPES
    from . import physician_service
    physician = await physician_service.get_physician_by_npi(npi)
    if not physician:
        physician = {"npi": npi, "full_name": "Unknown", "first_name": "", "last_name": ""}

    full_name = physician.get("full_name", "Unknown")
    first_name = physician.get("first_name", "")
    last_name = physician.get("last_name", "")
    city = physician.get("practice_city", "") or hospital_data.get("city", "")
    state = physician.get("practice_state", "") or hospital_data.get("state", "")

    # Fetch enrichment data in parallel
    tasks = {}

    if options.include_trials:
        tasks["trials"] = trial_service.get_trials_for_physician(full_name)

    if options.include_publications:
        tasks["publications"] = publication_service.get_publications(
            first_name=first_name,
            last_name=last_name,
            institution=hospital_data.get("name"),
            npi=npi,
        )

    if options.include_payments:
        tasks["payments"] = payment_service.get_payments_for_npi(npi)

    if options.include_historical:
        tasks["history"] = history_service.get_history_for_npi(npi)

    # Run all enrichment tasks in parallel
    results = {}
    if tasks:
        gathered = await asyncio.gather(
            *tasks.values(), return_exceptions=True
        )
        for key, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                logger.warning("Enrichment %s failed for NPI %s: %s", key, npi, result)
                results[key] = None
            else:
                results[key] = result

    # Parse enrichment results
    trials = results.get("trials", []) or []
    publications = results.get("publications", []) or []
    payments = results.get("payments")
    history = results.get("history")

    # Payments come back as a summary dict from payment_service
    if isinstance(payments, dict) and "total_payments" in payments:
        payment_export = {
            "total_payments": payments.get("total_payments", 0),
            "companies": payments.get("companies", {}),
            "years": payments.get("years", {}),
            "payment_types": payments.get("payment_types", {}),
        }
    else:
        payment_export = None

    # History comes back as a summary dict
    if isinstance(history, dict) and "volume_by_year" in history:
        history_export = {
            "latest_volume": history.get("latest_volume", 0),
            "avg_annual_growth_pct": history.get("avg_annual_growth_pct", 0),
            "trend_indicator": history.get("trend_indicator", "—"),
            "volume_by_year": history.get("volume_by_year", {}),
        }
    else:
        history_export = None

    return PhysicianExportRecord(
        npi=npi,
        full_name=full_name,
        credential=physician.get("credential"),
        primary_specialty=physician.get("primary_specialty"),
        tavr_volume=physician.get("total_services", 0) or 0,
        hospital_name=hospital_data.get("name", ""),
        hospital_city=hospital_data.get("city", ""),
        hospital_state=hospital_data.get("state", ""),
        practice_address_line1=physician.get("practice_address_line1"),
        practice_address_line2=physician.get("practice_address_line2"),
        practice_city=city,
        practice_state=state,
        practice_postal_code=physician.get("practice_postal_code", ""),
        practice_phone=physician.get("practice_phone"),
        trials=trials,
        publications=publications,
        payments=payment_export,
        historical=history_export,
        npi_registry_url=f"https://npiregistry.cms.hhs.gov/provider-view/{npi}" if npi else "",
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


def get_export_history() -> list[dict[str, Any]]:
    """Get list of past exports."""
    return _load_history()


def get_export_by_id(export_id: str) -> Optional[dict[str, Any]]:
    """Find an export record by ID."""
    for record in _load_history():
        if record.get("export_id") == export_id:
            return record
    return None


def get_export_file(export_id: str) -> Optional[tuple[str, bytes, str]]:
    """Get export file bytes for download.

    Returns (filename, file_bytes, mime_type) or None.
    """
    record = get_export_by_id(export_id)
    if not record:
        return None

    file_path = Path(record["file_path"])
    if not file_path.exists():
        return None

    fmt = record.get("format", "excel")
    mime_types = {
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "json": "application/json",
    }

    return (
        record["filename"],
        file_path.read_bytes(),
        mime_types.get(fmt, "application/octet-stream"),
    )
