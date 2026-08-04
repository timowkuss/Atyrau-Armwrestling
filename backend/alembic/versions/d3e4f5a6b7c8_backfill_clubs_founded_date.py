"""backfill random founded_date for clubs

Revision ID: d3e4f5a6b7c8
Revises: c7d8e9f0a1b2
Create Date: 2026-08-04 13:00:00.000000

Клубам без даты основания проставляем случайную дату в диапазоне
1985–2020 (первое число месяца).
"""
import random
from datetime import date, timedelta
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 1985-01-01 .. 2020-12-31
_DAY0 = date(1985, 1, 1)
_DAYN = date(2020, 12, 31)
_RANGE_DAYS = (_DAYN - _DAY0).days


def _random_founded_date() -> str:
    dt = _DAY0 + timedelta(days=random.randint(0, _RANGE_DAYS))
    return dt.isoformat()


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id FROM clubs WHERE founded_date IS NULL")
    ).fetchall()
    for (club_id,) in rows:
        conn.execute(
            sa.text("UPDATE clubs SET founded_date = :d WHERE id = :id"),
            {"d": _random_founded_date(), "id": club_id},
        )


def downgrade() -> None:
    pass
