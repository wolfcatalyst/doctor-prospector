"""Discover TAVR hospitals not in the TVT Registry.

Analyzes CMS billing data to find addresses with TAVR activity
that are not represented in the TVT public reporting registry.

Usage:
    python discover_non_tvt_hospitals.py
    python discover_non_tvt_hospitals.py --min-volume 50 --min-physicians 2
    python discover_non_tvt_hospitals.py --add
    python discover_non_tvt_hospitals.py --resolve-names
    python discover_non_tvt_hospitals.py --resolve-pos
    python discover_non_tvt_hospitals.py --resolve-pos --validate-only
    python discover_non_tvt_hospitals.py --enrich-pos
    python discover_non_tvt_hospitals.py --resolve-practices
"""

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from src.doctor_prospector.sources.cms_historical import CMSHistoricalSource
from src.doctor_prospector.sources.cms_pos import CMSPOSSource

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

console = Console()

DISCOVERED_HOSPITALS_PATH = Path("data/output/cms_discovered_hospitals.json")


def _normalize_street(street: str) -> str:
    """Normalize a street address for comparison."""
    s = street.upper().strip()
    # Remove suite/floor/room
    s = re.sub(r'\b(STE|SUITE|FLOOR|FL|RM|ROOM|BLDG|DEPT|UNIT)\b.*', '', s)
    # Normalize abbreviations
    s = re.sub(r'\bST\b', 'STREET', s)
    s = re.sub(r'\bAVE?\b', 'AVENUE', s)
    s = re.sub(r'\bBLVD\b', 'BOULEVARD', s)
    s = re.sub(r'\bDR\b', 'DRIVE', s)
    s = re.sub(r'\bRD\b', 'ROAD', s)
    s = re.sub(r'\bLN\b', 'LANE', s)
    s = re.sub(r'\bPKWY\b', 'PARKWAY', s)
    # Normalize ordinals: 210TH -> 210
    s = re.sub(r'(\d+)(ST|ND|RD|TH)\b', r'\1', s)
    return re.sub(r'\s+', ' ', s).strip()


def _is_hospital_name(name: str) -> bool:
    """Check if an organization name looks like an actual hospital."""
    name_lower = name.lower()

    # Must contain a hospital-related keyword
    hospital_keywords = [
        'hospital', 'medical center', 'health system', 'healthcare',
        'regional medical', 'medical group', 'clinic', 'health',
        'university', 'memorial',
    ]
    if not any(kw in name_lower for kw in hospital_keywords):
        return False

    # Reject names that are clearly not hospitals
    reject_keywords = [
        'crna', 'md ', 'do ', 'pa-c', 'rn ', 'physician',
        'anesthesi', 'radiology group', 'pathology', 'billing',
        'staffing', 'consulting', 'insurance', 'pharmacy',
        'ambulance', 'home health', 'hospice', 'nursing home',
        'assisted living', 'rehabilitation center',
    ]
    if any(kw in name_lower for kw in reject_keywords):
        return False

    return True


def _match_address_strict(
    cms_address: str,
    nppes_address: str,
    cms_city: str,
    nppes_city: str,
) -> bool:
    """Strict address matching: street number AND street name must match, plus city."""
    norm_cms = _normalize_street(cms_address)
    norm_nppes = _normalize_street(nppes_address)

    if not norm_cms or not norm_nppes:
        return False

    # Street numbers must match
    cms_nums = re.findall(r'\d+', norm_cms)
    nppes_nums = re.findall(r'\d+', norm_nppes)
    if not cms_nums or not nppes_nums or cms_nums[0] != nppes_nums[0]:
        return False

    # Street name words must have overlap (beyond just number and direction)
    filler = {'', 'N', 'S', 'E', 'W', 'NORTH', 'SOUTH', 'EAST', 'WEST'}
    # Remove numbers from word sets
    cms_words = {w for w in norm_cms.split() if not w.isdigit()} - filler
    nppes_words = {w for w in norm_nppes.split() if not w.isdigit()} - filler

    if not cms_words or not nppes_words:
        return False

    overlap = cms_words & nppes_words
    if not overlap:
        return False

    # City must match
    if cms_city.upper().strip() != nppes_city.upper().strip():
        return False

    return True


