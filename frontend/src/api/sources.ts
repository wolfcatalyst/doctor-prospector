import apiClient from "./client";
import type { SourceListResponse } from "../types/source";
import type { ProbeResult } from "../types/settings";

export async function getSources(): Promise<SourceListResponse> {
  const { data } = await apiClient.get<SourceListResponse>("/sources");
  return data;
}

export async function getSourceStatus(name: string) {
  const { data } = await apiClient.get(`/sources/${name}/status`);
  return data;
}

export async function refreshSource(
  name: string
): Promise<{ message: string; entries_cleared: number }> {
  const { data } = await apiClient.post(`/sources/${name}/refresh`);
  return data;
}

export async function checkSourceUpdates(): Promise<{
  probes: ProbeResult[];
  total: number;
}> {
  const { data } = await apiClient.post("/sources/check-updates");
  return data;
}

export interface DataVintage {
  tvt_registry: string | null;
  cms_utilization: string;
  cms_drg: string;
  cms_pos: string;
  open_payments_latest_year: number;
  history_years: [number, number] | null;
}

export async function getDataVintage(): Promise<DataVintage> {
  const { data } = await apiClient.get<DataVintage>("/sources/vintage");
  return data;
}
