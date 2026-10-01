"""TVT Registry scraper - STS/ACC public reporting data.

FRAGILE: This scraper may break if TVT changes their site structure.
If broken: Disable via config.yaml and use cms_utilization fallback.

Last verified working: February 4, 2026

Site: https://tvtpublicreporting.sts.org/tvt-registry
Architecture: Drupal CMS with embedded JSON in drupalSettings
"""

import asyncio
import html
import json
import logging
import re
from datetime import datetime
from typing import Any, Optional

import httpx
from bs4 import BeautifulSoup

from .base import DataSourcePlugin, SourceFetchError

logger = logging.getLogger(__name__)


class TVTRegistrySource(DataSourcePlugin):
    """Scraper for STS/ACC TVT Registry public reporting data.

    Two-step scraping process:
    1. Fetch hospital list from main page (embedded in drupalSettings JSON)
    2. Fetch detail pages for each hospital to get volumes, ratings, etc.
    """

    BASE_URL = "https://tvtpublicreporting.sts.org"
    LIST_URL = f"{BASE_URL}/tvt-registry"

    @property
    def name(self) -> str:
        return "tvt_registry"

    @property
    def provides(self) -> list[str]:
        return ["hospitals"]

    @property
    def category(self) -> str:
        return "tavr"

    @property
    def cache_ttl_hours(self) -> int:
        return 168  # 1 week - TVT updates quarterly

    async def fetch(self, state: Optional[str] = None, **filters) -> list[dict[str, Any]]:
        """Fetch hospital data from TVT Registry.

        Args:
            state: Optional state filter (e.g., "NJ")
            **filters: Additional filters (ignored for now)

        Returns:
            List of hospital dictionaries with TVT data
        """
        # Step 1: Get hospital list from main page
        logger.info("Fetching TVT Registry hospital list...")
        hospitals = await self._fetch_hospital_list()
        logger.info(f"Found {len(hospitals)} hospitals in TVT Registry")

        # Filter by state if provided
        if state:
            hospitals = [h for h in hospitals if h.get("state") == state]
            logger.info(f"Filtered to {len(hospitals)} hospitals in {state}")

        # Step 2: Fetch detail pages for each hospital
        logger.info("Fetching detail pages for hospital volumes and ratings...")
        enriched_hospitals = await self._fetch_hospital_details(hospitals)

        logger.info(f"Successfully scraped {len(enriched_hospitals)} hospitals from TVT Registry")
        return enriched_hospitals

    async def _fetch_hospital_list(self) -> list[dict[str, Any]]:
        """Fetch list of hospitals from main TVT Registry page.

        Parses drupalSettings embedded JSON to extract hospital list.
        """
        response = await self.fetch_with_retry(self.LIST_URL)
        html_content = response.text

        # Parse HTML
        soup = BeautifulSoup(html_content, "lxml")

        # Look for modern Drupal approach first: <script type="application/json" data-drupal-selector="drupal-settings-json">
        settings_script = soup.find("script", {"data-drupal-selector": "drupal-settings-json"})

        if settings_script and settings_script.string:
            # Clean JSON approach
            drupal_settings = json.loads(settings_script.string)
        else:
            # Fallback: search for drupalSettings in script tags
            drupal_settings = self._extract_drupal_settings_from_scripts(soup)

        if not drupal_settings:
            raise SourceFetchError(
                f"{self.name}: Could not find drupalSettings in page HTML"
            )

        # Extract hospital features from leaflet map data
        try:
            leaflet_data = drupal_settings["leaflet"]["leaflet-map-view-search-tvt-attachment-1"]
            features = leaflet_data["features"]
        except KeyError as e:
            raise SourceFetchError(
                f"{self.name}: Unexpected drupalSettings structure: {e}"
            )

        # Parse hospitals from features
        hospitals = []

        # Features is a list of groups, each group has a 'features' sub-array
        # Flatten all groups
        feature_list = []
        if isinstance(features, list):
            # List of groups - extract features from each group
            for group in features:
                if isinstance(group, dict) and "features" in group:
                    feature_list.extend(group["features"])
        elif isinstance(features, dict):
            # Dict of groups - flatten all groups
            for group in features.values():
                if isinstance(group, list):
                    feature_list.extend(group)
                elif isinstance(group, dict) and "features" in group:
                    feature_list.extend(group["features"])
        else:
            raise SourceFetchError(
                f"{self.name}: Unexpected features structure: {type(features)}"
            )

        logger.debug(f"Flattened {len(feature_list)} features from groups")

        for feature in feature_list:
            # Only process features with lat/lon (actual hospitals)
            if "lat" not in feature or "lon" not in feature:
                continue

            # Parse popup HTML to extract name, site ID, location
            popup_html = feature.get("popup", {}).get("value", "")

            try:
                # Extract name
                name_match = re.search(r'<a[^>]*>([^<]+)</a>', popup_html)
                if not name_match:
                    continue
                name = html.unescape(name_match.group(1).strip())

                # Extract site ID
                site_id_match = re.search(r'href="/site/(\d+)"', popup_html)
                if not site_id_match:
                    continue
                site_id = site_id_match.group(1)

                # Extract location (city, state)
                location_match = re.search(
                    r'class="search--location">\s*([^<]+)\s*</div>',
                    popup_html
                )
                if not location_match:
                    continue
                location = location_match.group(1).strip()

                # Split into city, state
                if ", " in location:
                    city, state = location.rsplit(", ", 1)
                else:
                    city = location
                    state = ""

                hospitals.append({
                    "name": name,
                    "site_id": site_id,
                    "city": city,
                    "state": state,
                    "latitude": feature.get("lat"),
                    "longitude": feature.get("lon"),
                    "entity_id": feature.get("entity_id"),
                })

            except Exception as e:
                logger.warning(f"Failed to parse hospital from feature: {e}")
                continue

        return hospitals

    def _extract_drupal_settings_from_scripts(self, soup: BeautifulSoup) -> Optional[dict]:
        """Extract drupalSettings from inline script tags (fallback method)."""
        for script in soup.find_all("script"):
            if not script.string or "drupalSettings" not in script.string:
                continue

            script_content = script.string

            # Try JSON.parse pattern
            match = re.search(r'JSON\.parse\("(.+?)"\)', script_content)
            if match:
                try:
                    raw = match.group(1).encode().decode("unicode_escape")
                    return json.loads(raw)
                except json.JSONDecodeError:
                    continue

            # Try direct assignment pattern
            match = re.search(
                r'drupalSettings\s*=\s*({.+?});',
                script_content,
                re.DOTALL
            )
            if match:
                try:
                    return json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue

        return None

    async def _fetch_hospital_details(
        self,
        hospitals: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Fetch detail pages for each hospital to get volumes, ratings, etc.

        Args:
            hospitals: List of basic hospital dicts from list page

        Returns:
            List of enriched hospital dicts with detail page data
        """
        enriched = []

        # Fetch details with rate limiting (0.5-1.0 second delay)
        for i, hospital in enumerate(hospitals):
            try:
                detail_url = f"{self.BASE_URL}/site/{hospital['site_id']}"
                response = await self.fetch_with_retry(detail_url)

                # Parse detail page
                detail_data = self._parse_detail_page(response.text, hospital['site_id'])

                # Merge with basic hospital data
                enriched.append({**hospital, **detail_data})

                # Progress logging
                if (i + 1) % 50 == 0:
                    logger.info(f"Processed {i + 1}/{len(hospitals)} hospitals...")

                # Rate limiting: 1.5 second delay between requests
                # Be respectful to TVT's servers - it's a free public service
                # Full scrape will take ~7-8 minutes, but that's fine (automated anyway)
                await asyncio.sleep(1.5)

            except Exception as e:
                logger.warning(
                    f"Failed to fetch details for {hospital['name']}: {e}"
                )
                # Still include hospital with basic data
                enriched.append(hospital)

        return enriched

    def _parse_detail_page(self, html_content: str, site_id: str) -> dict[str, Any]:
        """Parse hospital detail page to extract volumes, ratings, etc.

        Args:
            html_content: Raw HTML from detail page
            site_id: TVT site ID for constructing URL

        Returns:
            Dictionary with extracted fields
        """
        soup = BeautifulSoup(html_content, "lxml")
        data = {}

        # Get all text content for regex searching
        page_text = soup.get_text()

        # Extract first TAVR date (e.g., "Apr, 2012")
        match = re.search(
            r'Date of first commercial TAVR procedure performed[:\s*]+([A-Za-z]+,?\s*\d{4})',
            page_text,
            re.IGNORECASE
        )
        if match:
            data["first_tavr_date"] = match.group(1).strip()

        # Extract cumulative volume
        match = re.search(
            r'Cumulative volume since program inception[:\s]+([\d,]+)',
            page_text,
            re.IGNORECASE
        )
        if match:
            data["cumulative_volume"] = int(match.group(1).replace(",", ""))

        # Extract average annual volume
        # Look for the number after the label, skipping HTML tags
        match = re.search(
            r'Average annual volume for reporting period[:\s]*.*?([\d,]+)',
            html_content,
            re.IGNORECASE | re.DOTALL
        )
        if match:
            # Make sure we found a real number, not "30" from "30-Day"
            # Check the context around the match
            match_end = match.end(1)
            context_after = html_content[match_end:match_end + 50]

            # If "NA" or "did not meet" appears before the number, it's not valid
            text_before_number = html_content[match.start():match.start(1)]
            if "NA" in text_before_number[-100:] or "did not meet" in text_before_number[-200:]:
                logger.debug("Annual volume marked as NA (requirements not met)")
            elif "30-Day" in context_after[:20]:
                # We caught "30" from "30-Day Composite" - not the volume
                logger.debug("Annual volume not found (caught 30-Day instead)")
            else:
                data["annual_tavr_volume"] = int(match.group(1).replace(",", ""))

        # Extract reporting period
        match = re.search(
            r'Reporting Period[:\s]+([A-Za-z]+\s+\d+,\s+\d{4}\s+through\s+[A-Za-z]+\s+\d+,\s+\d{4})',
            page_text,
            re.IGNORECASE
        )
        if match:
            data["reporting_period"] = match.group(1).strip()

        # Extract eligible procedures in reporting period
        match = re.search(
            r'Eligible procedures in reporting period[:\s]+([\d,]+)',
            page_text,
            re.IGNORECASE
        )
        if match:
            data["eligible_procedures"] = int(match.group(1).replace(",", ""))

        # Extract composite score
        match = re.search(
            r'TAVR 30 Day Composite Score[:\s]+([\d.-]+)',
            page_text,
            re.IGNORECASE
        )
        if match:
            try:
                data["composite_score"] = float(match.group(1))
            except ValueError:
                pass

        # Extract star rating using BeautifulSoup to find the actual star div
        star_div = soup.find("div", class_=re.compile(r"report-card-stars"))
        if star_div:
            star_text = star_div.get_text()
            star_match = re.search(r'(\d+)\s+stars?', star_text)
            if star_match:
                data["star_rating"] = int(star_match.group(1))

        # Extract rating label (Better/As/Worse Than Expected)
        rating_match = re.search(
            r'(Better Than Expected|As Expected|Worse Than Expected)',
            page_text
        )
        if rating_match:
            rating_label = rating_match.group(1)
            data["rating_label"] = rating_label

            # Map to stars if not already found
            if "star_rating" not in data:
                rating_map = {
                    "Better Than Expected": 3,
                    "As Expected": 2,
                    "Worse Than Expected": 1
                }
                data["star_rating"] = rating_map.get(rating_label)
        else:
            # Check if rating is explicitly NA
            if re.search(
                r'TAVR 30-Day Composite Rating[:\s*]+(?:<[^>]+>)*\s*(?:<[^>]+>)*\s*NA',
                html_content,
                re.IGNORECASE
            ):
                logger.debug("Star rating marked as NA (requirements not met)")

        # Add metadata
        data["data_as_of"] = datetime.utcnow().isoformat()
        data["tvt_registry_url"] = f"{self.BASE_URL}/site/{site_id}"

        return data

    def get_cache_key(self, **filters) -> str:
        """Generate cache key for these filters."""
        state = filters.get("state", "all")
        if isinstance(state, str):
            state = state.lower().strip()
        return f"{self.name}:state={state}"

# Module-level instance for SourceRegistry auto-discovery
tvt_registry_source = TVTRegistrySource()
