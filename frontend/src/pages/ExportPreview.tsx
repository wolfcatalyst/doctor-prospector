import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useExportQueueStore } from "../stores/exportQueueStore";
import { createExport, listExports } from "../api/exports";
import type { ExportOptions, ExportHistoryItem } from "../api/exports";
import Badge from "../components/shared/Badge";
import LoadingSpinner from "../components/shared/LoadingSpinner";

const FORMAT_OPTIONS = [
  { value: "excel", label: "Excel (.xlsx)", description: "Multi-sheet workbook with hyperlinks" },
  { value: "csv", label: "CSV (.csv)", description: "Flat file, one row per physician" },
  { value: "json", label: "JSON (.json)", description: "Hierarchical structure, machine-readable" },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ExportPreview() {
  const items = useExportQueueStore((s) => s.items);
  const removeItem = useExportQueueStore((s) => s.removeItem);
  const clearAll = useExportQueueStore((s) => s.clearAll);

  // Export options
  const [formatType, setFormatType] = useState("excel");
  const [includeTrials, setIncludeTrials] = useState(true);
  const [includePublications, setIncludePublications] = useState(true);
  const [includePayments, setIncludePayments] = useState(true);
  const [includeContact, setIncludeContact] = useState(true);
  const [includeHistorical, setIncludeHistorical] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  // Export history
  const { data: historyData } = useQuery({
    queryKey: ["export-history"],
    queryFn: listExports,
    enabled: showHistory,
  });

  // Export mutation
  const exportMutation = useMutation({
    mutationFn: async () => {
      const options: ExportOptions = {
        format_type: formatType,
        include_hospitals: true,
        include_trials: includeTrials,
        include_publications: includePublications,
        include_payments: includePayments,
        include_contact: includeContact,
        include_historical: includeHistorical,
      };
      return createExport({ items, options });
    },
    onSuccess: (blob) => {
      // Trigger browser download
      const ext = formatType === "excel" ? "xlsx" : formatType;
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[T:]/g, "_");
      const filename = `prospects_${timestamp}.${ext}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  });

  const totalPhysicians = items.reduce(
    (sum, item) => sum + item.physicianNpis.length,
    0
  );

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Export Preview</h1>
          <p className="text-sm text-gray-500">
            Review and export queued hospitals and physicians
          </p>
        </div>
        {items.length > 0 && (
          <button
            onClick={clearAll}
            className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            Clear All
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">Export queue is empty.</p>
          <p className="mt-2 text-sm text-gray-400">
            Add hospitals from the{" "}
            <Link
              to="/hospitals"
              className="text-brand-600 hover:underline"
            >
              Hospital
            </Link>{" "}
            or{" "}
            <Link
              to="/physicians"
              className="text-brand-600 hover:underline"
            >
              Physician
            </Link>{" "}
            pages to get started.
          </p>
        </div>
      ) : (
        <>
          {/* Summary stats */}
          <div className="mb-4 grid grid-cols-3 gap-4">
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">{items.length}</p>
              <p className="text-xs text-gray-500">Hospital(s)</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {totalPhysicians}
              </p>
              <p className="text-xs text-gray-500">Physician(s)</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
              <p className="text-2xl font-bold text-gray-900">
                {formatType.toUpperCase()}
              </p>
              <p className="text-xs text-gray-500">Export Format</p>
            </div>
          </div>

          {/* Queue items */}
          <div className="mb-6 space-y-2">
            <h2 className="text-sm font-semibold text-gray-700">
              Queued Hospitals
            </h2>
            {items.map((item) => (
              <div
                key={item.hospitalId}
                className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4"
              >
                <div>
                  <Link
                    to={`/hospitals/${item.hospitalId}`}
                    className="font-medium text-brand-700 hover:underline"
                  >
                    {item.hospitalName}
                  </Link>
                  <p className="text-xs text-gray-500">
                    {item.physicianNpis.length} physician(s) queued
                  </p>
                  <p className="text-xs text-gray-400">
                    Added {new Date(item.addedAt).toLocaleDateString()}
                  </p>
                </div>
                <button
                  onClick={() => removeItem(item.hospitalId)}
                  className="text-sm text-red-500 hover:text-red-700"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>

          {/* Export options */}
          <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
            <h2 className="mb-4 text-sm font-semibold text-gray-700">
              Export Options
            </h2>

            {/* Format */}
            <div className="mb-4">
              <label className="mb-2 block text-xs font-medium text-gray-500">
                Format
              </label>
              <div className="flex gap-3">
                {FORMAT_OPTIONS.map((fmt) => (
                  <button
                    key={fmt.value}
                    onClick={() => setFormatType(fmt.value)}
                    className={`flex-1 rounded-lg border p-3 text-left transition-colors ${
                      formatType === fmt.value
                        ? "border-brand-500 bg-brand-50"
                        : "border-gray-200 hover:bg-gray-50"
                    }`}
                  >
                    <p className="text-sm font-medium text-gray-900">
                      {fmt.label}
                    </p>
                    <p className="text-xs text-gray-500">{fmt.description}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* Include sections */}
            <div>
              <label className="mb-2 block text-xs font-medium text-gray-500">
                Include in Export
              </label>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <OptionCheckbox
                  label="Hospital Summary"
                  checked={true}
                  disabled
                />
                <OptionCheckbox
                  label="Clinical Trials"
                  checked={includeTrials}
                  onChange={setIncludeTrials}
                />
                <OptionCheckbox
                  label="Publications"
                  checked={includePublications}
                  onChange={setIncludePublications}
                />
                <OptionCheckbox
                  label="Device Payments"
                  checked={includePayments}
                  onChange={setIncludePayments}
                />
                <OptionCheckbox
                  label="Contact Info"
                  checked={includeContact}
                  onChange={setIncludeContact}
                />
                <OptionCheckbox
                  label="Volume Trends"
                  checked={includeHistorical}
                  onChange={setIncludeHistorical}
                />
              </div>
            </div>
          </div>

          {/* Export button */}
          <div className="mb-6 flex items-center gap-4">
            <button
              onClick={() => exportMutation.mutate()}
              disabled={exportMutation.isPending}
              className="rounded-lg bg-brand-600 px-8 py-3 text-sm font-semibold text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
            >
              {exportMutation.isPending
                ? "Generating..."
                : `Export ${items.length} Hospital(s)`}
            </button>

            {exportMutation.isPending && (
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <LoadingSpinner size="sm" />
                <span>
                  Fetching enrichment data and generating file... This may take
                  a moment for many physicians.
                </span>
              </div>
            )}

            {exportMutation.isSuccess && (
              <p className="text-sm text-green-600">
                Export downloaded successfully!
              </p>
            )}

            {exportMutation.isError && (
              <p className="text-sm text-red-600">
                Export failed:{" "}
                {exportMutation.error instanceof Error
                  ? exportMutation.error.message
                  : "Unknown error"}
              </p>
            )}
          </div>

          {/* Info note */}
          <div className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-4 text-xs text-blue-700">
            <strong>How it works:</strong> The export fetches the latest
            enrichment data (payments, publications, trials, volume trends) for
            each physician at export time. Data comes from cached API responses
            where available, with fresh fetches for any missing data. Larger
            exports with many physicians may take 10-30 seconds.
          </div>
        </>
      )}

      {/* Export history */}
      <div className="mt-8 border-t border-gray-200 pt-6">
        <button
          onClick={() => setShowHistory(!showHistory)}
          className="mb-4 text-sm font-medium text-gray-600 hover:text-gray-900"
        >
          {showHistory ? "Hide" : "Show"} Export History
        </button>

        {showHistory && (
          <div>
            {!historyData ? (
              <LoadingSpinner size="sm" />
            ) : historyData.exports.length === 0 ? (
              <p className="text-sm text-gray-500">No exports yet.</p>
            ) : (
              <div className="space-y-2">
                {historyData.exports.map((exp: ExportHistoryItem) => (
                  <div
                    key={exp.export_id}
                    className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3"
                  >
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {exp.filename}
                      </p>
                      <p className="text-xs text-gray-500">
                        {exp.hospital_count} hospitals, {exp.physician_count}{" "}
                        physicians | {formatBytes(exp.file_size_bytes)} |{" "}
                        {new Date(exp.created_at).toLocaleString()}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={exp.status === "completed" ? "green" : "gray"}
                      >
                        {exp.format.toUpperCase()}
                      </Badge>
                      <a
                        href={`/api/v1/exports/${exp.export_id}/download`}
                        className="text-xs font-medium text-brand-600 hover:underline"
                      >
                        Download
                      </a>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function OptionCheckbox({
  label,
  checked,
  disabled,
  onChange,
}: {
  label: string;
  checked: boolean;
  disabled?: boolean;
  onChange?: (v: boolean) => void;
}) {
  return (
    <label
      className={`flex items-center gap-2 rounded-lg border p-3 text-sm ${
        disabled
          ? "border-gray-100 bg-gray-50 text-gray-400"
          : checked
            ? "border-brand-200 bg-brand-50 text-gray-700"
            : "border-gray-200 text-gray-500"
      } ${!disabled ? "cursor-pointer hover:bg-gray-50" : ""}`}
    >
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.checked)}
        className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
      />
      {label}
    </label>
  );
}
