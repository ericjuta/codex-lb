"""add websocket continuity states table

Revision ID: 20260702_090000_add_websocket_continuity_states
Revises: 20260702_082359_merge_weekly_pace_and_rebased_warmup_heads
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = "20260702_090000_add_websocket_continuity_states"
down_revision = "20260702_082359_merge_weekly_pace_and_rebased_warmup_heads"
branch_labels = None
depends_on = None


def _has_table(connection: Connection, table_name: str) -> bool:
    inspector = sa.inspect(connection)
    return inspector.has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "websocket_continuity_states"):
        op.create_table(
            "websocket_continuity_states",
            sa.Column("session_key", sa.String(), primary_key=True),
            sa.Column("api_key_id", sa.String(), primary_key=True, server_default=sa.text("''")),
            sa.Column("state", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index(
            "idx_websocket_continuity_states_updated_at",
            "websocket_continuity_states",
            ["updated_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "websocket_continuity_states"):
        op.drop_index(
            "idx_websocket_continuity_states_updated_at",
            table_name="websocket_continuity_states",
        )
        op.drop_table("websocket_continuity_states")
