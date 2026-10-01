import { useState } from "react";
import { useEdwardsHospitals } from "../hooks/useEdwards";
import { refreshEdwardsData } from "../api/edwards";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Badge from "../components/shared/Badge";
import MetricCard from "../components/shared/MetricCard";
import type { EdwardsHospital, EdwardsTeamMember } from "../types/edwards";

const EDWARDS_SEARCH_URL =
  "https://treatheartvalvefailure.com/find-a-tavr-hospital";

export default function Edwards() {
  const [stateFilter, setStateFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const { data, isLoading, error, refetch } = useEdwardsHospitals({
    state: stateFilter || undefined,
    search: searchFilter || undefined,
  });

  const handleSearch = () => {
    setSearchFilter(searchInput);
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshEdwardsData();
      refetch();
    } finally {
      setRefreshing(false);
    }
  };

  if (error) return <ErrorAlert message="Failed to load Edwards data." />;

  const hospitals = data?.hospitals || [];

  // Compute unique states for filter dropdown
  const allStates = [
    ...new Set(hospitals.map((h) => h.state).filter(Boolean)),
  ].sort();

  // Compute summary stats
  const thvCount = hospitals.filter((h) => h.thv).length;
  const tmttCount = hospitals.filter((h) => h.tmtt).length;
  const teamCount = hospitals.reduce(
    (sum, h) => sum + h.team_members.length,
    0
  );

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Edwards TAVR Centers
          </h1>
          <p className="mt-1 text-gray-600">
            Edwards Lifesciences hospital directory |{" "}
            <a
              href={EDWARDS_SEARCH_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 hover:underline"
            >
              Search on Edwards
            </a>
          </p>
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          {refreshing ? "Refreshing..." : "Refresh Data"}
        </button>
      </div>

      {/* Metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard label="Total Centers" value={data?.total ?? "..."} />
        <MetricCard label="THV Centers" value={thvCount} />
        <MetricCard label="TMTT Centers" value={tmttCount} />
        <MetricCard label="Team Members" value={teamCount} />
      </div>

      {/* Filters */}
      <div className="mb-6 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            State
          </label>
          <select
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="">All states</option>
            {allStates.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1">
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Search
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              placeholder="Hospital name, city, or doctor..."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
            />
            <button
              onClick={handleSearch}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Search
            </button>
          </div>
        </div>
      </div>

      {isLoading && <LoadingSpinner message="Loading Edwards data..." />}

      {/* Results */}
      {!isLoading && hospitals.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
          No Edwards centers found matching your filters.
        </div>
      )}

      {!isLoading && hospitals.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-gray-500">
            {hospitals.length} center{hospitals.length !== 1 ? "s" : ""} found
          </p>
          {hospitals.map((h: EdwardsHospital) => (
            <div
              key={h.edwards_id}
              className="rounded-lg border border-gray-200 bg-white"
            >
              {/* Header row - always visible */}
              <button
                onClick={() =>
                  setExpandedId(
                    expandedId === h.edwards_id ? null : h.edwards_id ?? null
                  )
                }
                className="flex w-full items-center justify-between px-5 py-4 text-left hover:bg-gray-50"
              >
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-gray-900">
                    {h.name}
                  </h3>
                  <p className="text-xs text-gray-500">
                    {h.city}, {h.state}
                    {h.zip_code ? ` ${h.zip_code}` : ""}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  {h.thv && <Badge variant="green">THV</Badge>}
                  {h.tmtt && <Badge variant="blue">TMTT</Badge>}
                  {h.teer && <Badge variant="purple">TEER</Badge>}
                  {h.ttvr && <Badge variant="orange">TTVR</Badge>}
                  <span className="ml-2 text-xs text-gray-400">
                    {h.team_members.length} team
                  </span>
                  <span className="text-gray-400">
                    {expandedId === h.edwards_id ? "▲" : "▼"}
                  </span>
                </div>
              </button>

              {/* Expanded detail */}
              {expandedId === h.edwards_id && (
                <div className="border-t border-gray-100 px-5 py-4">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    {/* Contact */}
                    <div>
                      <h4 className="mb-2 text-xs font-semibold uppercase text-gray-500">
                        Contact
                      </h4>
                      <div className="space-y-1 text-sm">
                        {h.address && (
                          <p className="text-gray-600">
                            {h.address}, {h.city}, {h.state} {h.zip_code}
                          </p>
                        )}
                        {h.phone && (
                          <p className="text-gray-600">Phone: {h.phone}</p>
                        )}
                        {h.email && (
                          <p>
                            Email:{" "}
                            <a
                              href={`mailto:${h.email}`}
                              className="text-brand-600 hover:underline"
                            >
                              {h.email}
                            </a>
                          </p>
                        )}
                        {h.website && (
                          <p>
                            <a
                              href={h.website}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-brand-600 hover:underline"
                            >
                              Website
                            </a>
                          </p>
                        )}
                      </div>
                    </div>

                    {/* Team */}
                    <div>
                      <h4 className="mb-2 text-xs font-semibold uppercase text-gray-500">
                        Heart Team ({h.team_members.length})
                      </h4>
                      {h.team_members.length === 0 ? (
                        <p className="text-sm text-gray-500">
                          No team members listed
                        </p>
                      ) : (
                        <div className="space-y-1 text-sm">
                          {h.team_members.map(
                            (tm: EdwardsTeamMember, idx: number) => (
                              <div
                                key={idx}
                                className="flex justify-between text-sm"
                              >
                                <span className="font-medium text-gray-900">
                                  {tm.first_name} {tm.last_name}
                                  {tm.suffix ? `, ${tm.suffix}` : ""}
                                </span>
                                <span className="text-gray-500">{tm.role}</span>
                              </div>
                            )
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  {h.updated_at && (
                    <p className="mt-3 text-xs text-gray-400">
                      Last updated: {h.updated_at.slice(0, 10)}
                    </p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
