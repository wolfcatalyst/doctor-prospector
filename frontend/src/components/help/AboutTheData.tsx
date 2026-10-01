import { useDataVintage } from "../../hooks/useSources";

interface SourceRow {
  name: string;
  gives: string;
  coverage: string;
  updated: string;
  current?: string;
}

interface FlagRow {
  level: "red" | "yellow";
  label: string;
  meaning: string;
}

const FLAGS: FlagRow[] = [
  {
    level: "red",
    label: "Physician practice",
    meaning:
      "The \"site\" is a doctors' group office. CMS reports volume where physicians bill, so a busy practice looks like a hospital. Use the affiliated hospitals listed on its page.",
  },
  {
    level: "red",
    label: "Unidentified billing address",
    meaning:
      "Procedures were billed from this address but no hospital or practice is registered there in CMS data. The physicians and affiliations are real; the site name is not.",
  },
  {
    level: "red",
    label: "No CMS facility match",
    meaning:
      "A real hospital whose name differs between sources (e.g. a health-system name vs. the campus name), so beds, cath lab, CMS rating and Medicare volume couldn't be attached.",
  },
  {
    level: "yellow",
    label: "Matched by ZIP only",
    meaning:
      "The site was named after the only hospital in its ZIP code. Usually right, but confirm before relying on it.",
  },
  {
    level: "yellow",
    label: "Missing TAVR capability",
    meaning:
      "CMS lists no cath lab or open-heart surgery at a TAVR site. TAVR programs normally have both, so the CMS record may be outdated or this is a satellite campus.",
  },
  {
    level: "yellow",
    label: "No CMS rating",
    meaning: "Hospital Compare has no overall star rating (not rated, or too few reported measures).",
  },
  {
    level: "yellow",
    label: "May have moved",
    meaning:
      "The physician's current NPI address is in a different city than where they billed Medicare in the data year. Check before visiting.",
  },
  {
    level: "yellow",
    label: "Stale NPI record",
    meaning:
      "The physician hasn't updated their NPI Registry entry in 5+ years. Providers self-report it, so the address or specialty may be old.",
  },
  {
    level: "yellow",
    label: "No Medicare volume",
    meaning:
      "No Medicare claims for this profile's procedures. CMS hides counts under 11 per code, and private-insurance cases are never included, so this doesn't mean zero.",
  },
];

const ISSUES: { title: string; body: string }[] = [
  {
    title: "Volumes are not apples to apples",
    body: "TVT Registry counts every TAVR (all payers) at participating hospitals. CMS counts only traditional Medicare fee-for-service claims, and hides any count under 11. Expect CMS numbers to be lower, and treat them as a trend and ranking signal rather than a total.",
  },
  {
    title: "Everything public runs behind",
    body: "Registries and claims data need months of collection and auditing. TVT publishes once a year, about 15 months after its window closes; CMS claims arrive about 17 months after the year ends. For what's happening now, lean on NPI addresses, Open Payments and ClinicalTrials.gov.",
  },
  {
    title: "Billing addresses are not hospitals",
    body: "CMS records where a physician bills. For many specialists that's their group practice. Those sites are labeled Practice and linked to the hospitals their doctors are affiliated with.",
  },
  {
    title: "Names don't line up across sources",
    body: "The same hospital can be \"CHI Memorial\" in one source and \"Memorial Hospital\" in another. Matching uses the CMS facility number first, then name and location. A few dozen hospitals still don't match and are flagged.",
  },
  {
    title: "Common names cause false matches",
    body: "Trials and publications are matched by name. A trial must list one person with both the first and last name, and confidence goes up when they're listed at a site in the physician's city. \"Name only\" matches may be someone else.",
  },
  {
    title: "TVT only covers hospitals that opt in",
    body: "Public reporting is voluntary and requires 60+ TAVRs in the 3-year window, so smaller or newer programs won't have TVT data. CMS-discovered sites fill that gap.",
  },
];

