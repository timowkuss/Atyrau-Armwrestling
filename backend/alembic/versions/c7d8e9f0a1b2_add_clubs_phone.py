"""add phone column to clubs

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-08-04 12:30:00.000000

Добавляет клубам контактный телефон. Уже существующим клубам заполняем
случайный казахстанский номер в формате 8(XXX)XXX-XX-XX (код + 7 цифр).
"""
import random
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Казахстанские мобильные коды: 70x/77x.
_KZ_MOBILE_CODES = ["700", "701", "702", "705", "708", "747", "775", "776", "777", "778"]


def _random_phone() -> str:
    code = random.choice(_KZ_MOBILE_CODES)
    rest = f"{random.randint(0, 9999999):07d}"
    return f"8({code}){rest[0:3]}-{rest[3:5]}-{rest[5:]}"


def upgrade() -> None:
    op.add_column("clubs", sa.Column("phone", sa.String(30), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id FROM clubs")).fetchall()
    for (club_id,) in rows:
        conn.execute(
            sa.text("UPDATE clubs SET phone = :p WHERE id = :id"),
            {"p": _random_phone(), "id": club_id},
        )


def downgrade() -> None:
    op.drop_column("clubs", "phone")
