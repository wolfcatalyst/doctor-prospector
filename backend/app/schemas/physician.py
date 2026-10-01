from typing import Any, Optional
from pydantic import BaseModel


class PhysicianSummary(BaseModel):
    npi: str
    full_name: Optional[str] = None
    provider_name: Optional[str] = None
    credential: Optional[str] = None
    primary_specialty: Optional[str] = None
    practice_city: Optional[str] = None
    practice_state: Optional[str] = None
    provider_city: Optional[str] = None
    provider_state: Optional[str] = None
    total_services: int = 0
    total_beneficiaries: int = 0
    has_volume: bool = False
    historical_only: bool = False
    address_mismatch: bool = False


class PhysicianDetail(PhysicianSummary):
    practice_address_line1: Optional[str] = None
    practice_address_line2: Optional[str] = None
    practice_postal_code: Optional[str] = None
    practice_phone: Optional[str] = None
    npi_registry_url: Optional[str] = None
    doximity_url: Optional[str] = None
    google_search_url: Optional[str] = None


class PaymentSummary(BaseModel):
    npi: str
    physician_name: Optional[str] = None
    total_payments: float = 0
    payment_count: int = 0
    avg_payment: float = 0
    companies: dict[str, float] = {}
    top_company: Optional[str] = None
    top_company_amount: float = 0
    years: dict[str, float] = {}
    payment_types: dict[str, float] = {}
    is_heartflow_user: bool = False
    key_relationships: dict[str, float] = {}
    years_active: int = 0
    latest_year: Optional[int] = None
    payment_trend_pct: float = 0
    payment_trend_indicator: str = ""


class HistorySummary(BaseModel):
    npi: str
    provider_name: Optional[str] = None
    total_tavr_procedures: int = 0
    years_active: int = 0
    first_year: Optional[int] = None
    latest_year: Optional[int] = None
    latest_volume: int = 0
    volume_by_year: dict[str, int] = {}
    trends: list[dict[str, Any]] = []
    avg_annual_growth_pct: float = 0
    trend_indicator: str = ""


class TrialSummary(BaseModel):
    nct_id: str
    title: str
    official_title: Optional[str] = None
    study_url: Optional[str] = None
    overall_status: Optional[str] = None
    start_date: Optional[str] = None
    completion_date: Optional[str] = None
    phase: list[str] = []
    enrollment: int = 0
    conditions: list[str] = []
    brief_summary: Optional[str] = None
    lead_sponsor: Optional[str] = None
    investigators: list[dict[str, Any]] = []
    locations: list[dict[str, Any]] = []


class PublicationSummary(BaseModel):
    pmid: str
    title: str
    journal: Optional[str] = None
    pub_date: Optional[str] = None
    abstract: Optional[str] = None
    authors: list[dict[str, Any]] = []
    coauthor_summary: Optional[str] = None
    categories: list[str] = []
    pubmed_url: Optional[str] = None
    confidence_tier: int = 4
    confidence_badge: str = ""
    match_method: Optional[str] = None


class PhysicianSearchResponse(BaseModel):
    physicians: list[PhysicianSummary]
    total: int
    page: int
    per_page: int
    total_pages: int
