"""Add "robotic" to the Robotic Surgery preset's trial search terms

Trial searches are now limited to a study's own text (title, summary,
interventions...), so the bare word "robotic" no longer matches site names
and picks up trials like "Laparoscopic vs. Robotic Ventral Hernia Repair"
that none of the multi-word phrases catch.

Revision ID: 006
Revises: 005
Create Date: 2026-09-30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401

from app.db.types import update_preset_filters

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_robotic(filters: dict) -> dict:
    terms = list(filters.get("trial_search_terms", []))
    if "robotic" not in terms:
        terms.append("robotic")
    return {**filters, "trial_search_terms": terms}


def upgrade() -> None:
    update_preset_filters(op.get_bind(), "Robotic Surgery", _add_robotic)


def downgrade() -> None:
    update_preset_filters(
        op.get_bind(), "Robotic Surgery",
        lambda f: {**f, "trial_search_terms": [t for t in f.get("trial_search_terms", []) if t != "robotic"]},
    )
