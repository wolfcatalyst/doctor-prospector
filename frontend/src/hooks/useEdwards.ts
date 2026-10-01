import { useQuery } from "@tanstack/react-query";
import {
  getEdwardsHospitals,
  matchEdwardsHospital,
} from "../api/edwards";

export function useEdwardsHospitals(filters: {
  state?: string;
  search?: string;
} = {}) {
  return useQuery({
    queryKey: ["edwards", filters],
    queryFn: () => getEdwardsHospitals(filters),
  });
}

export function useEdwardsMatch(
  name: string | undefined,
  city?: string,
  state?: string
) {
  return useQuery({
    queryKey: ["edwards-match", name, city, state],
    queryFn: () => matchEdwardsHospital(name!, city, state),
    enabled: !!name,
  });
}
