"""matches: client_mid + UNIQUE(category_id, client_mid) — идемпотентность create_match

Revision ID: f7a8b9c0d1e2
Revises: a3b4c5d6e7f8
Create Date: 2026-08-11

"""

import sqlalchemy as sa
from alembic import op

revision: str = "f7a8b9c0d1e2"
down_revision: str | None = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("matches", sa.Column("client_mid", sa.Integer(), nullable=True))
    # Если в данных уже есть повторы (двойная синхронизация одного турнира
    # в прошлом) — оставляем самый старый матч на пару, дубли вычищаем,
    # иначе UNIQUE не создастся. Дубли матчей — это двойное Эло и ложные
    # победы в расстановке мест, их удаление и есть починка данных.
    # ВАЖНО: legacy-матчи без client_mid (NULL) не трогаем — фильтр
    # client_mid IS NOT NULL обязателен, иначе NOT IN удалит все NULL-строки.
    op.execute(
        """
        DELETE FROM matches
        WHERE client_mid IS NOT NULL
          AND id NOT IN (
              SELECT MIN(id) FROM matches
              WHERE client_mid IS NOT NULL
              GROUP BY category_id, client_mid
          )
        """
    )
    op.create_unique_constraint(
        "uq_matches_category_client_mid",
        "matches",
        ["category_id", "client_mid"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_matches_category_client_mid", "matches", type_="unique")
    op.drop_column("matches", "client_mid")
