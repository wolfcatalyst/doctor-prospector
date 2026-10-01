import apiClient from "./client";
import type {
  HospitalListResponse,
  HospitalDetail,
  HospitalFilters,
} from "../types/hospital";
import type { PhysicianSummary } from "../types/physician";
import type { TrialSummary } from "../types/physician";

export async function getHospitals(
  filters: HospitalFilters = {}
): Promise<HospitalListResponse> {
  const params: Record<string, string | number> = {};
  if (filters.state) params.state = filters.state;
  if (filters.min_volume != null) params.min_volume = filters.min_volume;
  if (filters.max_volume != null) params.max_volume = filters.max_volume;
  if (filters.star_rating != null) params.star_rating = filters.star_rating;
  if (filters.cms_rating != null) params.cms_rating = filters.cms_rating;
  if (filters.search) params.search = filters.search;
  if (filters.sort_by) params.sort_by = filters.sort_by;
  if (filters.sort_order) params.sort_order = filters.sort_order;
  if (filters.page) params.page = filters.page;
  if (filters.per_page) params.per_page = filters.per_page;

  // Handle states array separately
  const { data } = await apiClient.get<HospitalListResponse>("/hospitals", {
    params: {
      ...params,
      ...(filters.states?.length ? { states: filters.states } : {}),
    },
    paramsSerializer: {
      indexes: null, // states=NJ&states=NY format
    },
  });
  return data;
}

export async function getHospital(siteId: string): Promise<HospitalDetail> {
  const { data } = await apiClient.get<HospitalDetail>(
    `/hospitals/${encodeURIComponent(siteId)}`
  );
  return data;
}

export async function getHospitalPhysicians(
  siteId: string,
  options?: {
    specialty?: string;
    search_scope?: "city" | "state" | "all";
    include_historical?: boolean;
  }
): Promise<{ physicians: PhysicianSummary[]; total: number }> {
  const { data } = await apiClient.get(
    `/hospitals/${encodeURIComponent(siteId)}/physicians`,
    { params: options }
  );
  return data;
}

export async function getHospitalTrials(
  siteId: string
): Promise<{ trials: TrialSummary[]; total: number }> {
  const { data } = await apiClient.get(
    `/hospitals/${encodeURIComponent(siteId)}/trials`
  );
  return data;
}

export async function reloadHospitals(): Promise<{ message: string }> {
  const { data } = await apiClient.post("/hospitals/reload");
  return data;
}