async def resolve_hospital_names(hospitals: list[dict]) -> int:
    """Look up real hospital names via NPPES organization search.

    For each discovered hospital, queries NPPES for General Acute Care Hospital
    organizations, then matches by strict address comparison (street number +
    street name + city must all match).

    Only accepts organizations that look like actual hospitals (filtered by
    name keywords). Uses frequency as tiebreaker when multiple hospitals
    share the same address.

    Args:
        hospitals: List of discovered hospital dicts (modified in place)

    Returns:
        Number of hospitals successfully resolved
    """
    to_resolve = [
        h for h in hospitals
        if h.get('name', '').startswith('TAVR Site -')
    ]

    if not to_resolve:
        console.print("[green]All hospitals already have resolved names.[/green]")
        return 0

    console.print(f"\n[bold cyan]Resolving hospital names via NPPES[/bold cyan]")
    console.print(f"[dim]{len(to_resolve)} hospitals need name resolution[/dim]")
    console.print(f"[dim]Strict matching: street number + street name + city must all match[/dim]")
    console.print(f"[dim]Two passes: 1) by postal code, 2) by city+state for unresolved[/dim]\n")

    resolved = 0
    errors = 0

    async with httpx.AsyncClient(timeout=30.0) as client:

        async def _try_resolve(hospital: dict, search_params: dict) -> bool:
            """Try to resolve a single hospital name. Returns True if resolved."""
            city = hospital.get('city', '')
            address = hospital.get('address', '')

            resp = await client.get(
                'https://npiregistry.cms.hhs.gov/api/',
                params=search_params,
            )
            resp.raise_for_status()
            data = resp.json()

            results = data.get('results', [])
            if not results:
                return False

            # Collect matching hospitals: name -> frequency count
            candidates: dict[str, int] = {}

            for org in results:
                org_name = org.get('basic', {}).get('organization_name', '')
                if not org_name or not _is_hospital_name(org_name):
                    continue

                for addr in org.get('addresses', []):
                    if addr.get('address_purpose') != 'LOCATION':
                        continue

                    org_street = addr.get('address_1', '')
                    org_city = addr.get('city', '')

                    if _match_address_strict(address, org_street, city, org_city):
                        candidates[org_name] = candidates.get(org_name, 0) + 1

            if not candidates:
                return False

            # Pick the most frequently occurring hospital at this address
            best_name = max(candidates, key=lambda n: candidates[n])
            hospital['name'] = best_name.title()
            return True

        # Pass 1: search by postal code
        with Progress() as progress:
            task = progress.add_task("Pass 1 (by zip)...", total=len(to_resolve))

            for i, hospital in enumerate(to_resolve):
                zip_code = hospital.get('zip', '')[:5]
                state = hospital.get('state', '')

                if not zip_code or not state:
                    progress.advance(task)
                    continue

                if i > 0:
                    await asyncio.sleep(0.7)

                try:
                    found = await _try_resolve(hospital, {
                        'version': '2.1',
                        'postal_code': zip_code,
                        'enumeration_type': 'NPI-2',
                        'taxonomy_description': 'General Acute Care Hospital',
                        'limit': 200,
                    })
                    if found:
                        resolved += 1
                except Exception as e:
                    errors += 1
                    if errors <= 3:
                        console.print(f"[yellow]Error: {hospital.get('city')}, {state}: {e}[/yellow]")

                progress.advance(task)

        # Pass 2: try city+state for remaining unresolved
        still_unresolved = [h for h in to_resolve if h.get('name', '').startswith('TAVR Site -')]
        if still_unresolved:
            console.print(f"\n[dim]Pass 2: trying city+state for {len(still_unresolved)} unresolved...[/dim]")
            with Progress() as progress:
                task2 = progress.add_task("Pass 2 (by city)...", total=len(still_unresolved))

                for i, hospital in enumerate(still_unresolved):
                    city = hospital.get('city', '')
                    state = hospital.get('state', '')

                    if not city or not state:
                        progress.advance(task2)
                        continue

                    if i > 0:
                        await asyncio.sleep(0.7)

                    try:
                        found = await _try_resolve(hospital, {
                            'version': '2.1',
                            'city': city,
                            'state': state,
                            'enumeration_type': 'NPI-2',
                            'taxonomy_description': 'General Acute Care Hospital',
                            'limit': 200,
                        })
                        if found:
                            resolved += 1
                    except Exception as e:
                        errors += 1

                    progress.advance(task2)

    console.print(f"\n[bold]Name resolution complete:[/bold] {resolved}/{len(to_resolve)} resolved, "
                  f"{len(to_resolve) - resolved - errors} unmatched, {errors} errors")
    return resolved


