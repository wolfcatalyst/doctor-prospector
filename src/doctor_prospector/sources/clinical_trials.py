"""ClinicalTrials.gov API source - find trial investigators (KOLs).

ClinicalTrials.gov is a database of clinical studies conducted around the world.
Use this source to:
- Identify KOL investigators (principal investigators, sub-investigators)
- Find which physicians lead TAVR trials
- Discover research activity at specific hospitals/locations

This solves the "billing attribution problem" - interventional cardiologists
who lead TAVR programs may not show up in CMS billing data (surgeons bill),
but they DO show up as trial investigators.

API: https://clinicaltrials.gov/api/v2/
Docs: https://clinicaltrials.gov/data-api/api
Rate limit: None specified (be respectful)
"""

import asyncio
import logging
from typing import Any, Optional
from urllib.parse import quote

import requests

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class ClinicalTrialsSource(DataSourcePlugin):
    """Query ClinicalTrials.gov to find trial investigators.

    This source identifies physicians leading clinical research - a strong
    signal of thought leadership and KOL status.

    Example:
        source = ClinicalTrialsSource()

        # Find TAVR trials at a specific location
        results = await source.fetch(condition="TAVR", location="Morristown, NJ")

        # Find trials by investigator name
        results = await source.fetch(investigator="Généreux")

        # Find recruiting TAVR trials in a state
        results = await source.fetch(
            condition="transcatheter aortic valve",
            location="New Jersey",
            status="RECRUITING"
        )
    """

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    # Fields describing the study itself (excludes location/contact fields)
    STUDY_TEXT_FIELDS = (
        "BriefTitle", "OfficialTitle", "Condition", "Keyword", "BriefSummary",
        "DetailedDescription", "InterventionName", "InterventionDescription",
        "ArmGroupDescription", "PrimaryOutcomeMeasure", "SecondaryOutcomeMeasure",
    )

    @property
    def name(self) -> str:
        return "clinical_trials"

    @property
    def provides(self) -> list[str]:
        return ["trials"]

    @property
    def cache_ttl_hours(self) -> int:
        return 24  # Trial data can change daily (new studies, status updates)

    async def fetch(
        self,
        condition: Optional[str] = None,
        location: Optional[str] = None,
        investigator: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        **filters
    ) -> list[dict[str, Any]]:
        """Query ClinicalTrials.gov for studies.

        Args:
            condition: Condition or intervention (e.g., "TAVR", "transcatheter aortic valve")
            location: City, state, or country (e.g., "Morristown, NJ", "New Jersey")
            investigator: Investigator name (last name or full name)
            status: Trial status (e.g., "RECRUITING", "COMPLETED")
            limit: Max results to return (API default 100, max 1000)
            **filters: Additional filters (ignored)

        Returns:
            List of trial records with study details and investigator info
        """
        # Build query params
        params = {
            "format": "json",
            "pageSize": min(limit, 1000),
        }

        # Build query terms
        query_terms = []
        if condition:
            # Search the study's own text only. Unscoped, terms also match
            # site names: "da Vinci" hit a cardiology trial with 888 sites
            # because one is the "Da Vinci Maganklinika" in Hungary.
            query_terms.append(
                "(" + " OR ".join(f"AREA[{f}]({condition})" for f in self.STUDY_TEXT_FIELDS) + ")"
            )

        if investigator:
            # Search the person fields only. A plain keyword query matches the
            # name words anywhere in a study ("John Brown" -> 200 unrelated hits).
            # Site investigators live in LocationContactName, not OverallOfficialName.
            words = investigator.split()
            name_expr = f"({words[0]} AND {words[-1]})" if len(words) > 1 else investigator
            query_terms.append(
                f"(AREA[OverallOfficialName]{name_expr}"
                f" OR AREA[LocationContactName]{name_expr}"
                f" OR AREA[ResponsiblePartyInvestigatorFullName]{name_expr})"
            )

        if location:
            # Add location filter
            params["query.locn"] = location

        if status:
            # Filter by overall status
            params["filter.overallStatus"] = status

        # Combine query terms - use simple space-separated query
        if query_terms:
            params["query.term"] = " ".join(query_terms)

        logger.info(f"Querying ClinicalTrials.gov API: {params}")

        # Add browser-like headers (requests library required - httpx gets blocked)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }

        try:
            # Use requests library in thread pool (httpx gets 403 Forbidden from bot protection)
            def _fetch():
                response = requests.get(self.BASE_URL, params=params, headers=headers, timeout=30.0)
                response.raise_for_status()
                return response.json()

            data = await asyncio.to_thread(_fetch)

            # API returns: {"studies": [...]}
            if not isinstance(data, dict) or "studies" not in data:
                logger.warning(f"Unexpected response format: {type(data)}")
                return []

            studies = data.get("studies", [])
            logger.info(f"ClinicalTrials.gov returned {len(studies)} studies")

            # Parse studies
            trials = []
            for study in studies:
                trial = self._parse_study(study)
                if trial:
                    trials.append(trial)

            logger.info(f"Parsed {len(trials)} trial records")
            return trials

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning("ClinicalTrials.gov API returned 404")
                return []
            raise SourceFetchError(f"ClinicalTrials.gov API error: {e}") from e
        except requests.RequestException as e:
            raise SourceFetchError(f"ClinicalTrials.gov request failed: {e}") from e

    def _parse_study(self, study: dict) -> Optional[dict[str, Any]]:
        """Parse a single study record from ClinicalTrials.gov API v2.

        Args:
            study: Raw study dict from API

        Returns:
            Trial dictionary or None if invalid
        """
        # API v2 structure: study -> protocolSection -> identificationModule
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
        description_module = protocol.get("descriptionModule", {})
        conditions_module = protocol.get("conditionsModule", {})
        contacts_module = protocol.get("contactsLocationsModule", {})

        # Basic study info
        nct_id = identification.get("nctId")
        if not nct_id:
            return None

        trial = {
            "nct_id": nct_id,
            "title": identification.get("briefTitle"),
            "official_title": identification.get("officialTitle"),
            "study_url": f"https://clinicaltrials.gov/study/{nct_id}",
            "overall_status": status_module.get("overallStatus"),
            "start_date": self._parse_date(status_module.get("startDateStruct")),
            "completion_date": self._parse_date(status_module.get("completionDateStruct")),
            "last_update": self._parse_date(status_module.get("lastUpdatePostDateStruct")),
            "study_type": protocol.get("designModule", {}).get("studyType"),
            "phase": protocol.get("designModule", {}).get("phases", []),
            "enrollment": status_module.get("enrollmentInfo", {}).get("count"),
            "conditions": conditions_module.get("conditions", []),
            "brief_summary": description_module.get("briefSummary"),
            "lead_sponsor": sponsor_module.get("leadSponsor", {}).get("name"),
            "collaborators": [c.get("name") for c in sponsor_module.get("collaborators", [])],
        }

        # Extract investigators
        investigators = []
        contacts = contacts_module.get("overallOfficials", [])
        for contact in contacts:
            investigator = {
                "name": contact.get("name"),
                "role": contact.get("role"),
                "affiliation": contact.get("affiliation"),
            }
            investigators.append(investigator)

        trial["investigators"] = investigators

        # Extract locations
        locations = []
        location_list = contacts_module.get("locations", [])
        for loc in location_list:
            facility = loc.get("facility")
            geo = loc.get("geoPoint", {}) if isinstance(loc.get("geoPoint"), dict) else {}

            location = {
                "facility": facility,
                "city": loc.get("city"),
                "state": loc.get("state"),
                "country": loc.get("country"),
                "zip": loc.get("zip"),
                "status": loc.get("status"),
                "latitude": geo.get("lat"),
                "longitude": geo.get("lon"),
            }

            # Contacts at this location
            location_contacts = loc.get("contacts", [])
            if location_contacts:
                location["contacts"] = [
                    {
                        "name": c.get("name"),
                        "role": c.get("role"),
                        "phone": c.get("phone"),
                        "email": c.get("email"),
                    }
                    for c in location_contacts
                ]

            locations.append(location)

        trial["locations"] = locations

        return trial

    def _parse_date(self, date_struct: Optional[dict]) -> Optional[str]:
        """Parse ClinicalTrials.gov date structure.

        API returns: {"date": "2023-01-15", "type": "ACTUAL"}
        """
        if not date_struct or not isinstance(date_struct, dict):
            return None
        return date_struct.get("date")

    def get_cache_key(self, **filters) -> str:
        """Generate cache key for these filters."""
        parts = []

        if filters.get("condition"):
            # Normalize condition (lowercase, remove spaces)
            condition = filters["condition"].lower().replace(" ", "_")
            # "cond2": field-scoped search; don't reuse old unscoped results
            parts.append(f"cond2={condition}")

        if filters.get("location"):
            location = filters["location"].lower().replace(" ", "_").replace(",", "")
            parts.append(f"loc={location}")

        if filters.get("investigator"):
            # "inv2": person-field search; don't reuse old keyword-search results
            investigator = filters["investigator"].lower().replace(" ", "_")
            parts.append(f"inv2={investigator}")

        if filters.get("status"):
            parts.append(f"status={filters['status'].lower()}")

        key = ":".join([self.name] + parts) if parts else f"{self.name}:all"
        return key

# Module-level instance for SourceRegistry auto-discovery
clinical_trials_source = ClinicalTrialsSource()
