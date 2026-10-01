"""Import CMS Medicare Physician PUF data into the physician_volumes table.

Downloads PUF files from CMS, filters to relevant HCPCS codes,
and bulk-inserts into Postgres. Downloaded files are saved locally
so they don't need to be re-downloaded.

Usage:
    # Fetch just the profile codes via the CMS API (fast; recommended)
    python scripts/import_puf.py --api --years 2019-2024

    # Download and import all years (2019-2023), filtering to profile codes
    python scripts/import_puf.py --download --years 2019-2023

    # Download a single year
    python scripts/import_puf.py --download --years 2023

    # Import from already-downloaded files in data/cms_historical/
    python scripts/import_puf.py --dir data/cms_historical/

    # Import a single local file
    python scripts/import_puf.py --file MUP_PHY_xxx.csv --year 2023

    # Custom HCPCS filter
    python scripts/import_puf.py --download --years 2019-2023 --codes 27447,27130

    # Import ALL procedure codes (huge!)
    python scripts/import_puf.py --download --years 2023 --all-codes
"""

import argparse
import csv
import os
import re
import sys
import time
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import database_url, describe  # noqa: E402

# Mirrors migration 005; Core table so this works on PostgreSQL and SQLite
_metadata = sa.MetaData()
PHYSICIAN_VOLUMES = sa.Table(
    "physician_volumes", _metadata,
    sa.Column("npi", sa.String(10)),
    sa.Column("year", sa.SmallInteger),
    sa.Column("hcpcs_code", sa.String(10)),
    sa.Column("hcpcs_description", sa.Text),
    sa.Column("services", sa.Integer),
    sa.Column("beneficiaries", sa.Integer),
    sa.Column("avg_medicare_payment", sa.Float),
    sa.Column("provider_name", sa.String(255)),
    sa.Column("provider_city", sa.String(100)),
    sa.Column("provider_state", sa.String(2)),
    sa.Column("provider_type", sa.String(100)),
)
_UPDATE_COLS = ["services", "beneficiaries", "avg_medicare_payment",
                "provider_name", "provider_city", "provider_state", "provider_type"]


# CMS PUF download URLs by year (from data.cms.gov/data.json catalog)
# These are direct CSV download links — no auth required, ~3 GB each
PUF_URLS = {
    2024: "https://data.cms.gov/sites/default/files/2026-05/b5ebab5a-f490-418a-9bce-4b9f31419356/PHY_R26_P05_V10_D24_Prov_Svc.csv",
    2023: "https://data.cms.gov/sites/default/files/2025-04/e3f823f8-db5b-4cc7-ba04-e7ae92b99757/MUP_PHY_R25_P05_V20_D23_Prov_Svc.csv",
    2022: "https://data.cms.gov/sites/default/files/2025-11/53fb2bae-4913-48dc-a6d4-d8c025906567/MUP_PHY_R25_P05_V20_D22_Prov_Svc.csv",
    2021: "https://data.cms.gov/sites/default/files/2025-11/bffaf97a-c2ab-4fd7-8718-be90742e3485/MUP_PHY_R25_P05_V20_D21_Prov_Svc.csv",
    2020: "https://data.cms.gov/sites/default/files/2025-11/d22b18cd-7726-4bf5-8e9c-3e4587c589a1/MUP_PHY_R25_P05_V20_D20_Prov_Svc.csv",
    2019: "https://data.cms.gov/sites/default/files/2025-11/7befba27-752e-47a8-a76c-6c6d4f74f2e3/MUP_PHY_R25_P04_V20_D19_Prov_Svc.csv",
    2018: "https://data.cms.gov/sites/default/files/2025-11/5669eafb-f0b3-4dc5-be6d-abc09b480c2e/MUP_PHY_R25_P04_V20_D18_Prov_Svc.csv",
    2017: "https://data.cms.gov/sites/default/files/2025-11/4623fb40-781e-4eef-860e-b851cd5d10ea/MUP_PHY_R25_P04_V20_D17_Prov_Svc.csv",
    2016: "https://data.cms.gov/sites/default/files/2025-11/426bf97a-4cb8-47ca-9727-a535d9e8c298/MUP_PHY_R25_P04_V20_D16_Prov_Svc.csv",
    2015: "https://data.cms.gov/sites/default/files/2025-11/14954ce3-4c43-43df-97e9-2c0437d7b43c/MUP_PHY_R25_P04_V20_D15_Prov_Svc.csv",
    2014: "https://data.cms.gov/sites/default/files/2025-11/6700f86d-d2e5-4f2d-9dcb-8c30412768ff/MUP_PHY_R25_P04_V20_D14_Prov_Svc.csv",
    2013: "https://data.cms.gov/sites/default/files/2025-11/bf4231f9-ec7f-4189-afc3-ba5d53b8bd12/MUP_PHY_R25_P04_V20_D13_Prov_Svc.csv",
}