async def resolve_hospital_names_pos(
    hospitals: list[dict],
    validate_only: bool = False,
) -> int:
    """Resolve generic hospital names using CMS Provider of Services data.

    Uses a tiered address matching approach:
      Tier 1: Full normalized address + city + state match (HIGH confidence)
      Tier 2: Street number + street name words + city match (HIGH confidence)
      Tier 3: Same ZIP, exactly ONE hospital in that ZIP (MEDIUM confidence)

    Args:
        hospitals: List of discovered hospital dicts (modified in place)
        validate_only: If True, only validate against NPPES-resolved names

    Returns:
        Number of hospitals resolved (or validated)
    """
    console.print("\n[bold cyan]Resolving hospital names via CMS Provider of Services[/bold cyan]")
    console.print("[dim]Fetching POS hospital registry...[/dim]\n")

    # Fetch POS data
    pos_source = CMSPOSSource()
    pos_hospitals = await pos_source.fetch()
    console.print(f"[dim]POS data: {len(pos_hospitals)} hospitals loaded[/dim]")

    # Build address index
    index = pos_source.build_address_index(pos_hospitals)

    # Split hospitals into already-resolved (for validation) and unresolved
    already_resolved = [
        h for h in hospitals
        if not h.get('name', '').startswith('TAVR Site -')
        and h.get('site_type') != 'practice'
    ]
    to_resolve = [
        h for h in hospitals
        if h.get('name', '').startswith('TAVR Site -')
    ]

    # Validation: check POS matches against NPPES-resolved names
    if already_resolved:
        console.print(f"\n[bold]Validating POS against {len(already_resolved)} NPPES-resolved hospitals...[/bold]")
        agreed = 0
        close = 0
        mismatch = 0
        no_pos_match = 0
        mismatches = []

        for h in already_resolved:
            result = pos_source.match_address(
                h.get('address', ''),
                h.get('city', ''),
                h.get('state', ''),
                h.get('zip', ''),
                index,
            )
            if result is None:
                no_pos_match += 1
                continue

            pos_record, tier, confidence = result
            pos_name = pos_record['fac_name'].title()
            nppes_name = h['name']

            # Compare names (normalize for comparison)
            pos_norm = pos_source.normalize_hospital_name(pos_name)
            nppes_norm = pos_source.normalize_hospital_name(nppes_name)

            if pos_norm == nppes_norm:
                agreed += 1
            elif _names_close(pos_name, nppes_name):
                close += 1
            else:
                mismatch += 1
                mismatches.append({
                    'city': h['city'],
                    'state': h['state'],
                    'nppes_name': nppes_name,
                    'pos_name': pos_name,
                    'tier': tier,
                })

        total_matched = agreed + close + mismatch
        accuracy = ((agreed + close) / total_matched * 100) if total_matched > 0 else 0

        table = Table(title="POS vs NPPES Validation")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", justify="right", style="green")
        table.add_row("Exact name match", str(agreed))
        table.add_row("Close name match", str(close))
        table.add_row("Name mismatch", str(mismatch))
        table.add_row("No POS match", str(no_pos_match))
        table.add_row("Accuracy", f"{accuracy:.1f}%")
        console.print(table)

        if mismatches:
            console.print(f"\n[yellow]Name mismatches ({len(mismatches)}):[/yellow]")
            for m in mismatches[:20]:
                console.print(
                    f"  {m['city']}, {m['state']}: "
                    f"NPPES=\"{m['nppes_name']}\" vs POS=\"{m['pos_name']}\" "
                    f"(tier {m['tier']})"
                )

        if validate_only:
            return 0

    # Also update NPPES-resolved hospitals with POS names (POS is more current)
    if already_resolved and not validate_only:
        console.print(f"\n[bold]Upgrading {len(already_resolved)} NPPES-resolved hospitals with POS names...[/bold]")
        upgraded = 0
        with Progress() as progress:
            task = progress.add_task("Upgrading NPPES names...", total=len(already_resolved))
            for h in already_resolved:
                result = pos_source.match_address(
                    h.get('address', ''),
                    h.get('city', ''),
                    h.get('state', ''),
                    h.get('zip', ''),
                    index,
                )
                if result is not None:
                    pos_record, tier, confidence = result
                    h['name'] = pos_record['fac_name'].title()
                    h['name_source'] = 'CMS_POS'
                    h['name_match_tier'] = tier
                    h['ccn'] = pos_record['ccn']
                    h['bed_count'] = pos_record['bed_count']
                    h['has_cath_lab'] = pos_record['has_cath_lab']
                    h['has_open_heart_surgery'] = pos_record['has_open_heart_surgery']
                    h['cath_lab_rooms'] = pos_record['cath_lab_rooms']
                    h['teaching_status'] = pos_record['teaching_status']
                    h['ownership_type'] = pos_record['ownership_type']
                    upgraded += 1
                progress.advance(task)
        console.print(f"  Upgraded {upgraded}/{len(already_resolved)} to POS names")

    if not to_resolve:
        console.print("[green]All hospitals already have resolved names.[/green]")
        return 0

    # Resolve unresolved hospitals
    console.print(f"\n[bold]Resolving {len(to_resolve)} unresolved hospitals...[/bold]")

    resolved = 0
    tier_counts = {1: 0, 2: 0, 3: 0}

    with Progress() as progress:
        task = progress.add_task("Matching addresses...", total=len(to_resolve))

        for h in to_resolve:
            result = pos_source.match_address(
                h.get('address', ''),
                h.get('city', ''),
                h.get('state', ''),
                h.get('zip', ''),
                index,
            )

            if result is not None:
                pos_record, tier, confidence = result
                h['name'] = pos_record['fac_name'].title()
                h['name_source'] = 'CMS_POS'
                h['name_match_tier'] = tier
                h['ccn'] = pos_record['ccn']
                h['bed_count'] = pos_record['bed_count']
                h['has_cath_lab'] = pos_record['has_cath_lab']
                h['has_open_heart_surgery'] = pos_record['has_open_heart_surgery']
                h['cath_lab_rooms'] = pos_record['cath_lab_rooms']
                h['teaching_status'] = pos_record['teaching_status']
                h['ownership_type'] = pos_record['ownership_type']
                resolved += 1
                tier_counts[tier] += 1

            progress.advance(task)

    # Also tag existing NPPES-resolved hospitals with name_source
    for h in already_resolved:
        if 'name_source' not in h:
            h['name_source'] = 'NPPES'

    console.print(f"\n[bold]POS resolution complete:[/bold] {resolved}/{len(to_resolve)} resolved")
    console.print(f"  Tier 1 (exact address): {tier_counts[1]}")
    console.print(f"  Tier 2 (street match):  {tier_counts[2]}")
    console.print(f"  Tier 3 (ZIP single):    {tier_counts[3]}")
    console.print(f"  Unresolved:             {len(to_resolve) - resolved}")

    # Show sample resolved names
    newly_resolved = [h for h in to_resolve if not h['name'].startswith('TAVR Site -')]
    if newly_resolved:
        console.print(f"\n[bold]Sample resolved names:[/bold]")
        for h in newly_resolved[:20]:
            console.print(
                f"  {h['name']} — {h['city']}, {h['state']} "
                f"(tier {h.get('name_match_tier')}, "
                f"beds: {h.get('bed_count', '?')}, "
                f"cath lab: {'Yes' if h.get('has_cath_lab') else 'No'})"
            )

    return resolved


