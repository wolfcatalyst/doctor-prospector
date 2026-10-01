"""PubMed E-utilities API source - physician publication data.

Searches PubMed for physician publications using a cascading strategy:
1. ORCID lookup (Tier 1 — Verified)
2. Name + Institution search (Tier 2/3 — High/Probable)
3. Name + TAVR keyword search (Tier 3 — Probable, catches prior institutions)

API: https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
Rate limit: 3 req/sec without API key, 10/sec with key
Cost: Free
"""

import asyncio
import logging
import re
import time
from typing import Any, Optional
from xml.etree import ElementTree

import requests

from .base import DataSourcePlugin, SourceFetchError
from .orcid import ORCIDSource

logger = logging.getLogger(__name__)

# TAVR-relevant categories and their keyword patterns (matched against title + abstract)
PUBLICATION_CATEGORIES = {
    "TAVR General": [
        "transcatheter aortic valve", "tavr", "tavi", "aortic stenosis",
        "valve replacement", "valve implantation",
    ],
    "Edwards / SAPIEN": [
        "sapien", "edwards lifesciences", "balloon-expandable",
    ],
    "Medtronic / Evolut": [
        "evolut", "corevalve", "medtronic", "self-expanding valve",
    ],
    "Abbott / Portico": [
        "portico", "abbott", "navitor",
    ],
    "AI / Robotics": [
        "artificial intelligence", "machine learning", "deep learning",
        "robotic", "computer-assisted", "automated",
    ],
    "Imaging / Planning": [
        "ct planning", "fluoroscopy", "valve sizing", "annular measurement",
        "computed tomography", "echocardiography",
    ],
    "Outcomes / Quality": [
        "mortality", "complication", "readmission", "paravalvular leak",
        "outcomes", "survival", "stroke",
    ],
}

# Cardiology-related journals (partial match) for confidence boosting
CARDIOLOGY_JOURNALS = [
    "jacc", "circulation", "heart", "cardiol", "cardiovasc",
    "interventional", "catheter", "structural", "valve",
    "annals of thoracic", "eur heart", "american heart",
]


def _build_author_queries(first_name: str | None, last_name: str) -> list[str]:
    """Build PubMed author query variants for compound first names.

    For "Mohamed Azeem" + "Latib" this produces:
      ["Latib M", "Latib A", "Latib MA"]
    so physicians who publish under a middle name are still found.
    """
    if not first_name:
        return [last_name]

    parts = first_name.strip().split()
    queries = set()

    # Each part's initial: "Latib M", "Latib A"
    for part in parts:
        if part:
            queries.add(f"{last_name} {part[0]}")

    # Combined initials: "Latib MA"
    if len(parts) > 1:
        initials = "".join(p[0] for p in parts if p)
        queries.add(f"{last_name} {initials}")

    return list(queries) if queries else [last_name]


def _author_or_clause(queries: list[str]) -> str:
    """Join author queries with OR for PubMed search."""
    if len(queries) == 1:
        return f'"{queries[0]}"[Author]'
    return "(" + " OR ".join(f'"{q}"[Author]' for q in queries) + ")"


def _categorize_publication(title: str, abstract: str) -> list[str]:
    """Tag a publication with relevant categories based on keyword matching."""
    text = f"{title} {abstract}".lower()
    categories = []
    for category, keywords in PUBLICATION_CATEGORIES.items():
        if any(kw in text for kw in keywords):
            categories.append(category)
    return categories if categories else ["Other"]


def _is_cardiology_journal(journal: str) -> bool:
    """Check if a journal name suggests cardiology/cardiovascular focus."""
    j_lower = journal.lower()
    return any(term in j_lower for term in CARDIOLOGY_JOURNALS)


