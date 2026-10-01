"""Export router - dispatches to the correct format writer."""

import logging
from datetime import datetime
from typing import Optional

from .models import ExportData
from .excel_writer import export_excel
from .csv_writer import export_csv
from .json_writer import export_json

logger = logging.getLogger(__name__)


def export_data(data: ExportData) -> tuple[str, Optional[bytes], str]:
    """Route export to the correct writer based on format_type.

    Args:
        data: Fully assembled export data (includes options with format_type).

    Returns:
        Tuple of (filename, file_bytes, mime_type).
        file_bytes is None for placeholder formats (pdf, html).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    format_type = data.options.format_type

    if format_type == "excel":
        filename = f"prospects_{timestamp}.xlsx"
        file_bytes = export_excel(data)
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    elif format_type == "csv":
        filename = f"prospects_{timestamp}.csv"
        file_bytes = export_csv(data)
        mime_type = "text/csv"

    elif format_type == "json":
        filename = f"prospects_{timestamp}.json"
        file_bytes = export_json(data)
        mime_type = "application/json"

    elif format_type in ("pdf", "html"):
        return f"prospects_{timestamp}.{format_type}", None, ""

    else:
        raise ValueError(f"Unsupported export format: {format_type}")

    logger.info(f"Generated {format_type} export: {filename} ({len(file_bytes)} bytes)")
    return filename, file_bytes, mime_type
