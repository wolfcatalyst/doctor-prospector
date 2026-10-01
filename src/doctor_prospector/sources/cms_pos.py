"""CMS Provider of Services (POS) data source.

The POS file is the authoritative CMS registry of every Medicare-certified
facility in the US. It contains facility name, physical address, bed count,
cardiac catheterization lab presence, open heart surgery capability, and
dozens of other characteristic fields.

API: https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities
Rate limit: None (public API, no key required)
Updates: Quarterly
"""

import asyncio
import logging
import re
from collections import defaultdict
from typing import Any, Optional

import httpx

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)

# Directional words to ignore when comparing street names
_DIRECTIONAL_FILLER = {'', 'N', 'S', 'E', 'W', 'NORTH', 'SOUTH', 'EAST', 'WEST',
                        'NE', 'NW', 'SE', 'SW'}

# Ownership type code mapping
_OWNERSHIP_TYPES = {
    '01': 'Church',
    '02': 'Private (non-profit)',
    '03': 'Other non-profit',
    '04': 'Private (for-profit)',
    '05': 'Federal Government',
    '06': 'State Government',
    '07': 'Local Government',
    '08': 'Hospital District',
    '09': 'Physician Owned',
    '10': 'Tribal',
}

# Teaching status code mapping
_TEACHING_CODES = {
    '1': 'Major teaching',
    '2': 'Minor teaching',
    '3': 'Non-teaching',
    '': 'Unknown',
}


