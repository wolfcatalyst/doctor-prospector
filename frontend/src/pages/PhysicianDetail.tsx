import { useState, useCallback } from "react";
import { useParams, Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  usePhysician,
  usePhysicianPayments,
  usePhysicianHistory,
  usePhysicianTrials,
  usePhysicianPublications,
} from "../hooks/usePhysicians";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Badge from "../components/shared/Badge";
import MetricCard from "../components/shared/MetricCard";
import { useActiveProfile } from "../hooks/useActiveProfile";
import type { PaymentSummary, HistorySummary } from "../types/physician";
import { DataFlagPanel } from "../components/shared/DataFlags";

function isPaymentSummary(data: unknown): data is PaymentSummary {
  return !!data && typeof data === "object" && "total_payments" in data;
}

function isHistorySummary(data: unknown): data is HistorySummary {
  return !!data && typeof data === "object" && "total_tavr_procedures" in data;
}

export default function PhysicianDetail() {
  const { procedureLabel } = useActiveProfile();
  const { npi } = useParams();
  const { data: physician, isLoading, error } = usePhysician(npi);
  const { data: paymentData, isLoading: paymentsLoading } =
    usePhysicianPayments(npi);
  const { data: historyData, isLoading: historyLoading } =
    usePhysicianHistory(npi);
  const { data: trialData, isLoading: trialsLoading } = usePhysicianTrials(
    npi,
    physician?.full_name || physician?.provider_name
  );
  const { data: pubData, isLoading: pubsLoading } = usePhysicianPublications(
    npi,
    physician
      ? {
          first_name: physician.first_name,
          last_name: physician.last_name,
        }
      : undefined
  );

  // Manual publication search state
  const queryClient = useQueryClient();
  const [pubSearchOpen, setPubSearchOpen] = useState(false);
  const [manualFirst, setManualFirst] = useState("");
  const [manualLast, setManualLast] = useState("");
  const [manualInst, setManualInst] = useState("");

  const handleManualPubSearch = useCallback(() => {
    if (!manualLast.trim()) return;
    // Custom search always skips backend cache for fresh PubMed results
    const params = {
      first_name: manualFirst || undefined,
      last_name: manualLast,
      institution: manualInst || undefined,
      skip_cache: true,
    };
    queryClient.setQueryData(
      ["physician-publications", npi, params],
      undefined
    );
    queryClient.fetchQuery({
      queryKey: ["physician-publications", npi, params],
      queryFn: async () => {
        const { getPhysicianPublications } = await import("../api/physicians");
        return getPhysicianPublications(npi!, params);
      },
    });
  }, [npi, manualFirst, manualLast, manualInst, queryClient]);

  // Force refresh: clear cache and re-search with current name
  const [refreshing, setRefreshing] = useState(false);
  const [refreshingTrials, setRefreshingTrials] = useState(false);
  const handleRefreshPubs = useCallback(async () => {
    if (!physician?.last_name) return;
    setRefreshing(true);
    const params = {
      first_name: physician.first_name,
      last_name: physician.last_name,
      skip_cache: true,
    };
    try {
      const { getPhysicianPublications } = await import("../api/physicians");
      const result = await getPhysicianPublications(npi!, params);
      // Update the main query cache with fresh results
      queryClient.setQueryData(
        ["physician-publications", npi, { first_name: physician.first_name, last_name: physician.last_name }],
        result
      );
    } finally {
      setRefreshing(false);
    }
  }, [npi, physician, queryClient]);

  // Build PubMed direct search URL using Author tag syntax
  // When custom search is open, use those fields instead of NPPES data
  const buildPubMedUrl = useCallback(() => {
    const ln = pubSearchOpen && manualLast ? manualLast : (physician?.last_name || "");
    const fn = pubSearchOpen && manualFirst ? manualFirst : (physician?.first_name || "");
    const parts = fn.split(/\s+/).filter(Boolean);
    const authorClauses = parts.length > 0
      ? parts.map((p) => `${ln} ${p[0]}[Author]`).join(" OR ")
      : `${ln}[Author]`;
    const query = `(${authorClauses}) AND ${procedureLabel}`;
    return `https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(query)}`;
  }, [physician, pubSearchOpen, manualFirst, manualLast, procedureLabel]);

  if (isLoading) return <LoadingSpinner message="Loading physician..." />;
  if (error) return <ErrorAlert message="Failed to load physician." />;
  if (!physician) return <ErrorAlert message="Physician not found." />;

  const p = physician;
  const payments = isPaymentSummary(paymentData) ? paymentData : null;
  const history = isHistorySummary(historyData) ? historyData : null;

  return (
    <div className="mx-auto max-w-7xl">
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm text-gray-500">
        <Link to="/physicians" className="hover:text-brand-600">
          Physicians
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">
          {p.full_name || p.provider_name || `NPI: ${npi}`}
        </span>
      </nav>

      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {p.full_name || p.provider_name || `NPI: ${npi}`}
          </h1>
          {p.credential && (
            <p className="text-sm text-gray-500">{p.credential}</p>
          )}
          <p className="mt-1 text-gray-600">
            {p.primary_specialty || "Specialty unknown"}
          </p>
          <p className="mt-1 text-xs text-gray-400">NPI: {npi}</p>
        </div>
        <div className="flex items-center gap-2">
          {p.has_volume ? (
            <Badge variant="green" size="md">
              Active {procedureLabel}
            </Badge>
          ) : p.historical_only ? (
            <Badge variant="yellow" size="md">
              Historical Only
            </Badge>
          ) : (
            <Badge variant="gray" size="md">
              No {procedureLabel} Volume
            </Badge>
          )}
        </div>
      </div>

      <DataFlagPanel flags={p.data_flags} />

      {/* Contact Info - front and center */}
      <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
        <div className="flex items-start justify-between gap-6">
          <div className="space-y-1.5">
            <h2 className="text-sm font-semibold text-gray-700">
              Contact Info
            </h2>
            {p.practice_address_line1 && (
              <p className="text-sm text-gray-600">
                {p.practice_address_line1}
                {p.practice_address_line2 && `, ${p.practice_address_line2}`}
              </p>
            )}
            <p className="text-sm text-gray-600">
              {p.practice_city || p.provider_city},{" "}
              {p.practice_state || p.provider_state}
              {p.practice_postal_code && ` ${p.practice_postal_code}`}
            </p>
            {p.practice_phone && (
              <p className="text-sm text-gray-600">
                Phone:{" "}
                <a
                  href={`tel:${p.practice_phone}`}
                  className="font-medium text-brand-600 hover:underline"
                >
                  {p.practice_phone}
                </a>
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {p.google_search_url && (
              <a
                href={p.google_search_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
              >
                Google Search
              </a>
            )}
            {p.npi_registry_url && (
              <a
                href={p.npi_registry_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
              >
                NPI Registry
              </a>
            )}
            {p.doximity_url && (
              <a
                href={p.doximity_url}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-lg border border-gray-200 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
              >
                Doximity
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard
          label={`Total ${procedureLabel} Services`}
          value={p.total_services}
        />
        <MetricCard
          label="Total Beneficiaries"
          value={p.total_beneficiaries}
        />
        <MetricCard
          label="Industry Payments"
          value={
            payments
              ? `$${payments.total_payments.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
              : paymentsLoading
                ? "..."
                : "N/A"
          }
          detail={payments ? `${payments.payment_count} payments` : undefined}
        />
        <MetricCard
          label="Historical Volume"
          value={
            history
              ? history.total_tavr_procedures
              : historyLoading
                ? "..."
                : "N/A"
          }
          detail={
            history
              ? `${history.years_active} years (${history.first_year}-${history.latest_year})`
              : undefined
          }
          trend={
            history
              ? history.trend_indicator === "↑"
                ? "up"
                : history.trend_indicator === "↓"
                  ? "down"
                  : "flat"
              : undefined
          }
        />
      </div>

      {/* Procedure Breakdown */}
      {p.procedure_breakdown && p.procedure_breakdown.length > 0 && (
        <div className="mb-6 rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold uppercase text-gray-500">
            Procedure Breakdown
          </h2>
          <div className="space-y-2">
            {p.procedure_breakdown.map((proc) => {
              const pct = p.total_services > 0
                ? Math.round((proc.services / p.total_services) * 100)
                : 0;
              return (
                <div key={proc.hcpcs_code} className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-gray-700">
                        {proc.description}
                        <span className="ml-1 text-xs text-gray-400">
                          ({proc.hcpcs_code})
                        </span>
                      </span>
                      <span className="font-medium text-gray-900">
                        {proc.services.toLocaleString()}
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 w-full rounded-full bg-gray-100">
                      <div
                        className="h-1.5 rounded-full bg-brand-500"
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Open Payments */}
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            Open Payments
          </h2>
          {paymentsLoading && <LoadingSpinner size="sm" />}
          {!paymentsLoading && !payments && (
            <p className="text-sm text-gray-500">No payment data available.</p>
          )}
          {payments && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">Total</span>
                  <p className="font-medium">
                    $
                    {payments.total_payments.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                    })}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Avg Payment</span>
                  <p className="font-medium">
                    $
                    {payments.avg_payment.toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                    })}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Top Company</span>
                  <p className="font-medium">{payments.top_company || "—"}</p>
                </div>
                <div>
                  <span className="text-gray-500">Years Active</span>
                  <p className="font-medium">{payments.years_active}</p>
                </div>
              </div>

              {Object.keys(payments.companies).length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">
                    By Company
                  </h4>
                  <div className="space-y-1">
                    {Object.entries(payments.companies)
                      .sort(([, a], [, b]) => b - a)
                      .slice(0, 5)
                      .map(([company, amount]) => (
                        <div
                          key={company}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="truncate text-gray-600">
                            {company}
                          </span>
                          <span className="ml-2 font-medium">
                            $
                            {amount.toLocaleString(undefined, {
                              minimumFractionDigits: 2,
                            })}
                          </span>
                        </div>
                      ))}
                  </div>
                </div>
              )}

              {Object.keys(payments.years).length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">
                    By Year
                  </h4>
                  <div className="flex gap-2">
                    {Object.entries(payments.years)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([year, amount]) => (
                        <div
                          key={year}
                          className="rounded bg-gray-50 px-3 py-1.5 text-center"
                        >
                          <p className="text-xs text-gray-500">{year}</p>
                          <p className="text-sm font-medium">
                            $
                            {amount.toLocaleString(undefined, {
                              maximumFractionDigits: 0,
                            })}
                          </p>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>

        {/* Historical Volume */}
        <section className="rounded-lg border border-gray-200 bg-white p-5">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            {procedureLabel} Volume History
          </h2>
          {historyLoading && <LoadingSpinner size="sm" />}
          {!historyLoading && !history && (
            <p className="text-sm text-gray-500">
              No historical data available.
            </p>
          )}
          {history && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-gray-500">Total Procedures</span>
                  <p className="font-medium">
                    {history.total_tavr_procedures.toLocaleString()}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Latest Volume</span>
                  <p className="font-medium">
                    {history.latest_volume.toLocaleString()}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Avg Annual Growth</span>
                  <p className="font-medium">
                    {history.avg_annual_growth_pct > 0 ? "+" : ""}
                    {history.avg_annual_growth_pct.toFixed(1)}%{" "}
                    {history.trend_indicator}
                  </p>
                </div>
                <div>
                  <span className="text-gray-500">Active Since</span>
                  <p className="font-medium">{history.first_year || "—"}</p>
                </div>
              </div>

              {Object.keys(history.volume_by_year).length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">
                    Annual Volume
                  </h4>
                  <div className="flex items-end gap-1">
                    {Object.entries(history.volume_by_year)
                      .sort(([a], [b]) => a.localeCompare(b))
                      .map(([year, vol]) => {
                        const maxVol = Math.max(
                          ...Object.values(history.volume_by_year)
                        );
                        const height = maxVol > 0 ? (vol / maxVol) * 80 : 0;
                        return (
                          <div
                            key={year}
                            className="flex flex-1 flex-col items-center"
                          >
                            <span className="mb-1 text-xs font-medium text-gray-700">
                              {vol}
                            </span>
                            <div
                              className="w-full rounded-t bg-brand-500"
                              style={{
                                height: `${Math.max(height, 4)}px`,
                              }}
                            />
                            <span className="mt-1 text-[10px] text-gray-400">
                              {year.slice(-2)}
                            </span>
                          </div>
                        );
                      })}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Clinical Trials */}
      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            Clinical Trials
            {trialData && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({trialData.total})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={async () => {
                setRefreshingTrials(true);
                queryClient.setQueryData(["physician-trials", npi], undefined);
                try {
                  const { getPhysicianTrials } = await import("../api/physicians");
                  const fresh = await getPhysicianTrials(
                    npi!,
                    p.full_name || p.provider_name,
                    true
                  );
                  queryClient.setQueryData(
                    ["physician-trials", npi],
                    fresh
                  );
                } finally {
                  setRefreshingTrials(false);
                }
              }}
              disabled={trialsLoading || refreshingTrials}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              title="Clear cache and search ClinicalTrials.gov again"
            >
              {refreshingTrials ? "Refreshing..." : "Refresh"}
            </button>
            <a
              href={`https://clinicaltrials.gov/search?term=${encodeURIComponent(
                (p.full_name || p.provider_name || "").split(",")[0].replace(/\b[A-Z]\.\s*/g, "").trim()
              )}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-brand-600 hover:bg-brand-50"
            >
              Search ClinicalTrials.gov
            </a>
          </div>
        </div>
        {(trialsLoading || refreshingTrials) && <LoadingSpinner size="sm" message="Searching ClinicalTrials.gov..." />}
        {!refreshingTrials && trialData && trialData.trials.length === 0 && (
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
            <p className="text-sm text-yellow-800">
              No clinical trials found.
            </p>
            <p className="mt-1 text-xs text-yellow-600">
              Try <strong>Refresh</strong> to re-check, or <strong>Search ClinicalTrials.gov</strong> to look manually.
            </p>
          </div>
        )}
        {trialData && trialData.trials.length > 0 && (
          <div className="space-y-3">
            {trialData.trials.map((t) => (
              <div
                key={t.nct_id}
                className="rounded border border-gray-100 p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">
                      {t.title}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {t.nct_id}
                      {t.lead_sponsor && ` | ${t.lead_sponsor}`}
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Badge
                      variant={
                        t.match_confidence === "confirmed"
                          ? "green"
                          : t.match_confidence === "likely"
                            ? "yellow"
                            : "orange"
                      }
                    >
                      {t.match_confidence === "confirmed"
                        ? "Confirmed"
                        : t.match_confidence === "likely"
                          ? "Likely"
                          : "Name Only"}
                    </Badge>
                    <Badge
                      variant={
                        t.overall_status === "RECRUITING"
                          ? "green"
                          : t.overall_status === "COMPLETED"
                            ? "blue"
                            : "gray"
                      }
                    >
                      {t.overall_status || "Unknown"}
                    </Badge>
                  </div>
                </div>
                {t.study_url && (
                  <a
                    href={t.study_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-xs text-brand-600 hover:underline"
                  >
                    View on ClinicalTrials.gov
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Publications */}
      <section className="mt-6 rounded-lg border border-gray-200 bg-white p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            Publications
            {pubData && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({pubData.total})
              </span>
            )}
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefreshPubs}
              disabled={refreshing || pubsLoading}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
              title="Clear cache and search PubMed again"
            >
              {refreshing ? "Refreshing..." : "Refresh"}
            </button>
            <button
              onClick={() => {
                if (!pubSearchOpen) {
                  setManualFirst(physician?.first_name || "");
                  setManualLast(physician?.last_name || "");
                  setManualInst("");
                }
                setPubSearchOpen(!pubSearchOpen);
              }}
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50"
            >
              {pubSearchOpen ? "Cancel" : "Custom Search"}
            </button>
            <a
              href={buildPubMedUrl()}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-brand-600 hover:bg-brand-50"
            >
              Browse PubMed
            </a>
          </div>
        </div>

        {/* Manual search form */}
        {pubSearchOpen && (
          <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
            <p className="mb-3 text-xs text-blue-700">
              Customize the publication search if the automatic results are
              missing publications (e.g. physician publishes under a different
              name).
            </p>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  First Name
                </label>
                <input
                  type="text"
                  value={manualFirst}
                  onChange={(e) => setManualFirst(e.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                  placeholder="e.g. Azeem"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Last Name *
                </label>
                <input
                  type="text"
                  value={manualLast}
                  onChange={(e) => setManualLast(e.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                  placeholder="e.g. Latib"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Institution
                </label>
                <input
                  type="text"
                  value={manualInst}
                  onChange={(e) => setManualInst(e.target.value)}
                  className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                  placeholder="e.g. Montefiore"
                />
              </div>
            </div>
            <button
              onClick={handleManualPubSearch}
              disabled={!manualLast.trim()}
              className="mt-3 rounded-lg bg-brand-600 px-4 py-1.5 text-xs font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              Search Publications
            </button>
          </div>
        )}

        {pubsLoading && <LoadingSpinner size="sm" />}
        {pubData && pubData.publications.length === 0 && (
          <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
            <p className="text-sm text-yellow-800">
              No publications found with the automatic search.
            </p>
            <p className="mt-1 text-xs text-yellow-600">
              Try the <strong>Custom Search</strong> button above to search with
              a different name variant, or <strong>Browse PubMed</strong> to
              search directly on PubMed.
            </p>
          </div>
        )}
        {pubData && pubData.publications.length > 0 && (
          <div className="space-y-3">
            {pubData.publications.map((pub) => (
              <div
                key={pub.pmid}
                className="rounded border border-gray-100 p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <p className="text-sm font-medium text-gray-900">
                      {pub.title}
                    </p>
                    <p className="mt-0.5 text-xs text-gray-500">
                      {pub.journal}
                      {pub.pub_date && ` (${pub.pub_date})`}
                    </p>
                    {pub.categories.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {pub.categories.map((cat) => (
                          <Badge key={cat} variant="blue">
                            {cat}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                  <Badge
                    variant={
                      pub.confidence_tier <= 2
                        ? "green"
                        : pub.confidence_tier === 3
                          ? "yellow"
                          : "gray"
                    }
                  >
                    {pub.confidence_badge}
                  </Badge>
                </div>
                {pub.pubmed_url && (
                  <a
                    href={pub.pubmed_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-xs text-brand-600 hover:underline"
                  >
                    View on PubMed
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

    </div>
  );
}
