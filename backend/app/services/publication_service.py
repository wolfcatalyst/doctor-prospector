"""Publication service - wraps PubMedSource."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_source = None


def _get_source():
    global _source
    if _source is None:
        from doctor_prospector.sources.pubmed import PubMedSource
        _source = PubMedSource()
    return _source


async def get_publications(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    institution: Optional[str] = None,
    npi: Optional[str] = None,
    skip_cache: bool = False,
    search_terms: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    """Search PubMed for physician publications.

    Args:
        search_terms: Profile-specific keywords for Tier 3 search
                      (e.g. ["robotic surgery", "da Vinci"]).
                      Falls back to TAVR keywords if not provided.
    """
    source = _get_source()
    try:
        kwargs: dict[str, Any] = dict(
            first_name=first_name,
            last_name=last_name,
            institution=institution,
            npi=npi,
        )
        if search_terms:
            kwargs["search_terms"] = search_terms

        if skip_cache:
            data = await source.fetch(**kwargs)
            return data if data else []
        result = await source.fetch_cached(**kwargs)
        return result.data if result.data else []
    except Exception as e:
        logger.error("Error fetching publications: %s", e)
        return []
