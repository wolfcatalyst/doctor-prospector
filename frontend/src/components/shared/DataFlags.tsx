import { Link } from "react-router-dom";
import { useShowDataFlags } from "../../hooks/useShowDataFlags";
import type { DataFlag } from "../../types/dataFlags";

function worstLevel(flags: DataFlag[]): "red" | "yellow" | null {
  if (flags.some((f) => f.level === "red")) return "red";
  if (flags.length > 0) return "yellow";
  return null;
}

/** Small dot for table rows; hover shows every flag. */
export function DataFlagIcon({ flags }: { flags?: DataFlag[] }) {
  const show = useShowDataFlags();
  const level = worstLevel(flags ?? []);
  if (!show || !level) return null;
  return (
    <span
      title={(flags ?? []).map((f) => `${f.level === "red" ? "RED" : "YELLOW"}: ${f.message}`).join("\n\n")}
      aria-label={`${flags!.length} data warning${flags!.length === 1 ? "" : "s"}`}
      className={`ml-2 inline-flex h-4 w-4 shrink-0 cursor-help items-center justify-center rounded-full text-[10px] font-bold text-white align-middle ${
        level === "red" ? "bg-red-500" : "bg-yellow-400"
      }`}
    >
      !
    </span>
  );
}

/** Full list of flags for detail pages. */
export function DataFlagPanel({ flags }: { flags?: DataFlag[] }) {
  const show = useShowDataFlags();
  if (!show || !flags || flags.length === 0) return null;
  const level = worstLevel(flags);
  return (
    <div
      className={`mb-6 rounded-lg border p-4 ${
        level === "red" ? "border-red-200 bg-red-50" : "border-yellow-200 bg-yellow-50"
      }`}
    >
      <div className="mb-2 flex items-center justify-between">
        <h3 className={`text-sm font-semibold ${level === "red" ? "text-red-900" : "text-yellow-900"}`}>
          Data warnings
        </h3>
        <Link to="/help#about-the-data" className="text-xs text-gray-600 hover:underline">
          About the data
        </Link>
      </div>
      <ul className="space-y-1.5 text-sm">
        {flags.map((f) => (
          <li key={f.code} className="flex gap-2">
            <span
              className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                f.level === "red" ? "bg-red-500" : "bg-yellow-400"
              }`}
            />
            <span className="text-gray-800">{f.message}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One-line notice about how old a source's data is. */
export function DataAgeNotice({ children }: { children: React.ReactNode }) {
  const show = useShowDataFlags();
  if (!show) return null;
  return (
    <div className="mb-4 rounded-lg border border-gray-200 bg-gray-50 px-4 py-2 text-xs text-gray-600">
      {children}{" "}
      <Link to="/help#about-the-data" className="text-brand-600 hover:underline">
        About the data
      </Link>
    </div>
  );
}
