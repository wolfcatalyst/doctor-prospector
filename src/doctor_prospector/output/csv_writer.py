"""CSV export - flat one-row-per-physician format."""

import csv
from io import StringIO

from .models import ExportData
from .styles import MISSING_CSV


def export_csv(data: ExportData) -> bytes:
    """Generate flat CSV with one row per physician.

    Returns:
        UTF-8 encoded bytes of the CSV file (with BOM for Excel compatibility).
    """
    output = StringIO()
    writer = csv.writer(output)
    options = data.options

    # Build header based on options
    header = ["Name", "Hospital", "City", "State", "Specialty", "Credential", "NPI", "Volume"]
    if options.include_historical:
        header.extend(["Trend %", "Trend Direction"])
    if options.include_trials:
        header.append("Trial Count")
    if options.include_publications:
        header.append("Publication Count")
    if options.include_payments:
        header.extend(["Payment Total", "Top Company"])
    if options.include_contact:
        header.extend(["Practice Address", "Phone"])

    writer.writerow(header)

    for physician in data.all_physicians:
        row = [
            physician.full_name,
            physician.hospital_name,
            physician.hospital_city,
            physician.hospital_state,
            physician.primary_specialty or MISSING_CSV,
            physician.credential or MISSING_CSV,
            physician.npi,
            physician.tavr_volume,
        ]

        if options.include_historical:
            if physician.historical:
                growth = physician.historical.get("avg_annual_growth_pct", 0)
                sign = "+" if growth > 0 else ""
                row.append(f"{sign}{growth:.1f}%")
                row.append(physician.historical.get("trend_indicator", MISSING_CSV))
            else:
                row.extend([MISSING_CSV, MISSING_CSV])

        if options.include_trials:
            row.append(len(physician.trials))

        if options.include_publications:
            row.append(len(physician.publications))

        if options.include_payments:
            if physician.payments:
                total = physician.payments.get("total_payments", 0)
                row.append(f"${total:,.0f}")
                row.append(physician.payments.get("top_company", MISSING_CSV))
            else:
                row.extend([MISSING_CSV, MISSING_CSV])

        if options.include_contact:
            row.append(physician.practice_address or MISSING_CSV)
            row.append(physician.practice_phone or MISSING_CSV)

        writer.writerow(row)

    # UTF-8 BOM for Excel compatibility
    return ("\ufeff" + output.getvalue()).encode("utf-8")
