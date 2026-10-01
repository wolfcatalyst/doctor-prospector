"""Shared openpyxl style constants for Excel export."""

from openpyxl.styles import Alignment, Font, PatternFill

# Sheet tab colors (hex without #)
TAB_COLORS = {
    "Physicians": "4472C4",
    "Hospitals": "70AD47",
    "Clinical Trials": "ED7D31",
    "Publications": "FFC000",
    "Device Payments": "5B9BD5",
    "Contact Info": "A5A5A5",
}

# Header row styles
HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
HEADER_FILL = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)

# Hyperlink style (internal and external)
LINK_FONT = Font(color="0563C1", underline="single")

# Missing data style
MISSING_FONT = Font(color="808080", italic=True)

# Missing data sentinels per format
MISSING_EXCEL = "\u2014"  # em-dash
MISSING_CSV = "N/A"

# Default cell alignment
DEFAULT_ALIGNMENT = Alignment(vertical="top", wrap_text=False)
