import apiClient from "./client";

export interface ExportOptions {
  format_type: string;
  include_hospitals: boolean;
  include_trials: boolean;
  include_publications: boolean;
  include_payments: boolean;
  include_contact: boolean;
  include_historical: boolean;
}

export interface ExportRequest {
  items: {
    hospitalId: string;
    hospitalName: string;
    physicianNpis: string[];
  }[];
  options: ExportOptions;
}

export interface ExportHistoryItem {
  export_id: string;
  filename: string;
  format: string;
  hospital_count: number;
  physician_count: number;
  file_size_bytes: number;
  status: string;
  created_at: string;
}

export async function createExport(request: ExportRequest): Promise<Blob> {
  const { data } = await apiClient.post("/exports", request, {
    responseType: "blob",
  });
  return data;
}

export async function listExports(): Promise<{
  exports: ExportHistoryItem[];
  total: number;
}> {
  const { data } = await apiClient.get("/exports");
  return data;
}

export async function downloadExport(exportId: string): Promise<Blob> {
  const { data } = await apiClient.get(`/exports/${exportId}/download`, {
    responseType: "blob",
  });
  return data;
}
