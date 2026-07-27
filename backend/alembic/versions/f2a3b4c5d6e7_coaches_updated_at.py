"""coaches updated_at for pull-sync

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-24 13:00:00.000000

Десктоп теперь опрашивает и тренеров через GET /api/v1/sync/coaches/changes
(по аналогии с athletes) — нужна колонка updated_at, чтобы отдавать только
то, что реально поменялось с последнего опроса, а не всю таблицу целиком
каждый раз.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'coaches',
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('coaches', 'updated_at')
