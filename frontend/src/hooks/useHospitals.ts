import { useQuery } from "@tanstack/react-query";
import {
  getHospitals,
  getHospital,
  getHospitalPhysicians,
  getHospitalTrials,
} from "../api/hospitals";
import type { HospitalFilters } from "../types/hospital";

export function useHospitals(filters: HospitalFilters = {}) {
  return useQuery({
    queryKey: ["hospitals", filters],
    queryFn: () => getHospitals(filters),
  });
}

export function useHospital(siteId: string | undefined) {
  return useQuery({
    queryKey: ["hospital", siteId],
    queryFn: () => getHospital(siteId!),
    enabled: !!siteId,
  });
}

export function useHospitalPhysicians(
  siteId: string | undefined,
  options?: {
    specialty?: string;
    search_scope?: "city" | "state" | "all";
    include_historical?: boolean;
  }
) {
  return useQuery({
    queryKey: ["hospital-physicians", siteId, options],
    queryFn: () => getHospitalPhysicians(siteId!, options),
    enabled: !!siteId,
  });
}

export function useHospitalTrials(siteId: string | undefined) {
  return useQuery({
    queryKey: ["hospital-trials", siteId],
    queryFn: () => getHospitalTrials(siteId!),
    enabled: !!siteId,
  });
}
