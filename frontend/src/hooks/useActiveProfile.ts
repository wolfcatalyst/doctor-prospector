import { useDeviceProfiles } from "./useDeviceProfiles";

/**
 * Returns the active device profile's procedure label, module membership,
 * and conditional visibility flags for TAVR-specific content.
 */
export function useActiveProfile() {
  const { data } = useDeviceProfiles();
  const active = data?.profiles.find((p) => p.is_active);

  const procedureLabel = active?.filters.procedure_label || "TAVR";
  const activeModules = active?.filters.modules ?? [];

  // Check if this is a TAVR profile:
  // 1. Explicitly has "tavr" module enabled
  // 2. Fallback: has TAVR HCPCS codes or "TAVR" in label (backward compat)
  const hasTavrModule = activeModules.includes("tavr");
  const tavrCodes = ["33361", "33362", "33363", "33364", "33365", "33366", "33367", "33368", "33369"];
  const hasTavrCodes = active
    ? active.filters.hcpcs_codes.some((c) => tavrCodes.includes(c))
    : true; // default to showing TAVR content when no profile is active
  const isTavrLabel = procedureLabel.toUpperCase().includes("TAVR");
  const isTavrProfile = hasTavrModule || hasTavrCodes || isTavrLabel;
  const showEdwards = isTavrProfile;

  return {
    procedureLabel,
    showEdwards,
    isTavrProfile,
    activeModules,
    activeProfile: active,
  };
}
