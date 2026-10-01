"""Export system for Doctor Prospector.

Multi-format export with linked Excel sheets, flat CSV, and hierarchical JSON.

Usage:
    from doctor_prospector.output import collect_export_data, export_data, ExportOptions

    options = ExportOptions(include_trials=True, format_type="excel")
    data = collect_export_data(export_queue, options, st.session_state)
    filename, file_bytes, mime_type = export_data(data)
"""

from .collector import collect_export_data
from .models import ExportData, ExportOptions, HospitalExportRecord, PhysicianExportRecord
from .router import export_data

__all__ = [
    "ExportOptions",
    "ExportData",
    "HospitalExportRecord",
    "PhysicianExportRecord",
    "collect_export_data",
    "export_data",
]
