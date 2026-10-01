import { useQuery } from "@tanstack/react-query";
import {
  searchPhysicians,
  getPhysician,
  getPhysicianPayments,
  getPhysicianHistory,
  getPhysicianTrials,
  getPhysicianPublications,
} from "../api/physicians";
import type { PhysicianSearchFilters } from "../types/physician";

export function usePhysicianSearch(filters: PhysicianSearchFilters = {}) {
  const hasState = !!(filters.state || filters.states?.length);
  return useQuery({
    queryKey: ["physicians", filters],
    queryFn: () => searchPhysicians(filters),
    enabled: hasState, // requires at least one state
  });
}

export function usePhysician(npi: string | undefined) {
  return useQuery({
    queryKey: ["physician", npi],
    queryFn: () => getPhysician(npi!),
    enabled: !!npi,
  });
}

export function usePhysicianPayments(npi: string | undefined) {
  return useQuery({
    queryKey: ["physician-payments", npi],
    queryFn: () => getPhysicianPayments(npi!),
    enabled: !!npi,
  });
}

export function usePhysicianHistory(npi: string | undefined) {
  return useQuery({
    queryKey: ["physician-history", npi],
    queryFn: () => getPhysicianHistory(npi!),
    enabled: !!npi,
  });
}

export function usePhysicianTrials(
  npi: string | undefined,
  physicianName?: string
) {
  return useQuery({
    queryKey: ["physician-trials", npi],
    queryFn: () => getPhysicianTrials(npi!, physicianName),
    enabled: !!npi,
  });
}

export function usePhysicianPublications(
  npi: string | undefined,
  options?: { first_name?: string; last_name?: string; institution?: string }
) {
  return useQuery({
    queryKey: ["physician-publications", npi, options],
    queryFn: () => getPhysicianPublications(npi!, options),
    enabled: !!npi,
  });
}
