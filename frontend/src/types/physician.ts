import type { DataFlag } from "./dataFlags";

export interface PhysicianSummary {
  npi: string;
  full_name?: string;
  provider_name?: string;
  credential?: string;
  primary_specialty?: string;
  practice_city?: string;
  practice_state?: string;
  provider_city?: string;
  provider_state?: string;
  total_services: number;
  total_beneficiaries: number;
  has_volume: boolean;
  historical_only: boolean;
  address_mismatch: boolean;
  data_flags?: DataFlag[];
}

export interface ProcedureBreakdown {
  hcpcs_code: string;
  description: string;
  services: number;
  beneficiaries: number;
}

export interface PhysicianDetail extends PhysicianSummary {
  procedure_breakdown?: ProcedureBreakdown[];
  first_name?: string;
  last_name?: string;
  practice_address_line1?: string;
  practice_address_line2?: string;
  practice_postal_code?: string;
  practice_phone?: string;
  npi_registry_url?: string;
  doximity_url?: string;
  google_search_url?: string;
}

export interface PhysicianSearchResponse {
  physicians: PhysicianSummary[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface PhysicianSearchFilters {
  state?: string;
  states?: string[];
  city?: string;
  name?: string;
  specialty?: string;
  min_volume?: number;
  hcpcs_codes?: string[];
  page?: number;
  per_page?: number;
}

export interface PaymentSummary {
  npi: string;
  physician_name?: string;
  total_payments: number;
  payment_count: number;
  avg_payment: number;
  companies: Record<string, number>;
  top_company?: string;
  top_company_amount: number;
  years: Record<string, number>;
  payment_types: Record<string, number>;
  is_heartflow_user: boolean;
  key_relationships: Record<string, number>;
  years_active: number;
  latest_year?: number;
  payment_trend_pct: number;
  payment_trend_indicator: string;
}

export interface HistorySummary {
  npi: string;
  provider_name?: string;
  total_tavr_procedures: number;
  years_active: number;
  first_year?: number;
  latest_year?: number;
  latest_volume: number;
  volume_by_year: Record<string, number>;
  trends: Record<string, unknown>[];
  avg_annual_growth_pct: number;
  trend_indicator: string;
}

export interface TrialSummary {
  nct_id: string;
  title: string;
  official_title?: string;
  study_url?: string;
  overall_status?: string;
  start_date?: string;
  completion_date?: string;
  phase: string[];
  enrollment: number;
  conditions: string[];
  brief_summary?: string;
  lead_sponsor?: string;
  investigators: Record<string, unknown>[];
  locations: Record<string, unknown>[];
  match_confidence?: "confirmed" | "likely" | "name_only";
}

export interface PublicationSummary {
  pmid: string;
  title: string;
  journal?: string;
  pub_date?: string;
  abstract?: string;
  authors: Record<string, unknown>[];
  coauthor_summary?: string;
  categories: string[];
  pubmed_url?: string;
  confidence_tier: number;
  confidence_badge: string;
  match_method?: string;
}