# CMS Data API dataset UUIDs for the same "by Provider and Service" data.
# Used by --api mode to fetch only the profile HCPCS codes (a few MB per
# year instead of a ~3 GB CSV). Each year is a separate catalog entry.
API_DATASETS = {
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

# All HCPCS codes we care about across all profiles
# Add new codes here as profiles are added
ALL_PROFILE_HCPCS = {
    # TAVR
    "33361", "33362", "33363", "33364", "33365", "33366", "33367", "33368", "33369",
    # Robotic Surgery
    "55866", "S2900",
    "58571", "58572", "58573",
    "44204", "44205", "44207", "44208", "44210", "44213",
    "27447", "27130",
    "22551", "22612", "22630",
}


def parse_year_range(year_str: str) -> list[int]:
    """Parse '2019-2023' or '2023' into list of years."""
    if "-" in year_str:
        start, end = year_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(year_str)]


def parse_year_from_filename(filename: str) -> int | None:
    """Extract year from PUF filename patterns."""
    m = re.search(r"CY(\d{4})", filename)
    if m:
        return int(m.group(1))
    m = re.search(r"D(\d{2})", filename)
    if m:
        return 2000 + int(m.group(1))
    return None


def download_puf(year: int, dest_dir: Path) -> Path:
    """Download a PUF file from CMS if not already present.

    Streams the ~3 GB file to disk, showing progress.
    Returns path to the downloaded file.
    """
    import urllib.request

    url = PUF_URLS.get(year)
    if not url:
        raise ValueError(f"No download URL known for year {year}. Available: {sorted(PUF_URLS.keys())}")

    filename = url.split("/")[-1]
    dest_path = dest_dir / filename

    if dest_path.exists():
        size_mb = dest_path.stat().st_size / (1024 * 1024)
        print(f"  Already downloaded: {filename} ({size_mb:.0f} MB)")
        return dest_path

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {filename} (~3 GB)...")
    print(f"  URL: {url}")

    start = time.time()
    downloaded = 0

    def _report(block_num, block_size, total_size):
        nonlocal downloaded
        downloaded = block_num * block_size
        if total_size > 0:
            pct = downloaded / total_size * 100
            mb = downloaded / (1024 * 1024)
            total_mb = total_size / (1024 * 1024)
            print(f"    {mb:.0f}/{total_mb:.0f} MB ({pct:.0f}%)", end="\r")
        else:
            mb = downloaded / (1024 * 1024)
            print(f"    {mb:.0f} MB downloaded...", end="\r")

    urllib.request.urlretrieve(url, dest_path, reporthook=_report)

    elapsed = time.time() - start
    size_mb = dest_path.stat().st_size / (1024 * 1024)
    print(f"\n  Downloaded {size_mb:.0f} MB in {elapsed:.0f}s")
    return dest_path


