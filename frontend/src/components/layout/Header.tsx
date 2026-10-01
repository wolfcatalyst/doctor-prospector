import { useQuery } from "@tanstack/react-query";
import { getHealth } from "../../api/health";
import { useDeviceProfiles } from "../../hooks/useDeviceProfiles";
import { useSettings } from "../../hooks/useSettings";
import ThemeSwitcher from "../shared/ThemeSwitcher";

export default function Header() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
    refetchInterval: 30000, // Check API health every 30s
  });

  const { data: profileData } = useDeviceProfiles();
  const { data: settings } = useSettings();
  const showAuthNotice = settings?.defaults?.show_auth_notice ?? true;
  const activeProfile = profileData?.profiles.find((p) => p.is_active);

  return (
    <header className="flex h-16 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div className="flex items-center gap-3">
        {health?.status === "ok" ? (
          <span className="flex items-center gap-1.5 text-sm text-green-600">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            API Connected
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-sm text-red-500">
            <span className="h-2 w-2 rounded-full bg-red-500" />
            API Disconnected
          </span>
        )}
        {health && !health.auth_enabled && showAuthNotice && (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            Login off
          </span>
        )}
        {activeProfile && (
          <span className="rounded bg-brand-100 px-2 py-0.5 text-xs font-medium text-brand-700">
            {activeProfile.filters.procedure_label || activeProfile.name}
          </span>
        )}
      </div>

      <div className="flex items-center gap-4">
        <ThemeSwitcher />
        <span className="text-sm text-gray-500">
          {health?.auth_enabled ? "User" : "Local user"}
        </span>
      </div>
    </header>
  );
}
