"""Seed Robotic Surgery preset profile

Revision ID: 003
Revises: 002
Create Date: 2026-03-14
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.types import device_profiles_table

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROBOTIC_SURGERY_FILTERS = {
    "hcpcs_codes": [
        "55866", "S2900",
        "58571", "58572", "58573",
        "44204", "44205", "44207", "44208", "44210", "44213",
        "27447", "27130",
        "22551", "22612", "22630",
    ],
    "manufacturers": {
        "intuitive_surgical": [
            "Intuitive Surgical", "Intuitive Surgical Inc",
            "Intuitive Surgical, Inc.", "Intuitive Surgical Operations",
        ],
        "medtronic": ["Medtronic", "Medtronic Inc", "Medtronic, Inc.", "Medtronic USA"],
        "stryker": ["Stryker", "Stryker Corporation", "Stryker Corp", "MAKO Surgical"],
        "zimmer_biomet": ["Zimmer Biomet", "Zimmer Biomet Holdings", "Biomet"],
        "globus_medical": ["Globus Medical", "Globus Medical Inc", "Globus Medical, Inc."],
        "johnson_and_johnson": [
            "Johnson & Johnson", "Ethicon", "Ethicon Inc",
            "Ethicon Endo-Surgery", "DePuy Synthes",
        ],
        "cmr_surgical": ["CMR Surgical", "CMR Surgical Ltd"],
    },
    "taxonomies": [
        "General Surgery", "Urology", "Gynecological Oncology", "Gynecology",
        "Orthopedic Surgery", "Thoracic Surgery (Cardiothoracic Vascular Surgery)",
        "Colorectal Surgery", "Neurological Surgery",
    ],
    "trial_search_terms": [
        "robotic surgery", "robot-assisted surgery", "da Vinci",
        "surgical robotics", "computer-assisted surgery",
        "AI-assisted surgery", "robotic-assisted laparoscopy",
    ],
    "trial_statuses": ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"],
    "procedure_label": "Robotic Surgery",
}


def upgrade() -> None:
    op.bulk_insert(device_profiles_table(), [{
        "id": uuid.uuid4(),
        "name": "Robotic Surgery",
        "description": "Robotic & AI-assisted surgery — da Vinci, Mako, Hugo, ROSA platforms",
        "is_preset": True,
        "is_active": False,
        "filters_json": ROBOTIC_SURGERY_FILTERS,
    }])


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM device_profiles WHERE name = :name AND is_preset = true").bindparams(
            name="Robotic Surgery",
        )
    )
