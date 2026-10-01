import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getSources, refreshSource, checkSourceUpdates, getDataVintage } from "../api/sources";

export function useSources() {
  return useQuery({
    queryKey: ["sources"],
    queryFn: getSources,
  });
}

export function useRefreshSource() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => refreshSource(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
}

export function useCheckSourceUpdates() {
  return useMutation({
    mutationFn: checkSourceUpdates,
  });
}

export function useDataVintage() {
  return useQuery({
    queryKey: ["data-vintage"],
    queryFn: getDataVintage,
    staleTime: 60 * 60 * 1000,
  });
}
