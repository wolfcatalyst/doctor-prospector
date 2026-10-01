# Doctor Prospector - Project Definition & Requirements

## Project Overview

**Name:** Doctor Prospector  
**Purpose:** Automated pipeline to generate physician-level prospect lists for medical device sales  
**Owner:** Wolf

## Business Context

Built for a medical device sales rep selling into TAVR programs. Key context:

- **Geographic flexibility:** the rep can target any US market (no assigned territory)
- **Warm leads:** existing physician relationships are the natural starting point
- **Strategy:** Start with warm connections, expand concentrically rather than spray-and-pray nationally

## Problem Statement

Medical device sales reps targeting TAVR programs currently rely on:
- Manual research across fragmented public data sources
- Outdated hospital lists from previous employers
- Anecdotal knowledge of KOL relationships

This tool automates the aggregation of publicly available data into actionable prospect lists with fit scoring.

## Target Users

- Medical device sales reps (primary)
- Regional sales directors
- Market access teams

---

## Architecture: Plugin-Based Data Sources

**Design Principle:** All data sources are modular plugins. Sources can be added, removed, or swapped without modifying core pipeline logic.

### Data Source Interface

Every data source implements a common interface:

```python
from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime

class DataSourcePlugin(ABC):
    """Base interface for all data source plugins."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this source."""
        pass
    
    @property
    @abstractmethod
    def provides(self) -> list[str]:
        """List of data types this source provides: 'hospitals', 'physicians', 'payments', 'trials'"""
        pass
    
    @abstractmethod
    async def fetch(self, **filters) -> list[dict[str, Any]]:
        """Fetch data with optional filters (geography, date range, etc.)"""
        pass
    
    @abstractmethod
    def get_cache_key(self, **filters) -> str:
        """Generate cache key for these filter params."""
        pass
    
    @property
    @abstractmethod
    def cache_ttl_hours(self) -> int:
        """How long to cache results."""
        pass
    
    @property
    def requires_auth(self) -> bool:
        """Whether this source needs API keys/credentials."""
        return False
```

### Source Registry

```python
# src/doctor_prospector/sources/registry.py

class SourceRegistry:
    """Central registry for data source plugins."""
    
    _sources: dict[str, DataSourcePlugin] = {}
    
    @classmethod
    def register(cls, source: DataSourcePlugin) -> None:
        cls._sources[source.name] = source
    
    @classmethod
    def get(cls, name: str) -> DataSourcePlugin:
        return cls._sources[name]
    
    @classmethod
    def get_by_type(cls, data_type: str) -> list[DataSourcePlugin]:
        """Get all sources that provide a given data type."""
        return [s for s in cls._sources.values() if data_type in s.provides]
    
    @classmethod
    def list_all(cls) -> list[str]:
        return list(cls._sources.keys())
    
    @classmethod
    def enable(cls, names: list[str]) -> None:
        """Enable only specified sources for a pipeline run."""
        pass
    
    @classmethod
    def disable(cls, name: str) -> None:
        """Disable a source (e.g., if API is down)."""
        pass
```

### Built-in Data Sources

| Source | Plugin Name | Provides | Auth Required | Cache TTL |
|--------|-------------|----------|---------------|-----------|
| STS/ACC TVT Registry | `tvt_registry` | hospitals | No | 168h (weekly) |
| CMS Provider Utilization | `cms_utilization` | physicians | No | 720h (monthly) |
| NPPES NPI Registry | `nppes` | physicians | No | 24h |
| CMS Open Payments | `open_payments` | payments | No | 720h (monthly) |
| ClinicalTrials.gov | `clinical_trials` | trials | No | 24h |

### Adding a New Source

1. Create plugin file in `src/doctor_prospector/sources/`
2. Implement `DataSourcePlugin` interface
3. Register in `sources/__init__.py`
4. Add any new fields to data models if needed

Example - adding a hypothetical conference faculty source:

```python
# src/doctor_prospector/sources/tct_faculty.py

class TCTFacultySource(DataSourcePlugin):
    name = "tct_faculty"
    provides = ["physicians"]
    cache_ttl_hours = 720  # Monthly
    
    async def fetch(self, year: int = 2025, **filters) -> list[dict]:
        # Scrape TCT conference faculty list
        ...
```

