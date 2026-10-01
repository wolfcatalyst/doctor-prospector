import { useState, useEffect } from "react";
import {
  useDeviceProfiles,
  useCreateProfile,
  useUpdateProfile,
  useDeleteProfile,
  useActivateProfile,
} from "../hooks/useDeviceProfiles";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import type { DeviceProfile, DeviceMarketFilters } from "../types/deviceProfile";

const EMPTY_FILTERS: DeviceMarketFilters = {
  hcpcs_codes: [],
  manufacturers: {},
  taxonomies: [],
  trial_search_terms: [],
  trial_statuses: ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"],
  drg_codes: [],
  modules: [],
  saved_specialties: [],
  procedure_label: "",
};

/* ── Chip Input ── */
function ChipInput({
  label,
  values,
  onChange,
  placeholder,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
}) {
  const [input, setInput] = useState("");

  const add = () => {
    const trimmed = input.trim();
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed]);
    }
    setInput("");
  };

  const remove = (idx: number) => {
    onChange(values.filter((_, i) => i !== idx));
  };

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
      <div className="flex flex-wrap gap-1.5 mb-2">
        {values.map((v, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-0.5 text-sm text-brand-700"
          >
            {v}
            <button
              type="button"
              onClick={() => remove(i)}
              className="ml-0.5 text-brand-400 hover:text-brand-700"
            >
              x
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
          placeholder={placeholder}
          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
        <button
          type="button"
          onClick={add}
          className="rounded-md bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200"
        >
          Add
        </button>
      </div>
    </div>
  );
}

/* ── Manufacturer Editor ── */
function ManufacturerEditor({
  manufacturers,
  onChange,
}: {
  manufacturers: Record<string, string[]>;
  onChange: (m: Record<string, string[]>) => void;
}) {
  const [newSlug, setNewSlug] = useState("");
  const [newAlias, setNewAlias] = useState("");

  const addManufacturer = () => {
    const slug = newSlug.trim().toLowerCase().replace(/\s+/g, "_");
    if (slug && !(slug in manufacturers)) {
      onChange({ ...manufacturers, [slug]: [newSlug.trim()] });
      setNewSlug("");
    }
  };

  const removeManufacturer = (slug: string) => {
    const next = { ...manufacturers };
    delete next[slug];
    onChange(next);
  };

  const addAlias = (slug: string) => {
    const trimmed = newAlias.trim();
    if (trimmed && !manufacturers[slug].includes(trimmed)) {
      onChange({ ...manufacturers, [slug]: [...manufacturers[slug], trimmed] });
    }
    setNewAlias("");
  };

  const removeAlias = (slug: string, idx: number) => {
    onChange({
      ...manufacturers,
      [slug]: manufacturers[slug].filter((_, i) => i !== idx),
    });
  };

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        Manufacturers (name variants for Open Payments matching)
      </label>

      {Object.entries(manufacturers).map(([slug, aliases]) => (
        <div key={slug} className="mb-3 rounded-lg border border-gray-200 p-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-semibold text-gray-800">{slug}</span>
            <button
              type="button"
              onClick={() => removeManufacturer(slug)}
              className="text-xs text-red-500 hover:text-red-700"
            >
              Remove
            </button>
          </div>
          <div className="flex flex-wrap gap-1 mb-2">
            {aliases.map((a, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-700"
              >
                {a}
                <button
                  type="button"
                  onClick={() => removeAlias(slug, i)}
                  className="text-gray-400 hover:text-red-500"
                >
                  x
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Add alias..."
              value={newAlias}
              onChange={(e) => setNewAlias(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addAlias(slug);
                }
              }}
              className="flex-1 rounded border border-gray-300 px-2 py-1 text-xs focus:border-brand-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => addAlias(slug)}
              className="rounded bg-gray-100 px-2 py-1 text-xs text-gray-600 hover:bg-gray-200"
            >
              Add
            </button>
          </div>
        </div>
      ))}

      <div className="flex gap-2 mt-2">
        <input
          type="text"
          value={newSlug}
          onChange={(e) => setNewSlug(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              addManufacturer();
            }
          }}
          placeholder="New manufacturer name..."
          className="flex-1 rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:outline-none"
        />
        <button
          type="button"
          onClick={addManufacturer}
          className="rounded-md bg-brand-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-700"
        >
          Add Manufacturer
        </button>
      </div>
    </div>
  );
}

/* ── Module Selector ── */
function ModuleSelector({
  selected,
  onChange,
}: {
  selected: string[];
  onChange: (m: string[]) => void;
}) {
  const [modules, setModules] = useState<{ name: string; sources: string[] }[]>([]);

  // Fetch available modules from API
  useEffect(() => {
    fetch("/api/sources/modules")
      .then((r) => r.json())
      .then((d) => setModules(d.modules || []))
      .catch(() => {});
  }, []);

  if (modules.length === 0) return null;

  const toggle = (name: string) => {
    if (selected.includes(name)) {
      onChange(selected.filter((m) => m !== name));
    } else {
      onChange([...selected, name]);
    }
  };

  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-1">
        Source Modules (opt-in to specialty data sources)
      </label>
      <div className="space-y-2">
        {modules.map((mod) => (
          <label key={mod.name} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={selected.includes(mod.name)}
              onChange={() => toggle(mod.name)}
              className="rounded border-gray-300"
            />
            <span className="font-medium capitalize">{mod.name}</span>
            <span className="text-gray-400">
              ({mod.sources.join(", ")})
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

/* ── Profile Form ── */
function ProfileForm({
  initial,
  onSave,
  onCancel,
  saving,
}: {
  initial?: DeviceProfile;
  onSave: (name: string, description: string, filters: DeviceMarketFilters) => void;
  onCancel: () => void;
  saving: boolean;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [filters, setFilters] = useState<DeviceMarketFilters>(
    initial?.filters ?? { ...EMPTY_FILTERS }
  );

  const updateFilters = (patch: Partial<DeviceMarketFilters>) =>
    setFilters((f) => ({ ...f, ...patch }));

  return (
    <div className="space-y-5">
      {/* Name & Description */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Profile Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Hip Replacement"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Procedure Label</label>
          <input
            type="text"
            value={filters.procedure_label}
            onChange={(e) => updateFilters({ procedure_label: e.target.value })}
            placeholder="e.g. TAVR, TKA"
            className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />
        </div>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
        <input
          type="text"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Brief description of this device market"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
        />
      </div>

      {/* HCPCS Codes */}
      <ChipInput
        label="HCPCS/CPT Codes (procedure codes for CMS utilization search)"
        values={filters.hcpcs_codes}
        onChange={(v) => updateFilters({ hcpcs_codes: v })}
        placeholder="e.g. 33361"
      />

      {/* DRG Codes */}
      <ChipInput
        label="DRG Codes (hospital inpatient volume from CMS)"
        values={filters.drg_codes ?? []}
        onChange={(v) => updateFilters({ drg_codes: v })}
        placeholder="e.g. 266"
      />

      {/* Taxonomies */}
      <ChipInput
        label="Physician Taxonomies (NPPES specialty filter)"
        values={filters.taxonomies}
        onChange={(v) => updateFilters({ taxonomies: v })}
        placeholder="e.g. Interventional Cardiology"
      />

      {/* Trial Search Terms */}
      <ChipInput
        label="Clinical Trial Search Terms"
        values={filters.trial_search_terms}
        onChange={(v) => updateFilters({ trial_search_terms: v })}
        placeholder="e.g. transcatheter aortic valve"
      />

      {/* Trial Statuses */}
      <ChipInput
        label="Trial Statuses"
        values={filters.trial_statuses}
        onChange={(v) => updateFilters({ trial_statuses: v })}
        placeholder="e.g. RECRUITING"
      />

      {/* Manufacturers */}
      <ManufacturerEditor
        manufacturers={filters.manufacturers}
        onChange={(m) => updateFilters({ manufacturers: m })}
      />

      {/* Modules */}
      <ModuleSelector
        selected={filters.modules ?? []}
        onChange={(m) => updateFilters({ modules: m })}
      />

      {/* Actions */}
      <div className="flex gap-3 pt-2">
        <button
          type="button"
          disabled={!name.trim() || saving}
          onClick={() => onSave(name.trim(), description.trim(), filters)}
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {saving ? "Saving..." : initial ? "Update Profile" : "Create Profile"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ── Profile Card ── */
function ProfileCard({
  profile,
  onActivate,
  onEdit,
  onDelete,
  onClone,
  onHide,
  isHidden,
}: {
  profile: DeviceProfile;
  onActivate: () => void;
  onEdit: () => void;
  onDelete: () => void;
  onClone: () => void;
  onHide: () => void;
  isHidden: boolean;
}) {
  return (
    <div
      className={`rounded-lg border p-4 ${
        profile.is_active
          ? "border-brand-500 bg-brand-50 ring-1 ring-brand-200"
          : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-gray-900">{profile.name}</h3>
            {profile.is_preset && (
              <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-700">
                Preset
              </span>
            )}
            {profile.is_active && (
              <span className="rounded bg-green-100 px-1.5 py-0.5 text-xs font-medium text-green-700">
                Active
              </span>
            )}
          </div>
          {profile.description && (
            <p className="mt-0.5 text-xs text-gray-500">{profile.description}</p>
          )}
        </div>

        <div className="flex gap-1">
          {!profile.is_active && (
            <button
              onClick={onActivate}
              className="rounded px-2 py-1 text-xs font-medium text-brand-600 hover:bg-brand-50"
            >
              Activate
            </button>
          )}
          <button
            onClick={onClone}
            className="rounded px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100"
          >
            Clone
          </button>
          {!profile.is_preset && (
            <>
              <button
                onClick={onEdit}
                className="rounded px-2 py-1 text-xs font-medium text-gray-600 hover:bg-gray-100"
              >
                Edit
              </button>
              <button
                onClick={onDelete}
                className="rounded px-2 py-1 text-xs font-medium text-red-500 hover:bg-red-50"
              >
                Delete
              </button>
            </>
          )}
          {!profile.is_active && (
            <button
              onClick={onHide}
              title={isHidden ? "Unhide this profile" : "Hide this profile from the list"}
              className="rounded px-2 py-1 text-xs font-medium text-gray-400 hover:bg-gray-100 hover:text-gray-600"
            >
              {isHidden ? "Unhide" : "Hide"}
            </button>
          )}
        </div>
      </div>

      {/* Filter summary */}
      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-600">
        <div>
          <span className="font-medium">CPT Codes:</span>{" "}
          {profile.filters.hcpcs_codes.length > 0
            ? profile.filters.hcpcs_codes.join(", ")
            : "None"}
        </div>
        <div>
          <span className="font-medium">Procedure:</span>{" "}
          {profile.filters.procedure_label || "—"}
        </div>
        <div>
          <span className="font-medium">Manufacturers:</span>{" "}
          {Object.keys(profile.filters.manufacturers).length > 0
            ? Object.keys(profile.filters.manufacturers).join(", ")
            : "None"}
        </div>
        <div>
          <span className="font-medium">Taxonomies:</span>{" "}
          {profile.filters.taxonomies.length > 0
            ? profile.filters.taxonomies.length + " specialties"
            : "None"}
        </div>
        <div className="col-span-2">
          <span className="font-medium">Trial Terms:</span>{" "}
          {profile.filters.trial_search_terms.length > 0
            ? profile.filters.trial_search_terms.join(", ")
            : "None"}
        </div>
      </div>
    </div>
  );
}

/* ── Hidden profiles helpers (localStorage) ── */
const HIDDEN_KEY = "dg_hidden_profiles";

function getHiddenIds(): Set<string> {
  try {
    const raw = localStorage.getItem(HIDDEN_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function setHiddenIds(ids: Set<string>) {
  localStorage.setItem(HIDDEN_KEY, JSON.stringify([...ids]));
}

/* ── Main Component (embedded in Settings tab) ── */
export default function DeviceProfiles() {
  const { data, isLoading } = useDeviceProfiles();
  const createMutation = useCreateProfile();
  const updateMutation = useUpdateProfile();
  const deleteMutation = useDeleteProfile();
  const activateMutation = useActivateProfile();

  const [mode, setMode] = useState<"list" | "create" | "edit" | "clone">("list");
  const [editingProfile, setEditingProfile] = useState<DeviceProfile | null>(null);
  const [hiddenIds, setHiddenIdsState] = useState<Set<string>>(getHiddenIds);
  const [showHidden, setShowHidden] = useState(false);

  const hideProfile = (id: string) => {
    const next = new Set(hiddenIds);
    next.add(id);
    setHiddenIds(next);
    setHiddenIdsState(next);
  };

  const unhideProfile = (id: string) => {
    const next = new Set(hiddenIds);
    next.delete(id);
    setHiddenIds(next);
    setHiddenIdsState(next);
  };

  if (isLoading) return <LoadingSpinner />;

  const allProfiles = data?.profiles ?? [];
  const visibleProfiles = allProfiles.filter((p) => !hiddenIds.has(p.id));
  const hiddenProfiles = allProfiles.filter((p) => hiddenIds.has(p.id));
  const profiles = showHidden ? allProfiles : visibleProfiles;

  const handleCreate = (name: string, description: string, filters: DeviceMarketFilters) => {
    createMutation.mutate(
      { name, description, filters },
      { onSuccess: () => setMode("list") }
    );
  };

  const handleUpdate = (name: string, description: string, filters: DeviceMarketFilters) => {
    if (!editingProfile) return;
    updateMutation.mutate(
      { id: editingProfile.id, name, description, filters },
      { onSuccess: () => { setMode("list"); setEditingProfile(null); } }
    );
  };

  const handleClone = (profile: DeviceProfile) => {
    setEditingProfile({
      ...profile,
      id: "",
      name: `${profile.name} (Copy)`,
      is_preset: false,
      is_active: false,
    });
    setMode("clone");
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Device Market Profiles</h1>
          <p className="mt-1 text-sm text-gray-500">
            Configure which procedure codes, manufacturers, and specialties define your target
            device market. The active profile filters all physician and hospital data.
          </p>
        </div>
        {mode === "list" && (
          <button
            onClick={() => { setEditingProfile(null); setMode("create"); }}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            New Profile
          </button>
        )}
      </div>

      {mode === "list" ? (
        <div className="space-y-3">
          {profiles.length === 0 && (
            <p className="text-sm text-gray-500">
              No profiles yet. Create one or the TAVR preset will be used by default.
            </p>
          )}
          {profiles.map((p) => {
            const isHidden = hiddenIds.has(p.id);
            return (
              <div key={p.id} className={isHidden ? "opacity-50" : ""}>
                <ProfileCard
                  profile={p}
                  isHidden={isHidden}
                  onActivate={() => activateMutation.mutate(p.id)}
                  onEdit={() => {
                    setEditingProfile(p);
                    setMode("edit");
                  }}
                  onDelete={() => {
                    if (confirm(`Delete profile "${p.name}"?`)) {
                      deleteMutation.mutate(p.id);
                    }
                  }}
                  onClone={() => handleClone(p)}
                  onHide={() => (isHidden ? unhideProfile(p.id) : hideProfile(p.id))}
                />
              </div>
            );
          })}

          {/* Show/hide hidden profiles toggle */}
          {hiddenProfiles.length > 0 && (
            <button
              onClick={() => setShowHidden(!showHidden)}
              className="text-sm text-gray-500 hover:text-brand-600"
            >
              {showHidden
                ? "Hide hidden profiles"
                : `Show ${hiddenProfiles.length} hidden profile${hiddenProfiles.length === 1 ? "" : "s"}`}
            </button>
          )}
        </div>
      ) : mode === "create" || mode === "clone" ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            {mode === "clone" ? "Clone Profile" : "Create New Profile"}
          </h2>
          <ProfileForm
            initial={mode === "clone" ? (editingProfile ?? undefined) : undefined}
            onSave={handleCreate}
            onCancel={() => { setMode("list"); setEditingProfile(null); }}
            saving={createMutation.isPending}
          />
        </div>
      ) : (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">Edit Profile</h2>
          <ProfileForm
            initial={editingProfile ?? undefined}
            onSave={handleUpdate}
            onCancel={() => { setMode("list"); setEditingProfile(null); }}
            saving={updateMutation.isPending}
          />
        </div>
      )}
    </div>
  );
}
