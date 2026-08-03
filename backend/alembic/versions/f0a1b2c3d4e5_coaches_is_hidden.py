"""add is_hidden column to coaches

Revision ID: f0a1b2c3d4e5
Revises: d9a3f0c2b7e4
Create Date: 2026-08-03 10:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "d9a3f0c2b7e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "coaches",
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("coaches", "is_hidden")
