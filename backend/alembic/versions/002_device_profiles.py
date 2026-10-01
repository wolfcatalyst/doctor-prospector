"""Add device_profiles table and active_device_profile_id to users

Revision ID: 002
Revises: 001
Create Date: 2026-03-14
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.types import JSONType, device_profiles_table, uuid_server_default

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# TAVR preset filters — seeded as the default built-in profile
TAVR_PRESET_FILTERS = {
    "hcpcs_codes": [
        "33361", "33362", "33363", "33364", "33365",
        "33366", "33367", "33368", "33369",
    ],
    "manufacturers": {
        "heartflow": ["HeartFlow", "HeartFlow Inc", "HeartFlow, Inc."],
        "edwards": ["Edwards Lifesciences", "Edwards Lifesciences LLC", "Edwards Lifesciences Corporation"],
        "medtronic": ["Medtronic", "Medtronic Inc", "Medtronic, Inc.", "Medtronic USA"],
        "abbott": ["Abbott", "Abbott Laboratories", "Abbott Vascular", "St. Jude Medical"],
        "boston_scientific": ["Boston Scientific", "Boston Scientific Corporation"],
    },
    "taxonomies": [
        "Interventional Cardiology",
        "Thoracic Surgery (Cardiothoracic Vascular Surgery)",
        "Adult Congenital Heart Disease",
    ],
    "trial_search_terms": [
        "TAVR", "TAVI",
        "transcatheter aortic valve replacement",
        "transcatheter aortic valve implantation",
    ],
    "trial_statuses": ["RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"],
    "procedure_label": "TAVR",
}


def upgrade() -> None:
    # Device Profiles table
    op.create_table(
        "device_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("is_preset", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("filters_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_device_profiles_user", "device_profiles", ["user_id"])
    op.create_index("idx_device_profiles_preset", "device_profiles", ["is_preset"])

    # Add active profile FK to users
    op.add_column(
        "users",
        sa.Column("active_device_profile_id", sa.Uuid(), nullable=True),
    )

    # Seed the TAVR preset (user_id=NULL means it's a global preset)
    op.bulk_insert(device_profiles_table(), [{
        "id": uuid.uuid4(),
        "name": "TAVR",
        "description": "Transcatheter Aortic Valve Replacement — heart valve device market",
        "is_preset": True,
        "is_active": False,
        "filters_json": TAVR_PRESET_FILTERS,
    }])


def downgrade() -> None:
    op.drop_column("users", "active_device_profile_id")
    op.drop_table("device_profiles")
