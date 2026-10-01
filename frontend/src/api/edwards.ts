import apiClient from "./client";
import type {
  EdwardsListResponse,
  EdwardsMatchResponse,
} from "../types/edwards";

export async function getEdwardsHospitals(
  filters: { state?: string; search?: string } = {}
): Promise<EdwardsListResponse> {
  const params: Record<string, string> = {};
  if (filters.state) params.state = filters.state;
  if (filters.search) params.search = filters.search;

  const { data } = await apiClient.get<EdwardsListResponse>("/edwards", {
    params,
  });
  return data;
}

export async function refreshEdwardsData(): Promise<{
  message: string;
  total: number;
}> {
  const { data } = await apiClient.post("/edwards/refresh");
  return data;
}

export async function matchEdwardsHospital(
  name: string,
  city?: string,
  state?: string
): Promise<EdwardsMatchResponse> {
  const params: Record<string, string> = { name };
  if (city) params.city = city;
  if (state) params.state = state;

  const { data } = await apiClient.get<EdwardsMatchResponse>("/edwards/match", {
    params,
  });
  return data;
}
