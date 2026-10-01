export interface SourceStatus {
  name: string;
  enabled: boolean;
  provides: string[];
  cache_ttl_hours: number;
  requires_auth: boolean;
  description?: string;
  update_frequency?: string;
}

export interface SourceFreshness {
  source: string;
  entry_count: number;
  oldest_entry?: string;
  newest_entry?: string;
  oldest_expiry?: string;
  newest_expiry?: string;
}

export interface SourceListResponse {
  sources: Record<string, SourceStatus & { freshness?: SourceFreshness }>;
  freshness: Record<string, SourceFreshness>;
}

export interface CacheStatusResponse {
  total_entries: number;
  valid_entries: number;
  expired_entries: number;
  by_source: Record<string, number>;
  db_path: string;
}
