"""add clubs.address (адрес зала)

Revision ID: f5e6a7b8c9d0
Revises: e3f4a5b6c7d8
Create Date: 2026-07-31 18:00:00.000000

Пользователи просят хранить физический адрес зала/клуба. Добавляем
необязательную колонку address (String(300)) — заполняется в админке
или из десктопа (см. ClubSyncCreate.address).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f5e6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("address", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("clubs", "address")
