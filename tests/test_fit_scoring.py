"""Tests for fit scoring algorithm."""

import pytest
from decimal import Decimal

from doctor_prospector.models import Hospital, Physician, FitScore, StarRating
from doctor_prospector.scoring import (
    calculate_fit_score,
    calculate_hospital_volume_points,
    calculate_hospital_rating_points,
    calculate_hospital_age_points,
    calculate_physician_trial_points,
    calculate_physician_volume_points,
    calculate_physician_payment_points,
    generate_targeting_notes,
)


class TestHospitalVolumePoints:
    def test_high_volume(self):
        assert calculate_hospital_volume_points(300) == 20
        assert calculate_hospital_volume_points(200) == 20
    
    def test_medium_high_volume(self):
        assert calculate_hospital_volume_points(150) == 15
        assert calculate_hospital_volume_points(100) == 15
    
    def test_medium_volume(self):
        assert calculate_hospital_volume_points(75) == 10
        assert calculate_hospital_volume_points(50) == 10
    
    def test_low_volume(self):
        assert calculate_hospital_volume_points(25) == 5
        assert calculate_hospital_volume_points(0) == 5


class TestHospitalRatingPoints:
    def test_three_star(self):
        assert calculate_hospital_rating_points(3) == 15
    
    def test_two_star(self):
        assert calculate_hospital_rating_points(2) == 10
    
    def test_one_star(self):
        assert calculate_hospital_rating_points(1) == 5
    
    def test_no_rating(self):
        assert calculate_hospital_rating_points(None) == 0


class TestHospitalAgePoints:
    def test_new_program(self):
        assert calculate_hospital_age_points(1) == 15
        assert calculate_hospital_age_points(2) == 15
    
    def test_established_program(self):
        assert calculate_hospital_age_points(3) == 10
        assert calculate_hospital_age_points(5) == 10
    
    def test_mature_program(self):
        assert calculate_hospital_age_points(6) == 5
        assert calculate_hospital_age_points(10) == 5
    
    def test_unknown_age(self):
        assert calculate_hospital_age_points(None) == 5


class TestPhysicianTrialPoints:
    def test_not_investigator(self):
        assert calculate_physician_trial_points(False, []) == 0
    
    def test_single_trial(self):
        assert calculate_physician_trial_points(True, ["PARTNER 3"]) == 15
    
    def test_multiple_trials(self):
        assert calculate_physician_trial_points(True, ["PARTNER 3", "EVOLUT", "EARLY TAVR"]) == 20
    
    def test_pi_role(self):
        assert calculate_physician_trial_points(True, ["EARLY TAVR PI"]) == 20


class TestPhysicianVolumePoints:
    def test_high_volume(self):
        assert calculate_physician_volume_points(150) == 15
        assert calculate_physician_volume_points(100) == 15
    
    def test_medium_volume(self):
        assert calculate_physician_volume_points(75) == 10
        assert calculate_physician_volume_points(50) == 10
    
    def test_low_volume(self):
        assert calculate_physician_volume_points(25) == 5
    
    def test_unknown_volume(self):
        assert calculate_physician_volume_points(None) == 5


class TestPhysicianPaymentPoints:
    def test_minimal_payments(self):
        assert calculate_physician_payment_points(5000) == 15
        assert calculate_physician_payment_points(0) == 15
    
    def test_moderate_payments(self):
        assert calculate_physician_payment_points(25000) == 10
        assert calculate_physician_payment_points(10000) == 10
    
    def test_heavy_payments(self):
        assert calculate_physician_payment_points(100000) == 5
        assert calculate_physician_payment_points(50000) == 5


class TestFullFitScore:
    @pytest.fixture
    def high_fit_hospital(self):
        return Hospital(
            name="Mount Sinai Hospital",
            city="New York",
            state="NY",
            annual_tavr_volume=513,
            star_rating=StarRating.THREE,
            program_age_years=2,
        )
    
    @pytest.fixture
    def high_fit_physician(self):
        return Physician(
            npi="1234567890",
            first_name="Samin",
            last_name="Sharma",
            suffix="MD",
            primary_hospital="Mount Sinai Hospital",
            estimated_annual_tavr_cases=200,
            is_trial_investigator=True,
            trial_names=["SURTAVI", "COAPT", "MACE"],
            total_device_payments=Decimal("45000"),
        )
    
    @pytest.fixture
    def warm_lead_physician(self):
        return Physician(
            npi="9876543210",
            first_name="Jane",
            last_name="Example",
            suffix="MD",
            primary_hospital="Morristown Medical Center",
            estimated_annual_tavr_cases=100,
            is_trial_investigator=True,
            trial_names=["EARLY TAVR PI", "PROGRESS PI"],
            total_device_payments=Decimal("75000"),
            has_known_relationship=True,
        )
    
    def test_high_fit_score(self, high_fit_hospital, high_fit_physician):
        prospect = calculate_fit_score(high_fit_hospital, high_fit_physician)
        
        assert prospect.fit_score_category == FitScore.HIGH
        assert prospect.fit_score_value >= 70
        assert not prospect.warm_lead
    
    def test_hospital_only_scoring(self, high_fit_hospital):
        prospect = calculate_fit_score(high_fit_hospital, None)
        
        # Hospital-only score (max 50 points)
        assert prospect.fit_score_value <= 50
        assert prospect.physician is None
    
    def test_warm_lead_flag(self, high_fit_hospital, warm_lead_physician):
        prospect = calculate_fit_score(high_fit_hospital, warm_lead_physician)
        
        assert prospect.warm_lead is True
    
    def test_score_breakdown(self, high_fit_hospital, high_fit_physician):
        prospect = calculate_fit_score(high_fit_hospital, high_fit_physician)
        
        # Verify breakdown adds up
        total = (
            prospect.hospital_volume_points +
            prospect.hospital_rating_points +
            prospect.hospital_age_points +
            prospect.physician_trial_points +
            prospect.physician_volume_points +
            prospect.physician_payment_points
        )
        assert total == prospect.fit_score_value


class TestTargetingNotes:
    @pytest.fixture
    def high_volume_hospital(self):
        return Hospital(
            name="Test Hospital",
            city="Test City",
            state="NY",
            annual_tavr_volume=300,
            star_rating=StarRating.THREE,
            program_age_years=10,
        )
    
    def test_high_volume_note(self, high_volume_hospital):
        prospect = calculate_fit_score(high_volume_hospital, None)
        notes = generate_targeting_notes(prospect)
        
        assert "High-volume" in notes
    
    def test_three_star_note(self, high_volume_hospital):
        prospect = calculate_fit_score(high_volume_hospital, None)
        notes = generate_targeting_notes(prospect)
        
        assert "3-star" in notes
    
    def test_warm_lead_note(self):
        hospital = Hospital(
            name="Morristown Medical Center",
            city="Morristown",
            state="NJ",
            annual_tavr_volume=300,
        )
        physician = Physician(
            npi="9876543210",
            first_name="Jane",
            last_name="Example",
            has_known_relationship=True,
        )
        prospect = calculate_fit_score(hospital, physician)
        notes = generate_targeting_notes(prospect)
        
        assert "WARM LEAD" in notes
