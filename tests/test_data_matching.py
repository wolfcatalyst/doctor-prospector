"""Tests for data-matching fixes: trials, catalog freshness, POS names, NPPES."""

from doctor_prospector.freshness.probes import _latest_catalog_release
from doctor_prospector.sources.cms_pos import CMSPOSSource
from doctor_prospector.sources.nppes import NPPESSource

from app.services.trial_service import _find_person_matches, _name_matches, _score_trial_match


def _trial(officials=(), sites=()):
    """Build a parsed trial: officials = [(name, affiliation)], sites = [(contact, city, state)]."""
    return {
        "investigators": [{"name": n, "affiliation": a} for n, a in officials],
        "locations": [
            {"facility": f"{city} Hospital", "city": city, "state": state, "contacts": [{"name": c}]}
            for c, city, state in sites
        ],
    }


class TestTrialNameMatching:
    def test_requires_both_names_on_one_person(self):
        assert _name_matches("John M. Brown, MD", "john", "brown")
        assert not _name_matches("John Smith", "john", "brown")
        assert not _name_matches("Brownstein", "", "brown")

    def test_split_names_across_people_do_not_match(self):
        trial = _trial(officials=[("John Smith", "Mayo"), ("Alice Brown", "Mayo")])
        assert _find_person_matches(trial, "john", "brown") == []

    def test_site_contact_in_city_is_confirmed(self):
        trial = _trial(sites=[("John Brown, MD", "Morristown", "New Jersey")])
        assert _score_trial_match(trial, "john", "brown", "MORRISTOWN", "NJ") == "confirmed"

    def test_same_state_is_likely(self):
        trial = _trial(sites=[("John Brown", "Newark", "New Jersey")])
        assert _score_trial_match(trial, "john", "brown", "MORRISTOWN", "NJ") == "likely"

    def test_other_state_is_name_only(self):
        trial = _trial(sites=[("John Brown", "Boston", "Massachusetts")])
        assert _score_trial_match(trial, "john", "brown", "MORRISTOWN", "NJ") == "name_only"


class TestCatalogLatestRelease:
    CATALOG = {"dataset": [
        {"title": "Provider of Services File - Quality Improvement and Evaluation System : 2011-12-31",
         "distribution": [{"title": "POS : 2011-12-31",
                           "accessURL": "https://data.cms.gov/data-api/v1/dataset/0a1b2c3d-0000-0000-0000-000000000001/data"}]},
        {"title": "Provider of Services File - Quality Improvement and Evaluation System : 2026-04-01",
         "distribution": [
             {"title": "POS : 2026-04-01", "accessURL": "https://data.cms.gov/data-api/v1/dataset/8ba0f9b4-0000-0000-0000-000000000002/data"},
             {"title": "POS : 2026-04-01", "accessURL": "https://data.cms.gov/data-api/v1/dataset/bb342fae-0000-0000-0000-000000000003/data"},
         ]},
    ]}

    def test_picks_newest_not_first(self):
        latest = _latest_catalog_release(self.CATALOG, lambda t: "provider of services" in t)
        assert latest["date"] == "2026-04-01"
        assert set(latest["uuids"]) == {
            "8ba0f9b4-0000-0000-0000-000000000002",
            "bb342fae-0000-0000-0000-000000000003",
        }

    def test_no_match(self):
        assert _latest_catalog_release(self.CATALOG, lambda t: "nothing" in t) is None


class TestPOSNameFallback:
    def _index(self):
        pos = CMSPOSSource()
        hospitals = [
            {"ccn": "310012", "fac_name": "THE VALLEY HOSPITAL", "city": "PARAMUS", "state": "NJ"},
            {"ccn": "310041", "fac_name": "COMMUNITY MEDICAL CENTER", "city": "TOMS RIVER", "state": "NJ"},
            {"ccn": "999999", "fac_name": "COMMUNITY MEDICAL CENTER", "city": "ELSEWHERE", "state": "NJ"},
        ]
        return pos, pos.build_name_index(hospitals)

    def test_unique_name_in_state_matches_across_cities(self):
        pos, index = self._index()
        match = pos.match_by_name("The Valley Hospital", "Ridgewood", "NJ", index)
        assert match is not None and match["ccn"] == "310012"

    def test_ambiguous_name_in_state_does_not_match(self):
        pos, index = self._index()
        assert pos.match_by_name("Community Medical Center", "Lakewood", "NJ", index) is None


