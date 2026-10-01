"""Edwards Connect data source - Edwards Lifesciences TAVR center directory.

Fetches the full Edwards hospital directory including heart team members,
product capabilities (THV, TMTT, TEER, TTVR), and contact information.

API backs the public search page at https://treatheartvalvefailure.com/find-a-tavr-hospital
No authentication required.

Last verified working: March 2026
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)

# Public search page for manual verification
EDWARDS_SEARCH_URL = "https://treatheartvalvefailure.com/find-a-tavr-hospital"

# API endpoint (backs the public search page above)
API_URL = "https://edwardsconnect.com/api/thv/fath"

# Fallback seed file (full dataset snapshot)
FALLBACK_FILE = Path("edwards.txt")


class EdwardsConnectSource(DataSourcePlugin):
    """Edwards Lifesciences TAVR center directory.

    Provides hospital listings with heart team members, product capability
    flags, and contact information. Data is fetched in a single API call
    (~726 hospitals, ~1.5MB) and cached as one entry.
    """

    @property
    def name(self) -> str:
        return "edwards_connect"

    @property
    def provides(self) -> list[str]:
        return ["hospitals"]

    @property
    def category(self) -> str:
        return "tavr"

    @property
    def cache_ttl_hours(self) -> int:
        return 168  # 1 week

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch all Edwards TAVR center listings.

        Single API call with a central US coordinate and high limit to
        retrieve the entire directory. Falls back to edwards.txt if
        the API is unreachable.
        """
        try:
            response = await self.fetch_with_retry(
                API_URL,
                params={
                    "lat": "42.8446356",
                    "lng": "-78.821275",
                    "limit": "1000",
                },
                max_retries=3,
            )
            data = response.json()
            raw_results = data.get("results", [])
        except Exception as e:
            logger.warning(f"Edwards API failed, trying fallback file: {e}")
            raw_results = self._load_fallback()

        hospitals = []
        for raw in raw_results:
            parsed = self._parse_hospital(raw)
            if parsed:
                hospitals.append(parsed)

        # Apply state filter if provided
        state = filters.get("state")
        if state:
            state_upper = state.upper()
            hospitals = [h for h in hospitals if h.get("state", "").upper() == state_upper]

        logger.info(f"edwards_connect: Fetched {len(hospitals)} hospitals")
        return hospitals

    def get_cache_key(self, **filters) -> str:
        state = filters.get("state", "all")
        return f"edwards_connect:state={state}"

    def _parse_hospital(self, raw: dict) -> Optional[dict[str, Any]]:
        """Normalize a single Edwards API record."""
        name = (raw.get("name") or "").strip()
        if not name:
            return None

        # Parse products field — can be [] or {"teer": true, "ttvr": true}
        products = raw.get("products", {})
        if isinstance(products, list):
            products = {}

        team_members = []
        for tm in raw.get("team_members", []):
            team_members.append({
                "first_name": (tm.get("first_name") or "").strip(),
                "last_name": (tm.get("last_name") or "").strip(),
                "suffix": (tm.get("suffix") or "").strip(),
                "role": (tm.get("role") or "").strip(),
                "primary": tm.get("primary", False),
            })

        return {
            "edwards_id": raw.get("id"),
            "edwards_cid": raw.get("cid"),
            "name": name,
            "secondary_name": (raw.get("secondary_name") or "").strip() or None,
            "address": (raw.get("address_1") or "").strip() or None,
            "city": (raw.get("city") or "").strip(),
            "state": (raw.get("state") or "").strip(),
            "zip_code": (raw.get("zip_code") or "").strip(),
            "latitude": raw.get("lat"),
            "longitude": raw.get("lng"),
            "email": (raw.get("email") or "").strip() or None,
            "phone": (raw.get("phone") or "").strip() or None,
            "website": (raw.get("website") or "").strip() or None,
            "thv": bool(raw.get("thv")),
            "tmtt": bool(raw.get("tmtt")),
            "teer": bool(products.get("teer")),
            "ttvr": bool(products.get("ttvr")),
            "accepting_patients": bool(raw.get("accepting_patients")),
            "active": bool(raw.get("active", True)),
            "team_members": team_members,
            "updated_at": raw.get("updated_at"),
            "edwards_search_url": EDWARDS_SEARCH_URL,
        }

    def _load_fallback(self) -> list[dict]:
        """Load from edwards.txt snapshot if API is down."""
        if not FALLBACK_FILE.exists():
            raise SourceFetchError(
                "Edwards API unreachable and no fallback file (edwards.txt) found"
            )

        logger.info("Loading Edwards data from fallback file edwards.txt")
        with FALLBACK_FILE.open(encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data.get("results", [])
        return data


# Module-level instance for auto-discovery by SourceRegistry
edwards_connect_source = EdwardsConnectSource()
