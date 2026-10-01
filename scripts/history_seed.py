"""Snapshot of the physician volume history, so installs don't re-download it.

Published CMS years never change, so a database that already has 2019-2024
loaded can be exported once and shipped. A new install imports it in seconds
instead of fetching ~40 minutes of data from the CMS API; refresh_all then
only fetches years that are missing.

Usage:
    python scripts/history_seed.py export            # -> data/seed/physician_volumes.csv.gz
    python scripts/history_seed.py import            # load it if the table is empty
    python scripts/history_seed.py import --force    # replace whatever is there
"""

import argparse
import csv
import gzip
import io
import sys
from pathlib import Path

import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import ROOT, database_url, describe  # noqa: E402
from import_puf import PHYSICIAN_VOLUMES, _insert_batch  # noqa: E402

DEFAULT_SEED = ROOT / "data" / "seed" / "physician_volumes.csv.gz"
COLUMNS = [c.name for c in PHYSICIAN_VOLUMES.columns]
INT_COLUMNS = {"year", "services", "beneficiaries"}


def export_seed(engine: sa.Engine, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    query = sa.select(*PHYSICIAN_VOLUMES.columns).order_by(
        PHYSICIAN_VOLUMES.c.year, PHYSICIAN_VOLUMES.c.npi, PHYSICIAN_VOLUMES.c.hcpcs_code
    )
    # mtime=0 so identical data produces an identical file
    with engine.connect() as conn, open(path, "wb") as raw, \
            gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz, \
            io.TextIOWrapper(gz, encoding="utf-8", newline="") as text:
        writer = csv.writer(text)
        writer.writerow(COLUMNS)
        for row in conn.execute(query):
            writer.writerow(row)
            count += 1
    return count


def years_in(engine: sa.Engine) -> set[int]:
    with engine.connect() as conn:
        if not sa.inspect(conn).has_table("physician_volumes"):
            raise RuntimeError("physician_volumes table missing; run migrations first")
        return {r[0] for r in conn.execute(sa.select(PHYSICIAN_VOLUMES.c.year).distinct())}


def import_seed(engine: sa.Engine, path: Path, force: bool = False) -> int:
    """Load the snapshot. Skips (returns 0) if the table already has data, unless force."""
    if years_in(engine) and not force:
        return 0
    if force:
        with engine.begin() as conn:
            conn.execute(PHYSICIAN_VOLUMES.delete())
    count = 0
    batch: list[dict] = []
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        for rec in csv.DictReader(f):
            row = {k: (int(v) if k in INT_COLUMNS else v) for k, v in rec.items()}
            row["avg_medicare_payment"] = float(rec["avg_medicare_payment"]) if rec["avg_medicare_payment"] else None
            batch.append(row)
            if len(batch) >= 20000:
                _insert_batch(engine, batch)
                count += len(batch)
                batch = []
    if batch:
        _insert_batch(engine, batch)
        count += len(batch)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "import"])
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--force", action="store_true", help="import: replace existing rows")
    args = parser.parse_args()

    engine = sa.create_engine(database_url())
    print(f"Database: {describe(engine.url.render_as_string(hide_password=False))}")
    if args.action == "export":
        count = export_seed(engine, args.file)
        print(f"Exported {count:,} rows -> {args.file} ({args.file.stat().st_size / 1e6:.1f} MB)")
    else:
        if not args.file.exists():
            print(f"No snapshot at {args.file}")
            return 1
        count = import_seed(engine, args.file, args.force)
        print(f"Imported {count:,} rows" if count else "Table already has data; nothing imported (use --force to replace)")
    print(f"Years in database: {sorted(years_in(engine))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
