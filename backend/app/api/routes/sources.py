import logging

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user
from app.services import cache_service

router = APIRouter()
logger = logging.getLogger(__name__)

# Known data sources - defined here since not all have module-level instances
# for auto-discovery. This is the definitive list.
KNOWN_SOURCES = {
    "tvt_registry": {
        "provides": ["hospitals"],
        "cache_ttl_hours": 168,
        "requires_auth": False,
        "description": "STS/ACC TVT Public Reporting - TAVR program volumes and ratings",
        "update_frequency": "Quarterly",
        "category": "tavr",
    },
    "nppes": {
        "provides": ["physicians"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "CMS NPI Registry - Physician profiles and specialties",
        "update_frequency": "Weekly",
    },
    "cms_utilization": {
        "provides": ["physician_procedures", "tavr_volumes"],
        "cache_ttl_hours": 168,
        "requires_auth": False,
        "description": "CMS Utilization Data - TAVR procedure volumes by physician",
        "update_frequency": "Annually",
    },
    "cms_pos": {
        "provides": ["hospitals"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "CMS Provider of Services - Hospital facility details",
        "update_frequency": "Quarterly",
    },
    "cms_historical": {
        "provides": ["physicians", "historical_trends"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "CMS Historical Data - Multi-year TAVR volume trends (2013-2023)",
        "update_frequency": "Annually",
    },
    "open_payments": {
        "provides": ["payments", "physicians"],
        "cache_ttl_hours": 168,
        "requires_auth": False,
        "description": "CMS Open Payments - Device company payment relationships",
        "update_frequency": "Annually",
    },
    "clinical_trials": {
        "provides": ["trials"],
        "cache_ttl_hours": 24,
        "requires_auth": False,
        "description": "ClinicalTrials.gov - TAVR trial participation and investigators",
        "update_frequency": "Daily",
    },
    "pubmed": {
        "provides": ["publications"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "PubMed - Physician research publications",
        "update_frequency": "As published",
    },
    "orcid": {
        "provides": ["publications"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "ORCID - Researcher identifier verification",
        "update_frequency": "Rarely",
    },
    "edwards_connect": {
        "provides": ["hospitals"],
        "cache_ttl_hours": 168,
        "requires_auth": False,
        "description": "Edwards Lifesciences - TAVR center directory with heart team members",
        "update_frequency": "Infrequently",
        "category": "tavr",
    },
    "cms_drg": {
        "provides": ["hospital_volumes"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "CMS Medicare Inpatient DRG - Hospital procedure volumes by DRG code",
        "update_frequency": "Annually",
        "category": "core",
    },
    "cms_hospital_compare": {
        "provides": ["hospitals"],
        "cache_ttl_hours": 720,
        "requires_auth": False,
        "description": "CMS Hospital Compare - Universal hospital quality ratings (1-5 stars)",
        "update_frequency": "Annually",
        "category": "core",
    },
}


@router.get("")
async def list_sources(user: dict = Depends(get_current_user)):
    """List all data sources with status and cache freshness."""
    freshness = await cache_service.get_cache_freshness()

    sources = {}
    for name, info in KNOWN_SOURCES.items():
        sources[name] = {
            **info,
            "enabled": True,
            "freshness": freshness.get(name, {}),
        }

    return {"sources": sources, "freshness": freshness}


@router.get("/modules")
async def list_modules(user: dict = Depends(get_current_user)):
    """List available source modules that profiles can opt into.

    Returns module names and which sources they include.
    Modules are discovered from plugin category declarations.
    """
    from doctor_prospector.sources.registry import SourceRegistry

    return {"modules": SourceRegistry.get_modules()}


@router.get("/vintage")
async def get_data_vintage(user: dict = Depends(get_current_user)):
    """What period each dataset actually covers, for "data age" notices.

    Read from the same places the data comes from, so it can't drift from
    the data: source constants next to each dataset UUID, the TVT hospital
    file, the Open Payments year map, and the physician_volumes table.
    """
    from sqlalchemy import text

    from app.db.engine import engine as async_engine
    from app.services import hospital_service
    from doctor_prospector.sources.cms_drg import CMSDRGSource
    from doctor_prospector.sources.cms_pos import CMSPOSSource
    from doctor_prospector.sources.cms_utilization import CMSUtilizationSource
    from doctor_prospector.sources.open_payments import GENERAL_PAYMENTS_DATASETS

    tvt_period = next(
        (h["reporting_period"] for h in hospital_service.load_all_hospitals()
         if h.get("data_source") == "TVT Registry" and h.get("reporting_period")),
        None,
    )

    history_years: list[int] = []
    try:
        async with async_engine.begin() as conn:
            rows = await conn.execute(text("SELECT DISTINCT year FROM physician_volumes ORDER BY year"))
            history_years = [r[0] for r in rows.fetchall()]
    except Exception as e:  # DB down shouldn't break the notice
        logger.warning("Could not read physician_volumes years: %s", e)

    return {
        "tvt_registry": tvt_period,
        "cms_utilization": CMSUtilizationSource.DATA_PERIOD,
        "cms_drg": CMSDRGSource.DATA_PERIOD,
        "cms_pos": CMSPOSSource.DATA_PERIOD,
        "open_payments_latest_year": max(GENERAL_PAYMENTS_DATASETS),
        "history_years": [min(history_years), max(history_years)] if history_years else None,
    }


@router.get("/{name}/status")
async def get_source_status(name: str, user: dict = Depends(get_current_user)):
    """Get detailed status for a specific source."""
    if name not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source: {name}")

    freshness = await cache_service.get_cache_freshness()
    source_info = KNOWN_SOURCES[name]

    return {
        "name": name,
        **source_info,
        "enabled": True,
        "freshness": freshness.get(name, {}),
    }


@router.post("/{name}/refresh")
async def refresh_source(name: str, user: dict = Depends(get_current_user)):
    """Clear cache for a specific source."""
    if name not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail=f"Unknown source: {name}")
    count = await cache_service.clear_source_cache(name)
    return {"message": f"Cleared {count} cache entries for {name}", "entries_cleared": count}


@router.post("/check-updates")
async def check_updates(user: dict = Depends(get_current_user)):
    """Run freshness probes on all sources."""
    probes = await cache_service.run_freshness_probes()
    return {"probes": probes, "total": len(probes)}
