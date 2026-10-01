import { useState } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { usePhysicianSearch } from "../hooks/usePhysicians";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Pagination from "../components/shared/Pagination";
import Badge from "../components/shared/Badge";
import { US_STATES } from "../constants/states";
import { useActiveProfile } from "../hooks/useActiveProfile";
import type { PhysicianSearchFilters } from "../types/physician";
import type { SavedSpecialty } from "../types/deviceProfile";
import { DataFlagIcon } from "../components/shared/DataFlags";

type SearchMode = "profile" | "custom";

export default function Physicians() {
  const queryClient = useQueryClient();
  const { procedureLabel, activeProfile } = useActiveProfile();
  const profileSpecialties = activeProfile?.filters.taxonomies ?? [];
  const savedSpecialties = activeProfile?.filters.saved_specialties ?? [];

  const [mode, setMode] = useState<SearchMode>("profile");
  const [filters, setFilters] = useState<PhysicianSearchFilters>({
    page: 1,
    per_page: 25,
  });
  const [selectedState, setSelectedState] = useState("");
  const [nameInput, setNameInput] = useState("");
  const [cityInput, setCityInput] = useState("");

  // Custom search state
  const [customSpecialty, setCustomSpecialty] = useState("");
  const [customHcpcsInput, setCustomHcpcsInput] = useState("");

  // Save specialty dialog
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [saveName, setSaveName] = useState("");
  const [saving, setSaving] = useState(false);

  const { data, isLoading, error, refetch } = usePhysicianSearch(filters);

  const runSearch = () => {
    const base: PhysicianSearchFilters = {
      ...filters,
      state: selectedState || undefined,
      name: nameInput || undefined,
      city: cityInput || undefined,
      page: 1,
    };

    if (mode === "custom") {
      base.specialty = customSpecialty || undefined;
      const codes = customHcpcsInput
        .split(/[,\s]+/)
        .map((c) => c.trim())
        .filter(Boolean);
      base.hcpcs_codes = codes.length > 0 ? codes : undefined;
    }

    setFilters(base);
  };

  const updateFilter = (key: keyof PhysicianSearchFilters, value: unknown) => {
    setFilters((f) => ({ ...f, [key]: value || undefined, page: 1 }));
  };

  const switchMode = (newMode: SearchMode) => {
    setMode(newMode);
    setFilters({ page: 1, per_page: 25 });
    setCustomSpecialty("");
    setCustomHcpcsInput("");
  };

  const applySavedSpecialty = (saved: SavedSpecialty) => {
    setMode("custom");
    setCustomSpecialty(saved.specialty);
    setCustomHcpcsInput(saved.hcpcs_codes.join(", "));
  };

  const handleSaveSpecialty = async () => {
    if (!saveName.trim() || !activeProfile) return;
    setSaving(true);
    try {
      const { addSavedSpecialty } = await import("../api/deviceProfiles");
      await addSavedSpecialty(activeProfile.id, {
        name: saveName.trim(),
        specialty: customSpecialty,
        hcpcs_codes: customHcpcsInput
          .split(/[,\s]+/)
          .map((c) => c.trim())
          .filter(Boolean),
      });
      // Refresh profiles so the saved specialty shows up
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
      setShowSaveDialog(false);
      setSaveName("");
    } catch (e) {
      console.error("Failed to save specialty:", e);
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteSpecialty = async (name: string) => {
    if (!activeProfile) return;
    try {
      const { deleteSavedSpecialty } = await import("../api/deviceProfiles");
      await deleteSavedSpecialty(activeProfile.id, name);
      queryClient.invalidateQueries({ queryKey: ["device-profiles"] });
    } catch (e) {
      console.error("Failed to delete specialty:", e);
    }
  };

  const searchLabel =
    mode === "custom" && customHcpcsInput ? "Custom" : procedureLabel;

  const canSave =
    mode === "custom" && (customSpecialty || customHcpcsInput) && activeProfile;

  return (
    <div className="mx-auto max-w-7xl">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Physician Search
          </h1>
          <p className="text-sm text-gray-500">
            Find physicians by state, specialty, and {searchLabel} volume
          </p>
        </div>
        {/* Mode toggle */}
        <div className="flex rounded-lg border border-gray-300 text-sm">
          <button
            onClick={() => switchMode("profile")}
            className={`rounded-l-lg px-4 py-1.5 font-medium ${
              mode === "profile"
                ? "bg-brand-600 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            Profile
          </button>
          <button
            onClick={() => switchMode("custom")}
            className={`rounded-r-lg px-4 py-1.5 font-medium ${
              mode === "custom"
                ? "bg-brand-600 text-white"
                : "bg-white text-gray-600 hover:bg-gray-50"
            }`}
          >
            Custom
          </button>
        </div>
      </div>

      {/* Saved Specialties — shown in both modes */}
      {savedSpecialties.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-gray-500">Saved:</span>
          {savedSpecialties.map((s) => (
            <span
              key={s.name}
              className="group inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700"
            >
              <button
                onClick={() => applySavedSpecialty(s)}
                className="hover:underline"
                title={`${s.specialty}${s.hcpcs_codes.length ? ` (${s.hcpcs_codes.join(", ")})` : ""}`}
              >
                {s.name}
              </button>
              <button
                onClick={() => handleDeleteSpecialty(s.name)}
                className="ml-0.5 hidden text-brand-400 hover:text-red-500 group-hover:inline"
                title="Remove saved specialty"
              >
                x
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          {/* State (required) */}
          <div className="w-48">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              State <span className="text-red-500">*</span>
            </label>
            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            >
              <option value="">Select a state...</option>
              {Object.entries(US_STATES).map(([code, name]) => (
                <option key={code} value={code}>
                  {code} - {name}
                </option>
              ))}
            </select>
          </div>

          {/* Specialty — dropdown for profile mode, text input for custom */}
          <div className="w-56">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Specialty
            </label>
            {mode === "profile" ? (
              <select
                value={filters.specialty || ""}
                onChange={(e) => updateFilter("specialty", e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              >
                <option value="">All Specialties</option>
                {profileSpecialties.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={customSpecialty}
                onChange={(e) => setCustomSpecialty(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                placeholder="e.g. Interventional Cardiology"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            )}
          </div>

          {/* HCPCS codes — custom mode only */}
          {mode === "custom" && (
            <div className="w-64">
              <label className="mb-1 block text-xs font-medium text-gray-500">
                HCPCS Codes{" "}
                <span className="text-gray-400">(comma-separated)</span>
              </label>
              <input
                type="text"
                value={customHcpcsInput}
                onChange={(e) => setCustomHcpcsInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && runSearch()}
                placeholder="e.g. 33361, 33362"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              />
            </div>
          )}

          {/* City */}
          <div className="w-40">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              City
            </label>
            <input
              type="text"
              value={cityInput}
              onChange={(e) => setCityInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="Any city"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Name */}
          <div className="w-48">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Name
            </label>
            <input
              type="text"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="Physician name..."
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
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
              min={0}
              placeholder="0"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>

          {/* Search button */}
          <button
            onClick={runSearch}
            disabled={!selectedState}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Search
          </button>

          {/* Save as Specialty button — custom mode with input */}
          {canSave && (
            <button
              onClick={() => {
                setSaveName(customSpecialty || customHcpcsInput);
                setShowSaveDialog(true);
              }}
              className="rounded-lg border border-brand-300 px-4 py-2 text-sm font-medium text-brand-600 hover:bg-brand-50"
            >
              Save Search
            </button>
          )}
        </div>

        {!selectedState && (
          <p className="mt-2 text-xs text-amber-600">
            Select a state to begin searching for physicians.
          </p>
        )}

        {mode === "custom" && (
          <p className="mt-2 text-xs text-gray-400">
            Custom search overrides your profile&apos;s procedure codes. Leave
            HCPCS blank to use your profile&apos;s defaults.
          </p>
        )}
      </div>

      {/* Save Specialty Dialog */}
      {showSaveDialog && (
        <div className="mb-4 rounded-lg border border-brand-200 bg-brand-50 p-4">
          <p className="mb-2 text-sm font-medium text-brand-800">
            Save this search as a specialty
          </p>
          <div className="flex items-center gap-3">
            <input
              type="text"
              value={saveName}
              onChange={(e) => setSaveName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSaveSpecialty()}
              placeholder="Name for this search..."
              className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
              autoFocus
            />
            <button
              onClick={handleSaveSpecialty}
              disabled={!saveName.trim() || saving}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
            <button
              onClick={() => setShowSaveDialog(false)}
              className="rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
          </div>
          <p className="mt-2 text-xs text-brand-600">
            Specialty: {customSpecialty || "(any)"} | Codes:{" "}
            {customHcpcsInput || "(profile defaults)"}
          </p>
        </div>
      )}

      {/* Results */}
      {isLoading && <LoadingSpinner message="Searching physicians..." />}

      {error && (
        <ErrorAlert
          message="Failed to search physicians."
          onRetry={() => refetch()}
        />
      )}

      {!filters.state && !isLoading && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">
            Select a state and click Search to find {searchLabel} physicians.
          </p>
          <p className="mt-2 text-sm text-gray-400">
            Data from CMS Utilization + NPPES + Open Payments + Clinical Trials
          </p>
        </div>
      )}

      {data && data.physicians.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">
            No physicians found matching your criteria.
          </p>
        </div>
      )}

      {data && data.physicians.length > 0 && (
        <>
          <p className="mb-3 text-sm text-gray-500">
            {data.total.toLocaleString()} physician(s) found
          </p>

          <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Physician
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Specialty
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                    Location
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                    Services
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                    Beneficiaries
                  </th>
                  <th className="px-4 py-3 text-center text-xs font-medium uppercase text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.physicians.map((p) => (
                  <tr key={p.npi} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link
                        to={`/physicians/${p.npi}`}
                        className="font-medium text-brand-700 hover:underline"
                      >
                        {p.full_name || p.provider_name || `NPI: ${p.npi}`}
                      </Link>
                      <DataFlagIcon flags={p.data_flags} />
                      {p.credential && (
                        <span className="ml-1 text-xs text-gray-400">
                          {p.credential}
                        </span>
                      )}
                      <p className="text-xs text-gray-400">NPI: {p.npi}</p>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {p.primary_specialty || "—"}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {p.practice_city || p.provider_city},{" "}
                      {p.practice_state || p.provider_state}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-medium">
                      {p.total_services > 0
                        ? p.total_services.toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-sm font-medium">
                      {p.total_beneficiaries > 0
                        ? p.total_beneficiaries.toLocaleString()
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-center">
                      {p.historical_only ? (
                        <Badge variant="yellow">Historical</Badge>
                      ) : p.has_volume ? (
                        <Badge variant="green">Active</Badge>
                      ) : (
                        <Badge variant="gray">Listed</Badge>
                      )}
                      {p.address_mismatch && (
                        <Badge variant="orange">Addr. Mismatch</Badge>
                      )}
                    </td>
                  </tr>
                ))}
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
