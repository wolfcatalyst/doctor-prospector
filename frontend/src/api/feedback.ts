import apiClient from "./client";
import type { FeedbackEntry, FeedbackSubmission } from "../types/settings";

export async function submitFeedback(
  submission: FeedbackSubmission
): Promise<{ message: string; entry: FeedbackEntry }> {
  const { data } = await apiClient.post("/feedback", submission);
  return data;
}

export async function listFeedback(): Promise<{
  feedback: FeedbackEntry[];
  total: number;
}> {
  const { data } = await apiClient.get("/feedback");
  return data;
}