---

## Core Features

### Phase 1: MVP
- [ ] Implement plugin architecture for data sources
- [ ] TVT Registry plugin (scrape all ~400 hospitals)
- [ ] Parse hospital data: name, location, volume, star rating, first TAVR date
- [ ] Geography-agnostic filtering (state, city, radius from point, region)
- [ ] Volume tier filtering
- [ ] Export to Excel with formatting

### Phase 2: Physician Enrichment
- [ ] CMS Provider Utilization plugin (TAVR CPT codes 33361-33369)
- [ ] NPPES plugin for physician-hospital matching
- [ ] Physician volume estimation
- [ ] Contact info aggregation

### Phase 3: KOL Intelligence
- [ ] Open Payments plugin (Edwards, Medtronic, Abbott)
- [ ] ClinicalTrials.gov plugin
- [ ] Fit scoring algorithm
- [ ] Warm lead flagging (configurable list of known contacts)

### Phase 4: Automation
- [ ] Scheduled refresh via cron/scheduler
- [ ] Change detection and diff reports
- [ ] Notification hooks (webhook, email, Slack)

---

## Configuration

### Source Configuration (config.yaml)

```yaml
sources:
  tvt_registry:
    enabled: true
    cache_ttl_hours: 168
    
  cms_utilization:
    enabled: true
    cache_ttl_hours: 720
    cpt_codes:
      - "33361"
      - "33362"
      - "33363"
      - "33364"
      - "33365"
      - "33366"
      - "33367"
      - "33368"
      - "33369"
    
  nppes:
    enabled: true
    cache_ttl_hours: 24
    rate_limit_per_minute: 100
    
  open_payments:
    enabled: true
    cache_ttl_hours: 720
    manufacturers:
      - "Edwards Lifesciences"
      - "Medtronic"
      - "Abbott"
      
  clinical_trials:
    enabled: true
    cache_ttl_hours: 24
    search_terms:
      - "TAVR"
      - "transcatheter aortic valve"
      - "TAVI"

# Known warm leads - flag these in output
warm_leads:
  physicians:
    - npi: "1234567890"
      name: "Jane Example, MD"
      relationship: "Existing customer"
      
scoring:
  hospital_volume_thresholds:
    high: 200
    medium: 100
    low: 50
  program_age_thresholds:
    new: 3
    established: 5
  payment_thresholds:
    low: 10000
    medium: 50000
```

---

## Project Structure

```
doctor-prospector/
├── PDR.md                        # This file
├── CLAUDE.md                     # Instructions for Claude Code
├── config.yaml                   # Source and scoring configuration
├── requirements.txt
├── pyproject.toml
├── src/
│   └── doctor_prospector/
│       ├── __init__.py
│       ├── cli.py                # Typer CLI
│       ├── config.py             # Config loader
│       ├── pipeline.py           # Orchestrates sources → enrichment → scoring → output
│       │
│       ├── sources/              # Data source plugins
│       │   ├── __init__.py       # Registry + auto-discovery
│       │   ├── base.py           # DataSourcePlugin ABC
│       │   ├── tvt_registry.py
│       │   ├── cms_utilization.py
│       │   ├── nppes.py
│       │   ├── open_payments.py
│       │   └── clinical_trials.py
│       │
│       ├── enrichment/           # Data joining/matching logic
│       │   ├── __init__.py
│       │   ├── physician_matcher.py
│       │   └── hospital_normalizer.py
│       │
│       ├── scoring/
│       │   ├── __init__.py
│       │   └── fit_score.py      # Configurable scoring algorithm
│       │
│       ├── output/
│       │   ├── __init__.py
│       │   ├── excel_writer.py
│       │   └── json_writer.py
│       │
│       ├── models/               # Pydantic models
│       │   ├── __init__.py
│       │   ├── hospital.py
│       │   ├── physician.py
│       │   └── prospect.py
│       │
│       └── cache/
│           ├── __init__.py
│           └── sqlite_cache.py   # Generic caching layer
│
├── data/
│   ├── cache/                    # SQLite cache files
│   └── output/                   # Generated files
│
├── tests/
│   ├── __init__.py
│   ├── test_sources/
│   │   └── test_tvt_registry.py
│   ├── test_scoring.py
│   └── fixtures/
│       └── sample_tvt_response.html
│
└── scripts/
    └── run_pipeline.py
```

