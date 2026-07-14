"""change warmup model default to gpt-5.6-luna

Revision ID: 20260714_000000_change_warmup_model_default_to_gpt_5_6_luna
Revises: 20260709_010000_merge_websocket_continuity_and_ttft_heads
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = "20260714_000000_change_warmup_model_default_to_gpt_5_6_luna"
down_revision = "20260709_010000_merge_websocket_continuity_and_ttft_heads"
branch_labels = None
depends_on = None


def _columns(connection: Connection, table_name: str) -> set[str]:
    inspector = sa.inspect(connection)
    if not inspector.has_table(table_name):
        return set()
    return {str(column["name"]) for column in inspector.get_columns(table_name) if column.get("name") is not None}


def upgrade() -> None:
    bind = op.get_bind()
    if "warmup_model" not in _columns(bind, "dashboard_settings"):
        return

    with op.batch_alter_table("dashboard_settings") as batch_op:
        batch_op.alter_column(
            "warmup_model",
            existing_type=sa.String(),
            server_default=sa.text("'gpt-5.6-luna'"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if "warmup_model" not in _columns(bind, "dashboard_settings"):
        return

    with op.batch_alter_table("dashboard_settings") as batch_op:
        batch_op.alter_column(
            "warmup_model",
            existing_type=sa.String(),
            server_default=sa.text("'gpt-5.4-mini'"),
        )
