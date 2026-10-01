import type { DataFlag } from "./dataFlags";

export interface HospitalSummary {
  name: string;
  city: string;
  state: string;
  site_id?: string;
  ccn?: string;
  annual_tavr_volume?: number;
  cumulative_volume?: number;
  star_rating?: number;
  first_tavr_date?: string;
  data_source: string;
  reporting_period?: string;
  address?: string;
  zip_code?: string;
  bed_count?: number;
  has_cath_lab?: boolean;
  has_open_heart_surgery?: boolean;
  cath_lab_rooms?: number;
  teaching_status?: string;
  ownership_type?: string;
  notes?: string;
  // CMS Inpatient DRG (universal procedure volumes)
  drg_volume?: number;
  drg_avg_payment?: number;
  // CMS Hospital Compare (universal quality rating 1-5)
  cms_overall_rating?: number;
  // "practice" = physician group billing address, not a hospital
  site_type?: "practice";
  practice_name?: string;
  affiliated_hospitals?: AffiliatedHospital[];
  data_flags?: DataFlag[];
}

export interface AffiliatedHospital {
  ccn: string;
  name?: string | null;
  city?: string | null;
  physician_count: number;
}

export interface HospitalDetail extends HospitalSummary {
  entity_id?: string;
  composite_score?: number;
  eligible_procedures?: number;
  rating_label?: string;
  tvt_registry_url?: string;
  latitude?: number;
  longitude?: number;
  physician_count?: number;
  total_tavr_volume?: number;
}

export interface HospitalListResponse {
  hospitals: HospitalSummary[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface HospitalFilters {
  state?: string;
  states?: string[];
  min_volume?: number;
  max_volume?: number;
  star_rating?: number;
  cms_rating?: number;
  search?: string;
  sort_by?: "volume" | "rating" | "name" | "state";
  sort_order?: "asc" | "desc";
  page?: number;
  per_page?: number;
}
