import { useState } from "react";
import { Link } from "react-router-dom";
import { useHospitals } from "../hooks/useHospitals";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Pagination from "../components/shared/Pagination";
import StarRating from "../components/shared/StarRating";
import Badge from "../components/shared/Badge";
import { US_STATES } from "../constants/states";
import { useActiveProfile } from "../hooks/useActiveProfile";
import type { HospitalFilters } from "../types/hospital";
import { DataFlagIcon, DataAgeNotice } from "../components/shared/DataFlags";
import { useDataVintage } from "../hooks/useSources";

/** Get the best available volume for display. */
function getVolume(h: { drg_volume?: number; annual_tavr_volume?: number }): number | null {
  return h.drg_volume ?? h.annual_tavr_volume ?? null;
}

export default function Hospitals() {
  const { procedureLabel, isTavrProfile } = useActiveProfile();
  const { data: vintage } = useDataVintage();
  const [filters, setFilters] = useState<HospitalFilters>({
    sort_by: "volume",
    sort_order: "desc",
    page: 1,
    per_page: 25,
  });
  const [searchInput, setSearchInput] = useState("");

  const { data, isLoading, error, refetch } = useHospitals(filters);

  const applySearch = () => {
    setFilters((f) => ({ ...f, search: searchInput || undefined, page: 1 }));
  };

  const updateFilter = (key: keyof HospitalFilters, value: unknown) => {
    setFilters((f) => ({ ...f, [key]: value || undefined, page: 1 }));
  };

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Hospitals</h1>
        <p className="text-sm text-gray-500">
          Browse {procedureLabel} programs across the US
          {data && (
            <span className="ml-2 font-medium text-gray-700">
              ({data.total.toLocaleString()} total)
            </span>
          )}
        </p>
      </div>

      {vintage && (
        <DataAgeNotice>
          {isTavrProfile && vintage.tvt_registry
            ? `TVT Registry volumes and star ratings cover ${vintage.tvt_registry} (updated yearly). CMS Medicare volumes are ${vintage.cms_drg}.`
            : `${procedureLabel} volumes are Medicare inpatient (DRG) counts for ${vintage.cms_drg}, the latest CMS release.`}
        </DataAgeNotice>
      )}

      {/* Filters */}
      <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* Search */}
          <div className="min-w-[200px] flex-1">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Search
            </label>
            <div className="flex gap-2">
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && applySearch()}
                placeholder="Hospital name or city..."
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              />
              <button
                onClick={applySearch}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
              >
                Search
              </button>
            </div>
          </div>

          {/* State filter */}
          <div className="w-40">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              State
            </label>
            <select
              value={filters.state || ""}
              onChange={(e) => updateFilter("state", e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">All States</option>
              {Object.entries(US_STATES).map(([code, name]) => (
                <option key={code} value={code}>
                  {code} - {name}
                </option>
              ))}
            </select>
          </div>

          {/* Min volume */}
          <div className="w-32">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Min Volume
            </label>
            <input
              type="number"
              value={filters.min_volume ?? ""}
              onChange={(e) =>
                updateFilter(
                  "min_volume",
                  e.target.value ? Number(e.target.value) : undefined
                )
              }
              placeholder="0"
              min={0}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* CMS Quality Rating (universal 1-5) */}
          <div className="w-32">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Min CMS Stars
            </label>
            <select
              value={filters.cms_rating ?? ""}
              onChange={(e) =>
                updateFilter(
                  "cms_rating",
                  e.target.value ? Number(e.target.value) : undefined
                )
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">Any</option>
              <option value="1">1+ Star</option>
              <option value="2">2+ Stars</option>
              <option value="3">3+ Stars</option>
              <option value="4">4+ Stars</option>
              <option value="5">5 Stars</option>
            </select>
          </div>

          {/* TVT Star rating — TAVR-only */}
          {isTavrProfile && (
          <div className="w-32">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              TVT Stars
            </label>
            <select
              value={filters.star_rating ?? ""}
              onChange={(e) =>
                updateFilter(
                  "star_rating",
                  e.target.value ? Number(e.target.value) : undefined
                )
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">Any</option>
              <option value="1">1+ Star</option>
              <option value="2">2+ Stars</option>
              <option value="3">3 Stars</option>
            </select>
          </div>
          )}

          {/* Sort */}
          <div className="w-36">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Sort By
            </label>
            <select
              value={filters.sort_by || "volume"}
              onChange={(e) =>
                updateFilter(
                  "sort_by",
                  e.target.value as HospitalFilters["sort_by"]
                )
              }
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="volume">Volume</option>
              <option value="rating">Rating</option>
              <option value="name">Name</option>
              <option value="state">State</option>
            </select>
          </div>

          {/* Sort order */}
          <button
            onClick={() =>
              updateFilter(
                "sort_order",
                filters.sort_order === "desc" ? "asc" : "desc"
              )
            }
            className="rounded-lg border border-gray-300 px-3 py-2 text-sm hover:bg-gray-50"
            title={filters.sort_order === "desc" ? "Descending" : "Ascending"}
          >
            {filters.sort_order === "desc" ? "▼" : "▲"}
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading && <LoadingSpinner message="Loading hospitals..." />}

      {error && (
        <ErrorAlert
          message="Failed to load hospitals. Is the API running?"
          onRetry={() => refetch()}
        />
      )}

      {data && data.hospitals.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">No hospitals found matching your filters.</p>
        </div>
      )}

      {data && data.hospitals.length > 0 && (
        <>
          {/* Table */}
          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Hospital
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Location
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                    Volume
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium uppercase text-gray-500">
                    CMS Rating
                  </th>
                  {isTavrProfile && (
                  <th className="px-4 py-3 text-center text-xs font-medium uppercase text-gray-500">
                    TVT
                  </th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Source
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.hospitals.map((h, i) => {
                  const id =
                    h.site_id ||
                    h.ccn ||
                    encodeURIComponent(
                      h.name
                        .toLowerCase()
                        .replace(/[^a-z0-9]+/g, "-")
                        .replace(/(^-|-$)/g, "")
                    );
                  const vol = getVolume(h);
                  return (
                    <tr
                      key={`${h.name}-${h.state}-${i}`}
                      className="hover:bg-gray-50"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to={`/hospitals/${id}`}
                          className="font-medium text-brand-700 hover:text-brand-800 hover:underline"
                        >
                          {h.name}
                        </Link>
                        <DataFlagIcon flags={h.data_flags} />
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600">
                        {h.city}, {h.state}
                      </td>
                      <td className="px-4 py-3 text-right text-sm font-medium text-gray-900">
                        {vol != null ? vol.toLocaleString() : "—"}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {h.cms_overall_rating ? (
                          <StarRating rating={h.cms_overall_rating} max={5} />
                        ) : (
                          <span className="text-sm text-gray-400">—</span>
                        )}
                      </td>
                      {isTavrProfile && (
                      <td className="px-4 py-3 text-center">
                        {h.star_rating ? (
                          <StarRating rating={h.star_rating} />
                        ) : (
                          <span className="text-sm text-gray-400">—</span>
                        )}
                      </td>
                      )}
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          <Badge
                            variant={
                              h.data_source === "TVT Registry"
                                ? "blue"
                                : h.data_source === "Manual"
                                  ? "purple"
                                  : "gray"
                            }
                          >
                            {h.data_source}
                          </Badge>
                          {h.site_type === "practice" && (
                            <Badge variant="orange">Practice</Badge>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <Pagination
            page={data.page}
            totalPages={data.total_pages}
            total={data.total}
            perPage={filters.per_page || 25}
            onPageChange={(p) => setFilters((f) => ({ ...f, page: p }))}
          />
        </>
      )}
    </div>
  );
}
