from typing import Any, Optional
from pydantic import BaseModel


class SourceStatus(BaseModel):
    name: str
    enabled: bool
    provides: list[str]
    cache_ttl_hours: int
    requires_auth: bool


class SourceFreshness(BaseModel):
    source: str
    entry_count: int = 0
    oldest_entry: Optional[str] = None
    newest_entry: Optional[str] = None
    oldest_expiry: Optional[str] = None
    newest_expiry: Optional[str] = None


class SourceListResponse(BaseModel):
    sources: list[SourceStatus]
    freshness: dict[str, SourceFreshness]


class CacheStatusResponse(BaseModel):
    total_entries: int
    valid_entries: int
    expired_entries: int
    by_source: dict[str, int]
    db_path: str


class ProbeResultResponse(BaseModel):
    source_name: str
    status: str
    message: str
    upstream_version: Optional[str] = None
    local_version: Optional[str] = None
    checked_at: Optional[str] = None
    error: Optional[str] = None
