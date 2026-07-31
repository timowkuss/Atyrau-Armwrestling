"""clubs: founded_year -> founded_date

Revision ID: c6f7a8b9d1e2
Revises: f5e6a7b8c9d0
Create Date: 2026-07-31 20:00:00.000000

Пользователи хотят хранить полную дату основания клуба (дд.мм.гггг), а не
только год. Заменяем founded_year (INTEGER) на founded_date (Date):
существующие значения переносим как 1 января соответствующего года.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c6f7a8b9d1e2"
down_revision: Union[str, Sequence[str], None] = "f5e6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("clubs", sa.Column("founded_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE clubs SET founded_date = make_date(founded_year, 1, 1) "
        "WHERE founded_year IS NOT NULL"
    )
    op.drop_column("clubs", "founded_year")


def downgrade() -> None:
    op.add_column("clubs", sa.Column("founded_year", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE clubs SET founded_year = EXTRACT(YEAR FROM founded_date)::INTEGER "
        "WHERE founded_date IS NOT NULL"
    )
    op.drop_column("clubs", "founded_date")
