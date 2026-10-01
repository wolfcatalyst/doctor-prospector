import apiClient from "./client";
import type { UserProfile, UserPreferences, CacheStatusResponse } from "../types/settings";

export async function getSettings(): Promise<UserProfile> {
  const { data } = await apiClient.get<UserProfile>("/settings");
  return data;
}

export async function updateSettings(
  defaults: UserPreferences
): Promise<UserProfile> {
  const { data } = await apiClient.put<UserProfile>("/settings", { defaults });
  return data;
}

export async function resetSettings(): Promise<UserProfile> {
  const { data } = await apiClient.post<UserProfile>("/settings/reset");
  return data;
}

export async function getCacheStatus(): Promise<CacheStatusResponse> {
  const { data } = await apiClient.get<CacheStatusResponse>("/settings/cache");
  return data;
}

export async function cleanExpiredCache(): Promise<{
  message: string;
  entries_removed: number;
}> {
  const { data } = await apiClient.post("/settings/cache/clean-expired");
  return data;
}

export async function clearAllCache(): Promise<{
  message: string;
  entries_cleared: number;
}> {
  const { data } = await apiClient.post("/settings/cache/clear-all");
  return data;
}
