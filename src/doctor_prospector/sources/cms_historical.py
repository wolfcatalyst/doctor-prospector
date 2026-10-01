"""CMS Historical Physician Utilization Data Source.

Loads and parses CMS Medicare Physician and Other Supplier PUF files
to track physician TAVR volume trends over time.

Data Source: https://data.cms.gov/provider-summary-by-type-of-service/
File Format: Tab-delimited text files (Medicare_Provider_Util_Payment_PUF_CY{year}.txt)
"""

import csv
import json
import logging
import re
from pathlib import Path
from typing import Any
from collections import defaultdict

from .base import DataSourcePlugin

logger = logging.getLogger(__name__)

# TAVR HCPCS procedure codes
TAVR_HCPCS_CODES = {
    '33361': 'TAVR percutaneous femoral',
    '33362': 'TAVR open femoral',
    '33363': 'TAVR open axillary',
    '33364': 'TAVR open iliac',
    '33365': 'TAVR transaortic',
    '33366': 'TAVR transapical'
}


class CMSHistoricalSource(DataSourcePlugin):
    """Load historical physician TAVR volumes from CMS data files."""

    def __init__(self, data_dir: Path = None):
        """Initialize CMS historical data source.

        Args:
            data_dir: Directory containing CMS data files
                     Default: data/cms_historical/
        """
        if data_dir is None:
            from ..paths import DATA_DIR
            data_dir = DATA_DIR / "cms_historical"

        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "CMS Historical TAVR Utilization"

    @property
    def provides(self) -> list[str]:
        return ['physicians', 'historical_trends']

    @property
    def cache_ttl_hours(self) -> int:
        # Cache for 30 days - historical data doesn't change
        return 24 * 30

    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Load and aggregate TAVR procedures from CMS files.

        Args:
            **filters: Optional filters
                - npi: Filter by specific physician NPI
                - year: Filter by specific year
                - min_year: Minimum year (default: 2013)
                - max_year: Maximum year (default: latest available)

        Returns:
            List of physician records with multi-year TAVR volumes
        """
        logger.info(f"Loading CMS historical TAVR data from {self.data_dir}")

        # Find available CMS data files
        cms_files = sorted(self.data_dir.glob("Medicare_Provider_Util_Payment_PUF_CY*.txt"))

        if not cms_files:
            logger.warning(
                f"No CMS data files found in {self.data_dir}. "
                f"Please download files from https://data.cms.gov/"
            )
            return []

        logger.info(f"Found {len(cms_files)} CMS data files")

        # Apply year filters
        min_year = filters.get('min_year', 2013)
        max_year = filters.get('max_year', 9999)
        target_npi = filters.get('npi')

        # Aggregate TAVR volumes by NPI and year
        # physician_data[NPI][year] = volume
        physician_data = defaultdict(lambda: defaultdict(int))
        physician_metadata = {}  # Store name, specialty, etc.

        for file_path in cms_files:
            # Extract year from filename
            year_str = file_path.stem.split('_CY')[-1]
            try:
                year = int(year_str)
            except ValueError:
                logger.warning(f"Could not parse year from {file_path.name}, skipping")
                continue

            # Apply year filter
            if year < min_year or year > max_year:
                logger.debug(f"Skipping {file_path.name} (year {year} outside filter range)")
                continue

            logger.info(f"Processing {file_path.name} (year {year})...")

            # Read and parse file
            tavr_count = 0
            try:
                with file_path.open('r', encoding='utf-8', errors='replace') as f:
                    # Tab-delimited format
                    reader = csv.DictReader(f, delimiter='\t')

                    for row in reader:
                        hcpcs_code = row.get('HCPCS_Cd', '').strip()

                        # Filter for TAVR codes only
                        if hcpcs_code not in TAVR_HCPCS_CODES:
                            continue

                        npi = row.get('Rndrng_NPI', '').strip()
                        if not npi:
                            continue

                        # Apply NPI filter if specified
                        if target_npi and npi != target_npi:
                            continue

                        # Get service count
                        try:
                            services = int(float(row.get('Tot_Srvcs', 0)))
                        except (ValueError, TypeError):
                            services = 0

                        if services > 0:
                            # Aggregate services by NPI and year
                            physician_data[npi][year] += services
                            tavr_count += services

                            # Store metadata (only need to do this once per NPI)
                            if npi not in physician_metadata:
                                physician_metadata[npi] = {
                                    'npi': npi,
                                    'provider_name': row.get('Rndrng_Prvdr_Last_Org_Name', '') +
                                                   (', ' + row.get('Rndrng_Prvdr_First_Name', '') if row.get('Rndrng_Prvdr_First_Name') else ''),
                                    'credential': row.get('Rndrng_Prvdr_Crdntls', ''),
                                    'gender': row.get('Rndrng_Prvdr_Gndr', ''),
                                    'entity_type': row.get('Rndrng_Prvdr_Ent_Cd', ''),
                                    'street': row.get('Rndrng_Prvdr_St1', ''),
                                    'city': row.get('Rndrng_Prvdr_City', ''),
                                    'state': row.get('Rndrng_Prvdr_State_Abrvtn', ''),
                                    'zip': row.get('Rndrng_Prvdr_Zip5', ''),
                                }

                logger.info(f"  → Found {tavr_count} TAVR procedures from {len(physician_data)} physicians")

            except Exception as e:
                logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
                continue

        # Convert to structured output
        results = []
        for npi, years_data in physician_data.items():
            metadata = physician_metadata.get(npi, {'npi': npi})

            # Calculate trends
            sorted_years = sorted(years_data.keys())
            total_procedures = sum(years_data.values())

            # Year-over-year growth
            trends = []
            for i in range(1, len(sorted_years)):
                prev_year = sorted_years[i-1]
                curr_year = sorted_years[i]
                prev_vol = years_data[prev_year]
                curr_vol = years_data[curr_year]

                if prev_vol > 0:
                    growth_pct = ((curr_vol - prev_vol) / prev_vol) * 100
                else:
                    growth_pct = 100.0 if curr_vol > 0 else 0.0

                trends.append({
                    'year': curr_year,
                    'volume': curr_vol,
                    'prev_volume': prev_vol,
                    'growth_pct': growth_pct,
                    'growth_absolute': curr_vol - prev_vol
                })

            # Latest year stats
            latest_year = sorted_years[-1] if sorted_years else None
            latest_volume = years_data[latest_year] if latest_year else 0

            # Build result record
            record = {
                **metadata,
                'total_tavr_procedures': total_procedures,
                'years_active': len(sorted_years),
                'first_year': sorted_years[0] if sorted_years else None,
                'latest_year': latest_year,
                'latest_volume': latest_volume,
                'volume_by_year': dict(years_data),  # {2019: 45, 2020: 52, ...}
                'trends': trends,  # List of year-over-year growth stats
            }

            # Add trend indicators
            if trends:
                avg_growth = sum(t['growth_pct'] for t in trends) / len(trends)
                record['avg_annual_growth_pct'] = avg_growth
                record['trend_indicator'] = '📈' if avg_growth > 10 else ('📉' if avg_growth < -10 else '➡️')
            else:
                record['avg_annual_growth_pct'] = 0
                record['trend_indicator'] = '➡️'

            results.append(record)

        # Sort by latest volume (descending)
        results.sort(key=lambda x: x.get('latest_volume', 0), reverse=True)

        logger.info(
            f"Loaded {len(results)} physicians with historical TAVR data "
            f"({len(physician_data)} total years)"
        )

        return results

    def get_cache_key(self, **filters) -> str:
        """Generate cache key."""
        npi = filters.get('npi', 'all')
        min_year = filters.get('min_year', 2013)
        max_year = filters.get('max_year', 'latest')
        return f"{self.name}:npi={npi}:years={min_year}-{max_year}"

    @staticmethod
    def _normalize_street(street: str) -> str:
        """Strip suite/unit/floor/room numbers to normalize addresses.

        '30 HARRISON ST STE 250' -> '30 HARRISON ST'
        '100 MAIN AVE UNIT 5B'   -> '100 MAIN AVE'
        '500 ELM BLVD #302'      -> '500 ELM BLVD'
        """
        # Remove suite/ste/unit/apt/fl/floor/rm/room and everything after
        normalized = re.sub(
            r'\s+(STE|SUITE|UNIT|APT|FL|FLOOR|RM|ROOM|#)\s*\S*.*$',
            '',
            street,
            flags=re.IGNORECASE,
        )
        return normalized.strip()

    async def discover_non_tvt_hospitals(
        self,
        tvt_hospitals_path: Path = None,
        min_volume: int = 10,
        min_physicians: int = 1,
    ) -> list[dict[str, Any]]:
        """Discover TAVR-active addresses not in the TVT Registry.

        Groups CMS billing data by normalized address (suite numbers stripped),
        cross-references against the TVT hospital list, and returns locations
        with TAVR activity but no TVT match.

        Args:
            tvt_hospitals_path: Path to all_hospitals.json
            min_volume: Minimum total TAVR procedures to include
            min_physicians: Minimum physicians at address to include

        Returns:
            List of discovered non-TVT hospital locations sorted by volume
        """
        if tvt_hospitals_path is None:
            tvt_hospitals_path = self.data_dir.parent / "output" / "all_hospitals.json"

        # Fetch all CMS physician data
        physicians = await self.fetch()
        if not physicians:
            logger.warning("No CMS data available for hospital discovery")
            return []

        # Group physicians by normalized billing address
        address_groups: dict[str, dict] = defaultdict(lambda: {
            'physicians': [],
            'total_volume': 0,
            'street': '',
            'city': '',
            'state': '',
            'zip': '',
        })

        for p in physicians:
            raw_street = (p.get('street') or '').strip().upper()
            street = self._normalize_street(raw_street)
            city = (p.get('city') or '').strip().upper()
            state = (p.get('state') or '').strip().upper()

            if not city or not state:
                continue

            addr_key = f"{street}|{city}|{state}"
            group = address_groups[addr_key]
            group['physicians'].append(p)
            group['total_volume'] += p.get('total_tavr_procedures', 0)
            group['street'] = street
            group['city'] = city
            group['state'] = state
            if not group['zip']:
                group['zip'] = p.get('zip', '')

        # Load TVT hospitals and build city+state lookup
        tvt_cities: set[str] = set()
        if tvt_hospitals_path.exists():
            with tvt_hospitals_path.open() as f:
                tvt_hospitals = json.load(f)
            for h in tvt_hospitals:
                h_city = (h.get('city') or '').strip().upper()
                h_state = (h.get('state') or '').strip().upper()
                if h_city and h_state:
                    tvt_cities.add(f"{h_city}|{h_state}")

        # Find addresses with TAVR activity but no TVT hospital in same city+state
        missing = []
        for addr_key, group in address_groups.items():
            city_state_key = f"{group['city']}|{group['state']}"

            if city_state_key in tvt_cities:
                continue

            if group['total_volume'] < min_volume:
                continue
            if len(group['physicians']) < min_physicians:
                continue

            # Estimate annual volume from latest year across physicians
            latest_annual = sum(
                p.get('latest_volume', 0) for p in group['physicians']
            )

            missing.append({
                'street': group['street'],
                'city': group['city'],
                'state': group['state'],
                'zip': group['zip'],
                'physician_count': len(group['physicians']),
                'total_tavr_volume': group['total_volume'],
                'estimated_annual_volume': latest_annual,
                'physicians': [
                    {
                        'npi': p['npi'],
                        'name': p.get('provider_name', 'Unknown'),
                        'latest_volume': p.get('latest_volume', 0),
                    }
                    for p in group['physicians']
                ],
            })

        missing.sort(key=lambda x: x['total_tavr_volume'], reverse=True)
        logger.info(f"Discovered {len(missing)} non-TVT TAVR locations")
        return missing


async def main():
    """Test the CMS historical data source."""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    source = CMSHistoricalSource()

    console.print(f"\n[bold cyan]Testing CMS Historical Data Source[/bold cyan]")
    console.print(f"Data directory: {source.data_dir}\n")

    # Fetch data
    physicians = await source.fetch(min_year=2019)

    if not physicians:
        console.print("[yellow]No data found. Please download CMS files to:[/yellow]")
        console.print(f"  {source.data_dir}")
        console.print("\nDownload from: https://data.cms.gov/provider-summary-by-type-of-service/")
        return

    # Show top 10 physicians by latest volume
    table = Table(title=f"Top 10 TAVR Physicians (Latest Year)")
    table.add_column("NPI", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("State", justify="center")
    table.add_column("Latest Vol", justify="right", style="yellow")
    table.add_column("Trend", justify="center")
    table.add_column("Avg Growth", justify="right", style="green")

    for p in physicians[:10]:
        table.add_row(
            p['npi'],
            p.get('provider_name', 'Unknown')[:40],
            p.get('state', ''),
            str(p.get('latest_volume', 0)),
            p.get('trend_indicator', ''),
            f"{p.get('avg_annual_growth_pct', 0):.1f}%"
        )

    console.print(table)

    # Show detailed trend for top physician
    if physicians:
        top_physician = physicians[0]
        console.print(f"\n[bold]Detailed Trends for {top_physician.get('provider_name')}:[/bold]")

        trend_table = Table()
        trend_table.add_column("Year", justify="center")
        trend_table.add_column("Volume", justify="right", style="yellow")
        trend_table.add_column("Change", justify="right")
        trend_table.add_column("Growth %", justify="right", style="green")

        for year, volume in sorted(top_physician['volume_by_year'].items()):
            # Find matching trend
            trend = next((t for t in top_physician['trends'] if t['year'] == year), None)
            if trend:
                change = f"+{trend['growth_absolute']}" if trend['growth_absolute'] > 0 else str(trend['growth_absolute'])
                growth = f"+{trend['growth_pct']:.1f}%" if trend['growth_pct'] > 0 else f"{trend['growth_pct']:.1f}%"
            else:
                change = "-"
                growth = "-"

            trend_table.add_row(str(year), str(volume), change, growth)

        console.print(trend_table)

# Module-level instance for SourceRegistry auto-discovery
cms_historical_source = CMSHistoricalSource()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
