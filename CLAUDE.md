# CLAUDE.md - Instructions for Claude Code

## Project Context

You're building Doctor Prospector - a **modular, plugin-based** Python CLI tool that aggregates public healthcare data to generate prospect lists for medical device sales.

**Read PDR.md first** - it contains the full requirements, plugin architecture, and configuration specs.

## Key Architecture Principle

**Everything is a plugin.** Data sources are modular and can be added/removed without touching core logic. This is non-negotiable - Wolf builds everything this way.

## Quick Start

Two ways to run it (details in README.md):
- **Docker** (PostgreSQL + Redis + nginx): `cd docker && docker compose up -d --build`, then http://localhost:3100
- **Standalone** (SQLite, one port): `install.ps1` / `install.sh`, then `run.ps1` / `run.sh`, then http://localhost:8000
- **Windows desktop app** (bundled Python, own window): `desktop\build.ps1` builds `dist\installer\DoctorProspector-Setup-<version>.exe`. Entry point `desktop/launcher.py`; user data in `%LOCALAPPDATA%\DoctorProspector` via `DOCTOR_PROSPECTOR_HOME` (see `src/doctor_prospector/paths.py`). Our code ships as plain source files (see `desktop/DoctorProspector.spec`), so anything that discovers files by path keeps working.

Code must work on both databases: use `app/db/types.py` (`JSONType`, `UUIDType`) in models and migrations, never postgresql-only types or SQL. Tests: `python -m pytest` (from the repo root).

---

## Development Order

### 1. Core Infrastructure (Do This First)

**a) Plugin Base Class** (`src/doctor_prospector/sources/base.py`)
```python
from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime

class DataSourcePlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def provides(self) -> list[str]: ...  # 'hospitals', 'physicians', 'payments', 'trials'
    
    @abstractmethod
    async def fetch(self, **filters) -> list[dict[str, Any]]: ...
    
    @abstractmethod
    def get_cache_key(self, **filters) -> str: ...
    
    @property
    @abstractmethod
    def cache_ttl_hours(self) -> int: ...
    
    @property
    def requires_auth(self) -> bool:
        return False
    
    @property
    def enabled(self) -> bool:
        return True  # Override via config
```

**b) Source Registry** (`src/doctor_prospector/sources/registry.py`)
- Auto-discover plugins in sources/ directory
- Enable/disable via config.yaml
- Get sources by data type they provide

**c) Cache Layer** (`src/doctor_prospector/cache/sqlite_cache.py`)
- Generic async SQLite cache
- Key-value with TTL
- Source-aware (can clear by source name)

**d) Config Loader** (`src/doctor_prospector/config.py`)
- Load config.yaml
- Validate with Pydantic
- Provide defaults

### 2. First Data Source Plugin

**TVT Registry** (`src/doctor_prospector/sources/tvt_registry.py`)
- Implements DataSourcePlugin
- Scrapes https://tvtpublicreporting.sts.org/tvt-registry
- Handles pagination (17+ pages)
- Returns list of Hospital dicts
- Check network tab first - there may be an XHR/JSON endpoint

### 3. Data Models (Already Partially Done)

Verify/update `src/doctor_prospector/models/`:
- Hospital, Physician, Prospect models exist
- Add any fields needed by new sources
- Keep models source-agnostic

### 4. Pipeline Orchestrator

**Pipeline** (`src/doctor_prospector/pipeline.py`)
```python
class Pipeline:
    def __init__(self, config: Config):
        self.config = config
        self.cache = SQLiteCache(config.cache_path)
        self.registry = SourceRegistry()
    
    async def run(self, filters: dict) -> list[Prospect]:
        # 1. Fetch from all enabled sources (parallel)
        # 2. Merge/enrich data
        # 3. Score prospects
        # 4. Apply filters
        # 5. Return sorted by fit score
```

### 5. Remaining Source Plugins

Build these one at a time, each as standalone plugin:

