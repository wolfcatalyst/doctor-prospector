# Doctor Prospector

Prospecting for medical device sales reps. Doctor Prospector pulls public healthcare data (CMS Medicare claims, the STS/ACC TVT Registry, NPI Registry, Open Payments, ClinicalTrials.gov, PubMed) into one place, so you can find the hospitals and physicians doing the procedures you sell into, see their volumes and trends, check their industry relationships, and export prospect lists.

It works for any procedure: TAVR and Robotic Surgery come built in, and you can add your own device profiles (procedure codes, DRGs, specialties, trial search terms).

> All data is public and needs no accounts or API keys. Public data lags: claims data is about 17 months behind, and the TVT Registry is published yearly. Help > About the Data in the app explains each source and its known gaps.

## Install

**Windows: download `DoctorProspector-Setup-<version>.exe` from [Releases](../../releases) and run it.** It installs everything it needs (no Python, Node or Docker), adds Start-menu shortcuts, and opens in its own window. The physician history comes preloaded, so it's ready the moment it opens.

Other ways to run it:

| | Docker | From source (scripts) |
|---|---|---|
| You need | Docker Desktop (or Rancher Desktop) | Python 3.11+ (and Node.js 20+ unless your copy includes `frontend/dist`) |
| Runs | PostgreSQL, Redis, nginx in containers | One Python process with a SQLite file |
| Good for | A server or several users | macOS/Linux, or developing it |

### Windows app

- Your data (database, settings, exports, logs) lives in `%LOCALAPPDATA%\DoctorProspector`. Start menu > **Open Doctor Prospector data folder** opens it.
- Start menu > **Refresh Doctor Prospector data** downloads newer public data (it takes a while; a console window shows progress).
- Uninstalling asks whether to keep your data.
- Building the installer yourself: `powershell -ExecutionPolicy Bypass -File desktop\build.ps1` (needs Python 3.11+, Node.js 20+, Inno Setup 6). Add `-SignCommand '...$f...'` to code-sign; see the top of `desktop\build.ps1`.

### Docker

```bash
cp docker/.env.example docker/.env      # then set POSTGRES_PASSWORD and SECRET_KEY
cd docker
docker compose up -d --build
```
Open http://localhost:3100 (API docs: http://localhost:8400/api/docs).

### From source (scripts)

Windows (PowerShell):
```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
powershell -ExecutionPolicy Bypass -File run.ps1
```

macOS / Linux:
```bash
./install.sh
./run.sh
```

The installer creates a virtual environment (`.venv`), installs dependencies, creates `.env` with a random secret key, builds the web pages, creates the database, and loads the physician volume history from the bundled snapshot (seconds). `run` starts the app and opens http://localhost:8000.

Re-running the installer is safe; it keeps your `.venv`, `.env` and database.

## Configuration

| File | Controls |
|---|---|
| `config.yaml` | What the app does: data sources, scoring, manual hospitals, cache |
| `.env` (standalone, from `.env.example`) | How it runs: database (SQLite default, PostgreSQL optional), Redis (optional), login, port |
| `docker/.env` (Docker, from `docker/.env.example`) | Same, for the containers |

Each example file explains every option.

## Keeping data current

```bash
python scripts/refresh_all.py          # use .venv\Scripts\python on Windows, .venv/bin/python on macOS/Linux
```
Refreshes hospitals, physician history and cached lookups in order, and checks every step. When a source publishes a new year or quarter, follow `docs/DATA_REFRESH_RUNBOOK.md`. It's written so an AI coding assistant can follow it too.

## Project status

Provided as-is and **not actively maintained**. It's complete and working, and the docs are written so you (or your AI coding assistant) can keep it running and extend it without the author:

- Data refreshes: `scripts/refresh_all.py` and `docs/DATA_REFRESH_RUNBOOK.md`
- Architecture and conventions: `CLAUDE.md`, `PDR.md`

Fork it and change whatever you like. Please don't expect replies to issues or feature requests. If you'd like to **pay for new features** or **use it commercially in a way the license doesn't allow** (see below), reach out through the author's GitHub profile.

## License

Source-available under the [Elastic License 2.0](LICENSE). In plain terms:

- ✅ Use it, including for your own work and business (a sales team running it internally is fine)
- ✅ Modify it, fork it, share it
- ❌ Offer it to others as a hosted or managed service (e.g. run it on a website and charge people to use it)
- ❌ Remove the license or copyright notices

This is a summary; the [LICENSE](LICENSE) file is what applies. Data comes from public sources and keeps its own terms; third-party libraries keep their own licenses.

## Development

```bash
pip install -e ".[dev]" -e ./backend     # inside the venv
python -m pytest
cd frontend && npm run dev               # hot-reloading UI on :5173, proxies the API
```

Architecture notes for contributors are in `CLAUDE.md` and `PDR.md`.
