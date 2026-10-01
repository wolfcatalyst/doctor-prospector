"""NPPES NPI Registry API source - physician search.

NPI (National Provider Identifier) Registry is the official CMS database
of all healthcare providers in the US. Use this to find physicians by
location, specialty, and name.

API: https://npiregistry.cms.hhs.gov/api/
Docs: https://npiregistry.cms.hhs.gov/api-page
Rate limit: 100 requests/minute
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class NPPESSource(DataSourcePlugin):
    """Search for physicians using CMS NPPES NPI Registry API.

    Use cases:
    - Find interventional cardiologists near a hospital
    - Get physician details by NPI
    - Match physician names to NPIs

    Example:
        source = NPPESSource()
        physicians = await source.fetch(
            city="Morristown",
            state="NJ",
            taxonomy_description="Interventional Cardiology",
            limit=50
        )
    """

    BASE_URL = "https://npiregistry.cms.hhs.gov/api/"
    API_VERSION = "2.1"

    # Interventional Cardiology taxonomy code
    INTERVENTIONAL_CARDIOLOGY_CODE = "207RI0008X"

    @property
    def name(self) -> str:
        return "nppes"

    @property
    def provides(self) -> list[str]:
        return ["physicians"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days - physician data changes infrequently

    async def fetch(
        self,
        npi: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        taxonomy_description: Optional[str] = None,
        taxonomy_code: Optional[str] = None,
        limit: int = 200,
        **filters
    ) -> list[dict[str, Any]]:
        """Search for physicians using NPPES API.

        Args:
            npi: National Provider Identifier (10-digit number)
            first_name: Physician first name (partial match supported)
            last_name: Physician last name (partial match supported)
            city: City name
            state: Two-letter state code (e.g., "NJ")
            postal_code: ZIP code
            taxonomy_description: Specialty name (e.g., "Interventional Cardiology")
            taxonomy_code: Taxonomy code (e.g., "207RI0008X")
            limit: Max results to return (API max 200 per request)
            **filters: Additional filters (ignored)

        Returns:
            List of physician dictionaries
        """
        # Build query params
        params = {
            "version": self.API_VERSION,
            "limit": min(limit, 200),  # API max is 200
        }

        if npi:
            params["number"] = npi
        if first_name:
            params["first_name"] = first_name
        if last_name:
            params["last_name"] = last_name
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if postal_code:
            params["postal_code"] = postal_code
        if taxonomy_description:
            params["taxonomy_description"] = taxonomy_description
        if taxonomy_code:
            params["taxonomy_code"] = taxonomy_code

        logger.info(f"Searching NPPES: {params}")

        # Fetch from API with retry
        response = await self.fetch_with_retry(self.BASE_URL, params=params)

        # Parse response
        data = response.json()
        result_count = data.get("result_count", 0)
        logger.info(f"NPPES returned {result_count} results")

        if result_count == 0:
            return []

        # Parse physicians
        physicians = []
        for result in data.get("results", []):
            physician = self._parse_physician(result)
            if physician:
                physicians.append(physician)

        logger.info(f"Parsed {len(physicians)} physicians from NPPES")
        return physicians

    def _parse_physician(self, result: dict) -> Optional[dict[str, Any]]:
        """Parse a single NPPES API result into physician dict.

        Args:
            result: Raw result from NPPES API

        Returns:
            Physician dictionary or None if not a valid physician
        """
        # Get basic info
        npi = result.get("number")

        # Only process Individual providers (not organizations)
        if result.get("enumeration_type") != "NPI-1":
            return None

        basic = result.get("basic", {})

        # Get name
        first_name = basic.get("first_name", "")
        last_name = basic.get("last_name", "")
        middle_name = basic.get("middle_name", "")
        credential = basic.get("credential", "")

        # Get primary practice address
        addresses = result.get("addresses", [])
        practice_address = None
        for addr in addresses:
            if addr.get("address_purpose") == "LOCATION":
                practice_address = addr
                break

        if not practice_address:
            # Fallback to mailing address
            for addr in addresses:
                if addr.get("address_purpose") == "MAILING":
                    practice_address = addr
                    break

        # Get taxonomies (specialties)
        taxonomies = result.get("taxonomies", [])
        primary_taxonomy = None
        specialty_list = []

        for tax in taxonomies:
            desc = tax.get("desc", "")
            code = tax.get("code", "")
            specialty_list.append({"description": desc, "code": code})

            if tax.get("primary"):
                primary_taxonomy = {"description": desc, "code": code}

        if not primary_taxonomy and specialty_list:
            primary_taxonomy = specialty_list[0]

        # Build physician dict
        physician = {
            "npi": npi,
            "first_name": first_name,
            "last_name": last_name,
            "middle_name": middle_name,
            "credential": credential,
            "full_name": f"{first_name} {middle_name} {last_name}".replace("  ", " ").strip(),
            "name_with_credential": f"{first_name} {last_name}, {credential}".strip(", "),
            "primary_specialty": primary_taxonomy.get("description") if primary_taxonomy else None,
            "primary_taxonomy_code": primary_taxonomy.get("code") if primary_taxonomy else None,
            "all_specialties": specialty_list,
            # NPPES API v2.1 returns "sex"; older responses used "gender"
            "gender": basic.get("sex") or basic.get("gender"),
            "sole_proprietor": basic.get("sole_proprietor") == "YES",
            "enumeration_date": basic.get("enumeration_date"),
            "last_updated": basic.get("last_updated"),
        }

        # Add practice address fields
        if practice_address:
            physician.update({
                "practice_address_line1": practice_address.get("address_1"),
                "practice_address_line2": practice_address.get("address_2"),
                "practice_city": practice_address.get("city"),
                "practice_state": practice_address.get("state"),
                "practice_postal_code": practice_address.get("postal_code"),
                "practice_country": practice_address.get("country_code"),
                "practice_phone": practice_address.get("telephone_number"),
                "practice_fax": practice_address.get("fax_number"),
            })

        return physician

    def get_cache_key(self, **filters) -> str:
        """Generate cache key for these filters."""
        parts = []

        if filters.get("npi"):
            return f"{self.name}:npi={filters['npi']}"

        if filters.get("city"):
            parts.append(f"city={filters['city'].lower().strip()}")
        if filters.get("state"):
            parts.append(f"state={filters['state'].lower().strip()}")
        if filters.get("postal_code"):
            parts.append(f"zip={filters['postal_code'].strip()}")
        if filters.get("taxonomy_description"):
            parts.append(f"specialty={filters['taxonomy_description'].lower().strip()}")
        if filters.get("last_name"):
            parts.append(f"name={filters['last_name'].lower().strip()}")

        key = ":".join([self.name] + parts) if parts else f"{self.name}:all"
        return key

# Module-level instance for SourceRegistry auto-discovery
nppes_source = NPPESSource()
