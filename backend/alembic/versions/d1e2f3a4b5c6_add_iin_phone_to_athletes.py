"""add iin and phone columns to athletes

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f6
Create Date: 2026-07-28 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("iin", sa.String(12), unique=True))
    op.add_column("athletes", sa.Column("phone", sa.String(30)))


def downgrade() -> None:
    op.drop_column("athletes", "phone")
    op.drop_column("athletes", "iin")
