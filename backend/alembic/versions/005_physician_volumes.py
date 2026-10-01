"""Add physician_volumes table for historical CMS utilization data

Stores per-physician, per-procedure, per-year volume data from CMS PUF files.
Replaces file-based historical data with DB-backed on-demand queries.

Revision ID: 005
Revises: 004
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "physician_volumes",
        # INTEGER on SQLite: only "INTEGER PRIMARY KEY" auto-increments there
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer, "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("npi", sa.String(10), nullable=False, index=True),
        sa.Column("year", sa.SmallInteger, nullable=False),
        sa.Column("hcpcs_code", sa.String(10), nullable=False),
        sa.Column("hcpcs_description", sa.Text, nullable=False, server_default=""),
        sa.Column("services", sa.Integer, nullable=False, default=0),
        sa.Column("beneficiaries", sa.Integer, nullable=False, default=0),
        sa.Column("avg_medicare_payment", sa.Float, nullable=True),
        # Provider metadata (denormalized for fast queries)
        sa.Column("provider_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("provider_city", sa.String(100), nullable=False, server_default=""),
        sa.Column("provider_state", sa.String(2), nullable=False, server_default=""),
        sa.Column("provider_type", sa.String(100), nullable=False, server_default=""),
        # Unique constraint: one row per NPI + year + HCPCS code
        sa.UniqueConstraint("npi", "year", "hcpcs_code", name="uq_physician_volume"),
    )
    # Index for profile-based queries (find all physicians doing code X in state Y)
    op.create_index(
        "idx_phys_vol_hcpcs_state",
        "physician_volumes",
        ["hcpcs_code", "provider_state"],
    )
    op.create_index(
        "idx_phys_vol_npi_year",
        "physician_volumes",
        ["npi", "year"],
    )


def downgrade() -> None:
    op.drop_table("physician_volumes")