async def enrich_all_hospitals_pos() -> None:
    """Enrich ALL hospitals (CMS discovered + TVT) with POS facility details.

    For CMS-discovered hospitals: matches by address (has street + zip).
    For TVT hospitals: matches by hospital name + city + state.

    Saves enrichment data back to the respective JSON files.
    """
    console.print("\n[bold cyan]Enriching ALL hospitals with CMS POS facility data[/bold cyan]")
    console.print("[dim]Fetching POS hospital registry...[/dim]\n")

    pos_source = CMSPOSSource()
    pos_hospitals = await pos_source.fetch()
    console.print(f"[dim]POS data: {len(pos_hospitals)} hospitals loaded[/dim]")

    addr_index = pos_source.build_address_index(pos_hospitals)
    name_index = pos_source.build_name_index(pos_hospitals)
    pos_by_ccn = {p['ccn']: p for p in pos_hospitals if p.get('ccn')}

    def _apply_pos_fields(target: dict, pos_record: dict) -> None:
        """Copy POS facility fields to a hospital dict."""
        target['ccn'] = pos_record['ccn']
        target['bed_count'] = pos_record['bed_count']
        target['has_cath_lab'] = pos_record['has_cath_lab']
        target['has_open_heart_surgery'] = pos_record['has_open_heart_surgery']
        target['cath_lab_rooms'] = pos_record['cath_lab_rooms']
        target['teaching_status'] = pos_record['teaching_status']
        target['ownership_type'] = pos_record['ownership_type']

    # --- Part 1: CMS-discovered hospitals (match by address) ---
    discovered = load_existing_discovered()
    cms_enriched = 0
    if discovered:
        console.print(f"\n[bold]Part 1: Enriching {len(discovered)} CMS-discovered hospitals (by address)...[/bold]")
        with Progress() as progress:
            task = progress.add_task("CMS hospitals...", total=len(discovered))
            for h in discovered:
                address = h.get('address', '')
                city = h.get('city', '')
                state = h.get('state', '')
                zip_code = h.get('zip', '')

                if not address or not city or not state:
                    progress.advance(task)
                    continue

                # Already matched: refresh from the current POS record by CCN
                # (skipping these left stale beds/cath-lab values forever)
                if h.get('ccn'):
                    pos_record = pos_by_ccn.get(h['ccn'])
                    if pos_record is not None:
                        _apply_pos_fields(h, pos_record)
                    cms_enriched += 1
                    progress.advance(task)
                    continue

                result = pos_source.match_address(address, city, state, zip_code, addr_index)
                if result is not None:
                    pos_record, _, _ = result
                    _apply_pos_fields(h, pos_record)
                    cms_enriched += 1
                elif h.get('site_type') != 'practice' and not h.get('name', '').startswith('TAVR Site -'):
                    # Named via NPPES but the billing address differs from the
                    # POS facility address -> fall back to name + city + state
                    pos_record = pos_source.match_by_name(h['name'], city, state, name_index)
                    if pos_record is not None:
                        _apply_pos_fields(h, pos_record)
                        cms_enriched += 1

                progress.advance(task)

        # Save
        with DISCOVERED_HOSPITALS_PATH.open('w', encoding='utf-8') as f:
            json.dump(discovered, f, indent=2, ensure_ascii=False)
        console.print(f"  Enriched {cms_enriched}/{len(discovered)} CMS hospitals")

    # --- Part 2: TVT Registry hospitals (match by name) ---
    tvt_path = Path("data/output/all_hospitals.json")
    tvt_enriched = 0
    if tvt_path.exists():
        with tvt_path.open(encoding="utf-8") as f:
            tvt_hospitals = json.load(f)

        console.print(f"\n[bold]Part 2: Enriching {len(tvt_hospitals)} TVT hospitals (by name)...[/bold]")
        with Progress() as progress:
            task = progress.add_task("TVT hospitals...", total=len(tvt_hospitals))
            for h in tvt_hospitals:
                name = h.get('name', '')
                city = h.get('city', '')
                state = h.get('state', '')

                if not name or not city or not state:
                    progress.advance(task)
                    continue

                pos_record = pos_source.match_by_name(name, city, state, name_index)
                if pos_record is not None:
                    _apply_pos_fields(h, pos_record)
                    tvt_enriched += 1

                progress.advance(task)

        # Save
        with tvt_path.open('w', encoding='utf-8') as f:
            json.dump(tvt_hospitals, f, indent=2, ensure_ascii=False)
        console.print(f"  Enriched {tvt_enriched}/{len(tvt_hospitals)} TVT hospitals")
    else:
        console.print("[dim]No TVT hospital file found (data/output/all_hospitals.json)[/dim]")

    total = cms_enriched + tvt_enriched
    console.print(f"\n[bold green]Total enriched: {total} hospitals with POS facility data[/bold green]")