---

## CLI Commands

```bash
# List available/enabled sources
doctor-prospector sources list
doctor-prospector sources status

# Fetch from specific source
doctor-prospector fetch tvt_registry --output data/cache/
doctor-prospector fetch nppes --state NJ --specialty "Interventional Cardiology"

# Run full pipeline with geography filter
doctor-prospector run --states NJ,PA --min-volume 50 --output prospects.xlsx
doctor-prospector run --radius 100 --center "Morristown, NJ" --output nj_region.xlsx
doctor-prospector run --all --min-volume 100 --output national.xlsx

# Generate from cached data only (no new fetches)
doctor-prospector generate --from-cache --output quick_report.xlsx

# Show cache status
doctor-prospector cache status
doctor-prospector cache clear --source tvt_registry

# Validate configuration
doctor-prospector config validate
doctor-prospector config show
```

---

## Fit Scoring Algorithm

Configurable via `config.yaml`. Default weights:

```
Base Score (0-100):

Hospital Factors (50 points max):
- Volume: 200+ = 20pts, 100-199 = 15pts, 50-99 = 10pts, <50 = 5pts
- Star Rating: 3-star = 15pts, 2-star = 10pts, 1-star = 5pts
- Program Age: <3 years = 15pts (newer = more receptive to AI)
             3-5 years = 10pts
             >5 years = 5pts

Physician Factors (50 points max):
- Trial Activity: Active PI = 20pts, Site investigator = 15pts, None = 0pts
- Volume: >100 cases = 15pts, 50-100 = 10pts, <50 = 5pts
- Device Payments: <$10k total = 15pts (not locked in)
                  $10k-50k = 10pts
                  >$50k = 5pts (likely entrenched)

Fit Categories:
- HIGH: 70-100
- MEDIUM: 40-69
- LOW: 0-39

Warm Lead Override:
- If physician is in warm_leads config, flag regardless of score
```

---

## Technical Stack

- **Language:** Python 3.11+
- **Async HTTP:** httpx (with sync fallback)
- **HTML Parsing:** beautifulsoup4 + lxml
- **Data:** pandas, pydantic
- **Excel:** openpyxl
- **Caching:** SQLite via aiosqlite
- **CLI:** typer + rich
- **Config:** pyyaml or tomli
- **Testing:** pytest + pytest-asyncio + respx (mock httpx)

---

## Constraints & Considerations

1. **Rate Limiting:** All sources implement exponential backoff; configurable per-source
2. **Data Freshness:** Cache TTL per source; timestamps in output
3. **Scraping Ethics:** Respect robots.txt, reasonable delays, identify as bot
4. **Privacy:** Physician data is public (NPI) but handle responsibly
5. **No Device Market Share:** Cannot determine valve brand preferences (requires paid data like IQVIA)
6. **Source Failures:** Pipeline continues if non-critical source fails; logs warning

---

## Success Criteria

1. Generate prospect list for any US state in <5 minutes
2. Match >90% of physicians to hospital affiliations
3. Correctly flag known KOLs and warm leads
4. Excel output is clean, professional, immediately usable
5. Adding a new data source requires only: new plugin file + config entry

---

## Future Enhancements (Out of Scope for MVP)

- Web UI for non-technical users
- CRM integration (Salesforce, HubSpot)
- Conference faculty tracking (TCT, ACC, TVT)
- News monitoring for TAVR program announcements
- Competitive intelligence
- Paid data source plugins (Definitive Healthcare, IQVIA)

---

## References

- TVT Registry: https://tvtpublicreporting.sts.org/tvt-registry
- NPPES API: https://npiregistry.cms.hhs.gov/api-page
- Open Payments API: https://openpaymentsdata.cms.gov/api
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api/api
- CMS Provider Utilization: https://data.cms.gov/provider-summary-by-type-of-service
