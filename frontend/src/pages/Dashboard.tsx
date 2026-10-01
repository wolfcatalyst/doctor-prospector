import { Link } from "react-router-dom";
import { useHospitals } from "../hooks/useHospitals";
import { useSources } from "../hooks/useSources";
import { useActiveProfile } from "../hooks/useActiveProfile";
import MetricCard from "../components/shared/MetricCard";
import Badge from "../components/shared/Badge";

export default function Dashboard() {
  const { procedureLabel } = useActiveProfile();
  const { data: hospitalData } = useHospitals({ per_page: 1 });
  const { data: sourceData } = useSources();

  const sourceCount = sourceData
    ? Object.keys(sourceData.sources).length
    : "...";
  const enabledCount = sourceData
    ? Object.values(sourceData.sources).filter((s) => s.enabled).length
    : 0;

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Doctor Prospector</h1>
        <p className="mt-2 text-gray-600">
          Healthcare provider intelligence for medical device sales teams.
        </p>
      </div>

      {/* Stats */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Hospitals"
          value={hospitalData?.total ?? "..."}
          detail="CMS + Registry + Manual"
        />
        <MetricCard
          label="Data Sources"
          value={sourceCount}
          detail={`${enabledCount} enabled`}
        />
        <MetricCard
          label="States"
          value="50"
          detail="Full US coverage"
        />
        <MetricCard
          label="Export Formats"
          value="3"
          detail="Excel, CSV, JSON"
        />
      </div>

      {/* Quick actions */}
      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link
          to="/physicians"
          className="flex flex-col rounded-lg border border-gray-200 bg-white p-6 transition-shadow hover:shadow-md"
        >
          <h2 className="text-lg font-semibold text-gray-900">
            Physician Search
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Find {procedureLabel} physicians by state, specialty, and volume.
          </p>
        </Link>
        <Link
          to="/hospitals"
          className="flex flex-col rounded-lg border border-gray-200 bg-white p-6 transition-shadow hover:shadow-md"
        >
          <h2 className="text-lg font-semibold text-gray-900">
            Hospital Browser
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            Browse {procedureLabel} programs by volume, rating, and location.
          </p>
        </Link>
      </div>

      {/* Data Sources Summary */}
      {sourceData && (
        <div className="rounded-lg border border-gray-200 bg-white p-6">
          <h2 className="mb-4 text-lg font-semibold text-gray-900">
            Data Sources
          </h2>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(sourceData.sources).map(([name, source]) => (
              <div
                key={name}
                className="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-2"
              >
                <div>
                  <p className="text-sm font-medium text-gray-900">{name}</p>
                  <p className="text-xs text-gray-400">
                    {source.provides?.join(", ")}
                  </p>
                </div>
                <Badge variant={source.enabled ? "green" : "gray"}>
                  {source.enabled ? "Active" : "Off"}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