DAC_API = "https://data.cms.gov/provider-data/api/1/datastore/query/{dataset}/0"
DAC_CLINICIANS = "mj5m-pzi6"     # Doctors & Clinicians National Downloadable File
DAC_AFFILIATIONS = "27ea-46a8"   # Doctors & Clinicians Facility Affiliations

# Business suffixes that .title() would mangle ("Pa", "Llc")
_KEEP_UPPER = {"PA", "PC", "LLC", "PLLC", "LLP", "MD", "DO", "PLC", "LTD", "INC", "II", "III", "USA"}


def _practice_title(name: str) -> str:
    """Title-case a practice name, keeping business suffixes uppercase."""
    words = []
    for w in name.split():
        core = re.sub(r'[^A-Za-z]', '', w).upper()
        words.append(w.upper() if core in _KEEP_UPPER else w.capitalize())
    return " ".join(words)


async def _dac_query_npis(client: httpx.AsyncClient, dataset: str, npis: list[str]) -> list[dict]:
    """Query a CMS Doctors & Clinicians dataset for many NPIs (batched)."""
    rows: list[dict] = []
    for i in range(0, len(npis), 100):
        batch = npis[i:i + 100]
        offset = 0
        while True:
            body = {
                "conditions": [{"property": "npi", "operator": "in", "value": batch}],
                "limit": 500,
                "offset": offset,
            }
            for attempt in range(4):
                try:
                    resp = await client.post(DAC_API.format(dataset=dataset), json=body)
                    resp.raise_for_status()
                    break
                except httpx.HTTPError:
                    if attempt == 3:
                        raise
                    await asyncio.sleep(2 ** attempt)
            page = resp.json().get("results", [])
            rows.extend(page)
            if len(page) < 500:
                break
            offset += 500
    return rows


