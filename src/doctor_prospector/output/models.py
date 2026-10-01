"""Export data models for Doctor Prospector.

Pydantic models defining the data contract between the collector and writers.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ExportOptions(BaseModel):
    """User-selected export options from the preview page."""

    include_hospitals: bool = True
    include_trials: bool = True
    include_publications: bool = True
    include_payments: bool = True
    include_contact: bool = True
    include_historical: bool = False
    format_type: str = "excel"  # "excel", "csv", "json", "pdf", "html"


class PhysicianExportRecord(BaseModel):
    """Fully assembled physician record with all enrichment data."""

    # Core physician fields
    npi: str = ""
    full_name: str = "Unknown"
    credential: Optional[str] = None
    primary_specialty: Optional[str] = None
    tavr_volume: int = 0

    # Hospital back-reference
    hospital_name: str = ""
    hospital_city: str = ""
    hospital_state: str = ""

    # Contact info
    practice_address: Optional[str] = None
    practice_address_line1: Optional[str] = None
    practice_address_line2: Optional[str] = None
    practice_city: Optional[str] = None
    practice_state: Optional[str] = None
    practice_postal_code: Optional[str] = None
    practice_phone: Optional[str] = None

    # Enrichment data (pulled from session state caches at export time)
    trials: list[dict[str, Any]] = Field(default_factory=list)
    publications: list[dict[str, Any]] = Field(default_factory=list)
    payments: Optional[dict[str, Any]] = None
    historical: Optional[dict[str, Any]] = None

    # External URLs for contact sheet
    npi_registry_url: str = ""
    doximity_url: str = ""
    google_search_url: str = ""


class HospitalExportRecord(BaseModel):
    """Hospital with its associated physicians for export."""

    name: str = ""
    city: str = ""
    state: str = ""
    annual_tavr_volume: int = 0
    cumulative_volume: Optional[int] = None
    star_rating: Optional[str] = None
    first_tavr_date: Optional[str] = None
    site_id: Optional[str] = None
    tvt_registry_url: Optional[str] = None
    reporting_period: Optional[str] = None
    # POS facility details
    bed_count: Optional[int] = None
    has_cath_lab: Optional[bool] = None
    has_open_heart_surgery: Optional[bool] = None
    cath_lab_rooms: Optional[int] = None
    teaching_status: Optional[str] = None
    ownership_type: Optional[str] = None
    physicians: list[PhysicianExportRecord] = Field(default_factory=list)


class ExportData(BaseModel):
    """Complete assembled export dataset."""

    hospitals: list[HospitalExportRecord] = Field(default_factory=list)
    options: ExportOptions = Field(default_factory=ExportOptions)
    exported_at: datetime = Field(default_factory=datetime.now)

    @property
    def all_physicians(self) -> list[PhysicianExportRecord]:
        """Flat list of all physicians across all hospitals."""
        return [p for h in self.hospitals for p in h.physicians]

    @property
    def summary(self) -> dict[str, int]:
        """Summary counts for display."""
        physicians = self.all_physicians
        return {
            "total_hospitals": len(self.hospitals),
            "total_physicians": len(physicians),
            "total_trials": sum(len(p.trials) for p in physicians),
            "total_publications": sum(len(p.publications) for p in physicians),
        }
