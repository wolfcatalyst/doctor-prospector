"""CMS Open Payments Data Source.

Loads physician payment data from CMS Open Payments database to identify:
- Industry relationships (device company payments)
- KOLs (high payment recipients)
- Physicians with payments from a profile's key companies (e.g. HeartFlow)
- Competitive intelligence (competitor relationships)

Data Source: https://openpaymentsdata.cms.gov/
API Docs: https://dev.socrata.com/foundry/openpaymentsdata.cms.gov/
"""

import asyncio
import logging
from typing import Any
from collections import defaultdict

import httpx

from .base import DataSourcePlugin

logger = logging.getLogger(__name__)

# Open Payments API endpoint (DKAN platform)
# Pattern: /api/1/datastore/query/{dataset_id}/0
OPEN_PAYMENTS_API_BASE = "https://openpaymentsdata.cms.gov/api/1/datastore/query"

# Dataset IDs for general payments by year (verified from CMS API).
# When a new year becomes available, add the dataset ID here:
#   1. Go to https://openpaymentsdata.cms.gov/
#   2. Navigate to General Payments for the new year
#   3. Click "API" and copy the dataset ID from the endpoint URL
#   4. Add a new entry: YYYY: "dataset-id-here"
GENERAL_PAYMENTS_DATASETS = {
    2025: "fb0b1734-1410-429d-92f6-3f4b35218e5e",
    2024: "e6b17c6a-2534-4207-a4a1-6746a14911ff",
    2023: "fb3a65aa-c901-4a38-a813-b04b00dfa2a9",
    2022: "df01c2f8-dc1f-4e79-96cb-8208beaf143c",
    2021: "0380bbeb-aea1-58b6-b708-829f92a48202",
    2020: "a08c4b30-5cf3-4948-ad40-36f404619019",
    2019: "4e54dd6c-30f8-4f86-86a7-3c109a89528e",
}

# Default device companies — used when no profile manufacturers are passed
DEFAULT_KEY_COMPANIES = {
    'heartflow': ['HeartFlow', 'HeartFlow Inc', 'HeartFlow, Inc.'],
    'edwards': ['Edwards Lifesciences', 'Edwards Lifesciences LLC', 'Edwards Lifesciences Corporation'],
    'medtronic': ['Medtronic', 'Medtronic Inc', 'Medtronic, Inc.', 'Medtronic USA'],
    'abbott': ['Abbott', 'Abbott Laboratories', 'Abbott Vascular', 'St. Jude Medical'],
    'boston_scientific': ['Boston Scientific', 'Boston Scientific Corporation'],
}

# Backward compatibility alias
KEY_COMPANIES = DEFAULT_KEY_COMPANIES