export default function AboutTheData() {
  const { data: v } = useDataVintage();

  const sources: SourceRow[] = [
    {
      name: "STS/ACC TVT Registry",
      gives: "TAVR program volume, star rating, first TAVR date",
      coverage: "All payers; only hospitals that opt in (60+ TAVRs in 3 years)",
      updated: "Yearly, 3-year rolling window, ~15 months after it closes",
      current: v?.tvt_registry ?? undefined,
    },
    {
      name: "CMS Physician & Other Practitioners",
      gives: "Physician procedure counts by code",
      coverage: "Medicare fee-for-service only; counts under 11 hidden",
      updated: "Yearly, ~17 months after year end",
      current: v?.cms_utilization,
    },
    {
      name: "CMS Inpatient Hospitals (DRG)",
      gives: "Hospital procedure volume and average payment",
      coverage: "Medicare fee-for-service inpatient only; counts under 11 hidden",
      updated: "Yearly",
      current: v?.cms_drg,
    },
    {
      name: "CMS physician volume history",
      gives: "Year-by-year physician counts for profile codes",
      coverage: "Same as CMS Physician data",
      updated: "Yearly (loaded into the database)",
      current: v?.history_years ? `${v.history_years[0]}-${v.history_years[1]}` : undefined,
    },
    {
      name: "CMS Provider of Services",
      gives: "Beds, cath lab, open-heart surgery, ownership, teaching",
      coverage: "All Medicare-certified hospitals",
      updated: "Quarterly snapshot",
      current: v?.cms_pos,
    },
    {
      name: "CMS Hospital Compare",
      gives: "Overall hospital star rating (1-5)",
      coverage: "Hospitals with enough reported measures",
      updated: "Several times a year",
    },
    {
      name: "CMS Doctors & Clinicians",
      gives: "Group practice names and hospital affiliations",
      coverage: "Clinicians enrolled in Medicare",
      updated: "Monthly",
    },
    {
      name: "NPPES NPI Registry",
      gives: "Current practice address, phone, specialty, gender",
      coverage: "Every US provider; self-reported",
      updated: "Live (weekly at the source)",
    },
    {
      name: "CMS Open Payments",
      gives: "Industry payments by company and year",
      coverage: "Payments from device and drug manufacturers",
      updated: "Yearly, published June 30 for the prior year",
      current: v ? `through ${v.open_payments_latest_year}` : undefined,
    },
    {
      name: "ClinicalTrials.gov",
      gives: "Trials at a hospital; trials naming a physician",
      coverage: "Registered studies worldwide",
      updated: "Live",
    },
    {
      name: "PubMed / ORCID",
      gives: "Publications",
      coverage: "Name-matched, with confidence scores",
      updated: "Live",
    },
  ];

  return (
    <section id="about-the-data" className="mt-6 scroll-mt-6 rounded-lg border border-gray-200 bg-white p-5">
      <h2 className="mb-1 text-base font-semibold text-gray-900">About the Data</h2>
      <p className="mb-4 text-sm text-gray-600">
        Every number here comes from a public source with its own coverage, delay and
        quirks. Knowing them is the difference between a good lead and a wasted trip.
      </p>

      <h3 className="mb-2 text-sm font-semibold uppercase text-gray-500">Sources</h3>
      <div className="mb-6 overflow-x-auto">
        <table className="min-w-full text-left text-xs">
          <thead className="border-b border-gray-200 text-gray-500">
            <tr>
              <th className="py-2 pr-3 font-semibold">Source</th>
              <th className="py-2 pr-3 font-semibold">What it provides</th>
              <th className="py-2 pr-3 font-semibold">Coverage</th>
              <th className="py-2 pr-3 font-semibold">Updated</th>
              <th className="py-2 font-semibold">Loaded now</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 text-gray-700">
            {sources.map((s) => (
              <tr key={s.name}>
                <td className="py-2 pr-3 font-medium text-gray-900">{s.name}</td>
                <td className="py-2 pr-3">{s.gives}</td>
                <td className="py-2 pr-3">{s.coverage}</td>
                <td className="py-2 pr-3">{s.updated}</td>
                <td className="py-2 whitespace-nowrap">{s.current ?? "Live"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3 className="mb-2 text-sm font-semibold uppercase text-gray-500">Known issues</h3>
      <div className="mb-6 grid grid-cols-1 gap-3 md:grid-cols-2">
        {ISSUES.map((i) => (
          <div key={i.title} className="rounded-lg bg-gray-50 p-3">
            <div className="text-sm font-semibold text-gray-800">{i.title}</div>
            <p className="mt-1 text-xs text-gray-600">{i.body}</p>
          </div>
        ))}
      </div>

      <h3 className="mb-2 text-sm font-semibold uppercase text-gray-500">Data warnings</h3>
      <p className="mb-3 text-xs text-gray-600">
        Shown as a red or yellow <strong>!</strong> next to a name and listed on detail
        pages. Turn them off in Settings &gt; Preferences &gt; Show data warnings.
      </p>
      <ul className="space-y-2">
        {FLAGS.map((f) => (
          <li key={f.label} className="flex gap-3 text-sm">
            <span
              className={`mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${
                f.level === "red" ? "bg-red-500" : "bg-yellow-400"
              }`}
            >
              !
            </span>
            <span>
              <span className="font-medium text-gray-900">{f.label}.</span>{" "}
              <span className="text-gray-600">{f.meaning}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
