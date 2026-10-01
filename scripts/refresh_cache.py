"""Refresh the SQLite source cache after new upstream data is loaded.

- Clears sources whose results depend on data that just changed
  (Open Payments years, historical files, trial queries)
- Drops expired entries
- Re-fetches every cached NPPES physician record (paced under the
  ~100 requests/minute NPPES limit) so addresses/specialties are current

Usage:
    python scripts/refresh_cache.py              # everything
    python scripts/refresh_cache.py --skip-nppes # clear only, no re-fetch
"""

import argparse
import asyncio
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from doctor_prospector.paths import CACHE_DB_PATH  # noqa: E402
from doctor_prospector.sources.base import _get_cache  # noqa: E402
from doctor_prospector.sources.nppes import NPPESSource  # noqa: E402

# Cache "source" names (as stored) whose results change when new data lands
CLEAR_SOURCES = ["CMS Open Payments", "CMS Historical TAVR Utilization", "clinical_trials"]

NPPES_MIN_SECONDS_PER_REQUEST = 0.65  # ~92/minute


async def refresh(skip_nppes: bool) -> tuple[int, int]:
    """Returns (failed, attempted) NPPES re-fetches."""
    # Collect NPIs first so expired entries get refreshed rather than dropped
    npis: list[str] = []
    if CACHE_DB_PATH.exists():
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            npis = [k.split("=", 1)[1] for (k,) in conn.execute(
                "SELECT key FROM cache WHERE source='nppes' AND key LIKE 'nppes:npi=%'")]

    cache = _get_cache()
    for source in CLEAR_SOURCES:
        await cache.clear_source(source)
        print(f"cleared cache for {source}")
    await cache.clear_expired()
    print("cleared expired entries")

    if skip_nppes or not npis:
        print("NPPES re-fetch skipped" if skip_nppes else "no cached NPPES records")
        return 0, 0

    print(f"re-fetching {len(npis)} NPPES records (~{len(npis) * NPPES_MIN_SECONDS_PER_REQUEST / 60:.0f} min)")
    nppes = NPPESSource()
    failed = 0
    start = time.time()
    for i, npi in enumerate(npis, 1):
        t = time.time()
        try:
            await nppes.fetch_cached(force_refresh=True, npi=npi)
        except Exception as e:  # old entry stays if the refresh fails
            failed += 1
            print(f"  {npi}: {e}")
        await asyncio.sleep(max(0.0, NPPES_MIN_SECONDS_PER_REQUEST - (time.time() - t)))
        if i % 100 == 0:
            print(f"  {i}/{len(npis)} ({time.time() - start:.0f}s)")
    print(f"NPPES: {len(npis) - failed} refreshed, {failed} failed")
    return failed, len(npis)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--skip-nppes", action="store_true", help="Don't re-fetch cached NPPES records")
    args = parser.parse_args()
    failed, attempted = asyncio.run(refresh(args.skip_nppes))
    # A few NPPES hiccups are normal; a lot means the API is down or blocking us
    sys.exit(1 if attempted and failed / attempted > 0.1 else 0)


if __name__ == "__main__":
    main()
