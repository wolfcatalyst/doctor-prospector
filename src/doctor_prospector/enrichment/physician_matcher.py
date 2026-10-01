"""Match physicians to hospitals using NPPES + CMS Utilization data.

This module enriches hospital data with physician-level intelligence by:
1. Finding specialists near a hospital (NPPES)
2. Filtering to those who actually perform target procedures (CMS Utilization)
3. Combining volume data with physician profiles
"""

import logging
from typing import Any, Optional

from ..sources.nppes import NPPESSource
from ..sources.cms_utilization import CMSUtilizationSource

logger = logging.getLogger(__name__)


class PhysicianMatcher:
    """Match physicians to hospitals using geographic proximity and procedure data.

    Example:
        matcher = PhysicianMatcher()

        hospital = {
            "hospital_name": "Morristown Medical Center",
            "city": "Morristown",
            "state": "NJ"
        }

        physicians = await matcher.find_physicians_for_hospital(hospital)
        # Returns list of physicians with procedure volumes
    """

    def __init__(self):
        self.nppes = NPPESSource()
        self.cms = CMSUtilizationSource()

    async def find_physicians_for_hospital(
        self,
        hospital: dict[str, Any],
        specialty: Optional[str] = None,
        include_nearby_cities: bool = False,
        limit: int = 200,
        hcpcs_codes: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Find procedure-performing physicians near a hospital.

        Uses a CMS-first approach: find physicians who bill TAVR in the state,
        then filter to those whose CMS billing address OR NPPES practice address
        is in/near the target city. This catches physicians who operate at a hospital
        but have their office registered in a neighboring town.

        Note: Default specialty=None shows all procedure performers regardless of
        listed specialty. TAVR is performed by interventional cardiologists,
        cardiothoracic surgeons, and general cardiologists — filtering by a
        single specialty misses valid physicians.

        Args:
            hospital: Hospital dict with city, state, hospital_name
            specialty: Physician specialty to filter by (None = all procedure performers)
            include_nearby_cities: If True, expands search beyond exact city match
            limit: Max physicians to return

        Returns:
            List of physician dicts with procedure volumes
        """
        city = hospital.get("city")
        state = hospital.get("state")
        hospital_name = hospital.get("hospital_name") or hospital.get("name")

        if not city or not state:
            logger.warning(f"Hospital missing city or state: {hospital_name}")
            return []

        logger.info(f"Finding physicians for {hospital_name} in {city}, {state}")

        # CMS-first approach: get all procedures in the state, then filter by city
        # This finds physicians who actually BILL from this city, not just who have an office there
        fetch_kwargs = dict(state=state, limit=1000)
        if hcpcs_codes:
            fetch_kwargs["hcpcs_codes"] = hcpcs_codes
        cms_result = await self.cms.fetch_cached(**fetch_kwargs)
        procedures = cms_result.data
        if cms_result.from_cache:
            logger.info(f"CMS state search: cache hit for {state}")

        if not procedures:
            logger.info(f"No procedure records found in CMS data for {state}")
            return []

        logger.info(f"Found {len(procedures)} TAVR procedure records in {state}")

        # Group by NPI
        physician_volumes = {}
        for proc in procedures:
            npi = proc.get("npi")
            if not npi:
                continue

            if npi not in physician_volumes:
                physician_volumes[npi] = {
                    "npi": npi,
                    "provider_name": f"{proc.get('provider_first_name', '')} {proc.get('provider_last_name', '')}".strip(),
                    "provider_city": proc.get("provider_city"),
                    "provider_state": proc.get("provider_state"),
                    "provider_credential": proc.get("provider_credential"),
                    "total_services": 0,
                    "total_beneficiaries": 0,
                    "procedures": [],
                }

            physician_volumes[npi]["total_services"] += proc.get("line_service_count", 0) or 0
            physician_volumes[npi]["total_beneficiaries"] += proc.get("beneficiary_unique_count", 0) or 0
            physician_volumes[npi]["procedures"].append(proc)

        # Log CMS cities for debugging
        cms_cities = set(v.get("provider_city", "N/A") for v in physician_volumes.values())
        logger.debug(f"CMS provider cities in {state}: {sorted(cms_cities)}")

        # Enrich with NPPES data, then filter by city (checking BOTH CMS and NPPES addresses)
        enriched_physicians = []

        for npi, volume_data in physician_volumes.items():
            # Query NPPES for detailed physician info (cached)
            nppes_result = await self.nppes.fetch_cached(npi=npi)
            nppes_results = nppes_result.data

            if nppes_results and len(nppes_results) > 0:
                physician_data = nppes_results[0]
                enriched = {
                    **physician_data,
                    **volume_data,
                    "has_volume": True,
                }
            else:
                volume_data["has_volume"] = True
                enriched = volume_data

            # Check if physician is near the target city
            # Match against BOTH CMS billing city and NPPES practice city
            cms_city = volume_data.get("provider_city")
            nppes_city = enriched.get("practice_city")
            city_match = (
                self._is_nearby(cms_city, city)
                or self._is_nearby(nppes_city, city)
            )

            # Address freshness: flag if NPPES (weekly) differs from CMS billing address
            if nppes_city and cms_city and not self._is_nearby(nppes_city, cms_city):
                enriched['address_mismatch'] = True
                enriched['nppes_current_city'] = nppes_city
                enriched['nppes_current_state'] = enriched.get('practice_state') or ''
                enriched['cms_billing_city'] = cms_city
                enriched['cms_billing_state'] = volume_data.get('provider_state') or ''

            if city_match:
                enriched_physicians.append(enriched)
                logger.debug(
                    f"  {enriched.get('full_name') or enriched.get('provider_name')}: "
                    f"{volume_data['total_services']} procedure records "
                    f"(CMS city: {cms_city}, NPPES city: {nppes_city})"
                )

        # Filter by specialty if specified
        if specialty and specialty != "All":
            keywords = []
            if "interventional" in specialty.lower():
                keywords.append("interventional")
            if "structural" in specialty.lower():
                keywords.append("structural")
            if not keywords:
                keywords = [specialty.lower()]

            before_count = len(enriched_physicians)
            enriched_physicians = [
                p for p in enriched_physicians
                if not p.get("primary_specialty")  # keep if no specialty data (CMS-only)
                or any(kw in (p.get("primary_specialty") or "").lower() for kw in keywords)
            ]
            logger.info(f"Specialty filter '{specialty}': {before_count} → {len(enriched_physicians)}")

        if not enriched_physicians:
            logger.info(f"No procedure performers found near {city}, {state}")
        else:
            logger.info(
                f"Found {len(enriched_physicians)} procedure-performing physicians near {city}, {state}"
            )

        # Sort by volume (highest first)
        enriched_physicians.sort(
            key=lambda p: p.get("total_services", 0),
            reverse=True
        )

        return enriched_physicians[:limit]

    async def find_physicians_for_state(
        self,
        state: str,
        specialty: Optional[str] = None,
        limit: int = 500,
        hcpcs_codes: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """Find all procedure-performing physicians in a state.

        Args:
            state: Two-letter state code (e.g., "NJ")
            specialty: Filter by specialty (e.g., "Interventional Cardiology").
                      Use "All" or None to include all procedure performers regardless of specialty.
            limit: Max physicians to return

        Returns:
            List of physician dicts with procedure volumes, sorted by volume (highest first)
        """
        specialty_desc = specialty if specialty and specialty != "All" else "all"
        logger.info(f"Finding {specialty_desc} physicians in {state}")

        # Get all procedures in the state from CMS (cached - first call hits API, then SQLite)
        fetch_kwargs = dict(state=state, limit=1000)
        if hcpcs_codes:
            fetch_kwargs["hcpcs_codes"] = hcpcs_codes
        cms_result = await self.cms.fetch_cached(**fetch_kwargs)
        procedures = cms_result.data
        if cms_result.from_cache:
            logger.info(f"CMS state search: cache hit for {state}")

        if not procedures:
            logger.info(f"No procedure records found in CMS data for {state}")
            return []

        logger.info(f"Found {len(procedures)} TAVR procedure records in {state}")

        # Group by NPI
        physician_volumes = {}
        for proc in procedures:
            npi = proc.get("npi")
            if not npi:
                continue

            if npi not in physician_volumes:
                physician_volumes[npi] = {
                    "npi": npi,
                    "provider_name": f"{proc.get('provider_first_name', '')} {proc.get('provider_last_name', '')}".strip(),
                    "provider_city": proc.get("provider_city"),
                    "provider_state": proc.get("provider_state"),
                    "provider_credential": proc.get("provider_credential"),
                    "total_services": 0,
                    "total_beneficiaries": 0,
                    "procedures": [],
                }

            physician_volumes[npi]["total_services"] += proc.get("line_service_count", 0) or 0
            physician_volumes[npi]["total_beneficiaries"] += proc.get("beneficiary_unique_count", 0) or 0
            physician_volumes[npi]["procedures"].append(proc)

        # Now enrich with NPPES data for each NPI
        enriched_physicians = []

        for npi, volume_data in physician_volumes.items():
            # Query NPPES for detailed physician info (cached)
            nppes_result = await self.nppes.fetch_cached(npi=npi)
            nppes_results = nppes_result.data

            if nppes_results and len(nppes_results) > 0:
                physician = nppes_results[0]
                # Merge NPPES data with volume data
                enriched = {
                    **physician,  # NPPES data (full profile)
                    **volume_data,  # Volume data from CMS
                    "has_volume": True,
                }

                # Address freshness: flag if NPPES (weekly) differs from CMS billing address
                nppes_city = enriched.get("practice_city")
                cms_city = volume_data.get("provider_city")
                if nppes_city and cms_city and not self._is_nearby(nppes_city, cms_city):
                    enriched['address_mismatch'] = True
                    enriched['nppes_current_city'] = nppes_city
                    enriched['nppes_current_state'] = enriched.get('practice_state') or ''
                    enriched['cms_billing_city'] = cms_city
                    enriched['cms_billing_state'] = volume_data.get('provider_state') or ''

                enriched_physicians.append(enriched)
            else:
                # No NPPES data, use CMS data only
                volume_data["has_volume"] = True
                enriched_physicians.append(volume_data)

        logger.info(f"Enriched {len(enriched_physicians)} physicians with NPPES data")

        # Filter by specialty if specified
        if specialty and specialty != "All":
            # Support multiple keywords (e.g., "Interventional and Structural Cardiology")
            # Match if specialty contains ANY of the keywords
            keywords = []
            if "interventional" in specialty.lower():
                keywords.append("interventional")
            if "structural" in specialty.lower():
                keywords.append("structural")

            # If no specific keywords, use exact match
            if not keywords:
                keywords = [specialty.lower()]

            filtered_physicians = []
            for p in enriched_physicians:
                # Handle None values - use 'or ""' to convert None to empty string
                primary_spec = (p.get("primary_specialty") or "").lower()
                if primary_spec and any(keyword in primary_spec for keyword in keywords):
                    filtered_physicians.append(p)

            logger.info(
                f"Filtered to {len(filtered_physicians)} physicians with specialty matching '{specialty}' "
                f"(keywords: {keywords}, from {len(enriched_physicians)} total procedure performers)"
            )
            enriched_physicians = filtered_physicians

        # Sort by volume
        enriched_physicians.sort(
            key=lambda p: p.get("total_services", 0),
            reverse=True
        )

        return enriched_physicians[:limit]

    def filter_by_city(
        self,
        physicians: list[dict[str, Any]],
        city: str,
    ) -> list[dict[str, Any]]:
        """Filter a list of physicians to those near a given city.

        Checks both CMS billing city (provider_city) and NPPES practice city
        (practice_city) so physicians who operate at a hospital but have their
        office in a neighboring town are still included.

        Args:
            physicians: Pre-fetched physician list (e.g. from find_physicians_for_state)
            city: Target city name

        Returns:
            Filtered list, same sort order as input
        """
        matched = []
        for p in physicians:
            cms_city = p.get("provider_city")
            nppes_city = p.get("practice_city")
            if self._is_nearby(cms_city, city) or self._is_nearby(nppes_city, city):
                matched.append(p)

        logger.info(f"City filter '{city}': {len(physicians)} → {len(matched)} physicians")
        return matched

    async def merge_historical_physicians(
        self,
        live_physicians: list[dict[str, Any]],
        historical_data: dict[str, dict[str, Any]],
        state: str,
        city: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Merge physicians from CMS historical data not in live API results.

        Catches physicians who performed TAVR in prior years but are absent
        from the latest CMS billing year (sabbatical, billing lag, changed
        address, etc.). Also verifies each historical physician's current
        address via NPPES to flag potential location changes.

        Args:
            live_physicians: Physicians already found via live CMS API
            historical_data: Dict of NPI -> historical record from CMSHistoricalSource
            state: Two-letter state code to filter historical physicians
            city: If provided, only include historical physicians near this city

        Returns:
            Merged list with historical-only physicians appended
        """
        live_npis = {p.get('npi') for p in live_physicians if p.get('npi')}
        merged = list(live_physicians)
        added = 0

        for npi, hist in historical_data.items():
            if npi in live_npis:
                continue

            # State filter
            hist_state = (hist.get('state') or '').upper().strip()
            if hist_state != state.upper().strip():
                continue

            # City filter
            if city and not self._is_nearby(hist.get('city', ''), city):
                continue

            physician = {
                'npi': npi,
                'provider_name': hist.get('provider_name', 'Unknown'),
                'provider_city': hist.get('city', ''),
                'provider_state': hist.get('state', ''),
                'credential': hist.get('credential', ''),
                'total_services': hist.get('latest_volume', 0),
                'total_beneficiaries': 0,
                'has_volume': True,
                'historical_only': True,
                'procedures': [],
            }

            # Verify current address via NPPES (updated weekly)
            try:
                nppes_result = await self.nppes.fetch_cached(npi=npi)
                if nppes_result.data:
                    nppes_data = nppes_result.data[0]
                    nppes_city = nppes_data.get('practice_city')
                    nppes_state = nppes_data.get('practice_state')
                    hist_city = hist.get('city', '')

                    # Enrich with NPPES profile data
                    physician['practice_city'] = nppes_city
                    physician['practice_state'] = nppes_state
                    physician['primary_specialty'] = nppes_data.get('primary_specialty')
                    physician['name_with_credential'] = nppes_data.get('name_with_credential')

                    if nppes_city and hist_city and not self._is_nearby(nppes_city, hist_city):
                        physician['address_mismatch'] = True
                        physician['nppes_current_city'] = nppes_city
                        physician['nppes_current_state'] = nppes_state or ''
                        physician['cms_billing_city'] = hist_city
                        physician['cms_billing_state'] = hist.get('state', '')
                        logger.info(
                            f"Address mismatch for {physician['provider_name']} (NPI {npi}): "
                            f"NPPES={nppes_city}, {nppes_state} vs CMS historical={hist_city}, {hist.get('state')}"
                        )
            except Exception as e:
                logger.debug(f"NPPES lookup failed for historical NPI {npi}: {e}")

            merged.append(physician)
            added += 1

        if added:
            logger.info(f"Merged {added} historical-only physicians into results")

        return merged

    def _is_nearby(self, city1: Optional[str], city2: Optional[str]) -> bool:
        """Check if two cities are the same or nearby.

        Uses case-insensitive comparison with substring matching to handle
        variations like "MORRISTOWN" vs "Morristown" and partial matches.

        Args:
            city1: First city name
            city2: Second city name

        Returns:
            True if cities match
        """
        if not city1 or not city2:
            return False

        # Normalize: strip, lowercase, remove common suffixes
        def normalize(city: str) -> str:
            city = city.lower().strip()
            # Remove common suffixes
            for suffix in [" city", " town", " village"]:
                if city.endswith(suffix):
                    city = city[:-len(suffix)].strip()
            return city

        n1 = normalize(city1)
        n2 = normalize(city2)

        # Exact match or substring match (handles partial city names)
        return n1 == n2 or n1 in n2 or n2 in n1
