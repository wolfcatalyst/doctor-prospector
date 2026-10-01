"""Download CMS Medicare Physician Utilization Data via API.

This script downloads TAVR-specific data from CMS using their data.cms.gov API,
filtering for cardiovascular procedure codes to minimize download size.

Instead of downloading 2-3GB files with ALL procedures, we download only
TAVR procedures (HCPCS codes 33361-33366), reducing size by ~99%.

Usage:
    python download_cms_data.py                    # Download 2013-2023 (all available)
    python download_cms_data.py --years 2019-2023  # Specific years
    python download_cms_data.py --check-2024       # Check if 2024 data available yet
"""

import argparse
import asyncio
import csv
import sys
from pathlib import Path
from typing import List, Dict, Any

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table

console = Console()

# CMS Data API dataset UUIDs (confirmed from data.cms.gov catalog Sep 2026)
CMS_DATASETS = {
    2024: "92396110-2aed-4d63-a6a2-5d6207d46a29",
    2023: "0e9f2f2b-7bf9-451a-912c-e02e654dd725",
    2022: "e650987d-01b7-4f09-b75e-b0b075afbf98",
    2021: "31dc2c47-f297-4948-bfb4-075e1bec3a02",
    2020: "c957b49e-1323-49e7-8678-c09da387551d",
    2019: "867b8ac7-ccb7-4cc9-873d-b24340d89e32",
    2018: "fb6d9fe8-38c1-4d24-83d4-0b7b291000b2",
    2017: "85bf3c9c-2244-490d-ad7d-c34e4c28f8ea",
    2016: "7918e22a-fbfb-4a07-9f59-f8aab2b757d4",
    2015: "f8cdb11a-d5f7-4fbe-aac4-05abc8ee2c83",
    2014: "f63b48ae-946e-48f7-9f56-327a68da4e0b",
    2013: "ad5e7548-98ab-4325-af4b-b2a7099b9351",
}

# TAVR HCPCS codes (cardiovascular procedures 33xxx)
TAVR_CODES = ['33361', '33362', '33363', '33364', '33365', '33366']

# CMS API base URL
CMS_API_BASE = "https://data.cms.gov/data-api/v1/dataset"

# Output directory
OUTPUT_DIR = Path("data/cms_historical")


async def check_dataset_exists(uuid: str) -> tuple[bool, int]:
    """Check if dataset exists and get row count.

    Returns:
        Tuple of (exists, total_rows)
    """
    url = f"{CMS_API_BASE}/{uuid}/data-viewer"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                # Try to get total count from metadata
                total = data.get('total', 0)
                return True, total
            else:
                return False, 0
        except Exception as e:
            console.print(f"[yellow]Error checking dataset: {e}[/yellow]")
            return False, 0


async def check_2024_data():
    """Check if 2024 data is available by probing the data.gov catalog API."""
    console.print("\n[bold cyan]Checking for 2024 data availability...[/bold cyan]")

    console.print("[dim]Querying data.gov catalog for new datasets...[/dim]")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Check the data.gov catalog for the dataset package
            catalog_url = "https://catalog.data.gov/api/3/action/package_show"
            params = {"id": "medicare-physician-other-practitioners-by-provider-and-service-b156e"}
            response = await client.get(catalog_url, params=params)

            if response.status_code == 200:
                data = response.json()
                resources = data.get("result", {}).get("resources", [])

                # Find the latest year available
                years_found = set()
                for r in resources:
                    name = r.get("name", "")
                    # Parse year from names like "by Provider and Service : 2023-12-31"
                    for year in range(2024, 2030):
                        if str(year) in name:
                            years_found.add(year)

                    # Also check URLs for dataset UUIDs
                    url = r.get("url", "")
                    if "data-api/v1/dataset" in url and "2024" in name:
                        uuid = url.split("/dataset/")[1].split("/")[0]
                        console.print(f"\n[green]🎉 Found 2024 dataset UUID: {uuid}[/green]")
                        console.print(f"[green]Add to CMS_DATASETS in download_cms_data.py:[/green]")
                        console.print(f'    2024: "{uuid}",')

                if 2024 in years_found:
                    console.print("\n[green]✓ 2024 data appears in the catalog![/green]")
                    console.print("[yellow]Run this script again after adding the UUID above.[/yellow]")
                else:
                    latest = max(years_found) if years_found else "unknown"
                    console.print(f"\n[yellow]ℹ️  2024 data not yet available[/yellow]")
                    console.print(f"  • Latest year in catalog: {latest}")
                    console.print("  • CMS typically releases data 18 months after year-end")
                    console.print("  • 2024 data expected: Mid-Late 2026")
                    console.print("  • Check manually: https://data.cms.gov/provider-summary-by-type-of-service/")
            else:
                console.print(f"[yellow]Catalog query returned {response.status_code}[/yellow]")
                console.print("Check manually: https://data.cms.gov/provider-summary-by-type-of-service/")

    except Exception as e:
        console.print(f"[yellow]Could not check catalog: {e}[/yellow]")
        console.print("Check manually: https://data.cms.gov/provider-summary-by-type-of-service/")