| Order | Plugin | File | Provides |
|-------|--------|------|----------|
| 1 | TVT Registry | `tvt_registry.py` | hospitals |
| 2 | NPPES | `nppes.py` | physicians |
| 3 | CMS Utilization | `cms_utilization.py` | physicians |
| 4 | Open Payments | `open_payments.py` | payments |
| 5 | ClinicalTrials.gov | `clinical_trials.py` | trials |

### 6. Enrichment Logic

**Physician Matcher** (`src/doctor_prospector/enrichment/physician_matcher.py`)
- Match physicians to hospitals (fuzzy name matching)
- Handle "NYU Langone" vs "NYU Langone Health"
- Use NPI as authoritative link when available

### 7. Output Writers

- Excel writer (openpyxl) - primary
- JSON writer - secondary
- Both implement common interface

### 8. CLI

Use typer + rich. Commands:
- `sources list` / `sources status`
- `fetch <source_name>`
- `run` (full pipeline)
- `generate` (from cache only)
- `cache status` / `cache clear`
- `config validate` / `config show`

---

## Code Style

- Type hints everywhere
- Async by default (httpx async client)
- Pydantic for models AND config validation
- Rich for CLI output
- Docstrings on public methods only

## API Reference

### NPPES API
```python
httpx.get("https://npiregistry.cms.hhs.gov/api/", params={
    "version": "2.1",
    "number": "1234567890",  # or search params
    "state": "NJ",
    "taxonomy_description": "Interventional Cardiology"
})
```

### Open Payments API
```python
httpx.get("https://openpaymentsdata.cms.gov/api/1/datastore/query/physician-general-payments", params={
    "filters[covered_recipient_npi]": "1234567890",
    "filters[applicable_manufacturer_or_applicable_gpo_making_payment_name]": "Edwards Lifesciences"
})
```

### ClinicalTrials.gov API v2
```python
httpx.get("https://clinicaltrials.gov/api/v2/studies", params={
    "query.term": "TAVR OR transcatheter aortic valve",
    "query.locn": "New Jersey",
    "filter.overallStatus": "RECRUITING"
})
```

---

## Testing Strategy

- Unit tests for: scoring algorithm, config loading, cache operations
- Integration tests for sources: use respx to mock httpx responses
- Fixtures in `tests/fixtures/` for sample API/HTML responses
- Each source plugin should have its own test file

---

## Common Pitfalls

1. **TVT Registry may need JS rendering** - Check XHR first, fallback to playwright
2. **NPPES rate limit** - 100/min, implement exponential backoff in base class
3. **Hospital name normalization** - Critical for matching; build a normalizer utility
4. **Physician name variants** - "John Smith MD" vs "John A. Smith, M.D."
5. **Cache invalidation** - Always check TTL; stale data is worse than slow data

---

## Adding a New Source (Future)

1. Create `src/doctor_prospector/sources/new_source.py`
2. Implement `DataSourcePlugin` interface
3. Add config section to `config.yaml`
4. Register in `sources/__init__.py` (or use auto-discovery)
5. Add tests with mocked responses

That's it. No changes to pipeline, CLI, or other sources needed.

---

## File Locations

- Config: `config.yaml` (project root)
- Cache: `data/cache/doctor_prospector.db`
- Output: `data/output/*.xlsx`
- Reference data: `data/output/reference_prospect_list.xlsx` (manual example)

---

## Refreshing Data

Run `python scripts/refresh_all.py` (Postgres must be up for the history step). If it fails, or a source publishes new data, follow **docs/DATA_REFRESH_RUNBOOK.md**: it covers every step, how to load new CMS/Open Payments releases, and past failures with their fixes. Never hand-edit files in `data/output/`; they're generated by scripts.

---

## Questions? 

If blocked:
- TVT scraping approach → check if JSON endpoint exists first
- Source priority → TVT Registry is MVP, others are enrichment
- Geography focus → any US market; start from known warm leads
