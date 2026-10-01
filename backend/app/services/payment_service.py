"""Payment service - wraps OpenPaymentsSource."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_source = None


def _get_source():
    global _source
    if _source is None:
        from doctor_prospector.sources.open_payments import OpenPaymentsSource
        _source = OpenPaymentsSource()
    return _source


async def get_payments_for_npi(
    npi: str,
    key_companies: Optional[dict[str, list[str]]] = None,
) -> Optional[dict[str, Any]]:
    """Get Open Payments data for a physician by NPI.

    Args:
        npi: National Provider Identifier
        key_companies: Dict of manufacturer name -> list of aliases for categorization.
                       If None, uses default TAVR manufacturers.
    """
    source = _get_source()
    try:
        fetch_kwargs: dict[str, Any] = {"npi": npi}
        if key_companies:
            fetch_kwargs["key_companies"] = key_companies
        result = await source.fetch_cached(**fetch_kwargs)
        if result.data:
            # Open Payments returns a list, one entry per NPI queried
            return result.data[0] if len(result.data) == 1 else result.data
        return None
    except Exception as e:
        logger.error("Error fetching payments for NPI %s: %s", npi, e)
        return None