def fetch_via_api(year: int, hcpcs_codes: set[str], dest_dir: Path) -> Path:
    """Fetch only the given HCPCS codes for a year from the CMS Data API.

    Writes a CSV with the same column names as the full PUF so it can be
    imported by import_puf_file(). Re-fetches every time (small download).
    """
    import json
    import urllib.parse
    import urllib.request

    uuid = API_DATASETS.get(year)
    if not uuid:
        raise ValueError(f"No API dataset known for year {year}. Available: {sorted(API_DATASETS.keys())}")

    base = f"https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
    page_size = 5000
    rows: list[dict] = []

    for code in sorted(hcpcs_codes):
        offset = 0
        code_rows = 0
        while True:
            query = urllib.parse.urlencode({"filter[HCPCS_Cd]": code, "size": page_size, "offset": offset})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(f"{base}?{query}", timeout=120) as resp:
                        page = json.load(resp)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            if not page:
                break
            rows.extend(page)
            code_rows += len(page)
            if len(page) < page_size:
                break
            offset += page_size
        print(f"    {year} {code}: {code_rows:,} rows")

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"api_CY{year}.csv"
    if rows:
        fieldnames = sorted({k for r in rows for k in r})
        with open(dest_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    else:
        dest_path.write_text("Rndrng_NPI,HCPCS_Cd,Tot_Srvcs\n", encoding="utf-8")
    print(f"  Fetched {len(rows):,} rows for {year} -> {dest_path}")
    return dest_path


def get_db_engine() -> sa.Engine:
    """Engine for the app database (SQLite by default, PostgreSQL in Docker)."""
    return sa.create_engine(database_url())


def import_puf_file(
    filepath: Path,
    year: int,
    hcpcs_filter: set[str] | None,
    engine: sa.Engine,
    flush_every: int = 50000,
) -> int:
    """Import a single PUF file into physician_volumes.

    The full PUF can have duplicate (NPI, HCPCS) rows (e.g. facility vs office
    place of service). We aggregate by (NPI, HCPCS) in memory, summing services
    and beneficiaries, then flush to DB periodically.
    """
    print(f"  Processing {filepath.name} (year {year})...")

    # Detect delimiter
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        first_line = f.readline()
    delimiter = "\t" if "\t" in first_line else ","

    t = PHYSICIAN_VOLUMES

    # Delete existing data for this year + codes
    delete = t.delete().where(t.c.year == year)
    if hcpcs_filter:
        delete = delete.where(t.c.hcpcs_code.in_(sorted(hcpcs_filter)))
    with engine.begin() as conn:
        conn.execute(delete)
    print(f"  Cleared existing year {year} data")

    # Accumulate by (npi, hcpcs_code), summing services across place-of-service
    accum: dict[tuple[str, str], dict] = {}
    rows_read = 0
    skipped = 0
    total_flushed = 0

    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter=delimiter)

        for row in reader:
            rows_read += 1
            if rows_read % 500000 == 0:
                print(f"    {rows_read:,} rows scanned, {len(accum):,} matched...", end="\r")

            hcpcs = row.get("HCPCS_Cd", "").strip()
            if not hcpcs:
                continue
            if hcpcs_filter and hcpcs not in hcpcs_filter:
                continue

            npi = row.get("Rndrng_NPI", "").strip()
            if not npi:
                continue

            try:
                services = int(float(row.get("Tot_Srvcs", 0) or 0))
            except (ValueError, TypeError):
                services = 0
            if services <= 0:
                continue

            try:
                beneficiaries = int(float(row.get("Tot_Benes", 0) or 0))
            except (ValueError, TypeError):
                beneficiaries = 0

            try:
                avg_payment = float(row.get("Avg_Mdcr_Pymt_Amt", 0) or 0)
            except (ValueError, TypeError):
                avg_payment = 0.0

            key = (npi, hcpcs)
            if key in accum:
                rec = accum[key]
                # Weighted average for payment
                old_svc = rec["services"]
                rec["services"] += services
                rec["beneficiaries"] += beneficiaries
                if rec["services"] > 0:
                    rec["avg_payment"] = (
                        (rec["avg_payment"] * old_svc + avg_payment * services) / rec["services"]
                    )
            else:
                last_name = row.get("Rndrng_Prvdr_Last_Org_Name", "").strip()
                first_name = row.get("Rndrng_Prvdr_First_Name", "").strip()
                name = f"{last_name}, {first_name}" if first_name else last_name

                accum[key] = {
                    "services": services,
                    "beneficiaries": beneficiaries,
                    "avg_payment": avg_payment,
                    "hcpcs_desc": row.get("HCPCS_Desc", "").strip()[:200],
                    "name": name[:255],
                    "city": row.get("Rndrng_Prvdr_City", "").strip()[:100],
                    "state": row.get("Rndrng_Prvdr_State_Abrvtn", "").strip()[:2],
                    "prov_type": row.get("Rndrng_Prvdr_Type", "").strip()[:100],
                }

            # Flush periodically to keep memory bounded
            if len(accum) >= flush_every:
                total_flushed += _flush_accum(engine, accum, year)
                print(f"    Flushed {total_flushed:,} rows ({rows_read:,} scanned)...", end="\r")
                accum.clear()

    # Final flush
    if accum:
        total_flushed += _flush_accum(engine, accum, year)

    print(f"  Imported {total_flushed:,} rows for year {year} ({rows_read:,} rows scanned)")
    return total_flushed


def _flush_accum(engine: sa.Engine, accum: dict, year: int) -> int:
    """Flush accumulated records to DB."""
    rows = [
        {
            "npi": npi, "year": year, "hcpcs_code": hcpcs,
            "hcpcs_description": rec["hcpcs_desc"], "services": rec["services"],
            "beneficiaries": rec["beneficiaries"], "avg_medicare_payment": rec["avg_payment"],
            "provider_name": rec["name"], "provider_city": rec["city"],
            "provider_state": rec["state"], "provider_type": rec["prov_type"],
        }
        for (npi, hcpcs), rec in accum.items()
    ]
    if rows:
        _insert_batch(engine, rows)
    return len(rows)


def _insert_batch(engine: sa.Engine, rows: list[dict], chunk: int = 1000) -> None:
    """Upsert rows on (npi, year, hcpcs_code); same SQL shape on PostgreSQL and SQLite."""
    if engine.dialect.name == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    with engine.begin() as conn:
        for i in range(0, len(rows), chunk):
            stmt = insert(PHYSICIAN_VOLUMES).values(rows[i:i + chunk])
            stmt = stmt.on_conflict_do_update(
                index_elements=["npi", "year", "hcpcs_code"],
                set_={c: stmt.excluded[c] for c in _UPDATE_COLS},
            )
            conn.execute(stmt)


