"""Data source plugins for Doctor Prospector.

All data sources implement the DataSourcePlugin interface,
making them modular and interchangeable.

Usage:
    from doctor_prospector.sources import SourceRegistry
    
    # Get a source
    tvt = SourceRegistry.get("tvt_registry")
    data = await tvt.fetch(state="NJ")
    
    # Get all hospital sources
    hospital_sources = SourceRegistry.get_by_type("hospitals")
    
    # List available sources
    print(SourceRegistry.list_all())
"""

from .base import (
    DataSourcePlugin,
    FetchResult,
    SourceFetchError,
    SourceNotFoundError,
    SourceDisabledError,
)
from .registry import SourceRegistry

__all__ = [
    "DataSourcePlugin",
    "FetchResult", 
    "SourceFetchError",
    "SourceNotFoundError",
    "SourceDisabledError",
    "SourceRegistry",
]

# Note: Individual source plugins are auto-discovered by the registry.
# To add a new source:
# 1. Create a new file in this directory (e.g., my_source.py)
# 2. Define a class that extends DataSourcePlugin
# 3. Create a module-level instance of your source
# 4. The registry will auto-discover and register it
