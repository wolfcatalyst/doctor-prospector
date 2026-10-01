import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listProfiles,
  getActiveProfile,
  createProfile,
  updateProfile,
  deleteProfile,
  activateProfile,
} from "../api/deviceProfiles";
import type { DeviceMarketFilters } from "../types/deviceProfile";

export function useDeviceProfiles() {
  return useQuery({
    queryKey: ["device-profiles"],
    queryFn: listProfiles,
  });
}

export function useActiveProfile() {
  return useQuery({
    queryKey: ["device-profiles", "active"],
    queryFn: getActiveProfile,
  });
}

export function useCreateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; description?: string; filters: DeviceMarketFilters }) =>
      createProfile(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
    },
  });
}

export function useUpdateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...body
    }: {
      id: string;
      name?: string;
      description?: string;
      filters?: DeviceMarketFilters;
    }) => updateProfile(id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
    },
  });
}

export function useDeleteProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
    },
  });
}

export function useActivateProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => activateProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
      // Invalidate data queries that depend on the active profile
      queryClient.invalidateQueries({ queryKey: ["physicians"] });
      queryClient.invalidateQueries({ queryKey: ["hospitals"] });
    },
  });
}
