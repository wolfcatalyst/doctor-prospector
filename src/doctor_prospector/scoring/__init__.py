"""Fit scoring algorithm for TAVR prospects."""

from ..models import FitScore, Hospital, Physician, Prospect


def calculate_hospital_volume_points(volume: int) -> int:
    """
    Score hospital based on annual TAVR volume.
    
    Higher volume = more established program, but also more entrenched.
    Mid-range often best for new technology adoption.
    """
    if volume >= 200:
        return 20  # High volume - established, may or may not need AI
    elif volume >= 100:
        return 15  # Medium-high - good target
    elif volume >= 50:
        return 10  # Medium - growth opportunity
    else:
        return 5   # Low volume - may lack resources/commitment


def calculate_hospital_rating_points(star_rating: int | None) -> int:
    """
    Score hospital based on TVT Registry star rating.
    
    3-star = top outcomes, may not feel need for AI
    2-star = room for improvement, good target
    1-star = struggling, may be desperate or may have systemic issues
    """
    if star_rating == 3:
        return 15  # Excellent outcomes
    elif star_rating == 2:
        return 10  # Good outcomes, room to improve
    elif star_rating == 1:
        return 5   # Below average outcomes
    else:
        return 0   # No rating available


def calculate_hospital_age_points(program_age_years: int | None) -> int:
    """
    Score hospital based on program maturity.
    
    Newer programs often more receptive to adopting new technology.
    Very established programs have entrenched workflows.
    """
    if program_age_years is None:
        return 5
    elif program_age_years < 3:
        return 15  # New program - building expertise
    elif program_age_years <= 5:
        return 10  # Established but still evolving
    else:
        return 5   # Mature program - workflows set


def calculate_physician_trial_points(is_investigator: bool, trial_names: list[str]) -> int:
    """
    Score physician based on clinical trial activity.
    
    Trial investigators are early adopters by definition.
    """
    if not is_investigator:
        return 0
    
    # Check for PI role (more points) vs site investigator
    pi_keywords = ["PI", "Principal", "Lead"]
    is_pi = any(
        any(kw.lower() in trial.lower() for kw in pi_keywords)
        for trial in trial_names
    )
    
    if is_pi or len(trial_names) >= 3:
        return 20  # Major KOL / active PI
    elif len(trial_names) >= 1:
        return 15  # Active in trials
    else:
        return 0


def calculate_physician_volume_points(estimated_cases: int | None) -> int:
    """
    Score physician based on personal case volume.
    
    High-volume operators have more influence and more to gain from efficiency tools.
    """
    if estimated_cases is None:
        return 5  # Unknown
    elif estimated_cases >= 100:
        return 15  # High-volume operator
    elif estimated_cases >= 50:
        return 10  # Medium volume
    else:
        return 5   # Lower volume


def calculate_physician_payment_points(total_payments: float) -> int:
    """
    Score physician based on device manufacturer payments.
    
    Lower payments = less entrenched with existing vendors.
    Very high payments = likely locked in to specific manufacturer.
    
    Note: This is counterintuitive - we WANT physicians who are NOT
    heavily paid by Edwards/Medtronic/Abbott, as they're more open.
    """
    if total_payments < 10000:
        return 15  # Minimal industry ties - most open
    elif total_payments < 50000:
        return 10  # Moderate ties
    else:
        return 5   # Heavy industry involvement - may be entrenched


def calculate_fit_score(hospital: Hospital, physician: Physician | None = None) -> Prospect:
    """
    Calculate overall fit score for a prospect.
    
    Returns a Prospect object with score breakdown.
    """
    # Hospital factors (50 points max)
    hospital_volume_pts = calculate_hospital_volume_points(hospital.annual_tavr_volume)
    hospital_rating_pts = calculate_hospital_rating_points(
        hospital.star_rating.value if hospital.star_rating else None
    )
    hospital_age_pts = calculate_hospital_age_points(hospital.program_age_years)
    
    # Physician factors (50 points max) - only if physician provided
    if physician:
        physician_trial_pts = calculate_physician_trial_points(
            physician.is_trial_investigator,
            physician.trial_names
        )
        physician_volume_pts = calculate_physician_volume_points(
            physician.estimated_annual_tavr_cases
        )
        physician_payment_pts = calculate_physician_payment_points(
            float(physician.total_device_payments)
        )
    else:
        physician_trial_pts = 0
        physician_volume_pts = 0
        physician_payment_pts = 0
    
    # Total score
    total_score = (
        hospital_volume_pts +
        hospital_rating_pts +
        hospital_age_pts +
        physician_trial_pts +
        physician_volume_pts +
        physician_payment_pts
    )
    
    # Categorize
    if total_score >= 70:
        category = FitScore.HIGH
    elif total_score >= 40:
        category = FitScore.MEDIUM
    else:
        category = FitScore.LOW
    
    # Check for warm lead indicators
    warm_lead = False
    if physician and physician.has_known_relationship:
        warm_lead = True
    
    return Prospect(
        hospital=hospital,
        physician=physician,
        fit_score_value=total_score,
        fit_score_category=category,
        hospital_volume_points=hospital_volume_pts,
        hospital_rating_points=hospital_rating_pts,
        hospital_age_points=hospital_age_pts,
        physician_trial_points=physician_trial_pts,
        physician_volume_points=physician_volume_pts,
        physician_payment_points=physician_payment_pts,
        warm_lead=warm_lead
    )


def generate_targeting_notes(prospect: Prospect) -> str:
    """Generate human-readable targeting notes based on scores."""
    notes = []
    
    # Hospital observations
    if prospect.hospital.annual_tavr_volume >= 200:
        notes.append("High-volume program - established market leader.")
    elif prospect.hospital.annual_tavr_volume < 50:
        notes.append("Lower volume - growth opportunity if committed.")
    
    if prospect.hospital.star_rating and prospect.hospital.star_rating.value == 3:
        notes.append("3-star outcomes - excellent quality, may not feel need for AI assistance.")
    elif prospect.hospital.star_rating and prospect.hospital.star_rating.value < 3:
        notes.append("Room for outcome improvement - AI guidance could help.")
    
    if prospect.hospital.program_age_years and prospect.hospital.program_age_years < 3:
        notes.append("Newer program - likely receptive to technology that accelerates learning.")
    
    # Physician observations
    if prospect.physician:
        if prospect.physician.is_trial_investigator:
            notes.append(f"Active trial investigator - early adopter profile.")
        
        if float(prospect.physician.total_device_payments) > 50000:
            notes.append("Heavy device company ties - may be less open to disruption.")
        elif float(prospect.physician.total_device_payments) < 10000:
            notes.append("Limited device company payments - potentially more open.")
        
        if prospect.physician.has_known_relationship:
            notes.append("★ EXISTING RELATIONSHIP - WARM LEAD ★")
    
    return " ".join(notes) if notes else "Standard prospect."
