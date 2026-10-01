"""Add modules and drg_codes to preset profiles

Both TAVR and Robotic Surgery presets need modules and drg_codes fields
so the backend can route to the correct hospital data source.

Revision ID: 004
Revises: 003
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401

from app.db.types import update_preset_filters

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ROBOTIC_DRG_CODES = ["710", "714", "715", "716", "717", "734", "735", "736", "737", "738", "329", "330", "331", "469", "470"]


def upgrade() -> None:
    bind = op.get_bind()
    update_preset_filters(bind, "TAVR", lambda f: {**f, "modules": ["tavr"], "drg_codes": ["266", "267"]})
    update_preset_filters(bind, "Robotic Surgery", lambda f: {**f, "modules": [], "drg_codes": ROBOTIC_DRG_CODES})


def downgrade() -> None:
    bind = op.get_bind()
    for name in ("TAVR", "Robotic Surgery"):
        update_preset_filters(
            bind, name, lambda f: {k: v for k, v in f.items() if k not in ("modules", "drg_codes")}
        )
