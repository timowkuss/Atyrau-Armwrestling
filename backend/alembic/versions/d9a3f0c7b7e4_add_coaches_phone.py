"""add phone column to coaches

Revision ID: d9a3f0c2b7e4
Revises: c0a1b2c3d4e5
Create Date: 2026-08-03 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision: str = "d9a3f0c2b7e4"
down_revision: str | None = "c0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("coaches", sa.Column("phone", sa.String(30), nullable=True))
    # Уже созданным тренерам проставляем служебный номер, чтобы они не
    # пустовали (по требованию организатора).
    op.execute("UPDATE coaches SET phone = '8(702)313-53-83' WHERE phone IS NULL")


def downgrade() -> None:
    op.drop_column("coaches", "phone")