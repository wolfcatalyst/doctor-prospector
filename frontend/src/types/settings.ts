export interface UserPreferences {
  search_scope: string;
  specialty_filter: string[];
  show_payments: boolean;
  show_trends: boolean;
  show_data_flags: boolean;
  show_auth_notice: boolean;
  preferred_specialties: string[];
  min_volume: number;
  sort_by: string;
  payment_company_filter: string;
  payment_level_filter: string;
  default_states: string[];
}

export interface UserProfile {
  name: string;
  created: string | null;
  updated: string | null;
  defaults: UserPreferences;
}

export interface CacheStatusResponse {
  total_entries: number;
  valid_entries: number;
  expired_entries: number;
  by_source: Record<string, number>;
  db_path: string;
}

export interface ProbeResult {
  source_name: string;
  status: "current" | "new_data" | "worth_checking" | "stale_uuid" | "unknown" | "error";
  message: string;
  upstream_version: string | null;
  local_version: string | null;
  checked_at: string | null;
  error: string | null;
}

export interface FeedbackSubmission {
  category: string;
  priority: string;
  content: string;
  name?: string;
  email?: string;
}

export interface FeedbackEntry {
  id: number;
  timestamp: string;
  category: string;
  priority: string;
  content: string;
  name: string;
  email: string;
  user_id: string | null;
}
