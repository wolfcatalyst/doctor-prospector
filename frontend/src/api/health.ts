import apiClient from "./client";

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  auth_enabled: boolean;
  timestamp: string;
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>("/health");
  return data;
}
