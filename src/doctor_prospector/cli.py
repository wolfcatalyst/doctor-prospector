"""Command-line interface for Doctor Prospector."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .paths import CACHE_DB_PATH

app = typer.Typer(
    name="doctor-prospector",
    help="Automated prospect list generator for TAVR medical device sales.",
    add_completion=False,
)
console = Console()

# Create cache subcommand group
cache_app = typer.Typer(help="Manage cached data")
app.add_typer(cache_app, name="cache")


@app.command()
def scrape_tvt(
    output: Path = typer.Option(
        Path("data/cache/tvt.db"),
        "--output", "-o",
        help="Output SQLite database path"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    """Scrape TVT Registry for hospital TAVR program data."""
    console.print("[bold blue]Scraping TVT Registry...[/bold blue]")
    # TODO: Implement TVT scraper
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def enrich(
    source: Path = typer.Option(
        Path("data/cache/tvt.db"),
        "--source", "-s",
        help="Source SQLite database with hospital data"
    ),
    output: Path = typer.Option(
        Path("data/cache/enriched.db"),
        "--output", "-o",
        help="Output SQLite database with enriched data"
    ),
    skip_nppes: bool = typer.Option(False, "--skip-nppes", help="Skip NPPES physician lookup"),
    skip_payments: bool = typer.Option(False, "--skip-payments", help="Skip Open Payments lookup"),
    skip_trials: bool = typer.Option(False, "--skip-trials", help="Skip ClinicalTrials.gov lookup"),
):
    """Enrich hospital data with physician, payment, and trial information."""
    console.print("[bold blue]Enriching data...[/bold blue]")
    # TODO: Implement enrichment pipeline
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def generate(
    source: Path = typer.Option(
        Path("data/cache/enriched.db"),
        "--source", "-s",
        help="Source SQLite database with enriched data"
    ),
    output: Path = typer.Option(
        Path("data/output/prospects.xlsx"),
        "--output", "-o",
        help="Output Excel file path"
    ),
    states: Optional[str] = typer.Option(
        None,
        "--states",
        help="Comma-separated state codes to filter (e.g., NY,IL,CA)"
    ),
    min_volume: int = typer.Option(
        0,
        "--min-volume",
        help="Minimum annual TAVR volume to include"
    ),
    min_fit: str = typer.Option(
        "LOW",
        "--min-fit",
        help="Minimum fit score category (LOW, MEDIUM, HIGH)"
    ),
):
    """Generate prospect list Excel file from enriched data."""
    console.print("[bold blue]Generating prospect list...[/bold blue]")
    # TODO: Implement Excel generation
    console.print("[yellow]Not yet implemented[/yellow]")


@app.command()
def run(
    states: str = typer.Option(
        "NY",
        "--states",
        help="Comma-separated state codes (e.g., NY,IL)"
    ),
    output: Path = typer.Option(
        Path("data/output/prospects.xlsx"),
        "--output", "-o",
        help="Output Excel file path"
    ),
    min_volume: int = typer.Option(
        50,
        "--min-volume",
        help="Minimum annual TAVR volume"
    ),
    cache_dir: Path = typer.Option(
        Path("data/cache"),
        "--cache-dir",
        help="Directory for cached data"
    ),
    force_refresh: bool = typer.Option(
        False,
        "--force-refresh",
        help="Force refresh all data even if cached"
    ),
):
    """Run full pipeline: scrape, enrich, and generate prospect list."""
    console.print(f"[bold green]Doctor Prospector - Full Pipeline[/bold green]")
    console.print(f"States: {states}")
    console.print(f"Min volume: {min_volume}")
    console.print(f"Output: {output}")
    console.print()
    
    # TODO: Implement full pipeline
    # 1. Scrape TVT Registry
    # 2. Enrich with NPPES, Open Payments, ClinicalTrials.gov
    # 3. Calculate fit scores
    # 4. Generate Excel output
    
    console.print("[yellow]Full pipeline not yet implemented[/yellow]")


@app.command()
def info():
    """Show information about data sources and their status."""
    table = Table(title="Doctor Prospector Data Sources")
    
    table.add_column("Source", style="cyan")
    table.add_column("URL", style="blue")
    table.add_column("Status", style="green")
    table.add_column("Last Updated", style="yellow")
    
    table.add_row(
        "TVT Registry",
        "tvtpublicreporting.sts.org",
        "Available",
        "Not cached"
    )
    table.add_row(
        "NPPES API",
        "npiregistry.cms.hhs.gov",
        "Available",
        "Real-time"
    )
    table.add_row(
        "Open Payments",
        "openpaymentsdata.cms.gov",
        "Available",
        "2023 data"
    )
    table.add_row(
        "ClinicalTrials.gov",
        "clinicaltrials.gov",
        "Available",
        "Real-time"
    )
    
    console.print(table)


@cache_app.command(name="status")
def cache_status():
    """Show cache statistics and freshness."""
    from .cache import SQLiteCache

    cache = SQLiteCache(CACHE_DB_PATH)

    async def _get_status():
        status = await cache.get_status()
        return status

    status = asyncio.run(_get_status())

    # Summary panel
    summary = f"""
    [cyan]Total Entries:[/cyan] {status['total_entries']}
    [green]Valid (Fresh):[/green] {status['valid_entries']}
    [yellow]Expired:[/yellow] {status['expired_entries']}
    [dim]Database:[/dim] {status['db_path']}
    """
    console.print(Panel(summary.strip(), title="Cache Summary", border_style="blue"))

    # Per-source breakdown
    if status['by_source']:
        console.print("\n[bold]Cached Entries by Source:[/bold]")
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Source", style="cyan")
        table.add_column("Entries", justify="right", style="green")

        for source_name, count in sorted(status['by_source'].items()):
            table.add_row(source_name, str(count))

        console.print(table)
    else:
        console.print("\n[dim]No cached data found.[/dim]")


@cache_app.command(name="clear")
def cache_clear(
    source: Optional[str] = typer.Argument(
        None,
        help="Specific source to clear (e.g., 'clinical_trials'). If omitted, clears ALL cache."
    ),
    force: bool = typer.Option(
        False,
        "--force", "-f",
        help="Skip confirmation prompt"
    ),
):
    """Clear cached data.

    ⚠️  WARNING: Only clear cache if absolutely necessary!

    Clearing cache will cause the next fetch to hit the original data sources.
    This is usually unnecessary - cache automatically expires based on TTL.

    Examples:
        doctor-prospector cache clear clinical_trials  # Clear specific source
        doctor-prospector cache clear --force          # Clear all cache (no prompt)
    """
    from .cache import SQLiteCache

    cache = SQLiteCache(CACHE_DB_PATH)

    # Confirm unless forced
    if not force:
        if source:
            confirm = typer.confirm(
                f"⚠️  Clear cache for source '{source}'? "
                f"This will cause the next fetch to hit the original data source."
            )
        else:
            confirm = typer.confirm(
                "⚠️  Clear ALL cached data? "
                "This will cause all sources to be fetched fresh on next use."
            )

        if not confirm:
            console.print("[yellow]Cancelled.[/yellow]")
            return

    async def _clear():
        if source:
            await cache.clear_source(source)
            console.print(f"[green]✓ Cleared cache for source: {source}[/green]")
        else:
            # Clear all by clearing each source
            status = await cache.get_status()
            sources = list(status['by_source'].keys())
            for s in sources:
                await cache.clear_source(s)
            console.print(f"[green]✓ Cleared cache for {len(sources)} sources[/green]")

    asyncio.run(_clear())


@cache_app.command(name="clean")
def cache_clean():
    """Remove expired cache entries.

    This is safe to run and only removes entries that have already expired.
    The system automatically ignores expired entries, so this just frees disk space.
    """
    from .cache import SQLiteCache

    cache = SQLiteCache(CACHE_DB_PATH)

    async def _clean():
        count = await cache.clear_expired()
        return count

    count = asyncio.run(_clean())

    if count > 0:
        console.print(f"[green]✓ Removed {count} expired cache entries[/green]")
    else:
        console.print("[dim]No expired entries to remove.[/dim]")


if __name__ == "__main__":
    app()
