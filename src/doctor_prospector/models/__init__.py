"""Data models for Doctor Prospector."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FitScore(str, Enum):
    """Prospect fit score categories."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class StarRating(int, Enum):
    """TVT Registry star rating."""
    ONE = 1
    TWO = 2
    THREE = 3


class Hospital(BaseModel):
    """Hospital/TAVR program data from TVT Registry."""
    
    # Core identifiers
    name: str
    city: str
    state: str
    
    # TVT Registry data
    annual_tavr_volume: int = Field(ge=0)
    cumulative_tavr_volume: Optional[int] = Field(default=None, ge=0)
    star_rating: Optional[StarRating] = None
    first_tavr_date: Optional[date] = None
    consecutive_3star_years: int = Field(default=0, ge=0)
    
    # Derived/computed
    program_age_years: Optional[int] = None
    hospital_type: Optional[str] = None  # Academic, Community, etc.
    health_system: Optional[str] = None  # Parent system if applicable
    
    # Metadata
    tvt_registry_url: Optional[str] = None
    data_as_of: Optional[datetime] = None
    
    def compute_program_age(self) -> Optional[int]:
        """Calculate years since first TAVR procedure."""
        if self.first_tavr_date:
            today = date.today()
            return today.year - self.first_tavr_date.year
        return None


class Physician(BaseModel):
    """Physician data aggregated from multiple sources."""
    
    # Core identifiers
    npi: str = Field(pattern=r"^\d{10}$")
    first_name: str
    last_name: str
    middle_name: Optional[str] = None
    suffix: Optional[str] = None  # MD, DO, etc.
    
    # Affiliation
    primary_hospital: Optional[str] = None
    hospital_state: Optional[str] = None
    hospital_city: Optional[str] = None
    
    # Role/specialty
    specialty: Optional[str] = None  # Interventional Cardiology, Cardiac Surgery, etc.
    role: Optional[str] = None  # Director, Chief, etc.
    
    # Volume (from CMS Provider Utilization)
    estimated_annual_tavr_cases: Optional[int] = None
    medicare_tavr_cases: Optional[int] = None  # ~65% of total
    
    # KOL indicators
    is_trial_investigator: bool = False
    trial_names: list[str] = Field(default_factory=list)
    is_kol: bool = False
    conference_faculty: list[str] = Field(default_factory=list)  # TCT, ACC, etc.
    
    # Device company relationships (from Open Payments)
    total_device_payments: Decimal = Decimal("0.00")
    edwards_payments: Decimal = Decimal("0.00")
    medtronic_payments: Decimal = Decimal("0.00")
    abbott_payments: Decimal = Decimal("0.00")
    payment_categories: list[str] = Field(default_factory=list)  # Consulting, Research, etc.
    
    # Special flags
    has_known_relationship: bool = False  # You already work with this physician
    notes: Optional[str] = None
    
    # Metadata
    nppes_last_updated: Optional[datetime] = None
    open_payments_year: Optional[int] = None
    
    @property
    def full_name(self) -> str:
        """Return formatted full name."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        if self.suffix:
            parts.append(f", {self.suffix}")
        return " ".join(parts)


class Prospect(BaseModel):
    """Combined hospital + physician prospect with fit scoring."""
    
    # References
    hospital: Hospital
    physician: Optional[Physician] = None
    
    # Scoring
    fit_score_value: int = Field(ge=0, le=100)
    fit_score_category: FitScore
    
    # Score breakdown
    hospital_volume_points: int = 0
    hospital_rating_points: int = 0
    hospital_age_points: int = 0
    physician_trial_points: int = 0
    physician_volume_points: int = 0
    physician_payment_points: int = 0
    
    # Priority/notes
    priority_rank: Optional[int] = None
    targeting_notes: Optional[str] = None
    warm_lead: bool = False  # Known connection exists


class DataSource(BaseModel):
    """Metadata about a data source."""
    
    name: str
    url: str
    description: str
    last_fetched: Optional[datetime] = None
    record_count: Optional[int] = None
    is_free: bool = True
    update_frequency: Optional[str] = None  # "Quarterly", "Annual", etc.
