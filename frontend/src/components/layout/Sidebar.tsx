import { useQuery } from "@tanstack/react-query";
import { NavLink } from "react-router-dom";
import { getHealth } from "../../api/health";
import { useExportQueueStore } from "../../stores/exportQueueStore";
import { useActiveProfile } from "../../hooks/useActiveProfile";

const navItems = [
  { path: "/", label: "Dashboard", icon: "H" },
  { path: "/physicians", label: "Physicians", icon: "P" },
  { path: "/hospitals", label: "Hospitals", icon: "+" },
  { path: "/edwards", label: "Edwards", icon: "W", tavrOnly: true },
  { path: "/publications", label: "Publications", icon: "B" },
  { path: "/export", label: "Export Preview", icon: "E" },
  { path: "/settings", label: "Settings", icon: "S" },
];

export default function Sidebar() {
  const queueCount = useExportQueueStore((s) => s.items.length);
  const { showEdwards } = useActiveProfile();
  // Version comes from the API so it can't drift from the release
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: getHealth, retry: false });

  return (
    <aside className="flex w-64 flex-col border-r border-gray-200 bg-white">
      {/* Brand */}
      <div className="flex h-16 items-center gap-2 border-b border-gray-200 px-6">
        <span className="text-2xl">🩺</span>
        <h1 className="text-xl font-bold text-brand-700">Doctor Prospector</h1>
      </div>

      {/* Navigation */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems
          .filter((item) => !item.tavrOnly || showEdwards)
          .map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            <span className="flex h-6 w-6 items-center justify-center rounded bg-gray-100 text-xs font-bold">
              {item.icon}
            </span>
            {item.label}
            {item.path === "/export" && queueCount > 0 && (
              <span className="ml-auto rounded-full bg-brand-600 px-2 py-0.5 text-xs text-white">
                {queueCount}
              </span>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Help link pinned to bottom */}
      <div className="border-t border-gray-200 px-3 py-3">
        <NavLink
          to="/help"
          className={({ isActive }) =>
            `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              isActive
                ? "bg-brand-50 text-brand-700"
                : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
            }`
          }
        >
          <span className="flex h-6 w-6 items-center justify-center rounded bg-gray-100 text-xs font-bold">
            ?
          </span>
          Help
        </NavLink>
        <p className="mt-2 px-3 text-xs text-gray-400">Doctor Prospector{health?.version ? ` v${health.version}` : ""}</p>
      </div>
    </aside>
  );
}
