"""add durable OAuth replica coordination state

Revision ID: 20260715_130000_add_oauth_replica_state
Revises: 20260712_020000_add_api_key_usage_rollups
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import Connection

revision = "20260715_130000_add_oauth_replica_state"
down_revision = "20260712_020000_add_api_key_usage_rollups"
branch_labels = None
depends_on = None


def _has_table(connection: Connection, table_name: str) -> bool:
    return sa.inspect(connection).has_table(table_name)


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_table(bind, "oauth_flow_states"):
        op.create_table(
            "oauth_flow_states",
            sa.Column("flow_id", sa.String(), nullable=False),
            sa.Column("state_token", sa.String(), nullable=True),
            sa.Column("method", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("code_verifier_encrypted", sa.LargeBinary(), nullable=True),
            sa.Column("device_auth_id", sa.String(), nullable=True),
            sa.Column("user_code", sa.String(), nullable=True),
            sa.Column("interval_seconds", sa.Integer(), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("flow_id"),
        )
        op.create_index(
            op.f("ix_oauth_flow_states_created_at"),
            "oauth_flow_states",
            ["created_at"],
            unique=False,
        )
        op.create_index(
            op.f("ix_oauth_flow_states_state_token"),
            "oauth_flow_states",
            ["state_token"],
            unique=True,
        )

    if not _has_table(bind, "oauth_device_flow_slots"):
        op.create_table(
            "oauth_device_flow_slots",
            sa.Column("slot_key", sa.String(), nullable=False),
            sa.Column("flow_id", sa.String(), nullable=False),
            sa.Column("generation", sa.Integer(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("slot_key"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _has_table(bind, "oauth_device_flow_slots"):
        op.drop_table("oauth_device_flow_slots")
    if _has_table(bind, "oauth_flow_states"):
        op.drop_index(op.f("ix_oauth_flow_states_state_token"), table_name="oauth_flow_states")
        op.drop_index(op.f("ix_oauth_flow_states_created_at"), table_name="oauth_flow_states")
        op.drop_table("oauth_flow_states")
