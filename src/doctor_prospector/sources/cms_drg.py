"""CMS Medicare Inpatient DRG data source.

Provides hospital-level procedure volumes from Medicare inpatient claims data,
organized by MS-DRG (Medicare Severity Diagnosis Related Group) codes.

This is a universal source — it works for ANY procedure type by filtering on
DRG codes from the active device profile. Replaces TVT Registry volume data
for non-TAVR profiles.

API: https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service
Rate limit: None (public API, no key required)
Updates: Annually (data year lags ~1-2 years)
"""

import logging
from collections import defaultdict
from typing import Any, Optional

import httpx

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class CMSDRGSource(DataSourcePlugin):
    """CMS Medicare Inpatient DRG data source.

    Fetches hospital-level discharge volumes by MS-DRG code from CMS Medicare
    inpatient claims data. Covers 3,000+ IPPS hospitals nationwide.

    Use cases:
    - Get hospital procedure volumes for any DRG code
    - Compare Medicare payment amounts across hospitals
    - Universal replacement for TVT Registry volume data

    Example:
        source = CMSDRGSource()
        result = await source.fetch_cached(drg_codes=["266", "267"])
        for hospital in result.data:
            print(f"{hospital['fac_name']}: {hospital['drg_volume']} discharges")
    """

    # UUID rotates when CMS publishes new annual data (typically May/June).
    # Current UUID is for CY2023 data (released May 2025).
    # If this returns 404, update the UUID:
    #   1. Go to https://data.cms.gov/provider-summary-by-type-of-service/medicare-inpatient-hospitals/medicare-inpatient-hospitals-by-provider-and-service
    #   2. Or check https://catalog.data.gov/dataset/medicare-inpatient-hospitals-by-provider-and-service-9af02
    #   3. Copy the UUID from the data-api URL
    #   4. Replace below
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset/690ddc6c-2767-4618-b277-420ffb2bf27c/data"
    # Data year of the dataset above -- update together with the UUID
    DATA_PERIOD = "calendar 2024"
    PAGE_SIZE = 5000

    @property
    def name(self) -> str:
        return "cms_drg"

    @property
    def provides(self) -> list[str]:
        return ["hospital_volumes"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days — data updates annually

    def get_cache_key(self, **filters) -> str:
        drg_codes = sorted(filters.get("drg_codes", []))
        state = filters.get("state", "all")
        codes_str = ",".join(drg_codes) if drg_codes else "none"
        return f"cms_drg:drgs={codes_str}:state={state}"

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch hospital DRG discharge data from CMS.

        Args:
            drg_codes: List of MS-DRG codes to query (e.g., ["266", "267"])
            state: Optional state abbreviation to filter by

        Returns:
            List of hospital dicts with aggregated volume across all DRG codes.
        """
        drg_codes: list[str] = filters.get("drg_codes", [])
        state: Optional[str] = filters.get("state")

        if not drg_codes:
            logger.warning("cms_drg: No DRG codes provided, returning empty")
            return []

        # Fetch records for each DRG code
        all_records: list[dict[str, Any]] = []
        for code in drg_codes:
            records = await self._fetch_drg_code(code, state)
            all_records.extend(records)

        # Aggregate by hospital (CCN)
        return self._aggregate_by_hospital(all_records)

    async def _fetch_drg_code(
        self, drg_code: str, state: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Fetch all records for a single DRG code, paginating as needed."""
        records: list[dict[str, Any]] = []
        offset = 0

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                params: dict[str, Any] = {
                    "size": self.PAGE_SIZE,
                    "offset": offset,
                    "filter[DRG_Cd]": drg_code,
                }
                if state:
                    params["filter[Rndrng_Prvdr_State_Abrvtn]"] = state.upper()

                for attempt in range(3):
                    try:
                        resp = await client.get(self.BASE_URL, params=params)
                        if resp.status_code == 429:
                            import asyncio
                            wait = 2 ** attempt
                            logger.warning("cms_drg: Rate limited, waiting %ds", wait)
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        break
                    except httpx.HTTPStatusError as e:
                        if attempt == 2:
                            raise SourceFetchError(
                                f"cms_drg: Failed fetching DRG {drg_code}: {e}"
                            )
                        import asyncio
                        await asyncio.sleep(2 ** attempt)
                    except httpx.RequestError as e:
                        if attempt == 2:
                            raise SourceFetchError(
                                f"cms_drg: Request failed for DRG {drg_code}: {e}"
                            )
                        import asyncio
                        await asyncio.sleep(1)
                else:
                    break

                batch = resp.json()
                if not batch:
                    break

                for rec in batch:
                    parsed = self._parse_record(rec, drg_code)
                    if parsed:
                        records.append(parsed)

                if len(batch) < self.PAGE_SIZE:
                    break
                offset += self.PAGE_SIZE

        logger.info(
            "cms_drg: Fetched %d records for DRG %s%s",
            len(records), drg_code, f" in {state}" if state else "",
        )
        return records

    def _parse_record(
        self, rec: dict[str, Any], drg_code: str
    ) -> Optional[dict[str, Any]]:
        """Parse a single CMS DRG record."""
        ccn = rec.get("Rndrng_Prvdr_CCN", "").strip()
        if not ccn:
            return None

        try:
            discharges = int(float(rec.get("Tot_Dschrgs", 0)))
        except (ValueError, TypeError):
            discharges = 0

        try:
            avg_payment = float(rec.get("Avg_Tot_Pymt_Amt", 0))
        except (ValueError, TypeError):
            avg_payment = 0.0

        try:
            avg_medicare = float(rec.get("Avg_Mdcr_Pymt_Amt", 0))
        except (ValueError, TypeError):
            avg_medicare = 0.0

        return {
            "ccn": ccn,
            "fac_name": rec.get("Rndrng_Prvdr_Org_Name", "").strip(),
            "city": rec.get("Rndrng_Prvdr_City", "").strip(),
            "state": rec.get("Rndrng_Prvdr_State_Abrvtn", "").strip(),
            "zip": rec.get("Rndrng_Prvdr_Zip5", "").strip(),
            "drg_code": drg_code,
            "drg_desc": rec.get("DRG_Desc", "").strip(),
            "discharges": discharges,
            "avg_payment": avg_payment,
            "avg_medicare_payment": avg_medicare,
        }

    def _aggregate_by_hospital(
        self, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Aggregate DRG records by hospital CCN.

        Sums discharges across all queried DRG codes per hospital.
        Computes weighted average payment.
        """
        hospitals: dict[str, dict[str, Any]] = {}

        for rec in records:
            ccn = rec["ccn"]
            if ccn not in hospitals:
                hospitals[ccn] = {
                    "ccn": ccn,
                    "fac_name": rec["fac_name"],
                    "city": rec["city"],
                    "state": rec["state"],
                    "zip": rec["zip"],
                    "drg_volume": 0,
                    "total_payments": 0.0,
                    "drg_codes_found": set(),
                }
            h = hospitals[ccn]
            h["drg_volume"] += rec["discharges"]
            h["total_payments"] += rec["avg_payment"] * rec["discharges"]
            h["drg_codes_found"].add(rec["drg_code"])

        # Compute weighted average and convert sets to lists
        result = []
        for h in hospitals.values():
            vol = h["drg_volume"]
            h["drg_avg_payment"] = round(h["total_payments"] / vol, 2) if vol > 0 else 0.0
            del h["total_payments"]
            h["drg_codes_found"] = sorted(h["drg_codes_found"])
            result.append(h)

        result.sort(key=lambda x: x["drg_volume"], reverse=True)
        logger.info("cms_drg: Aggregated %d hospitals", len(result))
        return result


# Module-level instance for auto-discovery by SourceRegistry
cms_drg_source = CMSDRGSource()
