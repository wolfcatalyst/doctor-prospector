import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import {
  useHospital,
  useHospitalPhysicians,
  useHospitalTrials,
} from "../hooks/useHospitals";
import { useEdwardsMatch } from "../hooks/useEdwards";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Badge from "../components/shared/Badge";
import StarRating from "../components/shared/StarRating";
import MetricCard from "../components/shared/MetricCard";
import { useActiveProfile } from "../hooks/useActiveProfile";
import type { EdwardsTeamMember } from "../types/edwards";
import { DataFlagIcon, DataFlagPanel, DataAgeNotice } from "../components/shared/DataFlags";

export default function HospitalDetail() {
  const { procedureLabel, showEdwards, isTavrProfile } = useActiveProfile();
  const { siteId } = useParams();
  const { data: hospital, isLoading, error } = useHospital(siteId);
  const [scope, setScope] = useState<"city" | "state" | "all">("city");
  const [includeHistorical, setIncludeHistorical] = useState(true);
  const {
    data: physData,
    isLoading: physLoading,
  } = useHospitalPhysicians(siteId, {
    search_scope: scope,
    include_historical: includeHistorical,
  });
  const { data: trialData, isLoading: trialsLoading } =
    useHospitalTrials(siteId);
  const { data: edwardsData, isLoading: edwardsLoading } = useEdwardsMatch(
    showEdwards ? hospital?.name : undefined,
    showEdwards ? hospital?.city : undefined,
    showEdwards ? hospital?.state : undefined
  );

  if (isLoading) return <LoadingSpinner message="Loading hospital..." />;
  if (error)
    return <ErrorAlert message="Failed to load hospital details." />;
  if (!hospital)
    return <ErrorAlert message="Hospital not found." />;

  const h = hospital;
  // Physician group billing address (CMS reports where doctors bill, which
  // for many operators is their practice office) -- no facility data exists
  const isPractice = h.site_type === "practice";
  const isUnidentified = !isPractice && h.name.startsWith("TAVR Site -");
  const notAFacility = isPractice || isUnidentified;

  return (
    <div className="mx-auto max-w-7xl">
      {/* Breadcrumb */}
      <nav className="mb-4 text-sm text-gray-500">
        <Link to="/hospitals" className="hover:text-brand-600">
          Hospitals
        </Link>
        <span className="mx-2">/</span>
        <span className="text-gray-900">{h.name}</span>
      </nav>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{h.name}</h1>
            <p className="mt-1 text-gray-600">
              {h.city}, {h.state}
              {h.zip_code && ` ${h.zip_code}`}
            </p>
            {h.address && (
              <p className="text-sm text-gray-400">{h.address}</p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                h.data_source === "TVT Registry"
                  ? "blue"
                  : h.data_source === "Manual"
                    ? "purple"
                    : "gray"
              }
              size="md"
            >
              {h.data_source}
            </Badge>
            {isPractice && (
              <Badge variant="orange" size="md">
                Physician Practice
              </Badge>
            )}
            {h.cms_overall_rating && <StarRating rating={h.cms_overall_rating} max={5} />}
            {isTavrProfile && h.star_rating && <StarRating rating={h.star_rating} />}
          </div>
        </div>
      </div>

      <DataFlagPanel flags={h.data_flags} />
      {isTavrProfile && h.reporting_period && (
        <DataAgeNotice>
          TVT Registry figures cover {h.reporting_period} and are updated once a year
          (about 15 months after each window closes).
        </DataAgeNotice>
      )}

      {/* Metrics */}
      <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricCard
          label={`Annual ${procedureLabel} Volume`}
          value={
            isTavrProfile
              ? (h.annual_tavr_volume ?? h.drg_volume ?? "N/A")
              : (h.drg_volume ?? "N/A")
          }
          detail={isTavrProfile ? (h.reporting_period || "Medicare DRG") : "Medicare DRG"}
        />
        {isTavrProfile && (
          <MetricCard
            label="Cumulative Volume"
            value={h.cumulative_volume ?? "N/A"}
          />
        )}
        <MetricCard
          label="CMS Quality Rating"
          value={h.cms_overall_rating ? `${h.cms_overall_rating}/5` : "N/A"}
          detail="Hospital Compare"
        />
        <MetricCard
          label="Physician Count"
          value={h.physician_count ?? physData?.total ?? "—"}
        />
        {!notAFacility && (
          <MetricCard
            label="Bed Count"
            value={h.bed_count ?? "N/A"}
            detail={h.teaching_status || undefined}
          />
        )}
      </div>

      {notAFacility && (
        <div className="mb-6 rounded-lg border border-orange-200 bg-orange-50 p-5">
          <h3 className="mb-1 text-sm font-semibold text-orange-900">
            {isPractice ? "Physician practice, not a hospital" : "Unidentified billing location"}
          </h3>
          <p className="mb-3 text-sm text-orange-800">
            CMS reports this volume at the address where these physicians bill
            {isPractice ? ", which is their group practice office" : ", and no hospital or practice is registered there"}.
            Procedures are performed at affiliated hospitals, so facility details
            (beds, cath lab, ratings) don't apply here.
          </p>
          {h.affiliated_hospitals && h.affiliated_hospitals.length > 0 && (
            <>
              <h4 className="mb-2 text-xs font-semibold uppercase text-orange-900">
                Affiliated hospitals
              </h4>
              <ul className="space-y-1 text-sm">
                {h.affiliated_hospitals.map((a) => (
                  <li key={a.ccn} className="flex justify-between gap-4">
                    <Link
                      to={`/hospitals/${a.ccn}`}
                      className="text-brand-700 hover:text-brand-800 hover:underline"
                    >
                      {a.name || `CCN ${a.ccn}`}
                      {a.city && <span className="text-gray-500"> — {a.city}</span>}
                    </Link>
                    <span className="whitespace-nowrap text-gray-600">
                      {a.physician_count} physician{a.physician_count === 1 ? "" : "s"}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {/* Hospital Details */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        {!notAFacility && (
        <div className="rounded-lg border border-gray-200 bg-white p-5">
          <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
            Capabilities
          </h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">Cath Lab</span>
              <span className="font-medium">
                {h.has_cath_lab == null
                  ? "Unknown"
                  : h.has_cath_lab
                    ? `Yes${h.cath_lab_rooms ? ` (${h.cath_lab_rooms} rooms)` : ""}`
                    : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Open Heart Surgery</span>
              <span className="font-medium">
                {h.has_open_heart_surgery == null
                  ? "Unknown"
                  : h.has_open_heart_surgery
                    ? "Yes"
                    : "No"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Ownership</span>
              <span className="font-medium">{h.ownership_type || "—"}</span>
            </div>
            {isTavrProfile && h.first_tavr_date && (
              <div className="flex justify-between">
                <span className="text-gray-600">First {procedureLabel}</span>
                <span className="font-medium">{h.first_tavr_date}</span>
              </div>
            )}
          </div>
        </div>
        )}

        {isTavrProfile && h.composite_score != null && (
          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
              TVT Registry Scores
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-600">Composite Score</span>
                <span className="font-medium">{h.composite_score}</span>
              </div>
              {h.eligible_procedures != null && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Eligible Procedures</span>
                  <span className="font-medium">{h.eligible_procedures}</span>
                </div>
              )}
              {h.rating_label && (
                <div className="flex justify-between">
                  <span className="text-gray-600">Rating</span>
                  <span className="font-medium">{h.rating_label}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {h.notes && (
          <div className="rounded-lg border border-gray-200 bg-white p-5">
            <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
              Notes
            </h3>
            <p className="text-sm text-gray-600">{h.notes}</p>
          </div>
        )}
      </div>

      {/* Physicians Section */}
      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            Physicians
            {physData && (
              <span className="ml-2 text-sm font-normal text-gray-500">
                ({physData.total} found)
              </span>
            )}
          </h2>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-sm text-gray-600">
              <input
                type="checkbox"
                checked={includeHistorical}
                onChange={(e) => setIncludeHistorical(e.target.checked)}
                className="rounded border-gray-300"
              />
              Include historical
            </label>
            <select
              value={scope}
              onChange={(e) =>
                setScope(e.target.value as "city" | "state" | "all")
              }
              className="rounded-lg border border-gray-300 px-2 py-1 text-sm"
            >
              <option value="city">Same city</option>
              <option value="state">Same state</option>
              <option value="all">All matches</option>
            </select>
          </div>
        </div>

        {physLoading && <LoadingSpinner size="sm" message="Finding physicians..." />}

        {physData && physData.physicians.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
            No physicians found. Try expanding the search scope.
          </div>
        )}

        {physData && physData.physicians.length > 0 && (
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
                  <th className="px-4 py-3 text-center text-xs font-medium uppercase text-gray-500">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {physData.physicians.map((p) => (
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
                    <td className="px-4 py-3 text-center">
                      {p.historical_only ? (
                        <Badge variant="yellow">Historical</Badge>
                      ) : p.has_volume ? (
                        <Badge variant="green">Active</Badge>
                      ) : (
                        <Badge variant="gray">No Volume</Badge>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Clinical Trials */}
      <div className="mb-6">
        <h2 className="mb-3 text-lg font-semibold text-gray-900">
          Clinical Trials
          {trialData && (
            <span className="ml-2 text-sm font-normal text-gray-500">
              ({trialData.total} found)
            </span>
          )}
        </h2>

        {trialsLoading && <LoadingSpinner size="sm" message="Searching trials..." />}

        {trialData && trialData.trials.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
            No clinical trials found for this hospital.
          </div>
        )}

        {trialData && trialData.trials.length > 0 && (
          <div className="space-y-3">
            {trialData.trials.map((t) => (
              <div
                key={t.nct_id}
                className="rounded-lg border border-gray-200 bg-white p-4"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-gray-900">
                      {t.title}
                    </h3>
                    <p className="mt-1 text-xs text-gray-500">
                      {t.nct_id}
                      {t.lead_sponsor && ` | ${t.lead_sponsor}`}
                      {t.enrollment > 0 && ` | ${t.enrollment} enrolled`}
                    </p>
                  </div>
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
                {t.brief_summary && (
                  <p className="mt-2 line-clamp-2 text-xs text-gray-500">
                    {t.brief_summary}
                  </p>
                )}
                {t.study_url && (
                  <a
                    href={t.study_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs text-brand-600 hover:underline"
                  >
                    View on ClinicalTrials.gov
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Edwards Section — only shown for TAVR-related profiles */}
      {showEdwards && (
      <div className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">
            Edwards Lifesciences
          </h2>
          <a
            href="https://treatheartvalvefailure.com/find-a-tavr-hospital"
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-brand-600 hover:underline"
          >
            Search on Edwards
          </a>
        </div>

        {edwardsLoading && (
          <LoadingSpinner size="sm" message="Searching Edwards directory..." />
        )}

        {edwardsData && !edwardsData.match && (
          <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8 text-center text-sm text-gray-500">
            Not found in Edwards TAVR center directory.{" "}
            <a
              href="https://treatheartvalvefailure.com/find-a-tavr-hospital"
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-600 hover:underline"
            >
              Search manually
            </a>
          </div>
        )}

        {edwardsData?.match && (
          <div className="space-y-4">
            {/* Product capabilities */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                <p className="text-xs font-medium uppercase text-gray-500">
                  THV
                </p>
                <p className="mt-1 text-lg font-semibold">
                  <Badge variant={edwardsData.match.thv ? "green" : "gray"}>
                    {edwardsData.match.thv ? "Yes" : "No"}
                  </Badge>
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                <p className="text-xs font-medium uppercase text-gray-500">
                  TMTT
                </p>
                <p className="mt-1 text-lg font-semibold">
                  <Badge variant={edwardsData.match.tmtt ? "green" : "gray"}>
                    {edwardsData.match.tmtt ? "Yes" : "No"}
                  </Badge>
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                <p className="text-xs font-medium uppercase text-gray-500">
                  TEER
                </p>
                <p className="mt-1 text-lg font-semibold">
                  <Badge variant={edwardsData.match.teer ? "green" : "gray"}>
                    {edwardsData.match.teer ? "Yes" : "No"}
                  </Badge>
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-white p-3 text-center">
                <p className="text-xs font-medium uppercase text-gray-500">
                  TTVR
                </p>
                <p className="mt-1 text-lg font-semibold">
                  <Badge variant={edwardsData.match.ttvr ? "green" : "gray"}>
                    {edwardsData.match.ttvr ? "Yes" : "No"}
                  </Badge>
                </p>
              </div>
            </div>

            {/* Contact & Team */}
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Contact info */}
              <div className="rounded-lg border border-gray-200 bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                  Contact
                </h3>
                <div className="space-y-2 text-sm">
                  {edwardsData.match.phone && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Phone</span>
                      <span className="font-medium">
                        {edwardsData.match.phone}
                      </span>
                    </div>
                  )}
                  {edwardsData.match.email && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Email</span>
                      <a
                        href={`mailto:${edwardsData.match.email}`}
                        className="font-medium text-brand-600 hover:underline"
                      >
                        {edwardsData.match.email}
                      </a>
                    </div>
                  )}
                  {edwardsData.match.website && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Website</span>
                      <a
                        href={edwardsData.match.website}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-medium text-brand-600 hover:underline"
                      >
                        Visit
                      </a>
                    </div>
                  )}
                  {edwardsData.match.address && (
                    <div className="flex justify-between">
                      <span className="text-gray-600">Address</span>
                      <span className="font-medium text-right">
                        {edwardsData.match.address}, {edwardsData.match.city},{" "}
                        {edwardsData.match.state}{" "}
                        {edwardsData.match.zip_code || ""}
                      </span>
                    </div>
                  )}
                </div>
              </div>

              {/* Team members */}
              <div className="rounded-lg border border-gray-200 bg-white p-5">
                <h3 className="mb-3 text-sm font-semibold uppercase text-gray-500">
                  Heart Team ({edwardsData.match.team_members.length})
                </h3>
                {edwardsData.match.team_members.length === 0 ? (
                  <p className="text-sm text-gray-500">
                    No team members listed
                  </p>
                ) : (
                  <div className="space-y-1.5 text-sm">
                    {edwardsData.match.team_members.map(
                      (tm: EdwardsTeamMember, idx: number) => (
                        <div key={idx} className="flex justify-between">
                          <span className="font-medium">
                            {tm.first_name} {tm.last_name}
                            {tm.suffix ? `, ${tm.suffix}` : ""}
                            {tm.primary ? " *" : ""}
                          </span>
                          <span className="text-gray-500">{tm.role}</span>
                        </div>
                      )
                    )}
                  </div>
                )}
              </div>
            </div>

            {edwardsData.match.updated_at && (
              <p className="text-xs text-gray-400">
                Edwards data updated:{" "}
                {edwardsData.match.updated_at.slice(0, 10)}
              </p>
            )}
          </div>
        )}
      </div>
      )}

      {/* External links */}
      <div className="flex gap-3">
        {isTavrProfile && h.tvt_registry_url && (
          <a
            href={h.tvt_registry_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            TVT Registry
          </a>
        )}
        {showEdwards && <a
          href="https://treatheartvalvefailure.com/find-a-tavr-hospital"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-lg border border-gray-200 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
        >
          Edwards Directory
        </a>}
      </div>
    </div>
  );
}
