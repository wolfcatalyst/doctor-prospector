"""CMS Physician Utilization API source - procedure volumes.

Medicare Physician and Other Practitioners Public Use File (PUF) contains
physician-level data on services provided to Medicare Fee-For-Service beneficiaries.

Use this to find which physicians perform TAVR procedures and their volumes.

API: https://data.cms.gov/provider-summary-by-type-of-service
Dataset: Medicare Physician & Other Practitioners - by Provider and Service
Rate limit: None specified (be respectful)
"""

import asyncio
import logging
from typing import Any, Optional

import httpx

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class CMSUtilizationSource(DataSourcePlugin):
    """Query CMS Physician Utilization data to find TAVR performers.

    This source provides physician-level procedure volumes from Medicare claims.
    Use it to:
    - Find which physicians perform TAVR procedures
    - Get procedure counts per physician per year
    - Filter NPPES results to active TAVR performers

    TAVR HCPCS Codes (CPT codes 33361-33369):
    - 33361: TAVR percutaneous femoral artery
    - 33362: TAVR percutaneous non-femoral
    - 33363: TAVR open (through chest)
    - 33364: TAVR open with cardiopulmonary bypass
    - 33365-33369: Additional TAVR procedure variants

    Example:
        source = CMSUtilizationSource()

        # Find TAVR procedures for a specific physician
        results = await source.fetch(npi="1043212434")

        # Find all TAVR procedures in a state (searches all 9 codes)
        results = await source.fetch(state="NJ")

        # Find specific HCPCS code in a state
        results = await source.fetch(state="NJ", hcpcs_code="33361")
    """

    # UUID rotates when CMS publishes a new year's data (typically annually).
    # The freshness probe auto-discovers the latest UUID from data.cms.gov/data.json.
    # If it reports a newer UUID, update BASE_URL below.
    # Manual fallback:
    #   1. Go to https://data.cms.gov/provider-summary-by-type-of-service/medicare-physician-other-practitioners/medicare-physician-other-practitioners-by-provider-and-service
    #   2. Click "API" or inspect network requests for the new data-api URL
    #   3. Copy the UUID from: /data-api/v1/dataset/{NEW_UUID}/data
    #   4. Replace the UUID below
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset/92396110-2aed-4d63-a6a2-5d6207d46a29/data"
    # Data year of the dataset above -- update together with the UUID
    DATA_PERIOD = "calendar 2024"

    # Default procedure HCPCS codes (TAVR) — used when no profile codes are passed
    DEFAULT_HCPCS_CODES = ["33361", "33362", "33363", "33364", "33365", "33366", "33367", "33368", "33369"]

    # Keep old name as alias for backward compatibility (Streamlit, scripts)
    TAVR_HCPCS_CODES = DEFAULT_HCPCS_CODES

    @property
    def name(self) -> str:
        return "cms_utilization"

    @property
    def provides(self) -> list[str]:
        return ["physician_procedures", "tavr_volumes"]

    @property
    def cache_ttl_hours(self) -> int:
        return 168  # 1 week - data updates annually but cache for freshness

    async def fetch(
        self,
        npi: Optional[str] = None,
        state: Optional[str] = None,
        hcpcs_code: Optional[str] = None,
        hcpcs_codes: Optional[list[str]] = None,
        limit: int = 1000,
        **filters
    ) -> list[dict[str, Any]]:
        """Query CMS Physician Utilization data.

        Args:
            npi: National Provider Identifier
            state: Two-letter state code (e.g., "NJ")
            hcpcs_code: Single HCPCS procedure code (e.g., "33361")
            hcpcs_codes: List of HCPCS codes to query (overrides DEFAULT_HCPCS_CODES)
            limit: Max results to return (API default 500, max 1000)
            **filters: Additional filters (ignored)

        Returns:
            List of procedure records with physician and volume data
        """
        # If a single code is specified, query just that one
        if hcpcs_code:
            return await self._fetch_single_code(npi=npi, state=state, hcpcs_code=hcpcs_code, limit=limit)

        # Otherwise query all codes from profile or defaults
        codes_to_query = hcpcs_codes or self.DEFAULT_HCPCS_CODES

        if npi:
            # One physician bills a few hundred codes at most: a single NPI query
            # filtered locally beats one ~6s API round trip per profile code
            wanted = set(codes_to_query)
            procedures = await self._fetch_single_code(npi=npi, state=state, limit=limit)
            return [p for p in procedures if p.get("hcpcs_code") in wanted]

        logger.info(f"Fetching {len(codes_to_query)} procedure codes")
        semaphore = asyncio.Semaphore(4)

        async def _fetch(code: str) -> list[dict[str, Any]]:
            async with semaphore:
                return await self._fetch_single_code(
                    npi=npi,
                    state=state,
                    hcpcs_code=code,
                    limit=limit
                )

        results = await asyncio.gather(*[_fetch(code) for code in codes_to_query])
        all_procedures = [p for procedures in results for p in procedures]
        logger.info(f"Combined {len(all_procedures)} total procedure records from {len(codes_to_query)} codes")
        return all_procedures

    async def _fetch_single_code(
        self,
        npi: Optional[str] = None,
        state: Optional[str] = None,
        hcpcs_code: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch data for a single HCPCS code using JSONAPI bracket notation.

        Args:
            npi: National Provider Identifier
            state: Two-letter state code
            hcpcs_code: HCPCS procedure code
            limit: Max results to return

        Returns:
            List of procedure records
        """
        # Build query params using JSONAPI bracket notation
        params = {
            "size": min(limit, 1000),  # API max is 1000
            "offset": 0,
        }

        if npi:
            params["filter[Rndrng_NPI]"] = npi

        if state:
            params["filter[Rndrng_Prvdr_State_Abrvtn]"] = state

        if hcpcs_code:
            params["filter[HCPCS_Cd]"] = hcpcs_code

        logger.info(f"Querying CMS Utilization API: {params}")

        # Fetch from API with retry
        try:
            response = await self.fetch_with_retry(self.BASE_URL, params=params)
            data = response.json()

            if not isinstance(data, list):
                logger.warning(f"Unexpected response format: {type(data)}")
                return []

            logger.info(f"CMS Utilization returned {len(data)} records for HCPCS {hcpcs_code}")

            # Parse records
            procedures = []
            for record in data:
                procedure = self._parse_record(record)
                if procedure:
                    procedures.append(procedure)

            logger.info(f"Parsed {len(procedures)} procedure records")
            return procedures

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("CMS Utilization API returned 404 - dataset may have moved or been updated")
                return []
            raise SourceFetchError(f"CMS Utilization API error: {e}") from e

    def _parse_record(self, record: dict) -> Optional[dict[str, Any]]:
        """Parse a single CMS Utilization record.

        Args:
            record: Raw record from CMS API

        Returns:
            Procedure dictionary or None if invalid
        """
        # Map CMS field names to our schema
        # CMS uses abbreviated field names
        procedure = {
            "npi": record.get("Rndrng_NPI"),
            "provider_last_name": record.get("Rndrng_Prvdr_Last_Org_Name"),
            "provider_first_name": record.get("Rndrng_Prvdr_First_Name"),
            "provider_middle_initial": record.get("Rndrng_Prvdr_MI"),
            "provider_credential": record.get("Rndrng_Prvdr_Crdntls"),
            "provider_gender": record.get("Rndrng_Prvdr_Gndr"),
            "provider_entity_code": record.get("Rndrng_Prvdr_Ent_Cd"),
            "provider_street1": record.get("Rndrng_Prvdr_St1"),
            "provider_street2": record.get("Rndrng_Prvdr_St2"),
            "provider_city": record.get("Rndrng_Prvdr_City"),
            "provider_zip": record.get("Rndrng_Prvdr_Zip5"),
            "provider_state": record.get("Rndrng_Prvdr_State_Abrvtn"),
            "provider_country": record.get("Rndrng_Prvdr_State_FIPS"),
            "provider_type": record.get("Rndrng_Prvdr_Type"),
            "place_of_service": record.get("Place_Of_Srvc"),
            "hcpcs_code": record.get("HCPCS_Cd"),
            "hcpcs_description": record.get("HCPCS_Desc"),
            "hcpcs_drug_indicator": record.get("HCPCS_Drug_Ind"),
            "line_service_count": self._safe_int(record.get("Tot_Srvcs")),
            "beneficiary_unique_count": self._safe_int(record.get("Tot_Benes")),
            "beneficiary_day_service_count": self._safe_int(record.get("Tot_Bene_Day_Srvcs")),
            "average_submitted_charge": self._safe_float(record.get("Avg_Sbmtd_Chrg")),
            "average_medicare_allowed": self._safe_float(record.get("Avg_Mdcr_Alowd_Amt")),
            "average_medicare_payment": self._safe_float(record.get("Avg_Mdcr_Pymt_Amt")),
            "average_medicare_standardized_payment": self._safe_float(record.get("Avg_Mdcr_Stdzd_Amt")),
        }

        # Only return if we have a valid NPI and HCPCS code
        if not procedure["npi"] or not procedure["hcpcs_code"]:
            return None

        return procedure

    def _safe_int(self, value: Any) -> Optional[int]:
        """Safely convert to int, return None if invalid."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))  # Handle "123.0" strings
        except (ValueError, TypeError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert to float, return None if invalid."""
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_cache_key(self, **filters) -> str:
        """Generate cache key for these filters."""
        parts = []

        if filters.get("npi"):
            npi_key = f"{self.name}:npi={filters['npi']}"
            # Include HCPCS codes in key so different profiles get separate cache entries
            if filters.get("hcpcs_codes"):
                import hashlib
                codes = sorted(filters["hcpcs_codes"])
                codes_hash = hashlib.md5(",".join(codes).encode()).hexdigest()[:8]
                npi_key += f":hcpcs={codes_hash}"
            return npi_key

        if filters.get("state"):
            parts.append(f"state={filters['state'].lower().strip()}")
        if filters.get("hcpcs_code"):
            parts.append(f"hcpcs={filters['hcpcs_code'].strip()}")
        elif filters.get("hcpcs_codes"):
            # Hash custom codes to keep key short but unique
            import hashlib
            codes = sorted(filters["hcpcs_codes"])
            codes_hash = hashlib.md5(",".join(codes).encode()).hexdigest()[:8]
            parts.append(f"hcpcs={codes_hash}")
        else:
            parts.append("hcpcs=default")

        key = ":".join([self.name] + parts) if parts else f"{self.name}:all"
        return key

# Module-level instance for SourceRegistry auto-discovery
cms_utilization_source = CMSUtilizationSource()
