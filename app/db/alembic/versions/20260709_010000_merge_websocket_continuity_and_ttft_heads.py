"""merge websocket continuity and ttft observability heads

Revision ID: 20260709_010000_merge_websocket_continuity_and_ttft_heads
Revises: 20260702_090000_add_websocket_continuity_states, 20260709_000000_add_ttft_phase_observability
Create Date: 2026-07-09
"""

from __future__ import annotations

revision = "20260709_010000_merge_websocket_continuity_and_ttft_heads"
down_revision = (
    "20260702_090000_add_websocket_continuity_states",
    "20260709_000000_add_ttft_phase_observability",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