class PubMedSource(DataSourcePlugin):
    """Search PubMed for physician publications with confidence-tiered matching.

    Example:
        source = PubMedSource()

        # Search by physician info (runs cascading strategy)
        result = await source.fetch_cached(
            first_name="Philippe",
            last_name="Généreux",
            institution="Morristown Medical Center",
        )
        for pub in result.data:
            print(f"[{pub['confidence_badge']}] {pub['title']} ({pub['journal']})")
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # Respect PubMed rate limit: 3 req/sec unauthenticated
    _last_request_time = 0.0
    _min_request_interval = 0.35  # ~3 req/sec
    _MAX_RETRIES = 3

    @property
    def name(self) -> str:
        return "pubmed"

    @property
    def provides(self) -> list[str]:
        return ["publications"]

    @property
    def cache_ttl_hours(self) -> int:
        return 720  # 30 days — publications don't change

    @property
    def rate_limit_per_minute(self) -> int:
        return 180  # 3 req/sec = 180/min (unauthenticated)

    def _rate_limit_wait(self):
        """Enforce minimum interval between requests."""
        now = time.time()
        elapsed = now - PubMedSource._last_request_time
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
        PubMedSource._last_request_time = time.time()

    def _request_with_backoff(self, url: str, params: dict, timeout: float = 15.0) -> requests.Response:
        """Make a request with rate limiting and exponential backoff on 429s."""
        for attempt in range(self._MAX_RETRIES):
            self._rate_limit_wait()
            response = requests.get(url, params=params, timeout=timeout)

            if response.status_code == 429:
                # Respect Retry-After header if present, otherwise exponential backoff
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    wait = int(retry_after)
                else:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    f"PubMed 429 rate limited (attempt {attempt + 1}/{self._MAX_RETRIES}), "
                    f"waiting {wait}s"
                )
                time.sleep(wait)
                continue

            response.raise_for_status()
            return response

        # Final attempt after all retries exhausted
        self._rate_limit_wait()
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response

    async def fetch(
        self,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        institution: Optional[str] = None,
        orcid_id: Optional[str] = None,
        npi: Optional[str] = None,
        search_terms: Optional[list[str]] = None,
        max_results: int = 50,
        **filters,
    ) -> list[dict[str, Any]]:
        """Search PubMed using cascading strategy with confidence tiers.

        Args:
            first_name: Physician first name
            last_name: Physician last name (required)
            institution: Hospital/institution name for affiliation matching
            orcid_id: If known, skips to Tier 1 verified search
            npi: NPI for record-keeping (stored in results, not used for search)
            search_terms: Profile-specific keywords for Tier 3 search.
                          Defaults to TAVR keywords if not provided.
            max_results: Max publications to return

        Returns:
            List of publication dicts with confidence tiers and categories
        """
        if not last_name:
            logger.warning("PubMed search requires at least a last_name")
            return []

        all_publications = {}  # pmid -> publication dict (deduplicates)

        # --- Tier 1: ORCID lookup (verified) ---
        if orcid_id:
            logger.info(f"PubMed Tier 1: Searching by ORCID {orcid_id}")
            pmids = await self._search_pmids(f"{orcid_id}[auid]", max_results)
            if pmids:
                pubs = await self._fetch_details(pmids)
                for pub in pubs:
                    pub["confidence_tier"] = 1
                    pub["confidence_badge"] = "\u2705 Verified"
                    pub["match_method"] = "orcid"
                    all_publications[pub["pmid"]] = pub
                logger.info(f"Tier 1: Found {len(pubs)} verified publications via ORCID")

        if not orcid_id:
            # Try ORCID lookup — for compound names, try each part individually
            # e.g. "Mohamed Azeem Latib" → try "Mohamed Azeem", "Mohamed", "Azeem"
            name_variants = [first_name] if first_name else [None]
            if first_name and " " in first_name.strip():
                for part in first_name.strip().split():
                    if part and part != first_name:
                        name_variants.append(part)

            found_orcid = None
            for fn_variant in name_variants:
                if found_orcid:
                    break
                try:
                    orcid_source = ORCIDSource()
                    orcid_result = await orcid_source.fetch_cached(
                        first_name=fn_variant,
                        last_name=last_name,
                        affiliation=institution,
                    )
                    if orcid_result.data:
                        found_orcid = orcid_result.data[0].get("orcid_id")
                except Exception as e:
                    logger.warning(f"ORCID lookup failed for {last_name} (variant={fn_variant}): {e}")

            if found_orcid:
                logger.info(f"Found ORCID {found_orcid} for {last_name} — using for verified search")
                pmids = await self._search_pmids(f"{found_orcid}[auid]", max_results)
                if pmids:
                    pubs = await self._fetch_details(pmids)
                    for pub in pubs:
                        pub["confidence_tier"] = 1
                        pub["confidence_badge"] = "\u2705 Verified"
                        pub["match_method"] = "orcid"
                        pub["orcid_id"] = found_orcid
                        all_publications[pub["pmid"]] = pub
                    logger.info(f"Tier 1: Found {len(pubs)} verified publications via ORCID")

        # --- Tier 2: Name + Institution ---
        if institution and last_name:
            author_queries = _build_author_queries(first_name, last_name)
            author_clause = _author_or_clause(author_queries)

            # Normalize institution name for PubMed affiliation search
            inst_short = re.sub(
                r"\b(medical center|hospital|health system|health)\b", "",
                institution, flags=re.IGNORECASE
            ).strip()

            query = f'{author_clause} AND "{inst_short}"[Affiliation]'
            logger.info(f"PubMed Tier 2: {query}")

            pmids = await self._search_pmids(query, max_results)
            if pmids:
                # Filter out already-found PMIDs
                new_pmids = [p for p in pmids if p not in all_publications]
                if new_pmids:
                    pubs = await self._fetch_details(new_pmids)
                    for pub in pubs:
                        # Tier 2 if in a cardiology journal, otherwise Tier 3
                        if _is_cardiology_journal(pub.get("journal", "")):
                            pub["confidence_tier"] = 2
                            pub["confidence_badge"] = "\U0001f7e2 High"
                            pub["match_method"] = "name+institution+specialty"
                        else:
                            pub["confidence_tier"] = 3
                            pub["confidence_badge"] = "\U0001f7e1 Probable"
                            pub["match_method"] = "name+institution"
                        all_publications[pub["pmid"]] = pub
                    logger.info(f"Tier 2/3: Found {len(pubs)} publications via name+institution")

        # --- Tier 3: Name + procedure keywords (catches prior institutions) ---
        # Use profile-specific search terms if provided, otherwise fall back to TAVR
        tier3_terms = search_terms or [
            "transcatheter aortic valve", "TAVR", "TAVI", "SAPIEN", "aortic stenosis",
        ]
        if last_name and tier3_terms:
            author_queries = _build_author_queries(first_name, last_name)
            author_clause = _author_or_clause(author_queries)
            terms_clause = " OR ".join(f'"{t}"' for t in tier3_terms)
            keyword_query = f'{author_clause} AND ({terms_clause})'
            logger.info(f"PubMed Tier 3: {keyword_query}")

            pmids = await self._search_pmids(keyword_query, max_results)
            if pmids:
                new_pmids = [p for p in pmids if p not in all_publications]
                if new_pmids:
                    pubs = await self._fetch_details(new_pmids)
                    for pub in pubs:
                        pub["confidence_tier"] = 3
                        pub["confidence_badge"] = "\U0001f7e1 Probable"
                        pub["match_method"] = "name+keywords"
                        all_publications[pub["pmid"]] = pub
                    logger.info(f"Tier 3: Found {len(pubs)} additional publications via name+keywords")

        # Sort by date (newest first) and add NPI
        result = sorted(all_publications.values(), key=lambda p: p.get("pub_date", ""), reverse=True)
        for pub in result:
            if npi:
                pub["npi"] = npi

        logger.info(f"PubMed total: {len(result)} publications for {last_name}")
        return result[:max_results]

    async def _search_pmids(self, query: str, max_results: int = 50) -> list[str]:
        """Search PubMed and return list of PMIDs."""
        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "date",
        }

        try:
            def _fetch():
                url = f"{self.BASE_URL}/esearch.fcgi"
                response = self._request_with_backoff(url, params)
                return response.json()

            data = await asyncio.to_thread(_fetch)

            result = data.get("esearchresult", {})
            pmids = result.get("idlist", [])
            count = result.get("count", "0")
            logger.info(f"PubMed search returned {count} total, fetching {len(pmids)}")
            return pmids

        except requests.RequestException as e:
            logger.error(f"PubMed search failed: {e}")
            return []

    async def _fetch_details(self, pmids: list[str]) -> list[dict[str, Any]]:
        """Fetch full article details for a list of PMIDs using efetch (XML)."""
        if not pmids:
            return []

        # Batch PMIDs (efetch supports comma-separated)
        pmid_str = ",".join(pmids)
        params = {
            "db": "pubmed",
            "id": pmid_str,
            "retmode": "xml",
        }

        try:
            def _fetch():
                url = f"{self.BASE_URL}/efetch.fcgi"
                response = self._request_with_backoff(url, params, timeout=30.0)
                return response.text

            xml_text = await asyncio.to_thread(_fetch)
            return self._parse_efetch_xml(xml_text)

        except requests.RequestException as e:
            logger.error(f"PubMed efetch failed: {e}")
            return []

    def _parse_efetch_xml(self, xml_text: str) -> list[dict[str, Any]]:
        """Parse PubMed efetch XML into publication dicts."""
        publications = []

        try:
            root = ElementTree.fromstring(xml_text)
        except ElementTree.ParseError as e:
            logger.error(f"Failed to parse PubMed XML: {e}")
            return []

        for article_el in root.findall(".//PubmedArticle"):
            pub = self._parse_article(article_el)
            if pub:
                publications.append(pub)

        return publications

    def _parse_article(self, article_el) -> Optional[dict[str, Any]]:
        """Parse a single PubmedArticle element."""
        medline = article_el.find("MedlineCitation")
        if medline is None:
            return None

        pmid_el = medline.find("PMID")
        pmid = pmid_el.text if pmid_el is not None else None
        if not pmid:
            return None

        article = medline.find("Article")
        if article is None:
            return None

        # Title
        title_el = article.find("ArticleTitle")
        title = title_el.text if title_el is not None else "Untitled"
        # Handle mixed content (title with inline tags)
        if title_el is not None:
            title = "".join(title_el.itertext())

        # Journal
        journal_el = article.find(".//Journal/Title")
        journal_abbrev_el = article.find(".//Journal/ISOAbbreviation")
        journal = ""
        if journal_el is not None and journal_el.text:
            journal = journal_el.text
        elif journal_abbrev_el is not None and journal_abbrev_el.text:
            journal = journal_abbrev_el.text

        # Publication date
        pub_date = self._parse_pub_date(article)

        # Abstract
        abstract_parts = []
        for abs_text in article.findall(".//Abstract/AbstractText"):
            label = abs_text.get("Label", "")
            text = "".join(abs_text.itertext())
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # Authors
        authors = []
        for author_el in article.findall(".//AuthorList/Author"):
            last = author_el.find("LastName")
            fore = author_el.find("ForeName")
            initials = author_el.find("Initials")

            author = {}
            if last is not None and last.text:
                author["last_name"] = last.text
            if fore is not None and fore.text:
                author["fore_name"] = fore.text
            elif initials is not None and initials.text:
                author["fore_name"] = initials.text

            # Affiliation
            aff_el = author_el.find(".//AffiliationInfo/Affiliation")
            if aff_el is not None and aff_el.text:
                author["affiliation"] = aff_el.text

            if author.get("last_name"):
                name_parts = []
                if author.get("fore_name"):
                    name_parts.append(author["fore_name"])
                name_parts.append(author["last_name"])
                author["name"] = " ".join(name_parts)
                authors.append(author)

        # MeSH terms
        mesh_terms = []
        for mesh_el in medline.findall(".//MeshHeadingList/MeshHeading/DescriptorName"):
            if mesh_el.text:
                mesh_terms.append(mesh_el.text)

        # Categorize
        categories = _categorize_publication(title, abstract)

        # Build co-author summary (first 5 + count)
        coauthor_names = [a["name"] for a in authors[:5]]
        coauthor_affiliations = set()
        for a in authors[:5]:
            aff = a.get("affiliation", "")
            if aff:
                # Extract just the institution name (before first comma usually)
                short_aff = aff.split(",")[0].strip()
                if len(short_aff) < 80:
                    coauthor_affiliations.add(short_aff)

        pub = {
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "pub_date": pub_date,
            "abstract": abstract[:500] if abstract else "",
            "authors": authors,
            "coauthor_summary": ", ".join(coauthor_names),
            "coauthor_affiliations": list(coauthor_affiliations),
            "mesh_terms": mesh_terms,
            "categories": categories,
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "author_count": len(authors),
            # Confidence fields set by caller
            "confidence_tier": 4,
            "confidence_badge": "\U0001f534 Unverified",
            "match_method": "unknown",
        }

        return pub

    def _parse_pub_date(self, article_el) -> str:
        """Extract publication date from article element."""
        # Try ArticleDate first (more precise)
        article_date = article_el.find(".//ArticleDate")
        if article_date is not None:
            year = article_date.findtext("Year", "")
            month = article_date.findtext("Month", "01")
            day = article_date.findtext("Day", "01")
            if year:
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Fall back to Journal PubDate
        pub_date = article_el.find(".//Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year = pub_date.findtext("Year", "")
            month = pub_date.findtext("Month", "")
            day = pub_date.findtext("Day", "")

            if year:
                # Month might be text like "Jan"
                month_map = {
                    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
                    "may": "05", "jun": "06", "jul": "07", "aug": "08",
                    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
                }
                if month.lower() in month_map:
                    month = month_map[month.lower()]
                elif not month:
                    month = "01"

                return f"{year}-{month.zfill(2)}"

            # MedlineDate fallback (e.g., "2023 Jan-Feb")
            medline_date = pub_date.findtext("MedlineDate", "")
            if medline_date:
                match = re.match(r"(\d{4})", medline_date)
                if match:
                    return match.group(1)

        return ""

    def get_cache_key(self, **filters) -> str:
        parts = []

        if filters.get("orcid_id"):
            parts.append(f"orcid={filters['orcid_id']}")
        if filters.get("last_name"):
            parts.append(f"ln={filters['last_name'].lower().strip()}")
        if filters.get("first_name"):
            parts.append(f"fn={filters['first_name'].lower().strip()}")
        if filters.get("institution"):
            inst = filters["institution"].lower().strip().replace(" ", "_")[:30]
            parts.append(f"inst={inst}")
        if filters.get("npi"):
            parts.append(f"npi={filters['npi']}")
        if filters.get("search_terms"):
            import hashlib
            terms = sorted(filters["search_terms"])
            terms_hash = hashlib.md5(",".join(terms).encode()).hexdigest()[:8]
            parts.append(f"terms={terms_hash}")

        return ":".join([self.name] + parts) if parts else f"{self.name}:all"

# Module-level instance for SourceRegistry auto-discovery
pubmed_source = PubMedSource()
