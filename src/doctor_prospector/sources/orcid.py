"""ORCID Public API source - look up physician ORCID iDs for verified publication matching.

ORCID (Open Researcher and Contributor ID) provides unique identifiers for researchers.
When a physician has an ORCID iD, we can use it to get a verified, complete publication
list from PubMed — no guessing needed.

API: https://pub.orcid.org/v3.0/
Rate limit: 24 req/sec (public, unauthenticated)
Cost: Free
"""

import asyncio
import logging
import time
from typing import Any, Optional

import requests

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class ORCIDSource(DataSourcePlugin):
    """Look up ORCID iDs for physicians by name and affiliation.

    Example:
        source = ORCIDSource()
        results = await source.fetch_cached(
            first_name="Philippe",
            last_name="Généreux",
            affiliation="Morristown"
        )
        # Returns: [{"orcid_id": "0000-0001-...", "given_names": "Philippe", ...}]
    """

    BASE_URL = "https://pub.orcid.org/v3.0"

    # Rate limiting: 24 req/sec is generous, but be a good citizen
    _last_request_time = 0.0
    _min_request_interval = 0.05  # 20 req/sec ceiling (well under 24 limit)
    _MAX_RETRIES = 3

    _HEADERS = {
        "Accept": "application/json",
        "User-Agent": "DoctorProspector/1.0 (research tool; +https://github.com/wolfcatalyst/doctor-prospector)",
    }

    @property
    def name(self) -> str:
        return "orcid"

    @property
    def provides(self) -> list[str]:
        return ["publications"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days — ORCID iDs don't change

    @property
    def rate_limit_per_minute(self) -> int:
        return 1200  # 20 req/sec = 1200/min (well under 24/sec API limit)

    def _request_with_backoff(self, url: str, headers: dict, timeout: float = 15.0) -> requests.Response:
        """Make a request with rate limiting and exponential backoff on 429s."""
        for attempt in range(self._MAX_RETRIES):
            # Enforce minimum interval between requests
            now = time.time()
            elapsed = now - ORCIDSource._last_request_time
            if elapsed < self._min_request_interval:
                time.sleep(self._min_request_interval - elapsed)
            ORCIDSource._last_request_time = time.time()

            response = requests.get(url, headers=headers, timeout=timeout)

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    f"ORCID 429 rate limited (attempt {attempt + 1}/{self._MAX_RETRIES}), "
                    f"waiting {wait}s"
                )
                time.sleep(wait)
                continue

            return response

        # Final attempt
        now = time.time()
        elapsed = now - ORCIDSource._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        ORCIDSource._last_request_time = time.time()
        return requests.get(url, headers=headers, timeout=timeout)

    async def fetch(
        self,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        affiliation: Optional[str] = None,
        orcid_id: Optional[str] = None,
        **filters,
    ) -> list[dict[str, Any]]:
        """Search ORCID for a researcher or fetch profile by ORCID iD.

        Args:
            first_name: Given name(s)
            last_name: Family name
            affiliation: Institution/hospital name (partial match)
            orcid_id: Direct ORCID iD lookup (skips search)

        Returns:
            List of ORCID profile dicts with orcid_id, names, affiliations
        """
        if orcid_id:
            return await self._fetch_profile(orcid_id)

        if not last_name:
            logger.warning("ORCID search requires at least a last_name")
            return []

        # Build expanded search query
        query_parts = [f"family-name:{last_name}"]
        if first_name:
            query_parts.append(f"given-names:{first_name}")
        if affiliation:
            query_parts.append(f"affiliation-org-name:{affiliation}")

        query = "+AND+".join(query_parts)
        url = f"{self.BASE_URL}/expanded-search/?q={query}&rows=5"

        logger.info(f"ORCID search: {query}")

        try:
            def _fetch():
                response = self._request_with_backoff(url, self._HEADERS)
                response.raise_for_status()
                return response.json()

            data = await asyncio.to_thread(_fetch)

            results = data.get("expanded-result", [])
            if not results:
                logger.info(f"No ORCID found for {last_name}, {first_name}")
                return []

            profiles = []
            for result in results:
                profile = {
                    "orcid_id": result.get("orcid-id"),
                    "given_names": result.get("given-names"),
                    "family_name": result.get("family-names"),
                    "institution_names": result.get("institution-name", []),
                    "email": None,  # Not available in public search
                }
                if profile["orcid_id"]:
                    profiles.append(profile)

            logger.info(f"Found {len(profiles)} ORCID match(es) for {last_name}")
            return profiles

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return []
            raise SourceFetchError(f"ORCID API error: {e}") from e
        except requests.RequestException as e:
            raise SourceFetchError(f"ORCID request failed: {e}") from e

    async def _fetch_profile(self, orcid_id: str) -> list[dict[str, Any]]:
        """Fetch a specific ORCID profile by iD."""
        url = f"{self.BASE_URL}/{orcid_id}/person"

        try:
            def _fetch():
                response = self._request_with_backoff(url, self._HEADERS)
                response.raise_for_status()
                return response.json()

            data = await asyncio.to_thread(_fetch)

            name_data = data.get("name", {})
            profile = {
                "orcid_id": orcid_id,
                "given_names": name_data.get("given-names", {}).get("value"),
                "family_name": name_data.get("family-name", {}).get("value"),
                "institution_names": [],
                "email": None,
            }
            return [profile]

        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return []
            raise SourceFetchError(f"ORCID profile fetch error: {e}") from e
        except requests.RequestException as e:
            raise SourceFetchError(f"ORCID profile fetch failed: {e}") from e

    def get_cache_key(self, **filters) -> str:
        parts = []

        if filters.get("orcid_id"):
            parts.append(f"id={filters['orcid_id']}")
        else:
            if filters.get("last_name"):
                parts.append(f"ln={filters['last_name'].lower().strip()}")
            if filters.get("first_name"):
                parts.append(f"fn={filters['first_name'].lower().strip()}")
            if filters.get("affiliation"):
                aff = filters["affiliation"].lower().strip().replace(" ", "_")
                parts.append(f"aff={aff}")

        return ":".join([self.name] + parts) if parts else f"{self.name}:all"

# Module-level instance for SourceRegistry auto-discovery
orcid_source = ORCIDSource()
