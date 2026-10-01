import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import AboutTheData from "../components/help/AboutTheData";

interface HelpSection {
  id: string;
  title: string;
  icon: string;
  route: string;
  summary: string;
  details: string[];
  tips?: string[];
}

const sections: HelpSection[] = [
  {
    id: "dashboard",
    title: "Dashboard",
    icon: "H",
    route: "/",
    summary:
      "Your home screen showing a quick overview of loaded data, source health, and shortcuts to common actions.",
    details: [
      "Hospital count and data source summary are pulled live from the backend.",
      "Quick action cards link to the most common workflows: browse hospitals, search physicians, or check data freshness.",
      "The data sources grid shows all 9 sources with their current status.",
    ],
  },
  {
    id: "hospitals",
    title: "Hospitals",
    icon: "+",
    route: "/hospitals",
    summary:
      "Browse, search, and filter hospitals for the active device profile (TVT Registry for TAVR, CMS procedure data for every profile).",
    details: [
      "Filter by state, minimum procedure volume, CMS quality rating (and STS star rating for TAVR), and free-text search.",
      "Sort by volume, rating, name, or state.",
      "Click any hospital name to see its full detail page with physicians, trials, and facility data.",
      "The data source badge (TVT/CMS/Manual) shows where each hospital's data originated. An orange Practice badge marks a physician group office, not a hospital.",
      "A red or yellow ! next to a name is a data warning; hover it to read why (see About the Data below).",
      "Use the 'Add to Export' button to queue hospitals for batch export.",
    ],
    tips: [
      "Star ratings come from the STS/ACC TVT Registry (1-3 stars).",
      "Hospitals without a rating may be CMS-discovered facilities that aren't in the TVT program.",
    ],
  },
  {
    id: "hospital-detail",
    title: "Hospital Detail",
    icon: "+",
    route: "/hospitals",
    summary:
      "Deep dive into a specific hospital: volume metrics, facility capabilities, associated physicians, and clinical trials.",
    details: [
      "Top metric cards show procedure volume, CMS quality rating, bed count, and (for TAVR) STS rating and reporting period.",
      "Capabilities section shows cath lab, open heart surgery, teaching status, and ownership (from CMS Provider of Services data).",
      "Physicians table shows interventional cardiologists and CT surgeons at this hospital.",
      "Use the scope selector (City/State/All) to widen or narrow the physician search radius.",
      "Toggle 'Include Historical' to include CMS 10-year volume trend data for each physician.",
      "Clinical Trials section shows trials at this location matching the profile's trial search terms (ClinicalTrials.gov).",
      "Practice sites show the hospitals their physicians are affiliated with instead of facility details.",
    ],
    tips: [
      "City scope is fastest and usually sufficient. State scope searches all physicians in the state.",
      "Physicians are matched to hospitals using CMS billing address data and POS facility records.",
    ],
  },
  {
    id: "physicians",
    title: "Physicians",
    icon: "P",
    route: "/physicians",
    summary:
      "Search physicians who perform the active profile's procedures by state, specialty, city, name, or volume.",
    details: [
      "You must select at least one state to search (required by CMS data structure).",
      "Filter by specialty, city, physician name, and minimum procedure volume.",
      "Results show NPI, specialty, location, total services, beneficiaries, and TAVR status.",
      "Click any physician to see their full profile: payments, volume history, trials, and publications.",
    ],
    tips: [
      "The volume badge means CMS Medicare data confirms this physician performs the profile's procedures.",
      "The first search in a new state can take a few minutes (the NPI Registry allows ~100 lookups a minute); repeat searches are fast.",
      "Multi-state searches are supported but slower -- each state requires a separate API call.",
    ],
  },
  {
    id: "physician-detail",
    title: "Physician Detail",
    icon: "P",
    route: "/physicians",
    summary:
      "Full physician profile with Open Payments, procedure volume history, clinical trial participation, and publications.",
    details: [
      "Open Payments shows industry payments by company and year from CMS Open Payments data.",
      "Volume History shows yearly Medicare procedure counts for the profile's codes (see About the Data for the years loaded).",
      "Clinical Trials lists studies where this physician is named as an investigator. Confirmed = listed at a site in their city; Likely = in their state; Name only = same name elsewhere, possibly a different person.",
      "Publications shows PubMed matches with confidence scoring (high/medium/low based on name match quality).",
      "External links provide quick access to NPI Registry, Doximity, and Google search.",
    ],
  },
  {
    id: "publications",
    title: "Publications",
    icon: "B",
    route: "/publications",
    summary:
      "Search PubMed for physician publications using NPI lookup or name-based search.",
    details: [
      "Enter an NPI to auto-resolve the physician's name and search PubMed.",
      "Optionally refine with last name, first name, or institution.",
      "Results show title, authors, journal, year, and a link to PubMed.",
      "Confidence badges indicate match quality based on author name overlap.",
    ],
  },
  {
    id: "export",
    title: "Export Preview",
    icon: "E",
    route: "/export",
    summary:
      "Review and manage your export queue before generating reports.",
    details: [
      "Hospitals are added to the queue from the Hospitals page or Hospital Detail page.",
      "Review queued items, remove individual hospitals, or clear the entire queue.",
      "Export functionality (Excel, JSON) will generate reports with all associated physician and enrichment data.",
    ],
    tips: [
      "The queue badge on the sidebar shows how many hospitals are queued.",
      "Queue is stored locally in your browser and persists across page navigations.",
    ],
  },
  {
    id: "settings",
    title: "Settings",
    icon: "S",
    route: "/settings",
    summary:
      "Manage data freshness, cache, user preferences, and submit feedback. Five sub-tabs:",
    details: [
      "Data Freshness -- View source statuses, run upstream freshness probes to detect new data, and selectively refresh stale sources.",
      "Cache Management -- See cache metrics (total/valid/expired entries), per-source breakdown, clean expired entries, or clear all cache.",
      "Preferences -- Set search defaults (scope, sort, volume threshold), display toggles (payments, trends, data warnings), and default states for searching.",
      "Feedback -- Submit feature requests, bug reports, or ideas with category and priority tagging.",
      "Data Sources -- Reference table of all sources with descriptions, update frequency, and cache tips.",
    ],
    tips: [
      "'Check for Updates' runs lightweight probes that detect new data without downloading it.",
      "CMS data sources use UUIDs that change quarterly -- the probes will catch stale UUIDs.",
      "Preferences are saved to a JSON file and persist across sessions.",
    ],
  },
];

