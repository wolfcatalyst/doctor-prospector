"""CMS Hospital Compare data source.

Provides universal hospital quality star ratings (1-5 scale) from the CMS
Hospital General Information dataset. Every Medicare-certified hospital gets
a rating. This is NOT procedure-specific — it's a general quality indicator
useful for all device market profiles.

API: https://data.cms.gov/provider-data/dataset/xubh-q36u
Rate limit: None (public API, no key required)
Updates: Annually (typically July/October)
"""

import logging
from typing import Any, Optional

import httpx

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class CMSHospitalCompareSource(DataSourcePlugin):
    """CMS Hospital Compare data source.

    Fetches hospital quality ratings from the CMS Hospital General Information
    dataset. Provides 1-5 star overall quality ratings for all Medicare-certified
    hospitals in the US.

    This is a core source — runs for ALL device market profiles.

    Example:
        source = CMSHospitalCompareSource()
        result = await source.fetch_cached()
        for hospital in result.data:
            print(f"{hospital['facility_name']}: {hospital['overall_rating']} stars")
    """

    # Hospital General Information dataset on CMS Provider Data Catalog.
    # Uses the Provider Data Catalog API (different from data-api pattern).
    # Dataset ID: xubh-q36u
    # If this returns errors, check:
    #   https://data.cms.gov/provider-data/dataset/xubh-q36u
    BASE_URL = "https://data.cms.gov/provider-data/api/1/datastore/query/xubh-q36u/0"
    PAGE_SIZE = 1500  # provider-data API rejects limit > 1500 with HTTP 400

    @property
    def name(self) -> str:
        return "cms_hospital_compare"

    @property
    def provides(self) -> list[str]:
        return ["hospitals"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days — data updates annually

    def get_cache_key(self, **filters) -> str:
        return "cms_hospital_compare:all"

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch hospital quality ratings from CMS Hospital Compare.

        Returns:
            List of hospital dicts with quality rating data.
        """
        records: list[dict[str, Any]] = []
        offset = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {
                    "limit": self.PAGE_SIZE,
                    "offset": offset,
                }

                for attempt in range(3):
                    try:
                        resp = await client.get(self.BASE_URL, params=params)
                        if resp.status_code == 429:
                            import asyncio
                            wait = 2 ** attempt
                            logger.warning(
                                "cms_hospital_compare: Rate limited, waiting %ds", wait
                            )
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if attempt == 2:
                            raise SourceFetchError(
                                f"cms_hospital_compare: Failed: {e}"
                            )
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
                    except httpx.RequestError as e:
                        if attempt == 2:
                            raise SourceFetchError(
                                f"cms_hospital_compare: Request failed: {e}"
                            )
                        import asyncio
                        await asyncio.sleep(1)
                else:
                    break

                data = resp.json()
                # Provider Data Catalog wraps results in {"results": [...]}
                batch = data.get("results", data) if isinstance(data, dict) else data
                if not batch:
                    break

                for rec in batch:
                    parsed = self._parse_record(rec)
                    if parsed:
                        records.append(parsed)

                if len(batch) < self.PAGE_SIZE:
                    break
                offset += self.PAGE_SIZE

        logger.info("cms_hospital_compare: Fetched %d hospitals", len(records))
        return records

    def _parse_record(self, rec: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Parse a single Hospital General Information record."""
        facility_id = rec.get("facility_id", "").strip()
        if not facility_id:
            return None

        # Parse overall rating — can be "1"-"5" or "Not Available"
        rating_str = rec.get("hospital_overall_rating", "").strip()
        try:
            overall_rating = int(rating_str)
        except (ValueError, TypeError):
            overall_rating = None

        return {
            "facility_id": facility_id,
            "facility_name": rec.get("facility_name", "").strip(),
            "city": rec.get("citytown", rec.get("city", "")).strip(),
            "state": rec.get("state", "").strip(),
            "zip_code": rec.get("zip_code", "").strip(),
            "overall_rating": overall_rating,
            "hospital_type": rec.get("hospital_type", "").strip(),
            "ownership": rec.get("hospital_ownership", "").strip(),
            "emergency_services": rec.get("emergency_services", "").strip().lower() == "yes",
        }


# Module-level instance for auto-discovery by SourceRegistry
cms_hospital_compare_source = CMSHospitalCompareSource()
