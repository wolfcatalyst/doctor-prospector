from typing import Optional
from pydantic import BaseModel


class HospitalSummary(BaseModel):
    name: str
    city: str
    state: str
    site_id: Optional[str] = None
    annual_tavr_volume: Optional[int] = None
    cumulative_volume: Optional[int] = None
    star_rating: Optional[int] = None
    first_tavr_date: Optional[str] = None
    data_source: str = "Unknown"
    reporting_period: Optional[str] = None
    # CMS/POS facility fields
    address: Optional[str] = None
    zip_code: Optional[str] = None
    bed_count: Optional[int] = None
    has_cath_lab: Optional[bool] = None
    has_open_heart_surgery: Optional[bool] = None
    cath_lab_rooms: Optional[int] = None
    teaching_status: Optional[str] = None
    ownership_type: Optional[str] = None
    notes: Optional[str] = None
    # CMS Inpatient DRG fields (universal procedure volumes)
    drg_volume: Optional[int] = None
    drg_avg_payment: Optional[float] = None
    # CMS Hospital Compare (universal quality rating 1-5)
    cms_overall_rating: Optional[int] = None


class HospitalDetail(HospitalSummary):
    entity_id: Optional[str] = None
    composite_score: Optional[float] = None
    eligible_procedures: Optional[int] = None
    rating_label: Optional[str] = None
    tvt_registry_url: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    physician_count: Optional[int] = None
    total_tavr_volume: Optional[int] = None


class HospitalListResponse(BaseModel):
    hospitals: list[HospitalSummary]
    total: int
    page: int
    per_page: int
    total_pages: int
