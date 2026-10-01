import { useState } from "react";
import { usePhysicianPublications } from "../hooks/usePhysicians";
import { useActiveProfile } from "../hooks/useActiveProfile";
import LoadingSpinner from "../components/shared/LoadingSpinner";
import ErrorAlert from "../components/shared/ErrorAlert";
import Badge from "../components/shared/Badge";

export default function Publications() {
  const { activeProfile, isTavrProfile } = useActiveProfile();
  // PubMed topic for the "Browse PubMed" link: the active profile's search terms
  const topicTerms = isTavrProfile ? ["TAVR"] : (activeProfile?.filters.trial_search_terms ?? []);
  const topic = topicTerms.length
    ? `(${topicTerms.map((t) => (t.includes(" ") ? `"${t}"` : t)).join(" OR ")})`
    : "";
  const [lastName, setLastName] = useState("");
  const [firstName, setFirstName] = useState("");
  const [institution, setInstitution] = useState("");
  const [searchNpi, setSearchNpi] = useState("");
  const [npiInput, setNpiInput] = useState("");

  const { data, isLoading, error } = usePhysicianPublications(
    searchNpi || undefined,
    searchNpi
      ? {
          last_name: lastName || undefined,
          first_name: firstName || undefined,
          institution: institution || undefined,
        }
      : undefined
  );

  const runSearch = () => {
    if (npiInput.trim()) {
      setSearchNpi(npiInput.trim());
    }
  };

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Publications</h1>
        <p className="text-sm text-gray-500">
          Search PubMed for physician research activity
        </p>
      </div>

      {/* Search */}
      <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-44">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              NPI <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={npiInput}
              onChange={(e) => setNpiInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="1234567890"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div className="w-40">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Last Name
            </label>
            <input
              type="text"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="Smith"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div className="w-40">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              First Name
            </label>
            <input
              type="text"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="John"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <div className="w-52">
            <label className="mb-1 block text-xs font-medium text-gray-500">
              Institution
            </label>
            <input
              type="text"
              value={institution}
              onChange={(e) => setInstitution(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runSearch()}
              placeholder="NYU Langone"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
            />
          </div>
          <button
            onClick={runSearch}
            disabled={!npiInput.trim()}
            className="rounded-lg bg-brand-600 px-6 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            Search
          </button>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <p className="text-xs text-gray-400">
            Enter an NPI to search PubMed. Name and institution help refine results.
          </p>
          {lastName && (
            <a
              href={`https://pubmed.ncbi.nlm.nih.gov/?term=${encodeURIComponent(
                firstName
                  ? `(${firstName.split(/\s+/).filter(Boolean).map((p) => `${lastName} ${p[0]}[Author]`).join(" OR ")}) ${topic ? `AND ${topic}` : ""}`
                  : `${lastName}[Author] ${topic ? `AND ${topic}` : ""}`
              )}`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-brand-600 hover:bg-brand-50"
            >
              Browse PubMed
            </a>
          )}
        </div>
      </div>

      {/* Results */}
      {isLoading && <LoadingSpinner message="Searching PubMed..." />}

      {error && <ErrorAlert message="Failed to search publications." />}

      {!searchNpi && !isLoading && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">
            Enter a physician NPI to search for publications.
          </p>
          <p className="mt-2 text-sm text-gray-400">
            Tip: You can also view publications on a physician's detail page.
          </p>
        </div>
      )}

      {data && data.publications.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 bg-white p-12 text-center">
          <p className="text-gray-500">No publications found.</p>
        </div>
      )}

      {data && data.publications.length > 0 && (
        <>
          <p className="mb-3 text-sm text-gray-500">
            {data.total} publication(s) found
          </p>
          <div className="space-y-3">
            {data.publications.map((pub) => (
              <div
                key={pub.pmid}
                className="rounded-lg border border-gray-200 bg-white p-4"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-gray-900">
                      {pub.title}
                    </h3>
                    <p className="mt-1 text-xs text-gray-500">
                      {pub.journal}
                      {pub.pub_date && ` (${pub.pub_date})`}
                    </p>
                    {pub.coauthor_summary && (
                      <p className="mt-1 text-xs text-gray-400">
                        {pub.coauthor_summary}
                      </p>
                    )}
                    {pub.categories.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {pub.categories.map((cat) => (
                          <Badge key={cat} variant="blue">
                            {cat}
                          </Badge>
                        ))}
                      </div>
                    )}
                    {pub.abstract && (
                      <p className="mt-2 line-clamp-3 text-xs text-gray-500">
                        {pub.abstract}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <Badge
                      variant={
                        pub.confidence_tier <= 2
                          ? "green"
                          : pub.confidence_tier === 3
                            ? "yellow"
                            : "gray"
                      }
                    >
                      {pub.confidence_badge}
                    </Badge>
                    {pub.match_method && (
                      <span className="text-[10px] text-gray-400">
                        {pub.match_method}
                      </span>
                    )}
                  </div>
                </div>
                {pub.pubmed_url && (
                  <a
                    href={pub.pubmed_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-2 inline-block text-xs text-brand-600 hover:underline"
                  >
                    View on PubMed
                  </a>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
