"""Full scrape of all 293 TVT Registry hospitals.

This script fetches ALL hospitals nationwide from the TVT Registry,
enriches with detail page data, and saves to JSON.

Runtime: ~7-8 minutes (293 detail page requests with 1.5s delay)
Note: Longer runtime due to respectful rate limiting. Go make coffee! ☕
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from src.doctor_prospector.sources.tvt_registry import TVTRegistrySource
from src.doctor_prospector.cache import SQLiteCache

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

console = Console()


async def main(output_path: Path = Path("data/output/all_hospitals.json")):
    """Scrape all TVT hospitals and save to file."""
    console.print("\n[bold cyan]═══ Full TVT Registry Scrape ═══[/bold cyan]\n")

    # Initialize
    cache_path = Path("data/cache/doctor_prospector.db")
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    cache = SQLiteCache(cache_path)
    scraper = TVTRegistrySource()

    # Start scraping
    console.print("[yellow]Fetching all hospitals nationwide...[/yellow]")
    console.print("[dim]This will take ~7-8 minutes (293 detail pages with 1.5s delay)[/dim]")
    console.print("[dim]☕ Go make coffee while you wait - being respectful to TVT's servers![/dim]\n")

    start_time = datetime.now()

    # Fetch all hospitals (no state filter = nationwide)
    hospitals = await scraper.fetch()

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Save to JSON
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(hospitals, f, indent=2, ensure_ascii=False)

    console.print(f"\n[green]✓ Saved {len(hospitals)} hospitals to {output_path}[/green]")
    console.print(f"[dim]Runtime: {duration:.1f} seconds ({duration/60:.1f} minutes)[/dim]\n")

    # Show summary statistics
    console.print("[bold cyan]Summary Statistics:[/bold cyan]\n")

    # Count by state
    states = {}
    for h in hospitals:
        state = h.get("state", "Unknown")
        states[state] = states.get(state, 0) + 1

    # Count by star rating
    ratings = {}
    for h in hospitals:
        rating = h.get("star_rating", "N/A")
        ratings[rating] = ratings.get(rating, 0) + 1

    # Volume stats
    volumes = [h.get("annual_tavr_volume", 0) for h in hospitals if h.get("annual_tavr_volume")]

    stats_table = Table(title="Overall Stats")
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green", justify="right")

    stats_table.add_row("Total hospitals", str(len(hospitals)))
    stats_table.add_row("States covered", str(len(states)))
    if volumes:
        stats_table.add_row("Avg annual volume", f"{sum(volumes) / len(volumes):.0f}")
        stats_table.add_row("Max annual volume", str(max(volumes)))
        stats_table.add_row("Min annual volume", str(min(volumes)))

    console.print(stats_table)
    console.print()

    # Top states by hospital count
    top_states = sorted(states.items(), key=lambda x: x[1], reverse=True)[:10]

    state_table = Table(title="Top 10 States by Hospital Count")
    state_table.add_column("State", style="cyan")
    state_table.add_column("Hospitals", style="green", justify="right")

    for state, count in top_states:
        state_table.add_row(state, str(count))

    console.print(state_table)
    console.print()

    # Star rating distribution
    rating_table = Table(title="Star Rating Distribution")
    rating_table.add_column("Rating", style="cyan")
    rating_table.add_column("Count", style="green", justify="right")

    for rating in [3, 2, 1, "N/A"]:
        count = ratings.get(rating, 0)
        rating_table.add_row(str(rating), str(count))

    console.print(rating_table)
    console.print()

    # Top hospitals by volume
    hospitals_with_volume = [h for h in hospitals if h.get("annual_tavr_volume")]
    top_volume = sorted(hospitals_with_volume, key=lambda x: x["annual_tavr_volume"], reverse=True)[:10]

    volume_table = Table(title="Top 10 Hospitals by Annual Volume")
    volume_table.add_column("Hospital", style="cyan", max_width=40)
    volume_table.add_column("City, State", style="white")
    volume_table.add_column("Volume", style="green", justify="right")
    volume_table.add_column("Stars", style="yellow", justify="center")

    for h in top_volume:
        volume_table.add_row(
            h.get("name", "N/A"),
            f"{h.get('city', 'N/A')}, {h.get('state', 'N/A')}",
            str(h.get("annual_tavr_volume", "N/A")),
            str(h.get("star_rating", "N/A"))
        )

    console.print(volume_table)
    console.print()

    console.print("[bold green]✓ Full scrape complete![/bold green]\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape all TVT Registry hospitals")
    parser.add_argument("--output", type=Path, default=Path("data/output/all_hospitals.json"),
                        help="Where to write the hospital JSON (default: data/output/all_hospitals.json)")
    asyncio.run(main(parser.parse_args().output))
