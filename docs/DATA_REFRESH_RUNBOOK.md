# Data Refresh Runbook

**Who this is for:** a developer, or an AI coding assistant working in this repo, who needs to refresh the public data behind Doctor Prospector, or fix `scripts/refresh_all.py` when it stops working.

**If you're an AI assistant:** read this whole file before changing anything. Work from the repo root. The sections below match the step names `refresh_all.py` prints when it fails. When upstream data changes shape, fix the code that reads it. Don't hand-edit the data files: every data file here is produced by a script, and it has to stay reproducible.

Last verified end to end: **2026-10-01**.

---

## 1. Quick start

```bash
# Standalone (SQLite): nothing to start. Use .venv\Scripts\python (Windows) or .venv/bin/python.
# Docker (Postgres):   cd docker && docker compose start postgres && cd ..
python scripts/refresh_all.py                          # normal refresh (~10-15 min)
python scripts/refresh_all.py --tvt                    # also re-scrape TVT (+~8 min)
python scripts/refresh_all.py --dry-run                # show the plan, change nothing
python scripts/refresh_all.py --only hospitals,cache   # run selected steps
```

Then restart the API (or `POST /api/v1/hospitals/reload`) so it reloads the hospital files.

On success the script writes `data/output/last_refresh.json` with counts. Before changing any data file, it saves a copy to `data/output/backups/`. To roll back, copy the backup over the file, or use `git checkout -- data/output/*.json` (both hospital JSON files are tracked in git).

## 2. What each source is and how it's loaded

| Source | Used for | Loaded by | Stored in | Upstream schedule |
|---|---|---|---|---|
| STS/ACC TVT Registry (tvtpublicreporting.sts.org) | TAVR hospital volume, star rating | `full_scrape_tvt.py` (HTML scrape, ~8 min) | `data/output/all_hospitals.json` | Yearly; 3-year window published ~15 months after it closes (recent releases appeared between late summer and February) |
| CMS Physician & Other Practitioners, by Provider and Service | Physician procedure counts | Live API, `sources/cms_utilization.py` | SQLite cache | Yearly, ~17 months after year end (spring) |
| Same dataset, older years | Physician volume history, all profiles | `scripts/import_puf.py --api` | `physician_volumes` table (SQLite file or Postgres) | Yearly |
| Same dataset, TAVR codes only | Legacy TAVR history and new-site discovery | `download_cms_data.py` | `data/cms_historical/*.txt` (tracked in git) | Yearly |
| CMS Medicare Inpatient Hospitals by Provider and Service (DRG) | Hospital volume for non-TAVR profiles | Live API, `sources/cms_drg.py` | SQLite cache | Yearly |
| CMS Provider of Services (POS), "Quality Improvement and Evaluation System" variant | Beds, cath lab, CCN, names | `sources/cms_pos.py` + `discover_non_tvt_hospitals.py --enrich-pos` | Fields inside both hospital JSON files | Quarterly |
| CMS Hospital Compare `xubh-q36u` | 1-5 star rating | Live, `sources/cms_hospital_compare.py` | Memory | Several times a year |
| CMS Doctors & Clinicians `mj5m-pzi6` and affiliations `27ea-46a8` | Practice names, hospital affiliations | `discover_non_tvt_hospitals.py --resolve-practices` | Fields in `cms_discovered_hospitals.json` | Monthly |
| NPPES NPI Registry | Current address, specialty, gender | Live, `sources/nppes.py` | SQLite cache (30 days) | Live |
| CMS Open Payments | Industry payments | Live, `sources/open_payments.py` | SQLite cache | Yearly, published June 30 for the prior year |
| ClinicalTrials.gov API v2 | Trials | Live, `sources/clinical_trials.py` | SQLite cache (24 h) | Live |

The SQLite cache is at `data/cache/doctor_prospector.db`. Paths resolve from the repo root (`src/doctor_prospector/paths.py`), so the app finds the same files whichever folder it starts in.

## 3. The steps (in `refresh_all.py` order)

Each step checks its result (files, counts, database rows) rather than trusting exit codes, because several of these scripts print an error and still exit 0.

### Preflight
Checks for the Python packages (`httpx rich yaml requests sqlalchemy`), the data files, and the database.
- **Missing package:** run the installer again (`install.ps1` / `install.sh`), or `pip install -e . -e ./backend` inside `.venv`.
- **Which database:** `scripts/db.py` picks it in this order: `DATABASE_URL` env var, then the root `.env` (standalone; SQLite `data/doctor_prospector.db` by default), then `docker/.env` (Docker Postgres on localhost), then the SQLite default. The preflight line prints which one it used, without the password.
- **Database not reachable:** step 6 is skipped with a warning. Docker: `cd docker && docker compose start postgres`. Standalone: there's nothing to start; see the next point.
- **Database exists but has no tables:** start the app once (it migrates on startup), or `cd backend` and run `python -m alembic upgrade head` with `PYTHONPATH="../src;."` (`:` instead of `;` on macOS/Linux). Set `DATABASE_URL` first if you're targeting Postgres.