def main():
    parser = argparse.ArgumentParser(
        description="Download and import CMS PUF data into physician_volumes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download and import years 2019-2023 (recommended first run)
  python scripts/import_puf.py --download --years 2019-2023

  # Import from existing local files
  python scripts/import_puf.py --dir data/cms_historical/

  # Single year download
  python scripts/import_puf.py --download --years 2023

  # Custom HCPCS codes only
  python scripts/import_puf.py --download --years 2023 --codes 27447,27130,55866
        """,
    )
    parser.add_argument("--download", action="store_true", help="Download PUF files from CMS before importing")
    parser.add_argument("--api", action="store_true", help="Fetch only the profile HCPCS codes via the CMS Data API (fast, small)")
    parser.add_argument("--years", type=str, help="Year or range to download (e.g. '2023' or '2019-2023')")
    parser.add_argument("--file", "-f", type=Path, help="Single local PUF file to import")
    parser.add_argument("--dir", "-d", type=Path, help="Directory of local PUF files to import")
    parser.add_argument("--save-dir", type=Path, default=Path("data/cms_puf"), help="Where to save downloaded PUFs (default: data/cms_puf)")
    parser.add_argument("--codes", "-c", type=str, help="Comma-separated HCPCS codes to filter")
    parser.add_argument("--all-codes", action="store_true", help="Import ALL procedure codes (no filter)")
    parser.add_argument("--keep-downloads", action="store_true", help="Keep full PUF files after import (default: keep)")
    args = parser.parse_args()

    if not args.download and not args.api and not args.file and not args.dir:
        args.dir = Path("data/cms_historical")
        if not args.dir.exists():
            parser.error("Specify --download, --file, or --dir")

    # Determine HCPCS filter
    if args.all_codes:
        hcpcs_filter = None
        print("Mode: Import ALL HCPCS codes (no filter)")
    elif args.codes:
        hcpcs_filter = set(c.strip() for c in args.codes.split(","))
        print(f"Mode: Filtering to {len(hcpcs_filter)} HCPCS codes")
    else:
        hcpcs_filter = ALL_PROFILE_HCPCS
        print(f"Mode: Using default profile codes ({len(hcpcs_filter)} codes)")
    print(f"  Codes: {sorted(hcpcs_filter) if hcpcs_filter else 'ALL'}")

    # Collect files to process
    files: list[tuple[Path, int]] = []

    if args.api:
        if not args.years:
            parser.error("--api requires --years (e.g. --years 2019-2024)")
        if hcpcs_filter is None:
            parser.error("--api cannot be combined with --all-codes; use --download instead")
        years = parse_year_range(args.years)
        print(f"\nFetching {len(years)} year(s) via CMS Data API: {years}")
        for year in years:
            try:
                files.append((fetch_via_api(year, hcpcs_filter, Path("data/cms_api")), year))
            except Exception as e:
                print(f"  ERROR fetching {year}: {e}")
    elif args.download:
        if not args.years:
            parser.error("--download requires --years (e.g. --years 2019-2023)")
        years = parse_year_range(args.years)
        print(f"\nDownloading {len(years)} year(s): {years}")
        print(f"Save directory: {args.save_dir}")
        for year in years:
            try:
                filepath = download_puf(year, args.save_dir)
                files.append((filepath, year))
            except Exception as e:
                print(f"  ERROR downloading {year}: {e}")
    elif args.file:
        year = parse_year_from_filename(args.file.name)
        if not year:
            parser.error(f"Cannot detect year from {args.file.name}, use --years")
        files.append((args.file, year))
    elif args.dir:
        for fp in sorted(args.dir.glob("*.txt")) + sorted(args.dir.glob("*.csv")):
            year = parse_year_from_filename(fp.name)
            if year:
                files.append((fp, year))
            else:
                print(f"  Skipping {fp.name} (cannot detect year)")

    if not files:
        print("No files to import")
        sys.exit(1)

    print(f"\nFiles to import: {len(files)}")
    for fp, year in files:
        print(f"  {fp.name} -> year {year}")

    # Connect and import
    engine = get_db_engine()
    print(f"\nDatabase: {describe(str(engine.url.render_as_string(hide_password=False)))}")

    start = time.time()
    grand_total = 0
    failed = False
    for fp, year in files:
        try:
            grand_total += import_puf_file(fp, year, hcpcs_filter, engine)
        except Exception as e:
            print(f"  ERROR importing {fp.name}: {e}")
            failed = True

    elapsed = time.time() - start
    print(f"\nDone! Imported {grand_total:,} total rows in {elapsed:.1f}s")
    engine.dispose()
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