class OpenPaymentsSource(DataSourcePlugin):
    """Load physician payment data from CMS Open Payments."""

    @property
    def name(self) -> str:
        return "CMS Open Payments"

    @property
    def provides(self) -> list[str]:
        return ['payments', 'physicians']

    @property
    def cache_ttl_hours(self) -> int:
        # Cache for 7 days - payment data is updated quarterly
        return 24 * 7

    @property
    def cache_empty_results(self) -> bool:
        # Don't cache empty results — the API is slow and timeouts often
        # produce false empties. Let the next attempt try fresh.
        return False

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch payment data from Open Payments API.

        Args:
            **filters: Optional filters
                - npi: Filter by specific physician NPI (string or list)
                - company: Filter by company name (string or list)
                - min_year: Minimum year (default: earliest in GENERAL_PAYMENTS_DATASETS)
                - max_year: Maximum year (default: latest in GENERAL_PAYMENTS_DATASETS)
                - limit: Max records per year (default: 50000)

        Returns:
            List of physician payment records with aggregated totals
        """
        npi_filter = filters.get('npi')
        company_filter = filters.get('company')
        key_companies = filters.get('key_companies') or DEFAULT_KEY_COMPANIES
        min_year = filters.get('min_year', min(GENERAL_PAYMENTS_DATASETS.keys()))
        max_year = filters.get('max_year', max(GENERAL_PAYMENTS_DATASETS.keys()))
        # DKAN API has max limit of 500 per request
        limit_per_request = 500
        # Reasonable per-NPI limit (most physicians have <500 records/year)
        max_records_per_npi_year = filters.get('limit', 2000)

        logger.info(f"Fetching Open Payments data (NPI: {npi_filter}, Company: {company_filter})")

        # Determine which years to query
        years_to_query = [
            year for year in range(min_year, max_year + 1)
            if year in GENERAL_PAYMENTS_DATASETS
        ]

        if not years_to_query:
            logger.warning(f"No datasets available for years {min_year}-{max_year}")
            return []

        all_records = []

        # Prepare NPI list for filtering
        npis_to_query = []
        if npi_filter:
            if isinstance(npi_filter, list):
                npis_to_query = npi_filter[:20]  # Limit to 20 NPIs at a time
            else:
                npis_to_query = [npi_filter]

        # CMS Open Payments API can take 60-90s on cold queries;
        # use a generous read timeout so first-ever NPI lookups succeed
        op_timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

        if npis_to_query:
            # NPI-specific queries: fetch all years in parallel per NPI
            async def _fetch_npi_year(client, npi, year):
                """Fetch records for one NPI in one year."""
                dataset_id = GENERAL_PAYMENTS_DATASETS[year]
                url = f"{OPEN_PAYMENTS_API_BASE}/{dataset_id}/0"
                npi_records = []
                offset = 0

                while len(npi_records) < max_records_per_npi_year:
                    npi_params = {
                        'conditions[0][property]': 'covered_recipient_npi',
                        'conditions[0][value]': npi,
                        'conditions[0][operator]': '=',
                        'limit': limit_per_request,
                        'offset': offset,
                    }

                    try:
                        logger.debug(f"Fetching {year} data for NPI {npi} (offset {offset})")
                        response = await client.get(url, params=npi_params)
                        response.raise_for_status()
                        data = response.json()

                        if isinstance(data, dict) and 'results' in data:
                            records = data['results']
                        elif isinstance(data, list):
                            records = data
                        else:
                            records = []

                        if not records:
                            break

                        npi_records.extend(records)
                        offset += len(records)

                        if len(records) < limit_per_request:
                            break

                    except httpx.TimeoutException:
                        logger.warning(f"Timeout fetching NPI {npi} for {year} at offset {offset}")
                        break
                    except Exception as e:
                        logger.warning(f"Error fetching NPI {npi} for {year} at offset {offset}: {e}")
                        break

                logger.info(f"Found {len(npi_records)} records for NPI {npi} in {year}")
                return npi_records

            # Fetch all years concurrently for each NPI (3x speedup)
            async with httpx.AsyncClient(timeout=op_timeout) as client:
                for npi in npis_to_query:
                    tasks = [_fetch_npi_year(client, npi, year) for year in years_to_query]
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.warning(f"Error fetching NPI {npi} for {years_to_query[i]}: {result}")
                        else:
                            all_records.extend(result)

        else:
            # Non-NPI query (e.g. company search) — fetch years in parallel
            async def _fetch_company_year(client, year):
                """Fetch records for a company search in one year."""
                dataset_id = GENERAL_PAYMENTS_DATASETS[year]
                url = f"{OPEN_PAYMENTS_API_BASE}/{dataset_id}/0"
                params = {
                    'limit': limit_per_request,
                    'offset': 0,
                }
                if company_filter:
                    company_name = company_filter if isinstance(company_filter, str) else company_filter[0]
                    params['conditions[0][property]'] = 'applicable_manufacturer_or_applicable_gpo_making_payment_name'
                    params['conditions[0][value]'] = company_name
                    params['conditions[0][operator]'] = '='

                logger.info(f"Fetching {year} data from: {url}")
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if isinstance(data, dict) and 'results' in data:
                    records = data['results']
                elif isinstance(data, list):
                    records = data
                else:
                    logger.warning(f"Unexpected response format for {year}: {type(data)}")
                    records = []

                logger.info(f"Received {len(records)} payment records from {year}")
                return records

            async with httpx.AsyncClient(timeout=op_timeout) as client:
                tasks = [_fetch_company_year(client, year) for year in years_to_query]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        logger.error(f"Error fetching {years_to_query[i]} Open Payments data: {result}")
                    else:
                        all_records.extend(result)

        if not all_records:
            logger.warning("No payment records found across all years")
            return []

        logger.info(f"Total records fetched: {len(all_records)}")

        # Aggregate by physician NPI
        physician_payments = defaultdict(lambda: {
            'npi': None,
            'physician_name': None,
            'total_payments': 0.0,
            'payment_count': 0,
            'companies': defaultdict(float),  # company -> total amount
            'years': defaultdict(float),  # year -> total amount
            'payment_types': defaultdict(float),  # type -> total amount
            'records': []
        })

        for record in all_records:
            # Only process physician records (not entities)
            recipient_type = record.get('covered_recipient_type', '')
            if 'Physician' not in recipient_type:
                continue

            npi = record.get('covered_recipient_npi', '').strip()
            if not npi:
                continue

            # Client-side filtering: If we requested specific NPIs, only include those
            if npi_filter:
                npis_requested = npis_to_query if npis_to_query else []
                if npi not in npis_requested:
                    continue

            # Client-side filtering: If we requested specific company, check it
            if company_filter:
                company = record.get('applicable_manufacturer_or_applicable_gpo_making_payment_name', '')
                company_to_match = company_filter if isinstance(company_filter, str) else company_filter[0] if company_filter else None
                if company_to_match and company_to_match.lower() not in company.lower():
                    continue

            # Parse payment amount
            try:
                amount_str = record.get('total_amount_of_payment_usdollars', '0')
                amount = float(amount_str)
            except (ValueError, TypeError):
                amount = 0.0

            if amount <= 0:
                continue

            # Aggregate data
            physician_data = physician_payments[npi]
            physician_data['npi'] = npi

            # Store physician name (from first record)
            if not physician_data['physician_name']:
                first_name = record.get('covered_recipient_first_name', '')
                last_name = record.get('covered_recipient_last_name', '')
                physician_data['physician_name'] = f"{first_name} {last_name}".strip()

            # Add to totals
            physician_data['total_payments'] += amount
            physician_data['payment_count'] += 1

            # By company
            company = record.get('applicable_manufacturer_or_applicable_gpo_making_payment_name', 'Unknown')
            physician_data['companies'][company] += amount

            # By year
            try:
                year_str = record.get('program_year', '0')
                year = int(year_str)
                if year > 0:
                    physician_data['years'][year] += amount
            except (ValueError, TypeError):
                pass

            # By payment type
            payment_type = record.get('nature_of_payment_or_transfer_of_value', 'Other')
            physician_data['payment_types'][payment_type] += amount

            # Store raw record (limit to avoid memory issues)
            if len(physician_data['records']) < 100:
                physician_data['records'].append(record)

        # Convert to structured output
        results = []
        for npi, data in physician_payments.items():
            # Sort companies by payment amount
            top_companies = sorted(
                data['companies'].items(),
                key=lambda x: x[1],
                reverse=True
            )

            # Sort years for trend analysis
            years_sorted = sorted(data['years'].items())

            # Check if HeartFlow user (only if heartflow is in the profile's companies)
            is_heartflow_user = False
            if 'heartflow' in key_companies:
                is_heartflow_user = any(
                    any(hf_name.lower() in company.lower() for hf_name in key_companies['heartflow'])
                    for company in data['companies'].keys()
                )

            # Identify key company relationships
            key_relationships = {}
            for key, company_variants in key_companies.items():
                total = sum(
                    amount for company, amount in data['companies'].items()
                    if any(variant.lower() in company.lower() for variant in company_variants)
                )
                if total > 0:
                    key_relationships[key] = total

            result = {
                'npi': npi,
                'physician_name': data['physician_name'],
                'total_payments': data['total_payments'],
                'payment_count': data['payment_count'],
                'avg_payment': data['total_payments'] / data['payment_count'] if data['payment_count'] > 0 else 0,
                'companies': dict(data['companies']),
                'top_company': top_companies[0][0] if top_companies else None,
                'top_company_amount': top_companies[0][1] if top_companies else 0,
                'years': dict(data['years']),
                'payment_types': dict(data['payment_types']),
                'is_heartflow_user': is_heartflow_user,
                'key_relationships': key_relationships,  # {'heartflow': 50000, 'edwards': 25000, ...}
                'years_active': len(data['years']),
                'latest_year': max(data['years'].keys()) if data['years'] else None,
            }

            # Calculate payment trend (if multi-year data)
            if len(years_sorted) >= 2:
                first_year_amount = years_sorted[0][1]
                last_year_amount = years_sorted[-1][1]
                if first_year_amount > 0:
                    trend_pct = ((last_year_amount - first_year_amount) / first_year_amount) * 100
                    result['payment_trend_pct'] = trend_pct
                    result['payment_trend_indicator'] = '📈' if trend_pct > 20 else ('📉' if trend_pct < -20 else '➡️')
                else:
                    result['payment_trend_pct'] = 0
                    result['payment_trend_indicator'] = '➡️'
            else:
                result['payment_trend_pct'] = 0
                result['payment_trend_indicator'] = '➡️'

            results.append(result)

        # Sort by total payments (descending)
        results.sort(key=lambda x: x['total_payments'], reverse=True)

        logger.info(
            f"Aggregated {len(results)} physicians with payment data "
            f"(HeartFlow users: {sum(1 for r in results if r['is_heartflow_user'])})"
        )

        return results

    def get_cache_key(self, **filters) -> str:
        """Generate cache key."""
        npi = filters.get('npi', 'all')
        company = filters.get('company', 'all')
        if isinstance(company, str):
            company = company.lower().strip()
        # For list of NPIs, sort and join for deterministic key
        if isinstance(npi, list):
            npi = ','.join(sorted(npi))
        min_year = filters.get('min_year', min(GENERAL_PAYMENTS_DATASETS.keys()))
        max_year = filters.get('max_year', max(GENERAL_PAYMENTS_DATASETS.keys()))
        # Include profile companies hash if custom companies passed
        companies_tag = "default"
        if filters.get('key_companies'):
            import hashlib
            keys = sorted(filters['key_companies'].keys())
            companies_tag = hashlib.md5(",".join(keys).encode()).hexdigest()[:8]
        return f"{self.name}:npi={npi}:company={company}:mfg={companies_tag}:years={min_year}-{max_year}"


async def main():
    """Test the Open Payments data source."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    source = OpenPaymentsSource()

    console.print(f"\n[bold cyan]Testing CMS Open Payments Data Source[/bold cyan]\n")

    # Test 1: Fetch HeartFlow payments
    console.print("[bold]Test 1: HeartFlow Payments[/bold]")
    heartflow_data = await source.fetch(company='HeartFlow', min_year=2019, limit=1000)

    if heartflow_data:
        console.print(f"[green]✓ Found {len(heartflow_data)} physicians with HeartFlow payments[/green]\n")

        table = Table(title="Top 10 HeartFlow Payment Recipients")
        table.add_column("NPI", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Total", justify="right", style="yellow")
        table.add_column("Count", justify="right")
        table.add_column("Avg", justify="right")
        table.add_column("Years", justify="center")

        for p in heartflow_data[:10]:
            table.add_row(
                p['npi'],
                (p.get('physician_name') or 'Unknown')[:30],
                f"${p['total_payments']:,.0f}",
                str(p['payment_count']),
                f"${p['avg_payment']:,.0f}",
                f"{min(p['years'].keys())}-{max(p['years'].keys())}" if p['years'] else '-'
            )

        console.print(table)
    else:
        console.print("[yellow]No HeartFlow payment data found[/yellow]")

    # Test 2: Fetch by specific NPI (if available)
    if heartflow_data:
        test_npi = heartflow_data[0]['npi']
        console.print(f"\n[bold]Test 2: Payments for NPI {test_npi}[/bold]")

        npi_data = await source.fetch(npi=test_npi, min_year=2019)

        if npi_data:
            physician = npi_data[0]
            console.print(f"[green]✓ Found payment data for {physician['physician_name']}[/green]\n")

            # Company breakdown
            console.print("[bold]Top Companies:[/bold]")
            for company, amount in sorted(
                physician['companies'].items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]:
                console.print(f"  • {company}: ${amount:,.0f}")

            # Year breakdown
            console.print(f"\n[bold]Yearly Payments:[/bold]")
            for year, amount in sorted(physician['years'].items()):
                console.print(f"  • {year}: ${amount:,.0f}")

# Module-level instance for SourceRegistry auto-discovery
open_payments_source = OpenPaymentsSource()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