class CMSPOSSource(DataSourcePlugin):
    """CMS Provider of Services data source.

    Provides the authoritative registry of Medicare-certified hospitals
    including names, addresses, bed counts, and service capabilities.

    Use cases:
    - Resolve billing addresses to hospital names
    - Get facility details (bed count, cath lab, teaching status)
    - Cross-reference with CMS billing data

    Example:
        source = CMSPOSSource()
        hospitals = await source.fetch()
        index = source.build_address_index(hospitals)
    """

    # UUID rotates quarterly when CMS publishes updated POS data.
    # If the freshness probe reports "stale_uuid" (HTTP 404), update the UUID:
    #   1. Go to https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-hospital-non-hospital-facilities
    #   2. Click "API" or inspect network requests for the new data-api URL
    #   3. Copy the UUID from: /data-api/v1/dataset/{NEW_UUID}/data
    #   4. Replace the UUID below and in config.yaml (cms_pos.uuid)
    BASE_URL = "https://data.cms.gov/data-api/v1/dataset/8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5/data"
    # Snapshot covered by the dataset above -- update together with the UUID
    DATA_PERIOD = "Q2 2026 snapshot"
    PAGE_SIZE = 5000

    @property
    def name(self) -> str:
        return "cms_pos"

    @property
    def provides(self) -> list[str]:
        return ["hospitals"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days — POS updates quarterly

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch hospital records from POS API.

        Paginates through the full dataset filtered to hospitals only
        (PRVDR_CTGRY_CD=01). Parses each record into a normalized dict.

        Args:
            state: Optional 2-letter state code filter

        Returns:
            List of parsed hospital dicts
        """
        state = filters.get('state')

        all_records: list[dict[str, Any]] = []
        offset = 0

        async with httpx.AsyncClient(timeout=60.0) as client:
            while True:
                params: dict[str, Any] = {
                    'size': self.PAGE_SIZE,
                    'offset': offset,
                    'filter[PRVDR_CTGRY_CD]': '01',  # Hospitals only
                }
                if state:
                    params['filter[STATE_CD]'] = state.upper()

                logger.info(f"Fetching POS data: offset={offset}, state={state or 'all'}")

                for attempt in range(3):
                    try:
                        resp = await client.get(self.BASE_URL, params=params)
                        resp.raise_for_status()
                        break
                    except (httpx.HTTPStatusError, httpx.RequestError) as e:
                        if attempt == 2:
                            raise SourceFetchError(
                                f"cms_pos: Failed to fetch POS data after 3 attempts: {e}"
                            )
                        wait = 2 ** attempt
                        logger.warning(f"cms_pos: Attempt {attempt + 1} failed, retrying in {wait}s: {e}")
                        await asyncio.sleep(wait)

                data = resp.json()

                if not data:
                    break

                for raw in data:
                    parsed = self._parse_pos_record(raw)
                    if parsed:
                        all_records.append(parsed)

                # If we got fewer than PAGE_SIZE, we've reached the end
                if len(data) < self.PAGE_SIZE:
                    break

                offset += self.PAGE_SIZE

        logger.info(f"cms_pos: Fetched {len(all_records)} hospital records")
        return all_records

    # Facility name keywords that indicate non-TAVR-capable facilities
    _EXCLUDE_KEYWORDS = [
        'rehab', 'rehabilitation', 'psychiatric', 'psych ',
        'long term', 'long-term', 'ltac', 'kindred',
        'nursing', 'skilled nursing', 'hospice',
        'children', 'pediatric', "women's", 'maternity',
        'encompass health', 'state hospital', 'behavioral',
    ]

    def _parse_pos_record(self, raw: dict) -> Optional[dict[str, Any]]:
        """Parse a single POS API record into normalized form.

        Filters out non-general-acute-care facilities (rehab, psychiatric,
        long-term care, pediatric, etc.) that cannot perform TAVR.
        """
        fac_name = (raw.get('FAC_NAME') or '').strip()
        street = (raw.get('ST_ADR') or '').strip()
        city = (raw.get('CITY_NAME') or '').strip()
        state = (raw.get('STATE_CD') or '').strip()
        zip_code = (raw.get('ZIP_CD') or '').strip()[:5]

        if not fac_name or not street or not city or not state:
            return None

        # Filter out non-TAVR-capable facility types by name
        name_lower = fac_name.lower()
        if any(kw in name_lower for kw in self._EXCLUDE_KEYWORDS):
            return None

        # Parse numeric fields safely
        def _safe_int(val, default=0):
            try:
                return int(val) if val else default
            except (ValueError, TypeError):
                return default

        bed_count = _safe_int(raw.get('BED_CNT'))
        cath_lab_rooms = _safe_int(raw.get('CRDC_CTHRTZTN_PRCDR_ROOMS_CNT'))

        # Service codes: 0 = not provided, 1 = by staff, 2 = under arrangement,
        # 3 = both; blank = not reported. Counting only "1" marked hospitals
        # like Deborah Heart & Lung (3/2) as having no cath lab or open heart.
        def _service(code: Optional[str]) -> Optional[bool]:
            code = (code or '').strip()
            if code in ('1', '2', '3'):
                return True
            if code == '0':
                return False
            return None

        has_cath_lab = _service(raw.get('CRDC_CTHRTZTN_LAB_SRVC_CD'))
        has_open_heart = _service(raw.get('OPEN_HRT_SRGRY_SRVC_CD'))

        # Teaching status
        teaching_code = (raw.get('MDCL_SCHL_AFLTN_CD') or '').strip()
        teaching_status = _TEACHING_CODES.get(teaching_code, 'Unknown')

        # Ownership type
        ownership_code = (raw.get('GNRL_CNTL_TYPE_CD') or '').strip()
        ownership_type = _OWNERSHIP_TYPES.get(ownership_code, ownership_code)

        return {
            'fac_name': fac_name,
            'street': street,
            'city': city,
            'state': state,
            'zip': zip_code,
            'ccn': (raw.get('PRVDR_NUM') or '').strip(),
            'bed_count': bed_count,
            'has_cath_lab': has_cath_lab,
            'has_open_heart_surgery': has_open_heart,
            'cath_lab_rooms': cath_lab_rooms,
            'teaching_status': teaching_status,
            'ownership_type': ownership_type,
        }

    @staticmethod
    def _normalize_street(street: str) -> str:
        """Normalize a street address for comparison.

        Applies the same normalization as discover_non_tvt_hospitals.py
        so both CMS billing addresses and POS addresses match consistently.
        """
        s = street.upper().strip()
        # Remove suite/floor/room
        s = re.sub(r'\b(STE|SUITE|FLOOR|FL|RM|ROOM|BLDG|DEPT|UNIT|APT|#)\b.*', '', s)
        # Normalize abbreviations
        s = re.sub(r'\bST\b', 'STREET', s)
        s = re.sub(r'\bAVE?\b', 'AVENUE', s)
        s = re.sub(r'\bBLVD\b', 'BOULEVARD', s)
        s = re.sub(r'\bDR\b', 'DRIVE', s)
        s = re.sub(r'\bRD\b', 'ROAD', s)
        s = re.sub(r'\bLN\b', 'LANE', s)
        s = re.sub(r'\bPKWY\b', 'PARKWAY', s)
        s = re.sub(r'\bCT\b', 'COURT', s)
        s = re.sub(r'\bPL\b', 'PLACE', s)
        s = re.sub(r'\bCIR\b', 'CIRCLE', s)
        s = re.sub(r'\bHWY\b', 'HIGHWAY', s)
        # Normalize ordinals: 210TH -> 210
        s = re.sub(r'(\d+)(ST|ND|RD|TH)\b', r'\1', s)
        # Remove punctuation
        s = re.sub(r'[.,\-]', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    def build_address_index(self, hospitals: list[dict]) -> dict:
        """Build a multi-tier lookup index for address matching.

        Returns a dict with three tiers:
            'exact': {normalized_full_address -> hospital_record}
            'street': {(street_num, street_words, city, state) -> [records]}
            'zip': {zip_code -> [records]}
        """
        index: dict[str, Any] = {
            'exact': {},
            'street': defaultdict(list),
            'zip': defaultdict(list),
        }

        for h in hospitals:
            norm_street = self._normalize_street(h['street'])
            city_upper = h['city'].upper().strip()
            state_upper = h['state'].upper().strip()
            zip5 = h['zip'][:5]

            # Tier 1: exact full normalized address
            exact_key = f"{norm_street}|{city_upper}|{state_upper}"
            # If multiple hospitals at same exact address, keep all (list)
            if exact_key not in index['exact']:
                index['exact'][exact_key] = []
            index['exact'][exact_key].append(h)

            # Tier 2: street number + street name words + city + state
            nums = re.findall(r'\d+', norm_street)
            words = {w for w in norm_street.split() if not w.isdigit()} - _DIRECTIONAL_FILLER
            if nums and words:
                street_key = f"{nums[0]}|{'|'.join(sorted(words))}|{city_upper}|{state_upper}"
                index['street'][street_key].append(h)

            # Tier 3: ZIP code
            if zip5:
                index['zip'][zip5].append(h)

        logger.info(
            f"POS index built: {len(index['exact'])} exact keys, "
            f"{len(index['street'])} street keys, "
            f"{len(index['zip'])} zip keys"
        )
        return index

    def match_address(
        self,
        address: str,
        city: str,
        state: str,
        zip_code: str,
        index: dict,
    ) -> Optional[tuple[dict, int, str]]:
        """Match a CMS billing address against the POS index.

        Args:
            address: Street address from CMS billing data
            city: City name
            state: 2-letter state code
            zip_code: ZIP code
            index: Address index from build_address_index()

        Returns:
            Tuple of (hospital_record, tier, confidence) or None if no match.
            tier: 1, 2, or 3
            confidence: "HIGH" or "MEDIUM"
        """
        norm_addr = self._normalize_street(address)
        city_upper = city.upper().strip()
        state_upper = state.upper().strip()
        zip5 = zip_code[:5] if zip_code else ''

        # Tier 1: exact match (street + city + state)
        exact_key = f"{norm_addr}|{city_upper}|{state_upper}"
        candidates = index['exact'].get(exact_key, [])
        if candidates:
            if len(candidates) == 1:
                return (candidates[0], 1, 'HIGH')
            # Multiple hospitals at exact same address — pick largest by bed count
            best = max(candidates, key=lambda h: h.get('bed_count', 0))
            return (best, 1, 'HIGH')

        # Tier 2: street number + street name words + city + state
        nums = re.findall(r'\d+', norm_addr)
        words = {w for w in norm_addr.split() if not w.isdigit()} - _DIRECTIONAL_FILLER
        if nums and words:
            street_key = f"{nums[0]}|{'|'.join(sorted(words))}|{city_upper}|{state_upper}"
            candidates = index['street'].get(street_key, [])
            if len(candidates) == 1:
                return (candidates[0], 2, 'HIGH')
            elif len(candidates) > 1:
                # Multiple matches — use bed count tiebreaker
                best = max(candidates, key=lambda h: h.get('bed_count', 0))
                return (best, 2, 'HIGH')

        # Tier 3: same ZIP code, only if exactly ONE hospital in that ZIP
        if zip5:
            zip_candidates = index['zip'].get(zip5, [])
            if len(zip_candidates) == 1:
                return (zip_candidates[0], 3, 'MEDIUM')
            # Multiple hospitals in ZIP — do NOT guess

        return None

    def build_name_index(self, hospitals: list[dict]) -> dict:
        """Build a lookup index by normalized hospital name + city + state.

        Returns a dict: {(normalized_name, city_upper, state_upper) -> hospital_record}
        When there are duplicates, keeps the one with more beds.
        Also builds a secondary index by (city, state) for fuzzy name matching.
        """
        name_index: dict[tuple, dict] = {}
        city_state_index: dict[tuple, list[dict]] = defaultdict(list)
        name_state_index: dict[tuple, dict[str, dict]] = defaultdict(dict)

        for h in hospitals:
            name_norm = self.normalize_hospital_name(h['fac_name'])
            city_upper = h['city'].upper().strip()
            state_upper = h['state'].upper().strip()

            key = (name_norm, city_upper, state_upper)
            if key not in name_index or h.get('bed_count', 0) > name_index[key].get('bed_count', 0):
                name_index[key] = h

            city_state_index[(city_upper, state_upper)].append(h)
            name_state_index[(name_norm, state_upper)][h['ccn']] = h

        return {
            'name': name_index,
            'city_state': dict(city_state_index),
            'name_state': dict(name_state_index),
        }

    def match_by_name(
        self,
        hospital_name: str,
        city: str,
        state: str,
        name_index: dict,
    ) -> Optional[dict]:
        """Match a hospital by name + city + state against the POS name index.

        First tries exact normalized name match, then fuzzy word overlap.

        Returns the matched POS record or None.
        """
        name_norm = self.normalize_hospital_name(hospital_name)
        city_upper = city.upper().strip()
        state_upper = state.upper().strip()

        # Exact normalized name match
        key = (name_norm, city_upper, state_upper)
        if key in name_index['name']:
            return name_index['name'][key]

        # Fuzzy: find POS hospitals in same city/state and compare names
        cs_key = (city_upper, state_upper)
        candidates = name_index['city_state'].get(cs_key, [])

        best_match = None
        best_score = 0.0

        name_words = set(re.findall(r'\w+', name_norm))
        if not name_words:
            return None

        for pos_h in candidates:
            pos_norm = self.normalize_hospital_name(pos_h['fac_name'])
            pos_words = set(re.findall(r'\w+', pos_norm))
            if not pos_words:
                continue

            # Jaccard-like overlap
            overlap = name_words & pos_words
            union = name_words | pos_words
            score = len(overlap) / len(union) if union else 0

            if score > best_score:
                best_score = score
                best_match = pos_h

        # Require at least 40% word overlap
        if best_score >= 0.4 and best_match:
            return best_match

        # Last resort: exact normalized name anywhere in the state, but only
        # when that name is unique there (hospitals move or register under a
        # different city, e.g. Valley Hospital Ridgewood -> Paramus)
        same_name = name_index.get('name_state', {}).get((name_norm, state_upper), {})
        if len(same_name) == 1:
            return next(iter(same_name.values()))

        return None

    def get_cache_key(self, **filters) -> str:
        state = filters.get('state', 'all')
        return f"cms_pos:state={state}"


# Module-level instance for auto-discovery by SourceRegistry
cms_pos_source = CMSPOSSource()
