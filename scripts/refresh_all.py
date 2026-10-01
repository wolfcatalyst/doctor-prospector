"""Refresh every data source in the right order, verifying each step.

Runs the same scripts you'd run by hand, but checks the RESULT of each
(files, record counts, database rows) instead of trusting exit codes,
backs up data files before changing them, and stops with a pointer to
docs/DATA_REFRESH_RUNBOOK.md when something needs a human (or an AI).

Steps:
  1. Preflight      packages, files, database connection
  2. Freshness      which upstream sources published something new
  3. TVT Registry   re-scrape (only with --tvt, or when step 2 found new data)
  4. TAVR history   download any CMS year configured but missing locally
  5. Hospitals      discover new sites, name them, attach CMS facility data
  6. DB history     import any configured year missing from physician_volumes
  7. Cache          clear stale cached results, re-fetch NPI records
  8. Summary        counts + data/output/last_refresh.json

Usage (from the repo root):
    python scripts/refresh_all.py                 # normal refresh
    python scripts/refresh_all.py --tvt           # also force a TVT re-scrape (~8 min)
    python scripts/refresh_all.py --skip-nppes    # skip the ~7 min NPI re-fetch
    python scripts/refresh_all.py --only hospitals,cache
    python scripts/refresh_all.py --dry-run       # report what would run

Step 6 writes to the app database: DATABASE_URL, else the root .env, else
docker/.env (Docker Postgres on localhost), else the SQLite default. See
scripts/db.py.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Scripts live under ROOT; data lives under DATA_ROOT (different folders only
# in the desktop app, where DOCTOR_PROSPECTOR_HOME points at %LOCALAPPDATA%)
DATA_ROOT = Path(os.environ["DOCTOR_PROSPECTOR_HOME"]).resolve() if os.environ.get("DOCTOR_PROSPECTOR_HOME") else ROOT
OUTPUT = DATA_ROOT / "data" / "output"
TVT_FILE = OUTPUT / "all_hospitals.json"
DISCOVERED_FILE = OUTPUT / "cms_discovered_hospitals.json"
HISTORICAL_DIR = DATA_ROOT / "data" / "cms_historical"
BACKUP_DIR = OUTPUT / "backups"
RUNBOOK = "docs/DATA_REFRESH_RUNBOOK.md"

STEPS = ["preflight", "freshness", "tvt", "tavr_history", "hospitals", "db_history", "cache", "summary"]


class StepFailed(Exception):
    def __init__(self, step: str, message: str, runbook_section: str):
        super().__init__(message)
        self.step, self.runbook_section = step, runbook_section


# ── helpers ──────────────────────────────────────────────────────────────

def log(msg: str = "") -> None:
    print(msg, flush=True)


def header(n: int, title: str) -> None:
    log(f"\n{'=' * 70}\n[{n}/8] {title}\n{'=' * 70}")


def run(cmd: list[str], step: str, section: str, dry_run: bool, env: dict | None = None) -> None:
    """Run a repo script (path relative to ROOT) with DATA_ROOT as the working directory.

    The scripts use relative data/... paths, so the working directory decides
    which data they touch. In the frozen desktop app there is no python.exe to
    launch, so the script runs in this process instead (same effect).
    """
    script, args = ROOT / cmd[0], cmd[1:]
    log(f"$ {' '.join(cmd)}")
    if dry_run:
        return
    extra_env = {"PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1", "COLUMNS": "160", **(env or {})}
    if getattr(sys, "frozen", False):
        code = _run_in_process(script, args, extra_env)
    else:
        code = subprocess.run([sys.executable, str(script), *args], cwd=DATA_ROOT,
                              env={**os.environ, **extra_env}).returncode
    if code != 0:
        raise StepFailed(step, f"`{' '.join(cmd)}` exited with code {code}", section)


def _run_in_process(script: Path, args: list[str], extra_env: dict) -> int:
    import runpy

    saved = (os.getcwd(), sys.argv, dict(os.environ))
    os.chdir(DATA_ROOT)
    sys.argv = [str(script), *args]
    os.environ.update(extra_env)
    try:
        runpy.run_path(str(script), run_name="__main__")
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    finally:
        os.chdir(saved[0])
        sys.argv = saved[1]
        os.environ.clear()
        os.environ.update(saved[2])


def load_json_list(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a JSON list")
    return data


def backup(path: Path, stamp: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    log(f"backed up {path.name} -> {dest.relative_to(DATA_ROOT)}")
    return dest


def db_years(url: str) -> set[int]:
    import sqlalchemy as sa

    engine = sa.create_engine(url)
    try:
        with engine.connect() as conn:
            if not sa.inspect(conn).has_table("physician_volumes"):
                raise RuntimeError("physician_volumes table missing (run migrations)")
            return {r[0] for r in conn.execute(sa.text("SELECT DISTINCT year FROM physician_volumes"))}
    finally:
        engine.dispose()


# ── steps ────────────────────────────────────────────────────────────────

def step_preflight(state: dict) -> None:
    missing = []
    for mod in ["httpx", "rich", "yaml", "requests", "sqlalchemy"]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise StepFailed("preflight", f"missing Python packages: {', '.join(missing)}", "Preflight")

    for path in [TVT_FILE, DISCOVERED_FILE, HISTORICAL_DIR]:
        if not path.exists():
            raise StepFailed("preflight", f"{path.relative_to(DATA_ROOT)} not found", "Preflight")
    load_json_list(TVT_FILE)
    load_json_list(DISCOVERED_FILE)
    log("packages and data files OK")

    from db import database_url, describe

    url = database_url()
    state["db_url"] = None
    try:
        years = db_years(url)
        state["db_url"] = url
        log(f"database OK: {describe(url)} (physician_volumes years: {sorted(years) or 'none'})")
    except Exception as e:
        log(f"WARNING: database not usable ({type(e).__name__}: {e}); step 6 will be skipped.\n"
            f"  Using {describe(url)}. Docker: cd docker && docker compose start postgres. "
            "Standalone: start the app once (it creates the database), or see the runbook.")


def step_freshness(state: dict) -> None:
    from doctor_prospector.freshness.probes import run_all_probes

    tvt = load_json_list(TVT_FILE)
    local_period = next((h.get("reporting_period") for h in tvt if h.get("reporting_period")), None)
    results = asyncio.run(run_all_probes(local_period))
    state["manual_actions"] = []
    state["tvt_has_new_data"] = False
    for r in results:
        log(f"  {r.source_name:34} {r.status:15} {r.message}")
        if r.status in ("new_data", "stale_uuid"):
            if r.source_name == "tvt_registry":
                state["tvt_has_new_data"] = True
            else:
                state["manual_actions"].append(f"{r.source_name}: {r.message}")
    if state["manual_actions"]:
        log("\nNEW UPSTREAM DATA needs a config update before it can be loaded:")
        for a in state["manual_actions"]:
            log(f"  - {a}")
        log(f"  See {RUNBOOK} > 'When a source publishes new data'. Continuing with current config.")


def step_tvt(state: dict, args) -> None:
    if not (args.tvt or state.get("tvt_has_new_data")):
        log("skipped (TVT has no new reporting window; use --tvt to force)")
        return
    old = load_json_list(TVT_FILE)
    tmp = OUTPUT / "all_hospitals.scrape.json"
    run(["full_scrape_tvt.py", "--output", str(tmp)], "tvt", "TVT Registry scrape", args.dry_run)
    if args.dry_run:
        return
    new = load_json_list(tmp)
    with_volume = sum(1 for h in new if h.get("annual_tavr_volume"))
    problems = []
    if len(new) < max(100, int(len(old) * 0.9)):
        problems.append(f"only {len(new)} hospitals (had {len(old)})")
    if new and with_volume / len(new) < 0.8:
        problems.append(f"only {with_volume}/{len(new)} have a TAVR volume")
    if not any(h.get("reporting_period") for h in new):
        problems.append("no reporting_period found")
    if problems:
        raise StepFailed("tvt", "TVT scrape looks broken (" + "; ".join(problems) +
                         f"). Kept the old file; scrape saved to {tmp.relative_to(DATA_ROOT)}",
                         "TVT Registry scrape")
    backup(TVT_FILE, state["stamp"])
    tmp.replace(TVT_FILE)
    log(f"TVT: {len(old)} -> {len(new)} hospitals, period {new[0].get('reporting_period')}")
    state["tvt_replaced"] = True


def step_tavr_history(state: dict, args) -> None:
    from download_cms_data import CMS_DATASETS

    have = {int(p.stem.split("_CY")[-1]) for p in HISTORICAL_DIR.glob("Medicare_Provider_Util_Payment_PUF_CY*.txt")}
    configured = {y for y, uuid in CMS_DATASETS.items() if uuid != "check"}
    # Only years at/after what we already track (older years aren't used by the app)
    wanted = sorted(y for y in configured - have if not have or y > min(have))
    if not wanted:
        log(f"up to date (local years {min(have)}-{max(have)})")
        return
    for year in wanted:
        run(["download_cms_data.py", "--years", f"{year}-{year}"], "tavr_history", "TAVR historical files", args.dry_run)
        if args.dry_run:
            continue
        f = HISTORICAL_DIR / f"Medicare_Provider_Util_Payment_PUF_CY{year}.txt"
        if not f.exists() or sum(1 for _ in f.open(encoding="utf-8")) < 100:
            raise StepFailed("tavr_history", f"download of {year} produced no usable file", "TAVR historical files")
        log(f"CY{year}: {f.stat().st_size // 1024} KB")
        state["new_tavr_history"] = True


def step_hospitals(state: dict, args) -> None:
    before = load_json_list(DISCOVERED_FILE)
    if not args.dry_run:
        backup(DISCOVERED_FILE, state["stamp"])
    for flag in ["--add", "--resolve-pos", "--resolve-practices", "--enrich-pos"]:
        run(["discover_non_tvt_hospitals.py", flag], "hospitals", "Hospital discovery", args.dry_run)
    if args.dry_run:
        return
    after = load_json_list(DISCOVERED_FILE)
    if len(after) < len(before):
        raise StepFailed("hospitals", f"discovered sites dropped from {len(before)} to {len(after)}", "Hospital discovery")
    tvt = load_json_list(TVT_FILE)
    if sum(1 for h in tvt if h.get("ccn")) < len(tvt) * 0.7:
        raise StepFailed("hospitals", "fewer than 70% of TVT hospitals got CMS facility data", "Hospital discovery")
    log(f"discovered sites: {len(before)} -> {len(after)}")


def step_db_history(state: dict, args) -> None:
    from import_puf import API_DATASETS

    url = state.get("db_url")
    if not url:
        log("skipped (database not reachable)")
        state["db_skipped"] = True
        return
    have = db_years(url)
    # Track from the oldest year already loaded; an empty table gets the last 6 years
    first_year = min(have) if have else max(API_DATASETS) - 5
    candidates = {y for y in API_DATASETS if y >= first_year}
    wanted = sorted(candidates if args.reimport_history else candidates - have)
    if not wanted:
        log(f"up to date (years {min(have)}-{max(have)})")
        return
    log(f"importing years {wanted} (~6-10 min each)")
    for year in wanted:
        run(["scripts/import_puf.py", "--api", "--years", str(year)], "db_history", "Physician history import",
            args.dry_run, env={"DATABASE_URL": url})
        if args.dry_run:
            continue
        if year not in db_years(url):
            raise StepFailed("db_history", f"year {year} has no rows after import", "Physician history import")


def step_cache(state: dict, args) -> None:
    cmd = ["scripts/refresh_cache.py"] + (["--skip-nppes"] if args.skip_nppes else [])
    run(cmd, "cache", "Cache refresh", args.dry_run)


def step_summary(state: dict, args) -> None:
    tvt = load_json_list(TVT_FILE)
    disc = load_json_list(DISCOVERED_FILE)
    practices = sum(1 for h in disc if h.get("site_type") == "practice")
    unnamed = sum(1 for h in disc if h.get("name", "").startswith("TAVR Site -"))
    summary = {
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "tvt_hospitals": len(tvt),
        "tvt_reporting_period": next((h.get("reporting_period") for h in tvt if h.get("reporting_period")), None),
        "tvt_with_cms_facility": sum(1 for h in tvt if h.get("ccn")),
        "discovered_sites": len(disc),
        "discovered_hospitals": len(disc) - practices - unnamed,
        "discovered_practices": practices,
        "discovered_unidentified": unnamed,
        "physician_history_years": sorted(db_years(state["db_url"])) if state.get("db_url") else None,
        "manual_actions": state.get("manual_actions", []),
    }
    for k, v in summary.items():
        log(f"  {k:28} {v}")
    if not args.dry_run:
        (OUTPUT / "last_refresh.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log("\nRestart the API (or POST /api/v1/hospitals/reload) so it picks up the new hospital files.")


# ── main ─────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tvt", action="store_true", help="Re-scrape the TVT Registry even if no new window was detected")
    parser.add_argument("--skip-nppes", action="store_true", help="Skip re-fetching cached NPI records")
    parser.add_argument("--reimport-history", action="store_true", help="Re-import every configured history year")
    parser.add_argument("--only", help=f"Comma-separated subset of steps: {','.join(STEPS)}")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without changing anything")
    args = parser.parse_args()

    selected = STEPS if not args.only else [s.strip() for s in args.only.split(",")]
    unknown = set(selected) - set(STEPS)
    if unknown:
        parser.error(f"unknown step(s): {', '.join(sorted(unknown))}")
    # preflight always runs; freshness feeds the TVT decision
    for required in ["preflight"]:
        if required not in selected:
            selected.insert(0, required)

    state: dict = {"stamp": datetime.now().strftime("%Y%m%d-%H%M%S")}
    titles = {
        "preflight": "Preflight", "freshness": "Upstream freshness", "tvt": "TVT Registry",
        "tavr_history": "TAVR historical files", "hospitals": "Hospital discovery & enrichment",
        "db_history": "Physician history (database)", "cache": "Cache refresh", "summary": "Summary",
    }
    funcs = {
        "preflight": lambda: step_preflight(state),
        "freshness": lambda: step_freshness(state),
        "tvt": lambda: step_tvt(state, args),
        "tavr_history": lambda: step_tavr_history(state, args),
        "hospitals": lambda: step_hospitals(state, args),
        "db_history": lambda: step_db_history(state, args),
        "cache": lambda: step_cache(state, args),
        "summary": lambda: step_summary(state, args),
    }
    start = time.time()
    try:
        for i, step in enumerate(STEPS, 1):
            if step in selected:
                header(i, titles[step])
                funcs[step]()
    except StepFailed as e:
        log(f"\nREFRESH STOPPED at step '{e.step}': {e}")
        log(f"Data files were backed up to {BACKUP_DIR} before any change.")
        log(f"How to fix: {RUNBOOK} > '{e.runbook_section}'")
        return 1
    log(f"\nRefresh complete in {(time.time() - start) / 60:.1f} min"
        + (" (database steps skipped)" if state.get("db_skipped") else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
