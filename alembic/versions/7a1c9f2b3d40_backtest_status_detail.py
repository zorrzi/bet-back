"""backtest_runs: status + detail columns (Phase 4)

Revision ID: 7a1c9f2b3d40
Revises: 542800be9671
Create Date: 2026-07-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a1c9f2b3d40"
down_revision: str | None = "542800be9671"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backtest_runs",
        sa.Column("status", sa.Text(), nullable=False, server_default="finished"),
    )
    op.add_column(
        "backtest_runs",
        sa.Column(
            "detail",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("backtest_runs", "detail")
    op.drop_column("backtest_runs", "status")