### Upstream freshness
Runs `src/doctor_prospector/freshness/probes.py::run_all_probes()`. A `new_data` result for a CMS source means a new release exists but **is not loaded until you update the config**. See section 4.
- **Probe reports an absurd "newer" date** (for example 2011): the CMS catalog lists each yearly or quarterly release as a *separate* dataset entry, oldest first. `_latest_catalog_release()` must scan every matching entry and pick the latest date. Never take the first match.
- **Catalog download fails:** `https://data.cms.gov/data.json` is about 30 MB and sometimes slow. Retry it. The probe is informational, so the refresh continues.

### TVT Registry scrape
Runs only with `--tvt`, or when the probe sees a new reporting window. It scrapes to `data/output/all_hospitals.scrape.json` and validates the result: at least 90% of the previous hospital count (minimum 100), at least 80% with a TAVR volume, and a reporting period present. Only then does it replace `all_hospitals.json`. The raw scrape has no CMS facility fields; the Hospital discovery step adds them back.
- **Validation failed:** the site layout probably changed. Compare the saved example pages in `docs/tvt-reference/` (the registry list page and two hospital detail pages) with the live site, then fix the parser in `src/doctor_prospector/sources/tvt_registry.py`. `docs/TVT_Recon_Findings.md` documents the page structure. The old file is untouched.
- **403 or timeouts:** the scraper waits 1.5 s between pages. Don't lower that.

### TAVR historical files
Downloads any year configured in `download_cms_data.py::CMS_DATASETS` that isn't yet in `data/cms_historical/`. The file holds the TAVR codes only (33361-33369, about 3,000 rows a year).
- `download_cms_data.py --years` requires a **range**: `--years 2025-2025`, never `--years 2025`.
- New year: add `YEAR: "uuid"` to `CMS_DATASETS`. See section 4.

### Hospital discovery
Four passes of `discover_non_tvt_hospitals.py`, in this order:
1. `--add`: finds TAVR billing addresses in the historical files that aren't TVT hospitals, and adds new *cities* only (deduplicated by city and state). New entries are named `TAVR Site - City, ST`.
2. `--resolve-pos`: names those sites by matching their address to CMS POS hospitals. Tier 1 is an exact address, tier 2 is street number plus street name, tier 3 is the only hospital in the ZIP (medium confidence, and flagged in the UI).
3. `--resolve-practices`: most remaining sites are **physician group offices**, not hospitals, because CMS reports where doctors *bill*. This pass batch-queries CMS Doctors & Clinicians for the site's physicians. The group registered at that address becomes the name, with `site_type: "practice"`. It also records `affiliated_hospitals` (CCNs, mapped to names through POS). Sites still named `TAVR Site - …` afterwards are genuinely unidentifiable.
4. `--enrich-pos`: attaches POS facility fields (`ccn`, `bed_count`, `has_cath_lab`, …) to every hospital in both files. Matching tries, in order: address, then name plus city, then a unique exact name within the state (this catches hospitals that moved, such as Valley Hospital, Ridgewood to Paramus).

Validation: the discovered count must not shrink, and at least 70% of TVT hospitals must get a CCN (normally about 86%).
- **POS returns 0 hospitals, or the counts collapse:** the POS dataset UUID rotated or the schema changed. Use the **"Quality Improvement and Evaluation System"** variant, *not* "Internet Quality Improvement…" (iQIES), which has different lowercase field names. Update `BASE_URL` and `DATA_PERIOD` in `sources/cms_pos.py`.
- **Doctors & Clinicians errors:** use `POST /provider-data/api/1/datastore/query/{id}/0` with a JSON body `{"conditions":[{"property":"npi","operator":"in","value":[...]}],"limit":500}`, in batches of 100 NPIs. GET with many conditions fails, and one request per NPI takes about 8 s each.
- **Never** let `--resolve-pos` overwrite a `site_type: "practice"` record. A guard in `resolve_hospital_names_pos()` prevents it.

