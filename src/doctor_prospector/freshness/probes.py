"""Lightweight upstream change-detection probes.

Each probe does the minimal HTTP request needed to determine whether
a data source has published new data since our last fetch. Probes run
concurrently and return structured results for the Settings dashboard.

These are standalone functions, NOT methods on DataSourcePlugin — this
keeps detection logic out of the base class.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from ..paths import DATA_DIR

logger = logging.getLogger(__name__)

# Module-level cache for CMS data.json catalog (~2.6 MB).
# Shared across probes so we only download it once per run_all_probes() call.
_cms_catalog_cache: Optional[dict] = None


async def _get_cms_catalog() -> dict:
    """Fetch and cache the CMS data.json catalog."""
    global _cms_catalog_cache
    if _cms_catalog_cache is not None:
        return _cms_catalog_cache
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://data.cms.gov/data.json")
        resp.raise_for_status()
    _cms_catalog_cache = resp.json()
    return _cms_catalog_cache


def _latest_catalog_release(
    catalog: dict,
    title_filter,
) -> Optional[dict]:
    """Find the newest release of a CMS dataset in the data.json catalog.

    CMS lists each yearly/quarterly release as a *separate* catalog entry
    (title suffix ": YYYY-MM-DD"), oldest first. Scan every matching entry
    and return the one with the latest date, including all of its API
    UUIDs (the newest release often has two: a dated one and an alias).

    Returns {'date': 'YYYY-MM-DD', 'uuids': [...]} or None.
    """
    best: Optional[dict] = None
    for ds in catalog.get("dataset", []):
        title = ds.get("title", "")
        if not title_filter(title.lower()):
            continue
        uuids = []
        dates = []
        for dist in ds.get("distribution", []):
            access_url = dist.get("downloadURL", dist.get("accessURL", ""))
            uuid_match = re.search(r'/dataset/([a-f0-9-]+)/data', access_url)
            if uuid_match:
                uuids.append(uuid_match.group(1))
                date_match = re.search(r':\s*(\d{4}-\d{2}-\d{2})\s*$', dist.get("title", ""))
                if date_match:
                    dates.append(date_match.group(1))
        if not dates:
            date_match = re.search(r':\s*(\d{4}-\d{2}-\d{2})\s*$', title)
            if date_match:
                dates.append(date_match.group(1))
        if not uuids or not dates:
            continue
        date = max(dates)
        if best is None or date > best["date"]:
            best = {"date": date, "uuids": uuids}
        elif date == best["date"]:
            best["uuids"].extend(u for u in uuids if u not in best["uuids"])
    return best


@dataclass
class ProbeResult:
    """Result from an upstream freshness probe."""

    source_name: str
    status: str  # "current" | "new_data" | "worth_checking" | "stale_uuid" | "unknown" | "error"
    message: str
    upstream_version: Optional[str] = None
    local_version: Optional[str] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None


async def probe_tvt_registry(
    local_reporting_period: Optional[str] = None,
) -> ProbeResult:
    """Check if TVT Registry has a new reporting period.

    Fetches one hospital detail page and extracts the reporting period.
    Compares against the local value from all_hospitals.json.

    Cost: 1 HTTP request (~2-3 seconds).
    """
    # Use a stable, well-known hospital page for the probe
    probe_url = "https://tvtpublicreporting.sts.org/site/331738"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(probe_url)
            resp.raise_for_status()

        # Strip HTML tags so regex can match across tag boundaries
        page_text = re.sub(r'<[^>]+>', ' ', resp.text)
        page_text = re.sub(r'\s+', ' ', page_text)

        # Extract reporting period using same regex as tvt_registry.py
        match = re.search(
            r'Reporting Period[:\s]+([A-Za-z]+\s+\d+,\s+\d{4}\s+through\s+[A-Za-z]+\s+\d+,\s+\d{4})',
            page_text,
            re.IGNORECASE,
        )

        if not match:
            return ProbeResult(
                source_name="tvt_registry",
                status="unknown",
                message="Could not extract reporting period from TVT page",
                local_version=local_reporting_period,
            )

        upstream_period = match.group(1).strip()

        if not local_reporting_period:
            return ProbeResult(
                source_name="tvt_registry",
                status="unknown",
                message=f"Upstream: {upstream_period} (no local data to compare)",
                upstream_version=upstream_period,
            )

        if upstream_period.lower() == local_reporting_period.lower():
            return ProbeResult(
                source_name="tvt_registry",
                status="current",
                message=f"Reporting period matches: {upstream_period}",
                upstream_version=upstream_period,
                local_version=local_reporting_period,
            )
        else:
            return ProbeResult(
                source_name="tvt_registry",
                status="new_data",
                message=f"New reporting period! Upstream: {upstream_period}, Local: {local_reporting_period}",
                upstream_version=upstream_period,
                local_version=local_reporting_period,
            )

    except Exception as e:
        logger.warning(f"TVT probe failed: {e}")
        return ProbeResult(
            source_name="tvt_registry",
            status="error",
            message=f"Probe failed: {e}",
            local_version=local_reporting_period,
            error=str(e),
        )


async def probe_cms_pos_uuid(
    current_uuid: str = "8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5",
) -> ProbeResult:
    """Check if the CMS POS dataset UUID is still valid.

    Two-step check:
    1. Verify our current UUID endpoint is alive (1 HTTP request)
    2. Query the CMS catalog to see if a newer quarterly UUID exists

    Cost: 1-2 HTTP requests (~2-5 seconds).
    """
    url = f"https://data.cms.gov/data-api/v1/dataset/{current_uuid}/data"
    params = {"size": 1, "offset": 0}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)

        if resp.status_code == 404:
            return ProbeResult(
                source_name="cms_pos",
                status="stale_uuid",
                message="POS UUID returned 404 — new quarterly dataset published! Update UUID in cms_pos.py and config.yaml.",
                local_version=current_uuid[:8],
            )
        elif resp.status_code != 200:
            return ProbeResult(
                source_name="cms_pos",
                status="unknown",
                message=f"Unexpected status {resp.status_code}",
                local_version=current_uuid[:8],
            )

        data = resp.json()
        if not data:
            return ProbeResult(
                source_name="cms_pos",
                status="stale_uuid",
                message="POS UUID returned empty data — may be rotating",
                local_version=current_uuid[:8],
            )

        # UUID is valid. Check CMS catalog for a newer quarterly release.
        try:
            catalog_result = await _check_cms_catalog_for_newer_pos(current_uuid)
            if catalog_result:
                return catalog_result
        except Exception as e:
            logger.debug(f"CMS POS catalog check failed (non-fatal): {e}")

        return ProbeResult(
            source_name="cms_pos",
            status="current",
            message=f"POS UUID is valid ({current_uuid[:8]}...)",
            upstream_version=current_uuid[:8],
            local_version=current_uuid[:8],
        )

    except Exception as e:
        logger.warning(f"CMS POS probe failed: {e}")
        return ProbeResult(
            source_name="cms_pos",
            status="error",
            message=f"Probe failed: {e}",
            local_version=current_uuid[:8],
            error=str(e),
        )


async def _check_cms_catalog_for_newer_pos(
    current_uuid: str,
) -> Optional[ProbeResult]:
    """Query CMS data.json catalog to detect newer POS datasets.

    We need the "Quality Improvement and Evaluation System" variant
    (uppercase field names like FAC_NAME, PRVDR_CTGRY_CD), NOT the
    "Internet Quality Improvement" (iQIES) variant or Clinical Labs.

    Returns ProbeResult if a newer dataset is found, None otherwise.
    """
    catalog = await _get_cms_catalog()
    latest = _latest_catalog_release(
        catalog,
        lambda t: (
            "provider of services" in t
            and "quality improvement" in t
            and "internet" not in t
            and "clinical lab" not in t
        ),
    )
    if latest is None or current_uuid in latest["uuids"]:
        return None  # Not in catalog, or our UUID is already the latest

    return ProbeResult(
        source_name="cms_pos",
        status="new_data",
        message=(
            f"Newer POS dataset found! Latest: {latest['date']} "
            f"(UUID: {latest['uuids'][0][:8]}...). "
            f"Update BASE_URL in cms_pos.py."
        ),
        upstream_version=f"{latest['date']} ({latest['uuids'][0][:8]})",
        local_version=current_uuid[:8],
    )


async def probe_cms_utilization(
    current_uuid: Optional[str] = None,
) -> ProbeResult:
    """Check CMS Utilization dataset for validity and newer data.

    Two-step check:
    1. Verify our current UUID endpoint is alive (1 HTTP request)
    2. Query the CMS catalog (data.json) to see if a newer year's
       dataset has been published (1 HTTP request, cached by CMS CDN)

    Cost: 1-2 HTTP requests (~2-5 seconds).
    """
    if current_uuid is None:
        try:
            from ..sources.cms_utilization import CMSUtilizationSource
            current_uuid = CMSUtilizationSource.BASE_URL.split("/dataset/")[1].split("/data")[0]
        except Exception:
            current_uuid = "92396110-2aed-4d63-a6a2-5d6207d46a29"

    url = f"https://data.cms.gov/data-api/v1/dataset/{current_uuid}/data"
    params = {"size": 1, "offset": 0}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, params=params)

        if resp.status_code == 404:
            return ProbeResult(
                source_name="cms_utilization",
                status="stale_uuid",
                message=f"CMS Utilization UUID returned 404 — dataset rotated. Check data.cms.gov for updated UUID.",
                local_version=current_uuid[:8],
            )
        elif resp.status_code != 200:
            return ProbeResult(
                source_name="cms_utilization",
                status="unknown",
                message=f"Unexpected status {resp.status_code}",
                local_version=current_uuid[:8],
            )

        data = resp.json()
        if not data:
            return ProbeResult(
                source_name="cms_utilization",
                status="unknown",
                message="CMS Utilization returned empty data",
                local_version=current_uuid[:8],
            )

        # UUID is valid. Now check the CMS catalog for a newer dataset year.
        try:
            catalog_result = await _check_cms_catalog_for_newer_utilization(current_uuid)
            if catalog_result:
                return catalog_result
        except Exception as e:
            logger.debug(f"CMS catalog check failed (non-fatal): {e}")

        return ProbeResult(
            source_name="cms_utilization",
            status="current",
            message=f"CMS Utilization endpoint is valid ({current_uuid[:8]}...)",
            local_version=current_uuid[:8],
        )

    except Exception as e:
        logger.warning(f"CMS Utilization probe failed: {e}")
        return ProbeResult(
            source_name="cms_utilization",
            status="error",
            message=f"Probe failed: {e}",
            local_version=current_uuid[:8],
            error=str(e),
        )


async def _check_cms_catalog_for_newer_utilization(
    current_uuid: str,
) -> Optional[ProbeResult]:
    """Query CMS data.json catalog to detect newer utilization datasets.

    Looks for the newest "Medicare Physician & Other Practitioners - by
    Provider and Service" release and compares our UUID against it.

    Returns ProbeResult if a newer dataset is found, None otherwise.
    """
    catalog = await _get_cms_catalog()
    latest = _latest_catalog_release(
        catalog,
        lambda t: "physician" in t and "by provider and service" in t,
    )
    if latest is None or current_uuid in latest["uuids"]:
        return None  # Not in catalog, or our UUID is already the latest

    return ProbeResult(
        source_name="cms_utilization",
        status="new_data",
        message=(
            f"Newer CMS Utilization dataset found! "
            f"Latest: {latest['date']} (UUID: {latest['uuids'][0][:8]}...). "
            f"Update BASE_URL in cms_utilization.py."
        ),
        upstream_version=f"{latest['date']} ({latest['uuids'][0][:8]})",
        local_version=current_uuid[:8],
    )


async def probe_cms_historical_files(
    data_dir: Optional[Path] = None,
) -> ProbeResult:
    """Check what CMS historical data files exist locally.

    Scans data/cms_historical/ and reports which years are available.
    No hardcoded year defaults — purely reports what's on disk.

    Cost: 0 HTTP requests (local filesystem only).
    """
    if data_dir is None:
        data_dir = DATA_DIR / "cms_historical"

    if not data_dir.exists():
        return ProbeResult(
            source_name="CMS Historical TAVR Utilization",
            status="unknown",
            message=f"Directory not found: {data_dir}",
        )

    # Scan for year files
    year_pattern = re.compile(r'CY(\d{4})')
    found_years = set()
    for f in data_dir.glob("Medicare_Provider_Util_Payment_PUF_CY*.txt"):
        match = year_pattern.search(f.name)
        if match:
            found_years.add(int(match.group(1)))

    if not found_years:
        return ProbeResult(
            source_name="CMS Historical TAVR Utilization",
            status="unknown",
            message="No historical data files found in data/cms_historical/",
        )

    max_local_year = max(found_years)
    min_local_year = min(found_years)

    # Check if data is likely stale: if max year is more than 2 years behind current year
    current_year = datetime.utcnow().year
    if current_year - max_local_year >= 3:
        return ProbeResult(
            source_name="CMS Historical TAVR Utilization",
            status="worth_checking",
            message=f"Data through CY{max_local_year} — newer files may exist (it's {current_year}). Check CMS if needed.",
            local_version=f"CY{min_local_year}-CY{max_local_year}",
        )
    else:
        return ProbeResult(
            source_name="CMS Historical TAVR Utilization",
            status="current",
            message=f"CY{min_local_year}-CY{max_local_year} ({len(found_years)} files)",
            local_version=f"CY{min_local_year}-CY{max_local_year}",
        )


async def probe_open_payments() -> ProbeResult:
    """Check whether Open Payments has published a program year we don't use.

    Lists General Payment datasets from the Open Payments metastore and
    compares the newest year against GENERAL_PAYMENTS_DATASETS.

    Cost: 1 HTTP request.
    """
    try:
        from ..sources.open_payments import GENERAL_PAYMENTS_DATASETS
    except ImportError:
        return ProbeResult(
            source_name="CMS Open Payments",
            status="unknown",
            message="Could not import Open Payments source module",
        )

    configured_years = sorted(GENERAL_PAYMENTS_DATASETS.keys())
    max_year = max(configured_years) if configured_years else 0

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items",
                params={"show-reference-ids": "false"},
            )
            resp.raise_for_status()
        upstream: dict[int, str] = {}
        for ds in resp.json():
            match = re.match(r"^(\d{4}) General Payment Data$", ds.get("title", "").strip())
            if match:
                upstream[int(match.group(1))] = ds.get("identifier", "")
    except Exception as e:
        logger.warning(f"Open Payments probe failed: {e}")
        return ProbeResult(
            source_name="CMS Open Payments",
            status="error",
            message=f"Probe failed: {e}",
            local_version=str(max_year),
            error=str(e),
        )

    if not upstream:
        return ProbeResult(
            source_name="CMS Open Payments",
            status="unknown",
            message="No General Payment datasets found in Open Payments catalog",
            local_version=str(max_year),
        )

    latest_year = max(upstream)
    # CMS only keeps recent program years online; a retired year 404s on every lookup
    retired = sorted(y for y, ds_id in GENERAL_PAYMENTS_DATASETS.items() if upstream.get(y) != ds_id)
    if retired:
        return ProbeResult(
            source_name="CMS Open Payments",
            status="stale_uuid",
            message=(
                f"Configured year(s) {retired} are no longer published under those dataset IDs. "
                f"Remove or update them in GENERAL_PAYMENTS_DATASETS in open_payments.py."
            ),
            upstream_version=str(latest_year),
            local_version=str(max_year),
        )
    if latest_year > max_year:
        return ProbeResult(
            source_name="CMS Open Payments",
            status="new_data",
            message=(
                f"Program year {latest_year} is published (dataset {upstream[latest_year]}). "
                f"Add it to GENERAL_PAYMENTS_DATASETS in open_payments.py."
            ),
            upstream_version=str(latest_year),
            local_version=str(max_year),
        )
    return ProbeResult(
        source_name="CMS Open Payments",
        status="current",
        message=f"Configured years: {min(configured_years)}-{max_year} (latest published)",
        upstream_version=str(latest_year),
        local_version=str(max_year),
    )


async def run_all_probes(
    local_tvt_reporting_period: Optional[str] = None,
) -> list[ProbeResult]:
    """Run all upstream probes concurrently.

    Reads UUIDs and year ranges dynamically from source modules.
    No hardcoded defaults — always reflects current configuration.

    Returns list of ProbeResult, one per source checked.
    """
    # Reset catalog cache so we get fresh data each time
    global _cms_catalog_cache
    _cms_catalog_cache = None

    # Read CMS POS UUID dynamically from the source class
    try:
        from ..sources.cms_pos import CMSPOSSource
        pos_uuid = CMSPOSSource.BASE_URL.split("/dataset/")[1].split("/data")[0]
    except Exception:
        pos_uuid = "8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5"

    tasks = [
        probe_tvt_registry(local_tvt_reporting_period),
        probe_cms_pos_uuid(pos_uuid),
        probe_cms_utilization(),
        probe_cms_historical_files(),
        probe_open_payments(),
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    probe_results = []
    for r in results:
        if isinstance(r, Exception):
            probe_results.append(ProbeResult(
                source_name="unknown",
                status="error",
                message=str(r),
                error=str(r),
            ))
        else:
            probe_results.append(r)

    return probe_results
