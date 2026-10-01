"""History service - physician volume trends from physician_volumes table.

Queries the DB for multi-year procedure volumes per physician,
filtered by the active profile's HCPCS codes. Falls back to the
legacy file-based CMSHistoricalSource if the DB table is empty.
"""

import logging
from collections import defaultdict
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def get_history_for_npi(
    npi: str,
    db: AsyncSession,
    hcpcs_codes: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    """Get historical volume trends for a physician.

    Args:
        npi: Physician NPI
        db: Database session
        hcpcs_codes: Profile-specific HCPCS codes to filter by.
                     If None, returns all procedures in the table.

    Returns:
        History summary dict with volume_by_year, trends, etc.
        None if no data found.
    """
    # Build query
    if hcpcs_codes:
        placeholders = ", ".join(f":code{i}" for i in range(len(hcpcs_codes)))
        query = text(f"""
            SELECT year, hcpcs_code, hcpcs_description, services, beneficiaries
            FROM physician_volumes
            WHERE npi = :npi AND hcpcs_code IN ({placeholders})
            ORDER BY year, hcpcs_code
        """)
        params = {"npi": npi}
        for i, code in enumerate(hcpcs_codes):
            params[f"code{i}"] = code
    else:
        query = text("""
            SELECT year, hcpcs_code, hcpcs_description, services, beneficiaries
            FROM physician_volumes
            WHERE npi = :npi
            ORDER BY year, hcpcs_code
        """)
        params = {"npi": npi}

    result = await db.execute(query, params)
    rows = result.fetchall()

    if not rows:
        # Fall back to legacy file-based source
        return await _legacy_history(npi)

    # Aggregate by year
    volume_by_year: dict[int, int] = defaultdict(int)
    breakdown_by_year: dict[int, list[dict]] = defaultdict(list)

    for year, hcpcs_code, hcpcs_desc, services, beneficiaries in rows:
        volume_by_year[year] += services
        breakdown_by_year[year].append({
            "hcpcs_code": hcpcs_code,
            "description": hcpcs_desc,
            "services": services,
            "beneficiaries": beneficiaries,
        })

    sorted_years = sorted(volume_by_year.keys())
    total_procedures = sum(volume_by_year.values())

    # Year-over-year trends
    trends = []
    for i in range(1, len(sorted_years)):
        prev_year = sorted_years[i - 1]
        curr_year = sorted_years[i]
        prev_vol = volume_by_year[prev_year]
        curr_vol = volume_by_year[curr_year]
        growth_pct = ((curr_vol - prev_vol) / prev_vol * 100) if prev_vol > 0 else (100.0 if curr_vol > 0 else 0.0)
        trends.append({
            "year": curr_year,
            "volume": curr_vol,
            "prev_volume": prev_vol,
            "growth_pct": round(growth_pct, 1),
            "growth_absolute": curr_vol - prev_vol,
        })

    latest_year = sorted_years[-1] if sorted_years else None
    latest_volume = volume_by_year[latest_year] if latest_year else 0

    avg_growth = sum(t["growth_pct"] for t in trends) / len(trends) if trends else 0
    trend_indicator = "\u2191" if avg_growth > 10 else ("\u2193" if avg_growth < -10 else "\u2192")

    return {
        "npi": npi,
        "total_tavr_procedures": total_procedures,  # kept for frontend compat
        "years_active": len(sorted_years),
        "first_year": sorted_years[0] if sorted_years else None,
        "latest_year": latest_year,
        "latest_volume": latest_volume,
        "volume_by_year": {str(y): v for y, v in volume_by_year.items()},
        "trends": trends,
        "avg_annual_growth_pct": round(avg_growth, 1),
        "trend_indicator": trend_indicator,
    }


async def _legacy_history(npi: str) -> Optional[dict[str, Any]]:
    """Fall back to file-based CMSHistoricalSource."""
    try:
        from doctor_prospector.sources.cms_historical import CMSHistoricalSource
        source = CMSHistoricalSource()
        result = await source.fetch_cached(npi=npi)
        if result.data:
            for entry in result.data:
                if entry.get("npi") == npi:
                    return entry
            return result.data[0] if result.data else None
    except Exception as e:
        logger.debug("Legacy history fallback failed for %s: %s", npi, e)
    return None
