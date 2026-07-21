"""competitions: weight_tolerance, bracket_system, format_type

Revision ID: d4e5f6a7b8c9
Revises: c3a8f2e90001
Create Date: 2026-07-21
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3a8f2e90001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("competitions", sa.Column("weight_tolerance", sa.Float(), nullable=True))
    op.add_column("competitions", sa.Column("bracket_system", sa.String(length=20), nullable=True))
    op.add_column("competitions", sa.Column("format_type", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("competitions", "format_type")
    op.drop_column("competitions", "bracket_system")
    op.drop_column("competitions", "weight_tolerance")
