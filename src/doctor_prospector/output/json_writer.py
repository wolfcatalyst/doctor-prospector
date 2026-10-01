"""JSON export - hierarchical structure for AI/CRM import."""

import json

from .models import ExportData


def export_json(data: ExportData) -> bytes:
    """Generate hierarchical JSON export.

    Structure: hospitals -> physicians -> trials/pubs/payments/contact/historical.
    Excluded data types are serialized as null.
    """
    options = data.options

    output = {
        "exported_at": data.exported_at.isoformat(),
        "export_options": {
            "hospitals": options.include_hospitals,
            "trials": options.include_trials,
            "publications": options.include_publications,
            "payments": options.include_payments,
            "contact": options.include_contact,
            "historical": options.include_historical,
        },
        "summary": data.summary,
        "hospitals": [],
    }

    for hospital in data.hospitals:
        h_dict = {
            "name": hospital.name,
            "location": {"city": hospital.city, "state": hospital.state},
            "annual_volume": hospital.annual_tavr_volume,
            "cumulative_volume": hospital.cumulative_volume,
            "star_rating": hospital.star_rating,
            "program_since": hospital.first_tavr_date,
            "site_id": hospital.site_id,
            "physicians": [],
        }

        for physician in hospital.physicians:
            p_dict = {
                "name": physician.full_name,
                "npi": physician.npi,
                "specialty": physician.primary_specialty,
                "credential": physician.credential,
                "volume": physician.tavr_volume,
            }

            # Trials (null if not included)
            p_dict["trials"] = (
                [
                    {
                        "title": t.get("title"),
                        "nct_id": t.get("nct_id"),
                        "sponsor": t.get("lead_sponsor"),
                        "status": t.get("overall_status"),
                        "role": _find_role(physician, t),
                    }
                    for t in physician.trials
                ]
                if options.include_trials
                else None
            )

            # Publications (null if not included)
            p_dict["publications"] = (
                [
                    {
                        "title": pub.get("title"),
                        "journal": pub.get("journal"),
                        "year": _extract_year(pub.get("pub_date")),
                        "orcid_verified": pub.get("confidence_badge", ""),
                        "pubmed_url": pub.get("pubmed_url"),
                    }
                    for pub in physician.publications
                ]
                if options.include_publications
                else None
            )

            # Payments (null if not included or no data)
            if options.include_payments and physician.payments:
                p_dict["payments"] = {
                    "total": physician.payments.get("total_payments", 0),
                    "payment_count": physician.payments.get("payment_count", 0),
                    "top_company": physician.payments.get("top_company"),
                    "companies": physician.payments.get("companies", {}),
                    "years": physician.payments.get("years", {}),
                    "payment_types": physician.payments.get("payment_types", {}),
                }
            else:
                p_dict["payments"] = None

            # Contact (null if not included)
            if options.include_contact:
                p_dict["contact"] = {
                    "practice_address": physician.practice_address,
                    "practice_city": physician.practice_city,
                    "practice_state": physician.practice_state,
                    "practice_postal_code": physician.practice_postal_code,
                    "phone": physician.practice_phone,
                    "npi_registry_url": physician.npi_registry_url or None,
                    "doximity_url": physician.doximity_url or None,
                    "google_search_url": physician.google_search_url or None,
                }
            else:
                p_dict["contact"] = None

            # Historical trends (null if not included or no data)
            if options.include_historical and physician.historical:
                p_dict["historical"] = {
                    "latest_volume": physician.historical.get("latest_volume"),
                    "trend_pct": physician.historical.get("avg_annual_growth_pct"),
                    "trend_direction": physician.historical.get("trend_indicator"),
                    "volume_by_year": physician.historical.get("volume_by_year", {}),
                    "years_active": physician.historical.get("years_active"),
                }
            else:
                p_dict["historical"] = None

            h_dict["physicians"].append(p_dict)

        output["hospitals"].append(h_dict)

    return json.dumps(output, indent=2, default=str).encode("utf-8")


def _find_role(physician, trial: dict) -> str | None:
    """Find physician's role in a trial by name matching."""
    if not physician.full_name:
        return None
    name_parts = physician.full_name.replace(",", "").split()
    last_name = name_parts[-1].lower() if name_parts else ""
    for inv in trial.get("investigators", []):
        inv_name = (inv.get("name", "") or "").lower()
        if last_name and last_name in inv_name:
            return inv.get("role")
    return None


def _extract_year(pub_date) -> str | None:
    """Extract year from a pub_date string."""
    if pub_date and len(str(pub_date)) >= 4:
        return str(pub_date)[:4]
    return None
