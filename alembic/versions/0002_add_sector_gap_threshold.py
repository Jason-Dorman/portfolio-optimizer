"""Add sector_gap_threshold column to screening_runs.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "screening_runs",
        sa.Column(
            "sector_gap_threshold",
            sa.Double(),
            nullable=False,
            server_default="0.02",
        ),
    )


def downgrade() -> None:
    op.drop_column("screening_runs", "sector_gap_threshold")
