import apiClient from "./client";
import type {
  PhysicianSearchResponse,
  PhysicianDetail,
  PhysicianSearchFilters,
  PaymentSummary,
  HistorySummary,
  TrialSummary,
  PublicationSummary,
} from "../types/physician";

export async function searchPhysicians(
  filters: PhysicianSearchFilters = {}
): Promise<PhysicianSearchResponse> {
  const params: Record<string, string | number> = {};
  if (filters.state) params.state = filters.state;
  if (filters.city) params.city = filters.city;
  if (filters.name) params.name = filters.name;
  if (filters.specialty) params.specialty = filters.specialty;
  if (filters.min_volume != null) params.min_volume = filters.min_volume;
  if (filters.page) params.page = filters.page;
  if (filters.per_page) params.per_page = filters.per_page;

  const { data } = await apiClient.get<PhysicianSearchResponse>(
    "/physicians/search",
    {
      params: {
        ...params,
        ...(filters.states?.length ? { states: filters.states } : {}),
        ...(filters.hcpcs_codes?.length ? { hcpcs_codes: filters.hcpcs_codes } : {}),
      },
      paramsSerializer: {
        indexes: null,
      },
    }
  );
  return data;
}

export async function getPhysician(npi: string): Promise<PhysicianDetail> {
  const { data } = await apiClient.get<PhysicianDetail>(
    `/physicians/${npi}`
  );
  return data;
}

export async function getPhysicianPayments(
  npi: string
): Promise<PaymentSummary | { npi: string; payments: []; message?: string }> {
  const { data } = await apiClient.get(`/physicians/${npi}/payments`);
  return data;
}

export async function getPhysicianHistory(
  npi: string
): Promise<
  HistorySummary | { npi: string; volume_by_year: Record<string, never>; message?: string }
> {
  const { data } = await apiClient.get(`/physicians/${npi}/history`);
  return data;
}

export async function getPhysicianTrials(
  npi: string,
  physicianName?: string,
  skipCache?: boolean
): Promise<{ npi: string; trials: TrialSummary[]; total: number }> {
  const params: Record<string, string | boolean> = {};
  if (physicianName) params.physician_name = physicianName;
  if (skipCache) params.skip_cache = true;
  const { data } = await apiClient.get(`/physicians/${npi}/trials`, { params });
  return data;
}

export async function getPhysicianPublications(
  npi: string,
  options?: { first_name?: string; last_name?: string; institution?: string; skip_cache?: boolean }
): Promise<{ npi: string; publications: PublicationSummary[]; total: number }> {
  const { data } = await apiClient.get(`/physicians/${npi}/publications`, {
    params: options,
  });
  return data;
}
