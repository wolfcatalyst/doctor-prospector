export interface SavedSpecialty {
  name: string;
  specialty: string;
  hcpcs_codes: string[];
}

export interface DeviceMarketFilters {
  hcpcs_codes: string[];
  manufacturers: Record<string, string[]>;
  taxonomies: string[];
  trial_search_terms: string[];
  trial_statuses: string[];
  drg_codes: string[];
  modules: string[];
  saved_specialties: SavedSpecialty[];
  procedure_label: string;
}

export interface DeviceProfile {
  id: string;
  name: string;
  description: string;
  is_preset: boolean;
  is_active: boolean;
  filters: DeviceMarketFilters;
  created_at: string;
  updated_at: string;
}

export interface DeviceProfileListResponse {
  profiles: DeviceProfile[];
  active_profile_id: string | null;
}