async def download_tavr_data_for_year(year: int, uuid: str) -> bool:
    """Download TAVR data for a specific year using CMS API.

    Args:
        year: Calendar year
        uuid: CMS dataset UUID

    Returns:
        True if successful
    """
    console.print(f"\n[bold cyan]Downloading {year} data...[/bold cyan]")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"Medicare_Provider_Util_Payment_PUF_CY{year}.txt"

    # Check if already exists
    if output_file.exists():
        console.print(f"[yellow]File already exists: {output_file}[/yellow]")
        overwrite = console.input("Overwrite? (y/N): ")
        if overwrite.lower() != 'y':
            console.print("[dim]Skipping...[/dim]")
            return True

    all_records = []

    async with httpx.AsyncClient(timeout=60.0) as client:
        # Download data for each TAVR code
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:

            # Task for overall progress
            overall_task = progress.add_task(
                f"[cyan]Year {year} - Fetching TAVR codes...",
                total=len(TAVR_CODES)
            )

            for hcpcs_code in TAVR_CODES:
                progress.update(
                    overall_task,
                    description=f"[cyan]Year {year} - Code {hcpcs_code}..."
                )

                # Fetch all records for this HCPCS code
                offset = 0
                page_size = 5000
                code_records = []

                while True:
                    # Build URL with filter
                    url = f"{CMS_API_BASE}/{uuid}/data"
                    params = {
                        'size': page_size,
                        'offset': offset,
                        'filter[HCPCS_Cd]': hcpcs_code
                    }

                    try:
                        response = await client.get(url, params=params)

                        if response.status_code != 200:
                            console.print(f"[red]Error: HTTP {response.status_code} for {hcpcs_code}[/red]")
                            break

                        page_data = response.json()

                        # Handle different response formats
                        if isinstance(page_data, list):
                            records = page_data
                        elif isinstance(page_data, dict):
                            records = page_data.get('data', [])
                        else:
                            console.print(f"[red]Unexpected response format for {hcpcs_code}[/red]")
                            break

                        if not records:
                            break  # No more data

                        code_records.extend(records)
                        offset += len(records)

                        # If we got fewer records than page size, we're done
                        if len(records) < page_size:
                            break

                    except Exception as e:
                        console.print(f"[red]Error fetching {hcpcs_code}: {e}[/red]")
                        break

                all_records.extend(code_records)
                console.print(f"  [dim]→ {hcpcs_code}: {len(code_records)} records[/dim]")

                progress.update(overall_task, advance=1)

    if not all_records:
        console.print(f"[red]✗ No data found for {year}[/red]")
        return False

    # Write to tab-delimited file
    console.print(f"\n[yellow]Writing {len(all_records)} records to file...[/yellow]")

    try:
        with output_file.open('w', newline='', encoding='utf-8') as f:
            if all_records:
                # Get fieldnames from first record
                fieldnames = list(all_records[0].keys())

                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
                writer.writeheader()
                writer.writerows(all_records)

        file_size_mb = output_file.stat().st_size / (1024 * 1024)
        console.print(f"[green]✓ Saved to {output_file}[/green]")
        console.print(f"[dim]  File size: {file_size_mb:.1f} MB[/dim]")

        return True

    except Exception as e:
        console.print(f"[red]Error writing file: {e}[/red]")
        return False


async def download_multiple_years(years: List[int]):
    """Download data for multiple years."""
    console.print(Panel.fit(
        "[bold cyan]CMS TAVR Data Downloader[/bold cyan]\n"
        "Downloading filtered data via CMS API",
        border_style="cyan"
    ))

    # Filter to valid years
    valid_years = [y for y in years if y in CMS_DATASETS and CMS_DATASETS[y] != "check"]

    if not valid_years:
        console.print("[red]No valid years specified[/red]")
        return

    console.print(f"\n[bold]Years to download:[/bold] {', '.join(map(str, valid_years))}")
    console.print(f"[bold]TAVR codes:[/bold] {', '.join(TAVR_CODES)}")
    console.print(f"[bold]Output directory:[/bold] {OUTPUT_DIR.absolute()}")

    # Download each year
    results = {}
    for year in valid_years:
        uuid = CMS_DATASETS[year]
        success = await download_tavr_data_for_year(year, uuid)
        results[year] = success

    # Summary
    console.print("\n" + "="*80)
    console.print("[bold cyan]Download Summary:[/bold cyan]\n")

    table = Table()
    table.add_column("Year", justify="center", style="cyan")
    table.add_column("Status", justify="center")
    table.add_column("Records", justify="right")

    for year in valid_years:
        if results[year]:
            file_path = OUTPUT_DIR / f"Medicare_Provider_Util_Payment_PUF_CY{year}.txt"
            if file_path.exists():
                # Count lines
                with file_path.open('r', encoding='utf-8') as f:
                    record_count = sum(1 for line in f) - 1  # Subtract header

                table.add_row(
                    str(year),
                    "[green]✓ Success[/green]",
                    f"{record_count:,}"
                )
        else:
            table.add_row(
                str(year),
                "[red]✗ Failed[/red]",
                "-"
            )

    console.print(table)

    # Next steps
    console.print("\n[bold green]Next Steps:[/bold green]")
    console.print("1. Find new TAVR sites in the new year's data:")
    console.print("   [cyan]python discover_non_tvt_hospitals.py --add[/cyan]")
    console.print("   (or run everything in order: [cyan]python scripts/refresh_all.py[/cyan])")


async def main():
    parser = argparse.ArgumentParser(
        description="Download CMS TAVR data via API (filtered for efficiency)"
    )
    parser.add_argument(
        '--years',
        type=str,
        default='2013-2023',
        help="Year range to download (e.g., '2013-2023' or '2019-2023')"
    )
    parser.add_argument(
        '--check-2024',
        action='store_true',
        help="Check if 2024 data is available"
    )

    args = parser.parse_args()

    # Check for 2024 data if requested
    if args.check_2024:
        await check_2024_data()
        return

    # Parse year range
    try:
        start_year, end_year = map(int, args.years.split('-'))
        years = list(range(start_year, end_year + 1))
    except ValueError:
        console.print(f"[red]Error: Invalid year range '{args.years}'[/red]")
        console.print("Use format: YYYY-YYYY (e.g., '2019-2023')")
        return

    # Download
    await download_multiple_years(years)


if __name__ == "__main__":
    asyncio.run(main())