class TestNPPESGender:
    def test_reads_sex_field(self):
        record = {
            "number": "1164424529",
            "enumeration_type": "NPI-1",
            "basic": {"first_name": "JOHN", "last_name": "BROWN", "sex": "M"},
            "taxonomies": [],
            "addresses": [],
        }
        physician = NPPESSource()._parse_physician(record)
        assert physician["gender"] == "M"


class TestDataFlags:
    def codes(self, flags):
        return {f["code"] for f in flags}

    def test_practice_is_red_and_only_flag(self):
        from app.services.data_flags import hospital_flags
        flags = hospital_flags({"name": "Virtua Medical Group, PA", "site_type": "practice"}, is_tavr=True)
        assert [(f["level"], f["code"]) for f in flags] == [("red", "PHYSICIAN_PRACTICE")]

    def test_unidentified_site(self):
        from app.services.data_flags import hospital_flags
        assert self.codes(hospital_flags({"name": "TAVR Site - Galloway, NJ"}, True)) == {"UNIDENTIFIED_SITE"}

    def test_hospital_without_ccn(self):
        from app.services.data_flags import hospital_flags
        assert "NO_FACILITY_MATCH" in self.codes(hospital_flags({"name": "CHI Memorial"}, True))

    def test_tavr_capability_only_for_tavr_profile(self):
        from app.services.data_flags import hospital_flags
        h = {"name": "X", "ccn": "1", "has_cath_lab": False, "has_open_heart_surgery": True, "cms_overall_rating": 4}
        assert self.codes(hospital_flags(h, True)) == {"MISSING_TAVR_CAPABILITY"}
        assert self.codes(hospital_flags(h, False)) == set()

    def test_zip_only_match(self):
        from app.services.data_flags import hospital_flags
        h = {"name": "X", "ccn": "1", "name_source": "CMS_POS", "name_match_tier": 3, "cms_overall_rating": 3}
        assert self.codes(hospital_flags(h, False)) == {"ZIP_ONLY_MATCH"}

    def test_clean_hospital_has_no_flags(self):
        from app.services.data_flags import hospital_flags
        h = {"name": "Morristown Medical Center", "ccn": "310015", "has_cath_lab": True,
             "has_open_heart_surgery": True, "cms_overall_rating": 5}
        assert hospital_flags(h, True) == []

    def test_physician_flags(self):
        from datetime import date
        from app.services.data_flags import physician_flags
        p = {"address_mismatch": True, "nppes_current_city": "Melbourne", "nppes_current_state": "FL",
             "cms_billing_city": "Cherry Hill", "cms_billing_state": "NJ",
             "last_updated": "2011-11-16", "has_volume": True, "total_services": 117}
        assert self.codes(physician_flags(p, today=date(2026, 10, 1))) == {"MAY_HAVE_MOVED", "STALE_NPI_RECORD"}
        assert self.codes(physician_flags({"has_volume": False, "last_updated": "2026-01-01"},
                                          today=date(2026, 10, 1))) == {"NO_MEDICARE_VOLUME"}


class TestPOSServiceCodes:
    def _parse(self, cath, open_heart):
        raw = {"PRVDR_NUM": "310031", "FAC_NAME": "DEBORAH HEART AND LUNG CENTER", "CITY_NAME": "BROWNS MILLS", "ST_ADR": "200 TRENTON RD",
               "STATE_CD": "NJ", "PRVDR_CTGRY_CD": "01", "PGM_TRMNTN_CD": "00",
               "CRDC_CTHRTZTN_LAB_SRVC_CD": cath, "OPEN_HRT_SRGRY_SRVC_CD": open_heart}
        return CMSPOSSource()._parse_pos_record(raw)

    def test_arrangement_codes_count_as_provided(self):
        rec = self._parse("3", "2")  # Deborah Heart & Lung's actual codes
        assert rec["has_cath_lab"] is True and rec["has_open_heart_surgery"] is True

    def test_zero_is_no_and_blank_is_unknown(self):
        rec = self._parse("0", "")
        assert rec["has_cath_lab"] is False and rec["has_open_heart_surgery"] is None
