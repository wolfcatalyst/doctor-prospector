"""Initial schema - users, tenants, exports, saved searches, feedback

Revision ID: 001
Revises: None
Create Date: 2026-02-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.db.types import JSONType, uuid_server_default

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tenants
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), unique=True, nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("settings_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Users
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("email", sa.String(320), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("preferences_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("auth_provider", sa.String(20), nullable=False, server_default="local"),
        sa.Column("oidc_sub", sa.String(255), unique=True, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Export Queues
    op.create_table(
        "export_queues",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("items_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_export_queues_user", "export_queues", ["user_id"])

    # Saved Searches
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("filters_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_saved_searches_user", "saved_searches", ["user_id"])

    # Export History
    op.create_table(
        "export_history",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("format", sa.String(20), nullable=False, server_default="excel"),
        sa.Column("options_json", JSONType, nullable=False, server_default="{}"),
        sa.Column("file_path", sa.Text, nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("hospital_count", sa.Integer, nullable=True),
        sa.Column("physician_count", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_export_history_user", "export_history", ["user_id"])
    op.create_index("idx_export_history_status", "export_history", ["status"])

    # Feedback
    op.create_table(
        "feedback",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=uuid_server_default(op.get_bind())),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(50), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("idx_feedback_user", "feedback", ["user_id"])


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("export_history")
    op.drop_table("saved_searches")
    op.drop_table("export_queues")
    op.drop_table("users")
    op.drop_table("tenants")