### Physician history import
Imports each configured year from `scripts/import_puf.py::API_DATASETS` that's missing from `physician_volumes` (SQLite or Postgres), fetching only the device-profile HCPCS codes (`ALL_PROFILE_HCPCS`) through the CMS Data API, about 6-10 min per year. The alternative, `--download`, pulls a ~3 GB CSV per year and is rarely worth it.
- **Long runs:** each year is a separate run, so earlier years are safe if a later one fails. Re-run to continue. API responses are saved to `data/cms_api/api_CY{year}.csv`, and `python scripts/import_puf.py --file data/cms_api/api_CY2024.csv` re-imports without re-fetching.
- **New device profile with new procedure codes:** add the codes to `ALL_PROFILE_HCPCS`, then `python scripts/refresh_all.py --only db_history --reimport-history`.
- `--reimport-history` re-imports every year from the oldest one already loaded.

### Cache refresh
`scripts/refresh_cache.py` clears cached results that depend on newly loaded data (Open Payments, historical, trials) and drops expired entries. It then re-fetches every cached NPPES physician at about 92 a minute, because NPPES allows about 100 a minute: roughly 7 min for 600 doctors. `--skip-nppes` skips the re-fetch.
- **Many NPPES failures** (it exits 1 above 10%): NPPES is down or rate-limiting. Wait and re-run `--only cache`.

## 4. When a source publishes new data

The probes tell you *that* something is new. Loading it is a small, deliberate code change, so a bad upstream release can't slip in silently. In every case, update the **dataset ID and its data-period label together**, because the UI's data-age notices read those labels.

**CMS datasets (utilization, DRG, POS).** Find the new release in `https://data.cms.gov/data.json`. Each release is its own `dataset` entry titled `"<name> : YYYY-MM-DD"`, and its `distribution[].accessURL` contains `/data-api/v1/dataset/<UUID>/data`. Confirm the year from the entry's `temporal` field. The title date is not the data year. Then:
- **Physician utilization:** in `sources/cms_utilization.py`, update `BASE_URL` and `DATA_PERIOD`. Also add the year to `API_DATASETS` and `PUF_URLS` in `scripts/import_puf.py` (the CSV link is the `text/csv` distribution), and to `CMS_DATASETS` in `download_cms_data.py`.
- **Inpatient DRG:** in `sources/cms_drg.py`, update `BASE_URL` and `DATA_PERIOD`.
- **POS:** in `sources/cms_pos.py`, update `BASE_URL` and `DATA_PERIOD`, using the non-iQIES variant.
- Sanity-check before committing: query the new UUID with a known NPI or CCN and compare the field names against the old UUID.

**Open Payments.** `GET https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items?show-reference-ids=false` and find `"<YEAR> General Payment Data"`. Add `YEAR: "identifier"` to `GENERAL_PAYMENTS_DATASETS` in `sources/open_payments.py`. Check that the fields match by querying `/api/1/datastore/query/<id>/0` with `conditions[0][property]=covered_recipient_npi`. CMS also **retires old program years** (2018 went away in 2026); the probe reports a configured year that's no longer in the catalog as `stale_uuid`, so delete that line from the map. A retired year otherwise 404s on every payments lookup.

**TVT Registry.** Nothing to configure: `python scripts/refresh_all.py --tvt`.

Then run `python scripts/refresh_all.py`.

## 5. Things that broke before, and the fix