async def resolve_practices(hospitals: list[dict]) -> int:
    """Identify unnamed "TAVR Site" records as physician group practices.

    CMS utilization data reports where a physician BILLS, which for many
    TAVR operators is their group practice office, not the hospital. These
    sites never match a hospital address in POS. For each one we look up its
    physicians in CMS Doctors & Clinicians data to get:
      - the group practice registered at that address (-> name)
      - the hospitals those physicians are affiliated with (-> CCNs)

    Sets site_type="practice", practice_name, affiliated_hospitals.

    Returns:
        Number of sites resolved to a named practice
    """
    targets = [
        h for h in hospitals
        if h.get('name', '').startswith('TAVR Site -') and h.get('physician_npis')
    ]
    if not targets:
        console.print("[green]No unnamed sites to resolve.[/green]")
        return 0

    npis = sorted({n for h in targets for n in h['physician_npis']})
    console.print(f"\n[bold cyan]Resolving {len(targets)} unnamed sites as physician practices[/bold cyan]")
    console.print(f"[dim]Looking up {len(npis)} physicians in CMS Doctors & Clinicians...[/dim]")

    async with httpx.AsyncClient(timeout=180.0) as client:
        clinician_rows = await _dac_query_npis(client, DAC_CLINICIANS, npis)
        affiliation_rows = await _dac_query_npis(client, DAC_AFFILIATIONS, npis)

    by_npi_groups: dict[str, list[dict]] = {}
    for r in clinician_rows:
        by_npi_groups.setdefault(r['npi'], []).append(r)
    by_npi_ccns: dict[str, set[str]] = {}
    for r in affiliation_rows:
        if (r.get('facility_type') or '').lower() == 'hospital':
            ccn = (r.get('facility_affiliations_certification_number') or '').strip()
            if ccn:
                by_npi_ccns.setdefault(r['npi'], set()).add(ccn)

    # CCN -> hospital name/city from POS
    pos_hospitals = await CMSPOSSource().fetch()
    pos_by_ccn = {p['ccn']: p for p in pos_hospitals if p.get('ccn')}

    resolved = 0
    for h in targets:
        address, city = h.get('address', ''), h.get('city', '')
        zip5 = (h.get('zip') or '')[:5]

        # Practice registered at this exact address wins; else same city+zip
        exact: dict[str, int] = {}
        nearby: dict[str, int] = {}
        for npi in h['physician_npis']:
            seen_exact, seen_nearby = set(), set()
            for r in by_npi_groups.get(npi, []):
                group = (r.get('facility_name') or '').strip()
                if not group:
                    continue
                if _match_address_strict(r.get('adr_ln_1', ''), address, r.get('citytown', ''), city):
                    seen_exact.add(group)
                elif (r.get('citytown') or '').upper() == city.upper() and (r.get('zip_code') or '')[:5] == zip5:
                    seen_nearby.add(group)
            for g in seen_exact:
                exact[g] = exact.get(g, 0) + 1
            for g in seen_nearby:
                nearby[g] = nearby.get(g, 0) + 1

        # Hospitals these physicians are affiliated with, most shared first
        ccn_counts: dict[str, int] = {}
        for npi in h['physician_npis']:
            for ccn in by_npi_ccns.get(npi, ()):
                ccn_counts[ccn] = ccn_counts.get(ccn, 0) + 1
        affiliated = []
        for ccn, count in sorted(ccn_counts.items(), key=lambda x: -x[1])[:5]:
            pos = pos_by_ccn.get(ccn, {})
            affiliated.append({
                'ccn': ccn,
                'name': pos.get('fac_name', '').title() or None,
                'city': (pos.get('city') or '').title() or None,
                'physician_count': count,
            })
        if affiliated:
            h['affiliated_hospitals'] = affiliated

        candidates = exact or nearby
        if candidates:
            practice = _practice_title(max(candidates, key=lambda g: candidates[g]))
            h['name'] = practice
            h['practice_name'] = practice
            h['site_type'] = 'practice'
            h['name_source'] = 'CMS_DAC'
            h['name_match_tier'] = 1 if exact else 2
            resolved += 1

    console.print(f"[bold]Practice resolution complete:[/bold] {resolved}/{len(targets)} named, "
                  f"{sum(1 for h in targets if h.get('affiliated_hospitals'))} with hospital affiliations")
    return resolved


