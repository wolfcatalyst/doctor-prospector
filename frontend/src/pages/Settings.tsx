import { useState, useEffect, useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSources, useRefreshSource, useCheckSourceUpdates } from "../hooks/useSources";
import {
  useSettings,
  useUpdateSettings,
  useResetSettings,
  useCacheStatus,
  useCleanExpiredCache,
  useClearAllCache,
  useSubmitFeedback,
  useFeedback,
} from "../hooks/useSettings";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import Badge from "../components/shared/Badge";
import MetricCard from "../components/shared/MetricCard";
import type { ProbeResult, UserPreferences } from "../types/settings";
import DeviceProfiles from "./DeviceProfiles";
import apiClient from "../api/client";


/* ── Background Refresh Panel ── */
interface RefreshSource {
  status: string;
  detail: string;
  last_checked: string;
}

function SchedulerPanel() {
  const [status, setStatus] = useState<{
    sources: Record<string, RefreshSource>;
    scheduler_running: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await apiClient.get("/settings/refresh-status");
      setStatus(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 10000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const triggerRefresh = async () => {
    setTriggering(true);
    try {
      await apiClient.post("/settings/refresh-now");
      // Poll for updates
      setTimeout(fetchStatus, 2000);
      setTimeout(fetchStatus, 5000);
      setTimeout(fetchStatus, 10000);
    } finally {
      setTriggering(false);
    }
  };

  if (loading) return <LoadingSpinner size="sm" />;

  const sources = status?.sources ?? {};
  const schedulerStatus = sources["_scheduler"];
  const dataSources = Object.entries(sources).filter(([k]) => k !== "_scheduler");

  const statusBadge = (s: string) => {
    switch (s) {
      case "ok": return <Badge variant="green">OK</Badge>;
      case "refreshing": return <Badge variant="blue">Refreshing</Badge>;
      case "checking": return <Badge variant="blue">Checking</Badge>;
      case "running": return <Badge variant="blue">Running</Badge>;
      case "update_available": return <Badge variant="yellow">Update Available</Badge>;
      case "empty": return <Badge variant="gray">No Data</Badge>;
      case "error": return <Badge variant="red">Error</Badge>;
      default: return <Badge variant="gray">{s}</Badge>;
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              Background Data Refresh
            </h2>
            <p className="text-sm text-gray-500">
              Data sources are automatically checked and refreshed every 6 hours.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {schedulerStatus && statusBadge(schedulerStatus.status)}
            <button
              onClick={triggerRefresh}
              disabled={triggering}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {triggering ? "Starting..." : "Refresh Now"}
            </button>
          </div>
        </div>

        {dataSources.length === 0 ? (
          <p className="text-sm text-gray-500">
            Scheduler is starting up. Status will appear after the first check (~30 seconds).
          </p>
        ) : (
          <div className="divide-y divide-gray-100">
            {dataSources.map(([name, src]) => (
              <div key={name} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm font-medium text-gray-900">
                    {name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
                  </p>
                  <p className="text-xs text-gray-500">{src.detail}</p>
                  {src.last_checked && (
                    <p className="text-xs text-gray-400">
                      Last checked: {new Date(src.last_checked).toLocaleString()}
                    </p>
                  )}
                </div>
                {statusBadge(src.status)}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-6">
        <h2 className="mb-2 text-lg font-semibold text-gray-900">How It Works</h2>
        <div className="space-y-2 text-sm text-gray-600">
          <p>The background scheduler runs automatically inside the application:</p>
          <ul className="ml-4 list-disc space-y-1">
            <li><strong>Every 6 hours</strong>: Checks API-based sources (Hospital Compare, DRG volumes) and refreshes if TTL expired</li>
            <li><strong>Weekly</strong>: Checks if CMS published new yearly PUF data</li>
            <li><strong>On startup</strong>: Runs an initial freshness check after 30 seconds</li>
          </ul>
          <p className="text-xs text-gray-400 mt-3">
            Historical PUF imports (multi-GB downloads) are not auto-downloaded.
            The scheduler will notify you when new data is available.
          </p>
        </div>
      </section>
    </div>
  );
}

/* ── Source display names & metadata ── */
const SOURCE_META: Record<
  string,
  { display: string; ttlLabel: string; updateFreq: string; warning: string }
> = {
  tvt_registry: {
    display: "TVT Registry",
    ttlLabel: "1 week",
    updateFreq: "Quarterly",
    warning: "Only refresh if hospitals are missing or data looks wrong",
  },
  nppes: {
    display: "NPPES",
    ttlLabel: "30 days",
    updateFreq: "Weekly",
    warning: "Only refresh if physician information looks incorrect",
  },
  cms_utilization: {
    display: "CMS Utilization",
    ttlLabel: "1 week",
    updateFreq: "Annually",
    warning: "CMS updates once per year - manual refresh rarely needed",
  },
  cms_pos: {
    display: "CMS Provider of Services",
    ttlLabel: "30 days",
    updateFreq: "Quarterly",
    warning: "POS UUID changes quarterly - check for updates first",
  },
  cms_historical: {
    display: "CMS Historical",
    ttlLabel: "30 days",
    updateFreq: "Annually",
    warning: "Historical data loaded from local CSV files",
  },
  open_payments: {
    display: "CMS Open Payments",
    ttlLabel: "1 week",
    updateFreq: "Annually",
    warning: "Payment data is slow to re-fetch (30-90s per physician)",
  },
  clinical_trials: {
    display: "ClinicalTrials.gov",
    ttlLabel: "24 hours",
    updateFreq: "Daily",
    warning: "Safe to refresh - trials update frequently",
  },
  pubmed: {
    display: "PubMed",
    ttlLabel: "30 days",
    updateFreq: "As published",
    warning: "Safe to refresh - publications rarely change once published",
  },
  orcid: {
    display: "ORCID",
    ttlLabel: "30 days",
    updateFreq: "Rarely",
    warning: "Safe to refresh - ORCID iDs are permanent identifiers",
  },
};

const FEEDBACK_CATEGORIES = [
  "New Data Source",
  "Dashboard Feature",
  "Data Visualization",
  "Export/Reporting",
  "Bug Report",
  "General Feedback",
  "Other",
];

const PRIORITIES = ["Nice to Have", "Would Be Useful", "Critical Need"];

const US_STATES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas", CA: "California",
  CO: "Colorado", CT: "Connecticut", DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa",
  KS: "Kansas", KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada", NH: "New Hampshire",
  NJ: "New Jersey", NM: "New Mexico", NY: "New York", NC: "North Carolina",
  ND: "North Dakota", OH: "Ohio", OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota", TN: "Tennessee",
  TX: "Texas", UT: "Utah", VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
};

/* ── Helper: format age from ISO string ── */
function formatAge(isoStr: string): string {
  const then = new Date(isoStr);
  const now = new Date();
  const diffMs = now.getTime() - then.getTime();
  const hours = Math.floor(diffMs / 3_600_000);
  const days = Math.floor(hours / 24);
  if (days > 30) return `${Math.floor(days / 30)}mo ago`;
  if (days > 0) return `${days}d ago`;
  if (hours > 0) return `${hours}h ago`;
  return `${Math.max(0, Math.floor(diffMs / 60_000))}m ago`;
}

function formatDate(isoStr: string): string {
  return new Date(isoStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/* ── Probe status helpers ── */
function probeIcon(status: string): string {
  switch (status) {
    case "current": return "OK";
    case "new_data": return "NEW";
    case "worth_checking": return "?";
    case "stale_uuid": return "!!";
    case "error": return "ERR";
    default: return "?";
  }
}

function probeBadgeVariant(
  status: string
): "green" | "blue" | "yellow" | "orange" | "red" | "gray" {
  switch (status) {
    case "current": return "green";
    case "new_data": return "blue";
    case "worth_checking": return "yellow";
    case "stale_uuid": return "orange";
    case "error": return "red";
    default: return "gray";
  }
}

/* ================================================================ */
/*                       SETTINGS PAGE                              */
/* ================================================================ */

export default function Settings() {
  const { data: sourceData, isLoading: sourcesLoading } = useSources();
  const refreshMutation = useRefreshSource();
  const checkUpdatesMutation = useCheckSourceUpdates();
  const { data: cacheData, isLoading: cacheLoading } = useCacheStatus();
  const { data: settingsData } = useSettings();
  const updateSettingsMutation = useUpdateSettings();
  const resetSettingsMutation = useResetSettings();
  const cleanExpiredMutation = useCleanExpiredCache();
  const clearAllMutation = useClearAllCache();
  const submitFeedbackMutation = useSubmitFeedback();
  const { data: feedbackData } = useFeedback();

  const [confirmRefresh, setConfirmRefresh] = useState<string | null>(null);
  const [clearAllConfirm, setClearAllConfirm] = useState("");
  type SettingsTab = "freshness" | "scheduler" | "cache" | "preferences" | "profiles" | "feedback" | "reference";
  const TABS: SettingsTab[] = ["freshness", "scheduler", "cache", "preferences", "profiles", "feedback", "reference"];
  // ?tab=preferences lets other pages (e.g. the login notice) link straight to a tab
  const [searchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab") as SettingsTab | null;
  const [activeTab, setActiveTab] = useState<SettingsTab>(
    requestedTab && TABS.includes(requestedTab) ? requestedTab : "freshness"
  );
  useEffect(() => {
    if (requestedTab && TABS.includes(requestedTab)) setActiveTab(requestedTab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedTab]);

  /* Feedback form state */
  const [fbCategory, setFbCategory] = useState(FEEDBACK_CATEGORIES[0]);
  const [fbPriority, setFbPriority] = useState(PRIORITIES[0]);
  const [fbContent, setFbContent] = useState("");
  const [fbSuccess, setFbSuccess] = useState(false);

  /* Settings form state */
  const defaults = settingsData?.defaults;
  const [editPrefs, setEditPrefs] = useState<UserPreferences | null>(null);
  const prefs = editPrefs ?? defaults;

  const probeResults: ProbeResult[] =
    (checkUpdatesMutation.data as unknown as { probes?: ProbeResult[] })?.probes ?? [];

  /* ── Stale sources based on probes ── */
  const staleSources = probeResults.filter(
    (p) => p.status === "new_data" || p.status === "stale_uuid"
  );

  /* ── Tab buttons ── */
  const tabs = [
    { id: "freshness" as const, label: "Data Freshness" },
    { id: "scheduler" as const, label: "Auto Refresh" },
    { id: "cache" as const, label: "Cache Management" },
    { id: "preferences" as const, label: "Preferences" },
    { id: "profiles" as const, label: "Device Profiles" },
    { id: "feedback" as const, label: "Feedback" },
    { id: "reference" as const, label: "Data Sources" },
  ];

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-sm text-gray-500">
          Data freshness, cache management, preferences, and feedback
        </p>
      </div>

      {/* Tab navigation */}
      <div className="mb-6 flex gap-1 rounded-lg border border-gray-200 bg-gray-50 p-1">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ================================================================ */}
      {/*  TAB 1: DATA FRESHNESS                                          */}
      {/* ================================================================ */}
      {activeTab === "freshness" && (
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">
              Source Status
            </h2>
            <p className="mb-4 text-sm text-gray-500">
              Check whether upstream data sources have published new data since
              your last fetch. Cache freshness is checked automatically.
            </p>

            {sourcesLoading && <LoadingSpinner size="sm" />}

            {sourceData && (
              <div className="overflow-hidden rounded-lg border border-gray-100">
                <table className="min-w-full divide-y divide-gray-100">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Source
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Last Fetched
                      </th>
                      <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                        Entries
                      </th>
                      <th className="px-4 py-2 text-center text-xs font-medium uppercase text-gray-500">
                        Status
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                        Updates
                      </th>
                      <th className="px-4 py-2 text-right text-xs font-medium uppercase text-gray-500">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {Object.entries(sourceData.sources).map(
                      ([name, source]) => {
                        const freshness =
                          source.freshness || sourceData.freshness?.[name];
                        const meta = SOURCE_META[name];
                        const probe = probeResults.find(
                          (p) => p.source_name === name
                        );

                        /* Compute status */
                        let statusBadge: { variant: "green" | "orange" | "gray" | "blue" | "red" | "yellow"; label: string };
                        if (probe) {
                          statusBadge = {
                            variant: probeBadgeVariant(probe.status),
                            label:
                              probe.status === "current"
                                ? "Fresh"
                                : probe.status === "new_data"
                                  ? "New Data!"
                                  : probe.status === "stale_uuid"
                                    ? "UUID Stale"
                                    : probe.status === "error"
                                      ? "Error"
                                      : "Worth Checking",
                          };
                        } else if (!freshness?.entry_count) {
                          statusBadge = { variant: "gray", label: "No data" };
                        } else {
                          const newest = freshness.newest_entry;
                          const ageHrs = newest
                            ? (Date.now() - new Date(newest).getTime()) / 3_600_000
                            : Infinity;
                          statusBadge =
                            ageHrs <= source.cache_ttl_hours
                              ? { variant: "green", label: "Fresh" }
                              : { variant: "orange", label: "Stale" };
                        }

                        return (
                          <tr key={name}>
                            <td className="px-4 py-2">
                              <div className="text-sm font-medium text-gray-900">
                                {meta?.display ?? name}
                              </div>
                              <div className="text-xs text-gray-400">
                                {source.provides?.join(", ")}
                              </div>
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-500">
                              {freshness?.newest_entry ? (
                                <div>
                                  <div>{formatDate(freshness.newest_entry)}</div>
                                  <div className="text-xs text-gray-400">
                                    {formatAge(freshness.newest_entry)}
                                  </div>
                                </div>
                              ) : (
                                <span className="text-gray-400">Never</span>
                              )}
                            </td>
                            <td className="px-4 py-2 text-right text-sm text-gray-500">
                              {freshness?.entry_count ?? 0}
                            </td>
                            <td className="px-4 py-2 text-center">
                              <Badge variant={statusBadge.variant}>
                                {statusBadge.label}
                              </Badge>
                            </td>
                            <td className="px-4 py-2 text-sm text-gray-500">
                              {meta?.updateFreq ?? "—"}
                            </td>
                            <td className="px-4 py-2 text-right">
                              <button
                                onClick={() => setConfirmRefresh(name)}
                                className="text-xs text-brand-600 hover:text-brand-800"
                              >
                                Clear Cache
                              </button>
                            </td>
                          </tr>
                        );
                      }
                    )}
                  </tbody>
                </table>
              </div>
            )}

            {/* Action buttons */}
            <div className="mt-4 flex gap-3">
              <button
                onClick={() => checkUpdatesMutation.mutate()}
                disabled={checkUpdatesMutation.isPending}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
              >
                {checkUpdatesMutation.isPending
                  ? "Checking upstream sources..."
                  : "Check for Updates"}
              </button>

              {staleSources.length > 0 && (
                <button
                  onClick={async () => {
                    for (const p of staleSources) {
                      await refreshMutation.mutateAsync(p.source_name);
                    }
                  }}
                  disabled={refreshMutation.isPending}
                  className="rounded-lg border border-orange-300 bg-orange-50 px-4 py-2 text-sm font-medium text-orange-700 hover:bg-orange-100 disabled:opacity-50"
                >
                  Refresh {staleSources.length} Stale Source
                  {staleSources.length > 1 ? "s" : ""}
                </button>
              )}
            </div>
          </section>

          {/* Probe results */}
          {probeResults.length > 0 && (
            <section className="rounded-lg border border-gray-200 bg-white p-6">
              <h2 className="mb-3 text-lg font-semibold text-gray-900">
                Upstream Check Results
              </h2>
              <div className="space-y-2">
                {probeResults.map((probe) => {
                  const meta = SOURCE_META[probe.source_name];
                  return (
                    <div
                      key={probe.source_name}
                      className="flex items-start gap-3 rounded-lg border border-gray-100 p-3"
                    >
                      <Badge variant={probeBadgeVariant(probe.status)}>
                        {probeIcon(probe.status)}
                      </Badge>
                      <div className="flex-1">
                        <div className="text-sm font-medium text-gray-900">
                          {meta?.display ?? probe.source_name}
                        </div>
                        <div className="text-sm text-gray-600">
                          {probe.message}
                        </div>
                        {probe.status === "stale_uuid" &&
                          probe.source_name === "cms_pos" && (
                            <p className="mt-1 text-xs text-orange-600">
                              Fix: Update BASE_URL UUID in
                              src/doctor_prospector/sources/cms_pos.py with the
                              new UUID from the CMS POS dataset page.
                            </p>
                          )}
                        {probe.status === "stale_uuid" &&
                          probe.source_name === "cms_utilization" && (
                            <p className="mt-1 text-xs text-orange-600">
                              Fix: Update BASE_URL UUID in
                              src/doctor_prospector/sources/cms_utilization.py.
                            </p>
                          )}
                        {probe.status === "new_data" &&
                          probe.source_name === "open_payments" && (
                            <p className="mt-1 text-xs text-blue-600">
                              Fix: Add the new year's dataset ID to
                              GENERAL_PAYMENTS_DATASETS in
                              src/doctor_prospector/sources/open_payments.py.
                            </p>
                          )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* Confirm refresh modal */}
          {confirmRefresh && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
              <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
                <h3 className="text-lg font-semibold text-gray-900">
                  Clear {SOURCE_META[confirmRefresh]?.display ?? confirmRefresh}{" "}
                  Cache?
                </h3>
                <p className="mt-2 text-sm text-yellow-700 bg-yellow-50 rounded-lg p-3">
                  {SOURCE_META[confirmRefresh]?.warning}
                </p>
                <p className="mt-3 text-sm text-gray-600">
                  This will delete all cached data for this source. The next
                  query will fetch fresh data from the original source.
                </p>
                <div className="mt-4 flex justify-end gap-3">
                  <button
                    onClick={() => setConfirmRefresh(null)}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={async () => {
                      await refreshMutation.mutateAsync(confirmRefresh);
                      setConfirmRefresh(null);
                    }}
                    disabled={refreshMutation.isPending}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    {refreshMutation.isPending ? "Clearing..." : "Yes, Clear Cache"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/*  TAB 2: CACHE MANAGEMENT                                        */}
      {/* ================================================================ */}
      {activeTab === "scheduler" && <SchedulerPanel />}

      {activeTab === "cache" && (
        <div className="space-y-6">
          {/* Cache overview */}
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">
              Cache Overview
            </h2>
            <p className="mb-4 text-sm text-gray-500">
              Cached queries return ~70x faster. Most data automatically expires
              based on update frequency.
            </p>

            {cacheLoading && <LoadingSpinner size="sm" />}

            {cacheData && (
              <>
                <div className="mb-6 grid grid-cols-3 gap-4">
                  <MetricCard
                    label="Total Entries"
                    value={cacheData.total_entries}
                  />
                  <MetricCard
                    label="Valid (Fresh)"
                    value={cacheData.valid_entries}
                  />
                  <MetricCard
                    label="Expired"
                    value={cacheData.expired_entries}
                  />
                </div>

                {/* Per-source cache */}
                <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                  Per-Source Breakdown
                </h3>
                <div className="space-y-2">
                  {Object.entries(cacheData.by_source).map(([name, count]) => {
                    const meta = SOURCE_META[name];
                    return (
                      <div
                        key={name}
                        className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3"
                      >
                        <div>
                          <div className="text-sm font-medium text-gray-900">
                            {meta?.display ?? name}
                          </div>
                          <div className="text-xs text-gray-400">
                            TTL: {meta?.ttlLabel ?? "—"}
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <span className="text-sm text-gray-600">
                            {count} entries
                          </span>
                          <button
                            onClick={() => setConfirmRefresh(name)}
                            className="text-xs text-brand-600 hover:text-brand-800"
                          >
                            Clear
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </section>

          {/* Maintenance */}
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-4 text-lg font-semibold text-gray-900">
              Maintenance
            </h2>

            <div className="flex items-center justify-between rounded-lg border border-gray-100 p-4">
              <div>
                <div className="text-sm font-medium text-gray-900">
                  Clean Expired Entries
                </div>
                <div className="text-xs text-gray-500">
                  Remove expired cache entries to free disk space. Safe -
                  expired entries are already ignored.
                </div>
              </div>
              <button
                onClick={() => cleanExpiredMutation.mutate()}
                disabled={cleanExpiredMutation.isPending}
                className="whitespace-nowrap rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                {cleanExpiredMutation.isPending
                  ? "Cleaning..."
                  : "Clean Expired"}
              </button>
            </div>

            {cleanExpiredMutation.isSuccess && (
              <p className="mt-2 text-sm text-green-600">
                {(cleanExpiredMutation.data as { entries_removed: number })
                  .entries_removed > 0
                  ? `Removed ${(cleanExpiredMutation.data as { entries_removed: number }).entries_removed} expired entries.`
                  : "No expired entries to remove."}
              </p>
            )}

            {/* Danger zone */}
            <div className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4">
              <h3 className="text-sm font-semibold text-red-700">
                Danger Zone: Clear All Cache
              </h3>
              <p className="mt-1 text-xs text-red-600">
                This deletes ALL cached data from ALL sources. Only do this
                for data corruption or full reset. This cannot be undone.
              </p>
              <div className="mt-3 flex items-center gap-3">
                <input
                  type="text"
                  placeholder="Type CLEAR ALL CACHE to confirm"
                  value={clearAllConfirm}
                  onChange={(e) => setClearAllConfirm(e.target.value)}
                  className="flex-1 rounded-lg border border-red-200 px-3 py-2 text-sm"
                />
                <button
                  onClick={() => {
                    clearAllMutation.mutate();
                    setClearAllConfirm("");
                  }}
                  disabled={
                    clearAllConfirm !== "CLEAR ALL CACHE" ||
                    clearAllMutation.isPending
                  }
                  className="whitespace-nowrap rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
                >
                  {clearAllMutation.isPending ? "Clearing..." : "Clear All"}
                </button>
              </div>
              {clearAllMutation.isSuccess && (
                <p className="mt-2 text-sm text-red-700">
                  {(clearAllMutation.data as { entries_cleared: number }).entries_cleared} entries
                  cleared from all sources.
                </p>
              )}
            </div>
          </section>

          {/* Confirm refresh modal (shared with freshness tab) */}
          {confirmRefresh && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
              <div className="w-full max-w-md rounded-lg border border-gray-200 bg-white p-6 shadow-xl">
                <h3 className="text-lg font-semibold text-gray-900">
                  Clear {SOURCE_META[confirmRefresh]?.display ?? confirmRefresh}{" "}
                  Cache?
                </h3>
                <p className="mt-2 text-sm text-yellow-700 bg-yellow-50 rounded-lg p-3">
                  {SOURCE_META[confirmRefresh]?.warning}
                </p>
                <div className="mt-4 flex justify-end gap-3">
                  <button
                    onClick={() => setConfirmRefresh(null)}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={async () => {
                      await refreshMutation.mutateAsync(confirmRefresh);
                      setConfirmRefresh(null);
                    }}
                    disabled={refreshMutation.isPending}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    {refreshMutation.isPending ? "Clearing..." : "Yes, Clear"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/*  TAB 3: PREFERENCES                                             */}
      {/* ================================================================ */}
      {activeTab === "preferences" && (
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Saved Defaults
                </h2>
                <p className="text-sm text-gray-500">
                  Settings you save here become the defaults on hospital detail
                  and search pages.
                </p>
              </div>
              {settingsData?.updated && (
                <span className="text-xs text-gray-400">
                  Last updated: {formatDate(settingsData.updated)}
                </span>
              )}
            </div>

            {prefs && (
              <div className="space-y-6">
                {/* Search defaults */}
                <div>
                  <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                    Search Defaults
                  </h3>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">
                        Physician Search Scope
                      </label>
                      <select
                        value={prefs.search_scope}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            search_scope: e.target.value,
                          })
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      >
                        <option value="city">City (fastest)</option>
                        <option value="state">State</option>
                        <option value="all">All nearby cities</option>
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">
                        Default Sort
                      </label>
                      <select
                        value={prefs.sort_by}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            sort_by: e.target.value,
                          })
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      >
                        <option value="volume">Volume (highest first)</option>
                        <option value="name">Name (A-Z)</option>
                        <option value="rating">Rating</option>
                      </select>
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">
                        Minimum Volume
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={prefs.min_volume}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            min_volume: parseInt(e.target.value) || 0,
                          })
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>

                    <div>
                      <label className="mb-1 block text-sm font-medium text-gray-700">
                        Payment Company Filter
                      </label>
                      <input
                        type="text"
                        value={prefs.payment_company_filter}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            payment_company_filter: e.target.value,
                          })
                        }
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                      />
                    </div>
                  </div>
                </div>

                {/* Toggles */}
                <div>
                  <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                    Display Options
                  </h3>
                  <div className="space-y-3">
                    <label className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={prefs.show_payments}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            show_payments: e.target.checked,
                          })
                        }
                        className="h-4 w-4 rounded border-gray-300 text-brand-600"
                      />
                      <span className="text-sm text-gray-700">
                        Show Open Payments by default on hospital detail
                      </span>
                    </label>
                    <label className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={prefs.show_trends}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            show_trends: e.target.checked,
                          })
                        }
                        className="h-4 w-4 rounded border-gray-300 text-brand-600"
                      />
                      <span className="text-sm text-gray-700">
                        Show procedure volume trends by default
                      </span>
                    </label>
                    <label className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={prefs.show_auth_notice ?? true}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            show_auth_notice: e.target.checked,
                          })
                        }
                        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600"
                      />
                      <span className="text-sm text-gray-700">
                        Show the "Login is off" notice
                        <span className="block text-xs text-gray-500">
                          If login isn't needed for your setup (one person on their own
                          computer), untick this to hide the notice. Login itself is set by
                          AUTH_ENABLED in .env (Docker: docker/.env).
                        </span>
                      </span>
                    </label>
                    <label className="flex items-start gap-3">
                      <input
                        type="checkbox"
                        checked={prefs.show_data_flags ?? true}
                        onChange={(e) =>
                          setEditPrefs({
                            ...(prefs as UserPreferences),
                            show_data_flags: e.target.checked,
                          })
                        }
                        className="mt-0.5 h-4 w-4 rounded border-gray-300 text-brand-600"
                      />
                      <span className="text-sm text-gray-700">
                        Show data warnings
                        <span className="block text-xs text-gray-500">
                          Red/yellow flags on hospitals and physicians whose data is
                          missing, mismatched or possibly outdated.{" "}
                          <Link to="/help#about-the-data" className="text-brand-600 hover:underline">
                            What the flags mean
                          </Link>
                        </span>
                      </span>
                    </label>
                  </div>
                </div>

                {/* Default states */}
                <div>
                  <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                    Default States
                  </h3>
                  <p className="mb-2 text-xs text-gray-500">
                    Select states that will be pre-selected when searching.
                  </p>
                  <div className="grid grid-cols-6 gap-1 max-h-48 overflow-y-auto rounded-lg border border-gray-200 p-3">
                    {Object.entries(US_STATES).map(([code, name]) => (
                      <label
                        key={code}
                        className="flex items-center gap-1 text-xs"
                      >
                        <input
                          type="checkbox"
                          checked={
                            prefs.default_states?.includes(code) ?? false
                          }
                          onChange={(e) => {
                            const current = prefs.default_states ?? [];
                            setEditPrefs({
                              ...(prefs as UserPreferences),
                              default_states: e.target.checked
                                ? [...current, code]
                                : current.filter((s) => s !== code),
                            });
                          }}
                          className="h-3 w-3 rounded border-gray-300 text-brand-600"
                        />
                        <span className="text-gray-700" title={name}>
                          {code}
                        </span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Save / Reset buttons */}
                <div className="flex items-center gap-3 border-t border-gray-200 pt-4">
                  <button
                    onClick={() => {
                      if (editPrefs) {
                        updateSettingsMutation.mutate(editPrefs);
                        setEditPrefs(null);
                      }
                    }}
                    disabled={!editPrefs || updateSettingsMutation.isPending}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                  >
                    {updateSettingsMutation.isPending
                      ? "Saving..."
                      : "Save Preferences"}
                  </button>
                  <button
                    onClick={() => {
                      resetSettingsMutation.mutate();
                      setEditPrefs(null);
                    }}
                    disabled={resetSettingsMutation.isPending}
                    className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    Reset to Defaults
                  </button>
                  {editPrefs && (
                    <span className="text-xs text-yellow-600">
                      Unsaved changes
                    </span>
                  )}
                  {updateSettingsMutation.isSuccess && !editPrefs && (
                    <span className="text-xs text-green-600">Saved!</span>
                  )}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ================================================================ */}
      {/*  TAB 4: FEEDBACK                                                */}
      {/* ================================================================ */}
      {activeTab === "feedback" && (
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">
              Feature Requests & Feedback
            </h2>
            <p className="mb-4 text-sm text-gray-500">
              Let us know what data or features you'd like to see!
            </p>

            {fbSuccess ? (
              <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
                <p className="text-sm font-medium text-green-700">
                  Thank you! Your feedback has been submitted.
                </p>
                <button
                  onClick={() => {
                    setFbSuccess(false);
                    setFbContent("");
                  }}
                  className="mt-2 text-sm text-green-600 underline hover:text-green-800"
                >
                  Submit another
                </button>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Category
                    </label>
                    <select
                      value={fbCategory}
                      onChange={(e) => setFbCategory(e.target.value)}
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                    >
                      {FEEDBACK_CATEGORIES.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-gray-700">
                      Priority
                    </label>
                    <div className="flex gap-2 pt-1">
                      {PRIORITIES.map((p) => (
                        <label
                          key={p}
                          className={`cursor-pointer rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                            fbPriority === p
                              ? "border-brand-300 bg-brand-50 text-brand-700"
                              : "border-gray-200 text-gray-500 hover:border-gray-300"
                          }`}
                        >
                          <input
                            type="radio"
                            name="priority"
                            value={p}
                            checked={fbPriority === p}
                            onChange={() => setFbPriority(p)}
                            className="sr-only"
                          />
                          {p}
                        </label>
                      ))}
                    </div>
                  </div>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">
                    Your Feedback
                  </label>
                  <textarea
                    value={fbContent}
                    onChange={(e) => setFbContent(e.target.value)}
                    rows={4}
                    placeholder="Describe the data, feature, or improvement you'd like to see..."
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
                  />
                </div>

                <button
                  onClick={async () => {
                    await submitFeedbackMutation.mutateAsync({
                      category: fbCategory,
                      priority: fbPriority,
                      content: fbContent,
                    });
                    setFbSuccess(true);
                  }}
                  disabled={
                    !fbContent.trim() || submitFeedbackMutation.isPending
                  }
                  className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  {submitFeedbackMutation.isPending
                    ? "Submitting..."
                    : "Submit Feedback"}
                </button>
              </div>
            )}
          </section>

          {/* Recent submissions */}
          {feedbackData && feedbackData.feedback.length > 0 && (
            <section className="rounded-lg border border-gray-200 bg-white p-6">
              <h2 className="mb-3 text-lg font-semibold text-gray-900">
                Recent Submissions ({feedbackData.total})
              </h2>
              <div className="space-y-2">
                {feedbackData.feedback.slice(0, 10).map((entry) => (
                  <div
                    key={entry.id}
                    className="rounded-lg border border-gray-100 p-3"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <Badge
                        variant={
                          entry.priority === "Critical Need"
                            ? "red"
                            : entry.priority === "Would Be Useful"
                              ? "yellow"
                              : "gray"
                        }
                        size="sm"
                      >
                        {entry.priority}
                      </Badge>
                      <Badge variant="blue" size="sm">
                        {entry.category}
                      </Badge>
                      <span className="text-xs text-gray-400">
                        {formatDate(entry.timestamp)}
                      </span>
                    </div>
                    <p className="text-sm text-gray-700">{entry.content}</p>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
      )}

      {/* ================================================================ */}
      {/*  TAB 4b: DEVICE MARKET PROFILES                                 */}
      {/* ================================================================ */}
      {activeTab === "profiles" && <DeviceProfiles />}

      {/* ================================================================ */}
      {/*  TAB 5: DATA SOURCES REFERENCE                                  */}
      {/* ================================================================ */}
      {activeTab === "reference" && (
        <div className="space-y-6">
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-1 text-lg font-semibold text-gray-900">
              Data Sources Reference
            </h2>
            <p className="mb-4 text-sm text-gray-500">
              All sources are public APIs and do not require authentication.
            </p>

            <div className="overflow-hidden rounded-lg border border-gray-100">
              <table className="min-w-full divide-y divide-gray-100">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Source
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Type
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Update Frequency
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Cache TTL
                    </th>
                    <th className="px-4 py-2 text-left text-xs font-medium uppercase text-gray-500">
                      Description
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {sourceData &&
                    Object.entries(sourceData.sources).map(([name, source]) => {
                      const meta = SOURCE_META[name];
                      return (
                        <tr key={name}>
                          <td className="px-4 py-2 text-sm font-medium text-gray-900">
                            {meta?.display ?? name}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {source.provides?.join(", ") ?? "—"}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {meta?.updateFreq ?? "—"}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {meta?.ttlLabel ?? `${source.cache_ttl_hours}h`}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500">
                            {source.description ?? "—"}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          </section>

          {/* Cache tips */}
          <section className="rounded-lg border border-gray-200 bg-white p-6">
            <h2 className="mb-3 text-lg font-semibold text-gray-900">
              Cache Management Tips
            </h2>
            <div className="grid grid-cols-2 gap-6 text-sm text-gray-600">
              <div>
                <h3 className="mb-2 font-semibold text-gray-900">
                  DO Refresh:
                </h3>
                <ul className="list-disc space-y-1 pl-4">
                  <li>"Check for Updates" shows new data available</li>
                  <li>Data looks incorrect or outdated</li>
                  <li>Missing expected hospitals/physicians</li>
                  <li>After major data updates (e.g., TVT quarterly release)</li>
                </ul>
              </div>
              <div>
                <h3 className="mb-2 font-semibold text-gray-900">
                  DON'T Refresh:
                </h3>
                <ul className="list-disc space-y-1 pl-4">
                  <li>"Just to be safe" - cache auto-expires</li>
                  <li>Right after the tool loaded data</li>
                  <li>For CMS data (only updates once per year)</li>
                </ul>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