| Symptom | Cause | Fix (already in code) |
|---|---|---|
| Hospital pages with blank beds, cath lab, ratings | About half the "TAVR Site" records were physician offices (CMS billing addresses) | `--resolve-practices`, `site_type: "practice"` |
| A real hospital has no facility data | NPPES or TVT name and address differ from POS | Name fallback plus unique-in-state exact name in `CMSPOSSource.match_by_name` |
| Gender always blank | NPPES v2.1 renamed `basic.gender` to `basic.sex` | `sources/nppes.py` reads `sex`, falls back to `gender` |
| Physician trials unrelated ("John Brown", 200 hits) | Name passed as plain keywords | Investigator search via `AREA[OverallOfficialName]`, `AREA[LocationContactName]`, `AREA[ResponsiblePartyInvestigatorFullName]`, plus a check that one person carries both names (`trial_service.py`) |
| Hospital trials unrelated (cardiology trial for "da Vinci") | Terms matched *site names* ("Da Vinci Maganklinika") | Terms searched only in study-text fields (`ClinicalTrialsSource.STUDY_TEXT_FIELDS`); multi-word terms quoted |
| Physician detail took 20-104 s | One CMS request per HCPCS code | One NPI-filtered request, filtered locally; state searches use 4 parallel requests |
| Freshness probe said a "newer" 2011 release | Took the first catalog match | `_latest_catalog_release()` picks the newest |
| Robotic Surgery history empty | `physician_volumes` never populated | `import_puf.py --api` |
| Exports had 0 volume or blank hospitals for non-TAVR profiles | Exports read only the TVT file and `annual_tavr_volume` | Export uses the profile-aware hospital list and falls back to `drg_volume` |
| App started from `backend/` saw an empty cache | Relative `data/...` paths | `doctor_prospector/paths.py`; backend settings anchored to the repo root |
| No hospital had a CMS star rating | Hospital Compare (provider-data API) rejects `limit` > 1500 with HTTP 400, and the error was swallowed | `CMSHospitalCompareSource.PAGE_SIZE = 1500`. The `data-api/v1` datasets (POS, DRG, utilization) still accept 5000 |
| Cardiac hospitals showed "no cath lab / no open heart" | POS service codes are 0 none, 1 staff, 2 under arrangement, 3 both; only `"1"` was counted | `_service()` in `CMSPOSSource._parse_pos_record` (1/2/3 = yes, 0 = no, blank = unknown) |
| POS fixes never reached discovered hospitals | `--enrich-pos` skipped records that already had a CCN | Re-applies POS fields by CCN every run |
| TVT scrape could wipe the hospital list | `full_scrape_tvt.py` overwrote the file directly | refresh_all scrapes to `--output` a temp file, validates it, then swaps |
| Standalone: profile pages 500 on SQLite | IDs passed as strings; SQLite's UUID type needs `uuid.UUID` | `app.db.types.UUIDType` converts strings |
| Postgres-only SQL in migrations (JSONB casts, `gen_random_uuid()`) | Written for Docker only | Portable types and Python data migrations in `app/db/types.py`; verified identical schema on a fresh Postgres |
| `UnicodeDecodeError` on Windows | Files opened without `encoding="utf-8"` | Always pass `encoding="utf-8"` |
| Background job "killed" mid-import | Tool or CI time limits | Run one year at a time (refresh_all already does this) |

## 6. Verify after any refresh

```bash
python -m pytest -q                                     # all tests pass
cd frontend && npx tsc --noEmit -p . && npx eslint . && cd ..
cat data/output/last_refresh.json
```
Expected ranges as of 2026-10: about 293 TVT hospitals with about 250 matched to CMS; about 600 discovered sites (about 290 hospitals, 185 practices, 125 unidentified); history 2019-2024 at about 25-28k rows a year; Open Payments through 2025.

With the API running, spot-check:
- `GET /api/v1/sources/vintage`: data periods match what you loaded.
- `GET /api/v1/hospitals?state=NJ`: Morristown Medical Center appears with `ccn` 310015 and few `data_flags`.
- `GET /api/v1/hospitals/923009/physicians`: physicians have `gender`.
- Activate the Robotic Surgery profile, then `GET /api/v1/physicians/{npi}/history`: years through the latest import.

## 7. Data warnings (UI flags)

Rules live in `backend/app/services/data_flags.py` (tests in `tests/test_data_matching.py::TestDataFlags`). The API always returns `data_flags`; the UI shows them unless the user turns off **Settings > Preferences > Show data warnings** (`show_data_flags`). The user-facing explanation is the "About the Data" section of the Help page (`frontend/src/components/help/AboutTheData.tsx`). Keep it in sync when you add or change a rule.

## 8. Shipping refreshed data in a new Windows installer

The desktop app ships a copy of the data: the hospital JSON files, `data/cms_historical/`, and the physician-history snapshot `data/seed/physician_volumes.csv.gz`. It copies them to `%LOCALAPPDATA%\DoctorProspector` on first run. After a refresh, to put the new data in the next installer:

1. `python scripts/refresh_all.py` (plus `--tvt` if TVT published a new window).
2. `python scripts/history_seed.py export` rewrites the snapshot from the database you just refreshed.
3. Set `data/seed/VERSION` to today's date (`YYYY-MM-DD`). On upgrade, installed apps replace their hospital files with the bundled ones only if this is newer *and* the user hasn't run their own refresh since. `config.yaml` is never overwritten.
4. Bump `version` in `backend/pyproject.toml` (it becomes the installer version).
5. `powershell -ExecutionPolicy Bypass -File desktop\build.ps1 [-SignCommand '...$f...']` produces `dist\installer\DoctorProspector-Setup-<version>.exe`.

Desktop-app troubleshooting: logs are in `%LOCALAPPDATA%\DoctorProspector\logs` (`app.log`; `console.log` has the server output and tracebacks). If startup fails, the window shows the error and the log path. The Start-menu "Refresh" shortcut runs `DoctorProspector.exe --refresh [refresh_all options]` in-process (the frozen app has no python.exe), so refresh_all's `run()` uses `runpy` when `sys.frozen` is set.
