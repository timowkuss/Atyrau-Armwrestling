"""club rating system: athlete activity fields + club_rating tables

Revision ID: c0a1b2c3d4e5
Revises: f5e6a7b8c9d0
Create Date: 2026-07-31 19:00:00.000000

Система рейтинга клубов федерации:
- у спортсмена появляются поля клубной активности: join_club_date,
  last_competition_date, next_inactive_date, club_active;
- появляются таблицы club_rating (текущий рейтинг клуба) и
  club_rating_history (журнал всех изменений с защитой от дублей).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c0a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "c6f7a8b9d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("athletes", sa.Column("join_club_date", sa.Date(), nullable=True))
    op.add_column("athletes", sa.Column("last_competition_date", sa.Date(), nullable=True))
    op.add_column("athletes", sa.Column("next_inactive_date", sa.Date(), nullable=True))
    op.add_column(
        "athletes",
        sa.Column("club_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_athletes_next_inactive_date",
        "athletes",
        ["next_inactive_date"],
    )

    op.create_table(
        "club_rating",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("rating", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "club_rating_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("athlete_id", sa.Integer(), sa.ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("competitions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=50), nullable=False),
        sa.Column("description", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "club_id", "athlete_id", "tournament_id", "reason", "description",
            name="uq_club_rating_history",
        ),
    )
    op.create_index(
        "ix_club_rating_history_club",
        "club_rating_history",
        ["club_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_club_rating_history_club", table_name="club_rating_history")
    op.drop_table("club_rating_history")
    op.drop_table("club_rating")
    op.drop_index("ix_athletes_next_inactive_date", table_name="athletes")
    op.drop_column("athletes", "club_active")
    op.drop_column("athletes", "next_inactive_date")
    op.drop_column("athletes", "last_competition_date")
    op.drop_column("athletes", "join_club_date")
