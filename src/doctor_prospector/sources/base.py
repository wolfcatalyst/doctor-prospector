"""Base class for data source plugins.

All data sources implement this interface, making them interchangeable
and allowing easy addition/removal of sources without modifying core logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
import asyncio
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Lazy import cache to avoid circular dependencies
_cache_instance = None


def _get_cache():
    """Get or create shared cache instance."""
    global _cache_instance
    if _cache_instance is None:
        from ..cache import SQLiteCache
        from ..paths import CACHE_DB_PATH
        _cache_instance = SQLiteCache(CACHE_DB_PATH)
    return _cache_instance


@dataclass
class FetchResult:
    """Result from a data source fetch operation."""
    
    source_name: str
    data: list[dict[str, Any]]
    fetched_at: datetime
    from_cache: bool
    cache_expires_at: Optional[datetime] = None
    error: Optional[str] = None
    
    @property
    def success(self) -> bool:
        return self.error is None and self.data is not None


class DataSourcePlugin(ABC):
    """Base interface for all data source plugins.
    
    To create a new data source:
    1. Subclass DataSourcePlugin
    2. Implement all abstract methods/properties
    3. Register in sources/__init__.py or use auto-discovery
    4. Add configuration section to config.yaml
    
    Example:
        class MySource(DataSourcePlugin):
            name = "my_source"
            provides = ["hospitals"]
            cache_ttl_hours = 24
            
            async def fetch(self, **filters) -> list[dict]:
                # Fetch and return data
                ...
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source.
        
        Used in config.yaml, CLI commands, and cache keys.
        Convention: lowercase_with_underscores
        """
        pass
    
    @property
    @abstractmethod
    def provides(self) -> list[str]:
        """List of data types this source provides.
        
        Valid values: 'hospitals', 'physicians', 'payments', 'trials'
        A source can provide multiple types.
        """
        pass
    
    @property
    @abstractmethod
    def cache_ttl_hours(self) -> int:
        """How long to cache results in hours.
        
        Guidelines:
        - Real-time APIs: 24 hours
        - Quarterly updates (TVT): 168 hours (1 week)
        - Annual updates (CMS): 720 hours (30 days)
        """
        pass
    
    @abstractmethod
    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch data from the source.
        
        Args:
            **filters: Source-specific filters (state, npi, date_range, etc.)
            
        Returns:
            List of dictionaries, each representing one record.
            Schema depends on what this source provides.
            
        Raises:
            SourceFetchError: If fetch fails after retries
        """
        pass
    
    @abstractmethod
    def get_cache_key(self, **filters) -> str:
        """Generate a unique cache key for these filter params.
        
        Must be deterministic - same filters = same key.
        Include source name to avoid collisions.
        
        Example: "tvt_registry:state=NJ:min_volume=50"
        """
        pass
    
    @property
    def requires_auth(self) -> bool:
        """Whether this source requires API keys or credentials.
        
        Override and return True if auth is needed.
        Credentials should be read from environment variables or config.
        """
        return False
    
    @property
    def rate_limit_per_minute(self) -> Optional[int]:
        """Rate limit for this source's API.
        
        Override if the source has rate limiting.
        The base fetch wrapper will respect this.
        """
        return None
    
    @property
    def category(self) -> str:
        """Plugin category: 'core' or a module name like 'tavr'.

        Core plugins run for all device market profiles.
        Module plugins only run when the active profile includes that
        module name in its ``modules`` list.

        Override to assign this source to a specific module.
        """
        return "core"

    @property
    def enabled(self) -> bool:
        """Whether this source is currently enabled.

        Typically controlled via config.yaml.
        """
        return True

    @property
    def cache_empty_results(self) -> bool:
        """Whether to cache empty results in SQLite.

        Default True. Override to False for sources where empty results
        usually indicate a timeout or transient failure rather than
        genuinely having no data (e.g., Open Payments API).
        """
        return True

    @staticmethod
    def normalize_cache_key(key: str) -> str:
        """Normalize a cache key for consistent cache hits.

        Lowercases, strips whitespace, and collapses internal whitespace.
        Apply to all cache keys to prevent mismatches from case/whitespace differences.
        """
        return key.lower().strip().replace("  ", " ")

    # --- Cache-aware fetch wrapper ---

    async def fetch_cached(
        self,
        force_refresh: bool = False,
        **filters
    ) -> FetchResult:
        """Fetch data with automatic caching.

        Checks cache first. If data is cached and not expired, returns cached data.
        Otherwise, fetches fresh data from source and caches it.

        Args:
            force_refresh: If True, bypass cache and fetch fresh data
            **filters: Passed to fetch() and get_cache_key()

        Returns:
            FetchResult with data and cache metadata
        """
        cache = _get_cache()
        cache_key = self.normalize_cache_key(self.get_cache_key(**filters))

        # Check cache unless force refresh
        if not force_refresh:
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                logger.debug(f"{self.name}: Cache hit for {cache_key}")
                # Calculate expiry time
                # Note: SQLiteCache.get() already filters by expiry, so if we got data, it's still valid
                expires_at = datetime.utcnow() + timedelta(hours=self.cache_ttl_hours)
                return FetchResult(
                    source_name=self.name,
                    data=cached_data,
                    fetched_at=datetime.utcnow(),  # We don't track original fetch time
                    from_cache=True,
                    cache_expires_at=expires_at,
                )

        # Cache miss or force refresh - fetch fresh data
        logger.info(f"{self.name}: {'Force refresh' if force_refresh else 'Cache miss'} - fetching from source")

        try:
            data = await self.fetch(**filters)

            # Store in cache (skip caching empty results if source opts out,
            # since empty often means timeouts rather than genuinely no data)
            if data or self.cache_empty_results:
                await cache.set(
                    key=cache_key,
                    value=data,
                    ttl_hours=self.cache_ttl_hours,
                    source=self.name
                )

            expires_at = datetime.utcnow() + timedelta(hours=self.cache_ttl_hours)

            return FetchResult(
                source_name=self.name,
                data=data,
                fetched_at=datetime.utcnow(),
                from_cache=False,
                cache_expires_at=expires_at,
            )

        except Exception as e:
            logger.error(f"{self.name}: Fetch failed: {e}")
            return FetchResult(
                source_name=self.name,
                data=[],
                fetched_at=datetime.utcnow(),
                from_cache=False,
                error=str(e),
            )

    # --- Helper methods (not abstract, subclasses can use or override) ---
    
    async def fetch_with_retry(
        self,
        url: str,
        params: Optional[dict] = None,
        max_retries: int = 3,
        backoff_base: float = 1.0,
    ) -> httpx.Response:
        """Fetch URL with exponential backoff retry.
        
        Handles rate limiting and transient failures.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(max_retries):
                try:
                    response = await client.get(url, params=params)
                    
                    # Rate limited
                    if response.status_code == 429:
                        wait_time = backoff_base * (2 ** attempt)
                        logger.warning(
                            f"{self.name}: Rate limited, waiting {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    
                    response.raise_for_status()
                    return response
                    
                except httpx.HTTPStatusError as e:
                    if attempt == max_retries - 1:
                        raise SourceFetchError(
                            f"{self.name}: Failed after {max_retries} attempts: {e}"
                        )
                    wait_time = backoff_base * (2 ** attempt)
                    logger.warning(
                        f"{self.name}: Attempt {attempt + 1} failed, "
                        f"retrying in {wait_time}s"
                    )
                    await asyncio.sleep(wait_time)
                    
                except httpx.RequestError as e:
                    if attempt == max_retries - 1:
                        raise SourceFetchError(
                            f"{self.name}: Request failed: {e}"
                        )
                    await asyncio.sleep(backoff_base)
        
        raise SourceFetchError(f"{self.name}: Exhausted retries")
    
    def normalize_hospital_name(self, name: str) -> str:
        """Normalize hospital name for matching.
        
        Handles common variations:
        - "NYU Langone" vs "NYU Langone Health"
        - "The Mount Sinai Hospital" vs "Mount Sinai Hospital"
        - Punctuation and case differences
        """
        import re
        
        # Lowercase
        normalized = name.lower().strip()
        
        # Remove common prefixes
        prefixes = ["the ", "a "]
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        # Remove common suffixes that vary
        suffixes = [
            " hospital", " medical center", " health system",
            " health", " healthcare", " medical"
        ]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
        
        # Remove punctuation
        normalized = re.sub(r"[^\w\s]", "", normalized)
        
        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        return normalized


class SourceFetchError(Exception):
    """Raised when a data source fetch fails."""
    pass


class SourceNotFoundError(Exception):
    """Raised when a requested source doesn't exist."""
    pass


class SourceDisabledError(Exception):
    """Raised when trying to use a disabled source."""
    pass