export default function Help() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const { hash } = useLocation();

  // Router navigation doesn't jump to #anchors on its own
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView({ behavior: "smooth" });
  }, [hash]);

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Help</h1>
        <p className="text-sm text-gray-500">
          How to use each feature in Doctor Prospector
        </p>
      </div>

      {/* Quick overview */}
      <section className="mb-6 rounded-lg border border-blue-200 bg-blue-50 p-5">
        <h2 className="mb-2 text-sm font-semibold text-blue-800">
          Quick Overview
        </h2>
        <p className="text-sm text-blue-700">
          Doctor Prospector aggregates public healthcare data (TVT Registry, CMS,
          NPPES, Open Payments, ClinicalTrials.gov, PubMed, and more) to build
          prospect lists for medical device sales, for whichever device profile
          is active. Browse
          hospitals, search physicians, view payment relationships, track volume
          trends, and export reports.
        </p>
      </section>

      {/* Section cards */}
      <div className="space-y-3">
        {sections.map((section) => {
          const isOpen = expanded === section.id;
          return (
            <div
              key={section.id}
              className="rounded-lg border border-gray-200 bg-white"
            >
              <button
                onClick={() => setExpanded(isOpen ? null : section.id)}
                className="flex w-full items-center gap-3 px-5 py-4 text-left"
              >
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-gray-100 text-sm font-bold text-gray-600">
                  {section.icon}
                </span>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-gray-900">
                    {section.title}
                  </div>
                  <div className="text-xs text-gray-500">
                    {section.summary}
                  </div>
                </div>
                <svg
                  className={`h-5 w-5 shrink-0 text-gray-400 transition-transform ${
                    isOpen ? "rotate-180" : ""
                  }`}
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 9l-7 7-7-7"
                  />
                </svg>
              </button>

              {isOpen && (
                <div className="border-t border-gray-100 px-5 pb-4 pt-3">
                  <ul className="space-y-2">
                    {section.details.map((detail, i) => (
                      <li
                        key={i}
                        className="flex gap-2 text-sm text-gray-600"
                      >
                        <span className="mt-1 text-brand-500">&#8226;</span>
                        <span>{detail}</span>
                      </li>
                    ))}
                  </ul>

                  {section.tips && section.tips.length > 0 && (
                    <div className="mt-3 rounded-lg bg-yellow-50 p-3">
                      <div className="mb-1 text-xs font-semibold text-yellow-700">
                        Tips
                      </div>
                      {section.tips.map((tip, i) => (
                        <p
                          key={i}
                          className="text-xs text-yellow-600"
                        >
                          {tip}
                        </p>
                      ))}
                    </div>
                  )}

                  <Link
                    to={section.route}
                    className="mt-3 inline-block text-sm font-medium text-brand-600 hover:text-brand-800"
                  >
                    Go to {section.title} &rarr;
                  </Link>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <AboutTheData />

      {/* Footer */}
      <div className="mt-6 text-center text-xs text-gray-400">
        All data comes from public sources and does not require
        authentication. See{" "}
        <Link
          to="/settings"
          className="text-brand-600 hover:text-brand-800"
        >
          Settings &gt; Data Sources
        </Link>{" "}
        for details on each source.
      </div>
    </div>
  );
}
