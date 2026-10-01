import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getHealth } from "../../api/health";
import { useSettings } from "../../hooks/useSettings";

/**
 * Notice shown while login is off (AUTH_ENABLED=false). Running without
 * login is a normal choice for one person on their own computer, so users
 * can hide this in Settings > Preferences once they've decided.
 */
export default function DevModeBanner() {
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    retry: false,
    refetchInterval: 30000,
  });
  const { data: settings } = useSettings();

  if (!health || health.auth_enabled) return null;
  if (settings?.defaults?.show_auth_notice === false) return null;

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-1 bg-amber-100 px-4 py-2 text-sm text-amber-900">
      <svg className="h-4 w-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
        />
      </svg>
      <span>
        <strong>Login is off.</strong> Anyone who can open this address can use the app. That's fine on
        your own computer; to require login, set <code className="rounded bg-amber-200 px-1">AUTH_ENABLED=true</code>{" "}
        in <code className="rounded bg-amber-200 px-1">.env</code> (Docker: <code className="rounded bg-amber-200 px-1">docker/.env</code>).
      </span>
      <Link to="/settings?tab=preferences" className="font-medium underline hover:text-amber-700">
        Hide this notice
      </Link>
    </div>
  );
}
