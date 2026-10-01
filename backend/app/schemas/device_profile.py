from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SavedSpecialty(BaseModel):
    """A user-saved custom physician search preset."""
    name: str
    specialty: str = ""
    hcpcs_codes: list[str] = []


class DeviceMarketFilters(BaseModel):
    """The configurable filters that define a device market."""

    # CMS Utilization - procedure codes
    hcpcs_codes: list[str] = []

    # Open Payments - manufacturer name variants keyed by slug
    manufacturers: dict[str, list[str]] = {}

    # NPPES - physician specialty taxonomies
    taxonomies: list[str] = []

    # Clinical Trials - search terms and statuses
    trial_search_terms: list[str] = []
    trial_statuses: list[str] = ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"]

    # CMS Inpatient DRG - hospital-level procedure volumes
    drg_codes: list[str] = []

    # Module system - opt-in to specialty source plugins (e.g., ["tavr"])
    modules: list[str] = []

    # User-saved physician search presets
    saved_specialties: list[SavedSpecialty] = []

    # Display
    procedure_label: str = "procedures"


class DeviceProfileCreate(BaseModel):
    name: str
    description: str = ""
    filters: DeviceMarketFilters


class DeviceProfileUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filters: Optional[DeviceMarketFilters] = None


class DeviceProfileResponse(BaseModel):
    id: UUID
    name: str
    description: str
    is_preset: bool
    is_active: bool
    filters: DeviceMarketFilters
    created_at: str
    updated_at: str


class DeviceProfileListResponse(BaseModel):
    profiles: list[DeviceProfileResponse]
    active_profile_id: Optional[UUID] = None
