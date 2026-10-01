import apiClient from "./client";
import type {
  DeviceProfile,
  DeviceProfileListResponse,
  DeviceMarketFilters,
} from "../types/deviceProfile";

export async function listProfiles(): Promise<DeviceProfileListResponse> {
  const { data } = await apiClient.get("/device-profiles");
  return data;
}

export async function getActiveProfile(): Promise<{ filters: DeviceMarketFilters }> {
  const { data } = await apiClient.get("/device-profiles/active");
  return data;
}

export async function getProfile(id: string): Promise<DeviceProfile> {
  const { data } = await apiClient.get(`/device-profiles/${id}`);
  return data;
}

export async function createProfile(body: {
  name: string;
  description?: string;
  filters: DeviceMarketFilters;
}): Promise<DeviceProfile> {
  const { data } = await apiClient.post("/device-profiles", body);
  return data;
}

export async function updateProfile(
  id: string,
  body: {
    name?: string;
    description?: string;
    filters?: DeviceMarketFilters;
  }
): Promise<DeviceProfile> {
  const { data } = await apiClient.put(`/device-profiles/${id}`, body);
  return data;
}

export async function deleteProfile(id: string): Promise<void> {
  await apiClient.delete(`/device-profiles/${id}`);
}

export async function activateProfile(id: string): Promise<void> {
  await apiClient.post(`/device-profiles/${id}/activate`);
}

export async function addSavedSpecialty(
  profileId: string,
  specialty: { name: string; specialty: string; hcpcs_codes: string[] }
): Promise<DeviceProfile> {
  const { data } = await apiClient.post(
    `/device-profiles/${profileId}/saved-specialties`,
    specialty
  );
  return data;
}

export async function deleteSavedSpecialty(
  profileId: string,
  specialtyName: string
): Promise<DeviceProfile> {
  const { data } = await apiClient.delete(
    `/device-profiles/${profileId}/saved-specialties/${encodeURIComponent(specialtyName)}`
  );
  return data;
}
