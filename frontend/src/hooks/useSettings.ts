import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getSettings,
  updateSettings,
  resetSettings,
  getCacheStatus,
  cleanExpiredCache,
  clearAllCache,
} from "../api/settings";
import { submitFeedback, listFeedback } from "../api/feedback";
import type { UserPreferences, FeedbackSubmission } from "../types/settings";

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: getSettings,
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (defaults: UserPreferences) => updateSettings(defaults),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useResetSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: resetSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useCacheStatus() {
  return useQuery({
    queryKey: ["cache-status"],
    queryFn: getCacheStatus,
  });
}

export function useCleanExpiredCache() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: cleanExpiredCache,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cache-status"] });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
}

export function useClearAllCache() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: clearAllCache,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cache-status"] });
      queryClient.invalidateQueries({ queryKey: ["sources"] });
    },
  });
}

export function useSubmitFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (submission: FeedbackSubmission) => submitFeedback(submission),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["feedback"] });
    },
  });
}

export function useFeedback() {
  return useQuery({
    queryKey: ["feedback"],
    queryFn: listFeedback,
  });
}
