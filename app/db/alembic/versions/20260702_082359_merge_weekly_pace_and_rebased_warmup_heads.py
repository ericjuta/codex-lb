"""merge weekly pace and rebased warmup migration heads

Revision ID: 20260702_082359_merge_weekly_pace_and_rebased_warmup_heads
Revises:
- 20260701_000000_add_weekly_pace_smoothing_minutes
- 20260701_000000_merge_rebased_warmup_heads
Create Date: 2026-07-02 08:23:59.000000
"""

from __future__ import annotations

revision = "20260702_082359_merge_weekly_pace_and_rebased_warmup_heads"
down_revision = (
    "20260701_000000_add_weekly_pace_smoothing_minutes",
    "20260701_000000_merge_rebased_warmup_heads",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