def _names_close(name1: str, name2: str) -> bool:
    """Check if two hospital names are close enough to be the same facility.

    Uses word overlap — if >50% of words overlap, they're close.
    """
    words1 = set(re.findall(r'\w+', name1.upper()))
    words2 = set(re.findall(r'\w+', name2.upper()))
    # Remove common filler words
    filler = {'THE', 'OF', 'AND', 'AT', 'IN', 'A', 'AN'}
    words1 -= filler
    words2 -= filler
    if not words1 or not words2:
        return False
    overlap = words1 & words2
    smaller = min(len(words1), len(words2))
    return len(overlap) / smaller >= 0.5


def load_existing_discovered() -> list[dict]:
    """Load previously discovered hospitals to avoid duplicates."""
    if DISCOVERED_HOSPITALS_PATH.exists():
        with DISCOVERED_HOSPITALS_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    return []


def dedup_key(city: str, state: str) -> str:
    """Create a dedup key from city+state."""
    return f"{city.strip().upper()}|{state.strip().upper()}"


async def main():
    parser = argparse.ArgumentParser(description="Discover non-TVT TAVR hospitals from CMS data")
    parser.add_argument('--min-volume', type=int, default=10,
                        help='Minimum total TAVR procedures at address (default: 10)')
    parser.add_argument('--min-physicians', type=int, default=1,
                        help='Minimum physicians at address (default: 1)')
    parser.add_argument('--add', action='store_true',
                        help='Add discovered hospitals to the hospital list')
    parser.add_argument('--resolve-names', action='store_true',
                        help='Resolve generic "TAVR Site" names to real hospital names via NPPES')
    parser.add_argument('--resolve-pos', action='store_true',
                        help='Resolve generic "TAVR Site" names via CMS Provider of Services (recommended)')
    parser.add_argument('--validate-only', action='store_true',
                        help='With --resolve-pos: only validate against NPPES-resolved names, do not modify')
    parser.add_argument('--resolve-practices', action='store_true',
                        help='Name unresolved "TAVR Site" records as physician practices + hospital affiliations (CMS Doctors & Clinicians)')
    parser.add_argument('--enrich-pos', action='store_true',
                        help='Enrich ALL hospitals (including TVT) with POS facility data (bed count, cath lab, etc.)')
    args = parser.parse_args()

    # Handle --resolve-pos as a standalone action
    if args.resolve_pos:
        existing = load_existing_discovered()
        if not existing:
            console.print("[yellow]No discovered hospitals found. Run --add first.[/yellow]")
            return

        resolved = await resolve_hospital_names_pos(existing, validate_only=args.validate_only)
        if resolved > 0 and not args.validate_only:
            with DISCOVERED_HOSPITALS_PATH.open('w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            console.print(f"[green]Updated {DISCOVERED_HOSPITALS_PATH} with {resolved} POS-resolved names[/green]")
        return

    # Handle --resolve-practices as a standalone action
    if args.resolve_practices:
        existing = load_existing_discovered()
        if not existing:
            console.print("[yellow]No discovered hospitals found. Run --add first.[/yellow]")
            return
        await resolve_practices(existing)
        with DISCOVERED_HOSPITALS_PATH.open('w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        console.print(f"[green]Updated {DISCOVERED_HOSPITALS_PATH}[/green]")
        return

    # Handle --enrich-pos as a standalone action
    if args.enrich_pos:
        await enrich_all_hospitals_pos()
        return

    # Handle --resolve-names as a standalone action
    if args.resolve_names:
        existing = load_existing_discovered()
        if not existing:
            console.print("[yellow]No discovered hospitals found. Run --add first.[/yellow]")
            return

        resolved = await resolve_hospital_names(existing)
        if resolved > 0:
            with DISCOVERED_HOSPITALS_PATH.open('w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            console.print(f"[green]Updated {DISCOVERED_HOSPITALS_PATH} with {resolved} resolved names[/green]")

            # Show some examples
            named = [h for h in existing if not h['name'].startswith('TAVR Site -')]
            if named:
                console.print(f"\n[bold]Sample resolved names:[/bold]")
                for h in named[:15]:
                    console.print(f"  {h['name']} — {h['city']}, {h['state']} (vol: {h.get('annual_tavr_volume', 0)})")
        return

    console.print("\n[bold cyan]Discovering Non-TVT TAVR Hospitals[/bold cyan]")
    console.print(f"[dim]Filters: min volume={args.min_volume}, min physicians={args.min_physicians}[/dim]\n")

    source = CMSHistoricalSource()
    results = await source.discover_non_tvt_hospitals(
        min_volume=args.min_volume,
        min_physicians=args.min_physicians,
    )

    if not results:
        console.print("[yellow]No non-TVT TAVR locations found.[/yellow]")
        return

    # Build dedup set from manual_hospitals in config.yaml
    config_path = Path("config.yaml")
    manual_keys: set[str] = set()
    if config_path.exists():
        with config_path.open() as f:
            config = yaml.safe_load(f)
        for h in config.get('manual_hospitals', []):
            manual_keys.add(dedup_key(h['city'], h['state']))

    # Filter out any already in manual_hospitals
    new_results = [
        r for r in results
        if dedup_key(r['city'], r['state']) not in manual_keys
    ]

    # Display results
    table = Table(title=f"Non-TVT TAVR Locations ({len(new_results)} found, {len(results) - len(new_results)} already in config)")
    table.add_column("#", style="dim", justify="right")
    table.add_column("City, State", style="cyan")
    table.add_column("Street", style="white", max_width=40)
    table.add_column("Zip", style="dim")
    table.add_column("Physicians", justify="right", style="yellow")
    table.add_column("Total Vol (all yrs)", justify="right", style="green")
    table.add_column("Est. Annual", justify="right", style="green")
    table.add_column("Top Physician", style="dim")

    for i, loc in enumerate(new_results, 1):
        top = loc['physicians'][0] if loc['physicians'] else {}
        table.add_row(
            str(i),
            f"{loc['city']}, {loc['state']}",
            loc['street'][:40],
            loc['zip'],
            str(loc['physician_count']),
            str(loc['total_tavr_volume']),
            str(loc.get('estimated_annual_volume', 0)),
            f"{top.get('name', 'N/A')} ({top.get('latest_volume', 0)})",
        )

    console.print(table)

    # Summary
    total_volume = sum(r['total_tavr_volume'] for r in new_results)
    total_physicians = sum(r['physician_count'] for r in new_results)
    console.print(f"\n[bold]Summary:[/bold] {len(new_results)} new locations, "
                  f"{total_physicians} physicians, {total_volume} total TAVR procedures")

    if args.add:
        # Load existing discovered hospitals and build dedup set
        existing = load_existing_discovered()
        existing_keys = {dedup_key(h['city'], h['state']) for h in existing}

        # Only add truly new ones
        added = 0
        for loc in new_results:
            key = dedup_key(loc['city'], loc['state'])
            if key in existing_keys:
                continue

            existing.append({
                'name': f"TAVR Site - {loc['city'].title()}, {loc['state']}",
                'city': loc['city'].title(),
                'state': loc['state'],
                'address': loc['street'].title(),
                'zip': loc['zip'],
                'annual_tavr_volume': loc.get('estimated_annual_volume', 0),
                'total_tavr_volume_all_years': loc['total_tavr_volume'],
                'physician_count': loc['physician_count'],
                'data_source': 'CMS Data',
                'discovered_at': datetime.now().isoformat(),
                'physician_npis': [p['npi'] for p in loc['physicians']],
            })
            existing_keys.add(key)
            added += 1

        # Write back
        DISCOVERED_HOSPITALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with DISCOVERED_HOSPITALS_PATH.open('w', encoding='utf-8') as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)

        console.print(f"\n[green]Added {added} new hospitals to {DISCOVERED_HOSPITALS_PATH}[/green]")
        console.print(f"[dim]Total in file: {len(existing)} (skipped {len(new_results) - added} duplicates)[/dim]")
    else:
        console.print(f"\n[dim]Run with --add to save these to the hospital list[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
