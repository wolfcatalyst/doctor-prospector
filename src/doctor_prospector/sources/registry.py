"""Source registry for data source plugin management.

Provides centralized registration, discovery, and access to all data sources.
"""

from typing import Optional
import importlib
import logging
import pkgutil
from pathlib import Path

from .base import DataSourcePlugin, SourceNotFoundError, SourceDisabledError

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Central registry for data source plugins.
    
    Usage:
        # Get a specific source
        tvt = SourceRegistry.get("tvt_registry")
        
        # Get all sources that provide hospitals
        hospital_sources = SourceRegistry.get_by_type("hospitals")
        
        # List all registered sources
        all_sources = SourceRegistry.list_all()
        
        # Check status
        SourceRegistry.is_enabled("nppes")
    """
    
    _sources: dict[str, DataSourcePlugin] = {}
    _disabled: set[str] = set()
    _initialized: bool = False
    
    @classmethod
    def register(cls, source: DataSourcePlugin) -> None:
        """Register a data source plugin.
        
        Args:
            source: Instance of a DataSourcePlugin subclass
        """
        if source.name in cls._sources:
            logger.warning(f"Overwriting existing source: {source.name}")
        
        cls._sources[source.name] = source
        logger.debug(f"Registered source: {source.name} (provides: {source.provides})")
    
    @classmethod
    def get(cls, name: str, require_enabled: bool = True) -> DataSourcePlugin:
        """Get a source by name.
        
        Args:
            name: Source identifier
            require_enabled: If True, raises error for disabled sources
            
        Returns:
            The data source plugin instance
            
        Raises:
            SourceNotFoundError: If source doesn't exist
            SourceDisabledError: If source is disabled and require_enabled=True
        """
        cls._ensure_initialized()
        
        if name not in cls._sources:
            available = ", ".join(cls._sources.keys())
            raise SourceNotFoundError(
                f"Source '{name}' not found. Available: {available}"
            )
        
        if require_enabled and name in cls._disabled:
            raise SourceDisabledError(f"Source '{name}' is disabled")
        
        return cls._sources[name]
    
    @classmethod
    def get_by_type(cls, data_type: str, only_enabled: bool = True) -> list[DataSourcePlugin]:
        """Get all sources that provide a given data type.
        
        Args:
            data_type: One of 'hospitals', 'physicians', 'payments', 'trials'
            only_enabled: If True, excludes disabled sources
            
        Returns:
            List of matching source plugins
        """
        cls._ensure_initialized()
        
        sources = [
            s for s in cls._sources.values()
            if data_type in s.provides
        ]
        
        if only_enabled:
            sources = [s for s in sources if s.name not in cls._disabled]
        
        return sources
    
    @classmethod
    def list_all(cls) -> list[str]:
        """List all registered source names."""
        cls._ensure_initialized()
        return list(cls._sources.keys())

    @classmethod
    def get_by_category(cls, category: str, only_enabled: bool = True) -> list[DataSourcePlugin]:
        """Get all sources in a given category.

        Args:
            category: 'core' or a module name like 'tavr'
            only_enabled: If True, excludes disabled sources
        """
        cls._ensure_initialized()
        sources = [s for s in cls._sources.values() if s.category == category]
        if only_enabled:
            sources = [s for s in sources if s.name not in cls._disabled]
        return sources

    @classmethod
    def get_modules(cls) -> list[dict]:
        """Get available module names with their associated sources.

        Returns a list of dicts, each with 'name' and 'sources' keys.
        Only includes non-core categories discovered from registered plugins.
        """
        cls._ensure_initialized()
        modules: dict[str, list[str]] = {}
        for s in cls._sources.values():
            if s.category != "core":
                modules.setdefault(s.category, []).append(s.name)
        return [
            {"name": name, "sources": sorted(sources)}
            for name, sources in sorted(modules.items())
        ]
    
    @classmethod
    def enable(cls, name: str) -> None:
        """Enable a source."""
        cls._disabled.discard(name)
        logger.info(f"Enabled source: {name}")
    
    @classmethod
    def disable(cls, name: str) -> None:
        """Disable a source."""
        cls._disabled.add(name)
        logger.info(f"Disabled source: {name}")
    
    @classmethod
    def is_enabled(cls, name: str) -> bool:
        """Check if a source is enabled."""
        return name not in cls._disabled
    
    @classmethod
    def status(cls) -> dict[str, dict]:
        """Get status of all sources.
        
        Returns:
            Dict mapping source name to status info
        """
        cls._ensure_initialized()
        
        return {
            name: {
                "enabled": name not in cls._disabled,
                "provides": source.provides,
                "category": source.category,
                "cache_ttl_hours": source.cache_ttl_hours,
                "requires_auth": source.requires_auth,
            }
            for name, source in cls._sources.items()
        }
    
    @classmethod
    def apply_config(cls, config: dict) -> None:
        """Apply configuration to enable/disable sources.
        
        Args:
            config: Dict from config.yaml sources section
        """
        for source_name, source_config in config.items():
            if source_name in cls._sources:
                if source_config.get("enabled", True):
                    cls.enable(source_name)
                else:
                    cls.disable(source_name)
    
    @classmethod
    def _ensure_initialized(cls) -> None:
        """Ensure sources have been discovered and registered."""
        if not cls._initialized:
            cls._auto_discover()
            cls._initialized = True
    
    @classmethod
    def _auto_discover(cls) -> None:
        """Auto-discover and register all source plugins in this package.
        
        Looks for any module in the sources/ directory that defines
        a subclass of DataSourcePlugin and has a module-level instance.
        """
        sources_dir = Path(__file__).parent
        
        for module_info in pkgutil.iter_modules([str(sources_dir)]):
            # Skip base and registry modules
            if module_info.name in ("base", "registry", "__init__"):
                continue
            
            try:
                module = importlib.import_module(f".{module_info.name}", package=__package__ or "doctor_prospector.sources")
                
                # Look for module-level source instances
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, DataSourcePlugin)
                        and not isinstance(attr, type)  # Not the class itself
                    ):
                        cls.register(attr)
                        
            except Exception as e:
                logger.warning(f"Failed to load source module {module_info.name}: {e}")
    
    @classmethod
    def reset(cls) -> None:
        """Reset registry (mainly for testing)."""
        cls._sources.clear()
        cls._disabled.clear()
        cls._initialized = False
